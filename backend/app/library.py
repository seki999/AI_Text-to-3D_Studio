"""Independent on-disk library, SQLite index and reference-safe deletion."""
import base64,io,json,shutil,uuid
from datetime import datetime,timezone
from .schema import Scene,SceneObject,AssetMetadata
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from PIL import Image,ImageDraw
from pydantic import Field
from .schema import Strict
from .ai3d.mesh import load_glb,inspect_scene,process_glb
router=APIRouter(prefix='/api/library')

def core():
    from . import main
    return main
def folder(id):return core().DATA/'library'/core().safe_id(id)
def row(id):
    core().safe_id(id)
    with core().connection() as db:r=db.execute('SELECT * FROM library_assets WHERE id=?',(id,)).fetchone()
    if not r:raise HTTPException(404,'资产库条目不存在')
    return dict(r)
def representation(r,protected):
    for key in ('stats','metadata'):r[key]=json.loads(r[key]) if r[key] else {}
    return {**r,'favorite':bool(r['favorite']),'is_mock':bool(r['is_mock']),'protected':r['id'] in protected,'thumbnail':f"/api/library/{r['id']}/thumbnail"}
class Add(Strict):model_id:str;description:str=Field('',max_length=2000)
class Update(Strict):favorite:bool|None=None;description:str|None=Field(None,max_length=2000)
class Thumbnail(Strict):data:str=Field(max_length=600000)
class Simplify(Strict):target_faces:int=Field(20000,ge=100,le=500000);confirmed:bool=False

def add_asset(model_id,description=''):
    c=core();asset=c.get_model(model_id);raw=c.asset_file(model_id,'glb').read_bytes();mesh,doc=load_glb(raw);stats=inspect_scene(mesh,doc)
    if c.storage.usage(c.DATA)+len(raw)*2>c.storage.limits()['max_bytes']:raise HTTPException(507,'资产库已超过本地磁盘软配额')
    id=str(uuid.uuid4());directory=folder(id);directory.mkdir(parents=True)
    scene=asset['scene'];objects=scene['objects'];metadata=objects[0].get('asset') if len(objects)==1 else None
    provider=(metadata or {}).get('generator','local/imported');mock=(metadata or {}).get('provenance',{}).get('kind')=='mock'
    metadata=dict(metadata) if metadata else AssetMetadata(asset_id=id,generator=provider,model_version='0.4.0',source_prompt=description,generated_at=datetime.now(timezone.utc).isoformat(),provenance={'kind':'local'},license_metadata={'name':'用户自有或外部资产，需自行核对权利'}).model_dump()
    metadata['asset_id']=id
    scene=Scene(name=description[:100] or scene['name'],objects=[SceneObject(id='asset_'+id,name=description[:100] or scene['name'],type='imported',asset=AssetMetadata.model_validate(metadata))]).model_dump()
    try:
        (directory/'model.glb').write_bytes(raw)
        original=(c.DATA/model_id/'original.glb')
        (directory/'original.glb').write_bytes(original.read_bytes() if original.is_file() else raw)
        (directory/'model.json').write_text(json.dumps(scene),encoding='utf-8')
        preview=Image.new('RGB',(256,192),'#202938');draw=ImageDraw.Draw(preview);draw.rectangle((72,40,184,140),outline='#dca080',width=3);draw.text((12,165),'MOCK / NOT AI' if mock else 'Preview unavailable',fill='white');preview.save(directory/'thumbnail.png')
        with c.connection() as db:
            db.execute('INSERT INTO jobs(id,status,progress,scene) VALUES(?,?,?,?)',(id,'completed',100,json.dumps(scene)))
            db.execute('INSERT INTO assets VALUES(?,?,?)',(id,id,json.dumps(stats)))
            db.execute('INSERT INTO library_assets(id,source_id,description,provider,is_mock,stats,bytes,metadata) VALUES(?,?,?,?,?,?,?,?)',(id,model_id,description or scene['name'],provider,int(mock),json.dumps(stats),len(raw),json.dumps(metadata or {'license_metadata':{'name':'用户自有或外部资产，需自行核对权利'}})))
    except Exception:shutil.rmtree(directory);raise
    return id

@router.post('',status_code=201)
def add(request:Add):return {'id':add_asset(request.model_id,request.description)}
@router.get('')
def listing(q:str='',favorite:bool=False):
    c=core()
    with c.connection() as db:
        protected=c.storage.referenced_assets(db)
        rows=db.execute("SELECT * FROM library_assets WHERE (description LIKE ? OR provider LIKE ?) AND (?=0 OR favorite=1) ORDER BY created DESC LIMIT 200",('%'+q[:200]+'%','%'+q[:200]+'%',int(favorite))).fetchall()
        return [representation(dict(r),protected) for r in rows]
@router.patch('/{id}')
def edit(id:str,request:Update):
    row(id)
    with core().connection() as db:
        if request.favorite is not None:db.execute('UPDATE library_assets SET favorite=? WHERE id=?',(int(request.favorite),id))
        if request.description is not None:db.execute('UPDATE library_assets SET description=? WHERE id=?',(request.description,id))
    return {'updated':True}
@router.get('/{id}/thumbnail')
def thumbnail(id:str):row(id);return FileResponse(folder(id)/'thumbnail.png',media_type='image/png')
@router.put('/{id}/thumbnail')
def save_thumbnail(id:str,request:Thumbnail):
    row(id)
    try:
        raw=base64.b64decode(request.data,validate=True)
        if len(raw)>400000:raise ValueError()
        with Image.open(io.BytesIO(raw)) as image:
            if image.width>512 or image.height>512:raise ValueError()
            image.convert('RGB').save(folder(id)/'thumbnail.png',format='PNG')
    except (ValueError,OSError):raise HTTPException(422,'预览必须是最大 512×512、400 KB 的有效图片') from None
    return {'saved':True}
@router.delete('/{id}')
def delete(id:str):
    row(id);c=core();directory=folder(id);trash=directory.with_name(id+'.deleting')
    with c.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if id in c.storage.referenced_assets(db):raise HTTPException(409,'资产已被项目引用，请先移除项目引用')
        directory.rename(trash)
        try:
            db.execute('DELETE FROM library_assets WHERE id=?',(id,));db.execute('DELETE FROM assets WHERE id=?',(id,));db.execute('DELETE FROM jobs WHERE id=?',(id,))
        except Exception:trash.rename(directory);raise
    shutil.rmtree(trash)
    return {'deleted':True}
@router.post('/{id}/simplify',status_code=201)
def simplify(id:str,request:Simplify):
    if not request.confirmed:raise HTTPException(422,'请明确确认创建独立简化副本，原模型不变')
    row(id);c=core();source=c.asset_file(id,'glb').read_bytes()
    try:result,stats=process_glb(source,{'normalize':False,'center':False,'simplify_faces':request.target_faces})
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    new_id=add_asset(id,'简化副本 · '+row(id)['description']);directory=folder(new_id)
    (directory/'model.glb').write_bytes(result)
    with c.connection() as db:
        db.execute('UPDATE library_assets SET stats=?,bytes=? WHERE id=?',(json.dumps(stats['after']),len(result),new_id))
        db.execute('UPDATE assets SET stats=? WHERE id=?',(json.dumps(stats['after']),new_id))
    return {'id':new_id,'original_preserved':True}
