import asyncio, json, os, shutil, struct, subprocess, sys
from pathlib import Path
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.schema import Scene, SceneObject, Parameters
from app.providers import RuleBasedProvider
from app import main

def scene(**p): return Scene(objects=[SceneObject(id='house',type='house',parameters=Parameters(**p))])

@pytest.mark.parametrize('params',[{'width':0},{'width':101},{'floors':4},{'windows':25},{'roof_color':'red'},{'height':float('nan')},{'roof_type':'code'}])
def test_invalid_parameters(params):
    with pytest.raises(ValidationError): Parameters(**params)

def test_defaults_and_schema():
    assert scene().objects[0].parameters.floors==2
    assert Scene.model_json_schema()['properties']['version']['const']=='1.0'
    assert Scene.model_validate({'version':'0.9','units':'m','objects':[]}).version=='1.0'

def test_duplicate_and_cycles():
    a=SceneObject(id='a',type='cube',parent='b'); b=SceneObject(id='b',type='cube',parent='a')
    for objects in [[a,a],[a,b],[a]]:
        with pytest.raises(ValidationError): Scene(objects=objects)

@pytest.mark.parametrize('text,kind,check',[
    ('生成一个红色立方体，边长2米。','cube',{'width':2,'height':2,'color':'#e34b4b'}),
    ('生成一个蓝色圆柱体，高度3米，半径1米。','cylinder',{'height':3,'radius':1,'color':'#3985ed'}),
    ('生成一栋日本两层独立住宅，白色外墙、灰色双坡屋顶、四个正面窗户、一个入口、二楼阳台。','house',{'floors':2,'windows':4,'balcony':True,'wall_color':'#ffffff','roof_color':'#666666'}),
    ('white house 3 floors width 8 depth 10 flat roof','house',{'floors':3,'width':8,'depth':10,'roof_type':'flat'}),
    ('白い外壁の2階の戸建、幅8、奥行10、切妻屋根、バルコニー','house',{'floors':2,'width':8,'depth':10,'balcony':True}),
])
def test_parser(text,kind,check):
    result=asyncio.run(RuleBasedProvider().parse(text))
    obj=result['scene']['objects'][0]
    assert obj['type']==kind
    for key,value in check.items(): assert obj['parameters'][key]==value

def test_room_counts():
    result=asyncio.run(RuleBasedProvider().parse('创建房间，里面放一张桌子、两把椅子和一个书架'))
    assert [o['type'] for o in result['scene']['objects']].count('chair')==2

def test_unknown():
    with pytest.raises(ValueError): asyncio.run(RuleBasedProvider().parse('a complicated dragon'))
    with pytest.raises(ValueError): asyncio.run(RuleBasedProvider().parse('cube width -2'))

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'test.sqlite3')
    monkeypatch.setattr(main,'DATA',tmp_path)
    with TestClient(main.app) as client: yield client

def test_api_projects_and_validation(client):
    assert client.get('/api/health').status_code==200
    assert client.post('/api/validate-scene',json={'objects':[],'evil':True}).status_code==422
    payload={'name':'test','scene':scene().model_dump(),'prompt':'住宅'}
    result=client.post('/api/projects',json=payload); assert result.status_code==201
    project_id=result.json()['id']
    assert client.get('/api/projects').json()[0]['prompt']=='住宅'
    payload['name']='updated'
    assert client.put('/api/projects/'+project_id,json=payload).status_code==200
    assert client.delete('/api/projects/'+project_id).status_code==200
    assert client.delete('/api/projects/'+project_id).status_code==404

def test_path_safety(client):
    assert client.get('/api/models/invalid/download').status_code==400
    with pytest.raises(Exception): main.asset_file('../outside','glb')
    with pytest.raises(Exception): main.asset_file('00000000-0000-0000-0000-000000000000','../../secret')

def test_missing_blender(client,monkeypatch):
    monkeypatch.setattr(main,'blender_path',lambda:None)
    assert client.post('/api/generate-model',json=scene().model_dump()).status_code==503

def test_failed_worker(client,monkeypatch):
    import uuid
    job_id=str(uuid.uuid4())
    with main.connection() as db: db.execute('INSERT INTO jobs(id,status,progress,scene) VALUES(?,?,?,?)',(job_id,'pending',0,'{}'))
    monkeypatch.setattr(main,'blender_path',lambda:None)
    assert main.SLOTS.acquire(False)
    main.generate(job_id,scene())
    result=client.get('/api/jobs/'+job_id).json()
    assert result['status']=='failed' and 'Blender' in result['error']

def test_parse_api(client):
    result=client.post('/api/parse-text',json={'text':'红色立方体边长2米'})
    assert result.status_code==200
    assert len(client.get('/api/history').json())==1
    assert client.post('/api/parse-text',json={'text':'x'*4001}).status_code==422

def test_body_limit(client):
    assert client.post('/api/validate-scene',content=b' '*524289).status_code==413

def test_job_states_and_restart(client):
    import uuid
    job_id=str(uuid.uuid4())
    with main.connection() as db: db.execute('INSERT INTO jobs(id,status,progress,scene) VALUES(?,?,?,?)',(job_id,'pending',0,'{}'))
    assert client.get('/api/jobs/'+job_id).json()['status']=='pending'
    main.update_job(job_id,'running',10)
    assert client.get('/api/jobs/'+job_id).json()['progress']==10
    main.initialize()
    assert client.get('/api/jobs/'+job_id).json()['status']=='failed'
    main.update_job(job_id,'completed',100)
    assert client.get('/api/jobs/'+job_id).json()['model_id']==job_id

def test_queue_full(client,monkeypatch):
    import threading
    monkeypatch.setattr(main,'blender_path',lambda:'blender')
    monkeypatch.setattr(main,'SLOTS',threading.BoundedSemaphore(0))
    assert client.post('/api/generate-model',json=scene().model_dump()).status_code==429

def test_snapshot_and_cleanup_protects_project(client):
    import base64,uuid
    data=(main.ROOT.parent/'examples/cube.glb').read_bytes()
    result=client.post('/api/models/snapshot',json={'scene':scene().model_dump(),'glb':base64.b64encode(data).decode()})
    assert result.status_code==201
    model_id=result.json()['id']
    result=client.post('/api/projects',json={'name':'protected','scene':scene().model_dump(),'model_id':model_id})
    assert result.status_code==201
    client.post('/api/storage/cleanup',json={'older_than_days':0})
    assert client.get('/api/models/'+model_id+'/download').status_code==200
    assert client.get('/api/storage').json()['assets'][0]['protected'] is True
    client.delete('/api/projects/'+result.json()['id'])
    assert model_id in client.post('/api/storage/cleanup',json={'older_than_days':0}).json()['removed']
    assert client.get('/api/models/'+model_id+'/download').status_code==404
    assert client.post('/api/models/snapshot',json={'scene':scene().model_dump(),'glb':'invalid'}).status_code==422

def test_pending_cancel(client):
    import uuid
    from app import job_runtime
    job_id=str(uuid.uuid4())
    with main.connection() as db:db.execute('INSERT INTO jobs(id,status,progress,scene) VALUES(?,?,?,?)',(job_id,'pending',0,'{}'))
    result=client.post('/api/jobs/'+job_id+'/cancel')
    assert result.status_code==200 and result.json()['status']=='cancelled'
    assert client.post('/api/jobs/'+job_id+'/cancel').status_code==409
    job_runtime.CANCELLED.discard(job_id)

@pytest.mark.integration
def test_blender_glb(tmp_path):
    executable=main.blender_path()
    if not executable: pytest.skip('Blender executable not installed')
    source=tmp_path/'scene.json'; output=tmp_path/'model.glb'
    source.write_text(scene(balcony=True,steps=True).model_dump_json(),encoding='utf-8')
    subprocess.run([executable,'--background','--factory-startup','--python',str(main.ROOT/'blender/generate.py'),'--',str(source),str(output)],timeout=120,check=True,capture_output=True)
    content=output.read_bytes(); assert content[:4]==b'glTF' and len(content)>100
    length,kind=struct.unpack_from('<II',content,12); data=json.loads(content[20:20+length])
    assert data['meshes'] and data['materials']
    assert any(a.get('count',0)>0 for a in data['accessors'])
    stats=json.loads((tmp_path/'stats.json').read_text())
    assert stats['vertices']>0 and stats['meshes']>10
    assert 7<stats['dimensions_blender_z_up'][0]<10

@pytest.mark.integration
@pytest.mark.parametrize('kind',['cube','cylinder','sphere','cone','plane','torus','table','chair','cabinet','bookshelf','bed'])
def test_other_meshes(tmp_path,kind):
    executable=main.blender_path()
    if not executable: pytest.skip('Blender executable not installed')
    source=tmp_path/'scene.json'; output=tmp_path/'model.glb'
    value=Scene(objects=[SceneObject(id='object',type=kind,parameters=Parameters(width=2,depth=2,height=3))])
    source.write_text(value.model_dump_json(),encoding='utf-8')
    subprocess.run([executable,'--background','--factory-startup','--python',str(main.ROOT/'blender/generate.py'),'--',str(source),str(output)],timeout=120,check=True,capture_output=True)
    stats=json.loads((tmp_path/'stats.json').read_text())
    assert stats['vertices']>0
    if kind in ('table','chair','cabinet','bookshelf','bed'): assert stats['meshes']>=5
    if kind=='cylinder': assert stats['dimensions_blender_z_up'][2]==pytest.approx(3)

@pytest.mark.integration
@pytest.mark.parametrize('roof',['flat','gable','shed','hip'])
def test_roof_material_and_roundtrip(tmp_path,roof):
    executable=main.blender_path()
    if not executable: pytest.skip('Blender executable not installed')
    source=tmp_path/'scene.json'; output=tmp_path/'model.glb'
    value=scene(roof_type=roof,roof_color='#ff0000',balcony=True)
    source.write_text(value.model_dump_json(),encoding='utf-8')
    subprocess.run([executable,'--background','--factory-startup','--python',str(main.ROOT/'blender/generate.py'),'--',str(source),str(output)],timeout=120,check=True,capture_output=True)
    content=output.read_bytes(); length=struct.unpack_from('<I',content,12)[0]; data=json.loads(content[20:20+length])
    assert any(m['pbrMetallicRoughness']['baseColorFactor'][:3]==[1,0,0] for m in data['materials'])
    assert sum(n.get('name','').startswith('window glass') for n in data['nodes'])==4
    # Trusted test script imports the artifact through Blender's own glTF importer.
    check=tmp_path/'check.py'
    check.write_text("import bpy,json\nfrom pathlib import Path\nbpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)\nbpy.ops.import_scene.gltf(filepath="+repr(str(output))+ ")\nfrom mathutils import Vector\nobjects=[o for o in bpy.context.scene.objects if o.type=='MESH']\nbpy.context.view_layer.update()\npoints=[o.matrix_world@Vector(v) for o in objects for v in o.bound_box]\nresult={'meshes':len(objects),'bounds':[max(v[i] for v in points)-min(v[i] for v in points) for i in range(3)],'materials':len(bpy.data.materials)}\nPath("+repr(str(tmp_path/'roundtrip.json'))+").write_text(json.dumps(result))\n",encoding='utf-8')
    subprocess.run([executable,'--background','--factory-startup','--python',str(check)],timeout=120,check=True,capture_output=True)
    before=json.loads((tmp_path/'stats.json').read_text()); after=json.loads((tmp_path/'roundtrip.json').read_text())
    assert after['meshes']==before['meshes']
    assert after['bounds']==pytest.approx(before['dimensions_blender_z_up'],abs=.001)
    assert after['materials']>=before['materials']
