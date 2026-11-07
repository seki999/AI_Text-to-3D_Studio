import asyncio,base64,hashlib,json,os,threading,time,uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from .adapters import ENGINES
from .contracts import ImageRequest,ImageUpload,TextureRequest,TextImageRequest
from .diagnostics import hardware_report
from .images import decode_image
from .mesh import load_glb,inspect_scene
from .text_image import OpenAICompatibleImageProvider,provider_info
from ..schema import Scene,SceneObject,Parameters,AssetMetadata

POOL=ThreadPoolExecutor(max_workers=2)
SLOTS=threading.BoundedSemaphore(6)
LOCK=threading.RLock()
CANCELS={}
FUTURES={}

def core():
    from .. import main
    return main

def initialize(connection):
    with connection() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS ai3d_images(id TEXT PRIMARY KEY,info TEXT,prompt TEXT,provider TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS ai3d_jobs(id TEXT PRIMARY KEY,engine TEXT,image_id TEXT,prompt TEXT,options TEXT,operation TEXT,source_job_id TEXT,remote_id TEXT,status TEXT,stage TEXT,progress REAL,progress_kind TEXT,error TEXT,asset_id TEXT,stats TEXT,metadata TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);''')
        db.execute("UPDATE ai3d_jobs SET status='failed',stage='服务重启',error=CASE WHEN engine='meshy' THEN '服务重启，本地等待已停止；云端可能继续运行和计费。请恢复获取已有结果，勿重复生成。' ELSE 'Web 服务重启；远端旧任务会在首次访问时请求取消' END WHERE status IN ('pending','running')")

async def recover():
    with core().connection() as db:rows=[dict(r) for r in db.execute("SELECT * FROM ai3d_jobs WHERE error LIKE 'Web 服务重启%' AND remote_id IS NOT NULL AND engine!='meshy'")]
    async def terminate(value):
        try:
            await ENGINES[value['engine']].cancel(value['remote_id'])
            update(value['id'],error='Web 服务重启，Worker 旧任务已取消')
        except ValueError:pass
    if rows:await asyncio.gather(*(terminate(v) for v in rows))

def shutdown():
    with LOCK:
        for event in CANCELS.values():event.set()
        for job_id,future in list(FUTURES.items()):
            if future.cancel():
                CANCELS.pop(job_id,None);FUTURES.pop(job_id,None);SLOTS.release();update(job_id,status='cancelled',stage='服务退出，排队任务取消',progress=None)

def save_image(data:bytes,info:dict,prompt='',provider='upload'):
    c=core();c.DATA.mkdir(parents=True,exist_ok=True)
    if c.storage.usage(c.DATA)+len(data)>c.storage.limits()['max_bytes']:raise HTTPException(507,'本地磁盘配额已满')
    image_id=str(uuid.uuid4());directory=c.DATA/image_id;directory.mkdir()
    try:
        (directory/'reference.png').write_bytes(data)
        with c.connection() as db:db.execute('INSERT INTO ai3d_images(id,info,prompt,provider) VALUES(?,?,?,?)',(image_id,json.dumps(info),prompt,provider))
    except Exception:
        import shutil
        shutil.rmtree(directory);raise
    return {'id':image_id,'url':f'/api/ai3d/images/{image_id}','info':info,'prompt':prompt,'provider':provider}

def image_file(image_id):
    c=core();c.safe_id(image_id)
    with c.connection() as db:row=db.execute('SELECT * FROM ai3d_images WHERE id=?',(image_id,)).fetchone()
    path=(c.DATA/image_id/'reference.png').resolve()
    if not row or not path.is_relative_to(c.DATA) or not path.is_file():raise HTTPException(404,'参考图片不存在')
    return path

def row(job_id):
    c=core();c.safe_id(job_id)
    with c.connection() as db:value=db.execute('SELECT * FROM ai3d_jobs WHERE id=?',(job_id,)).fetchone()
    if not value:raise HTTPException(404,'AI 任务不存在')
    return dict(value)

def update(job_id,**values):
    allowed={'status','stage','progress','progress_kind','error','asset_id','remote_id','stats','metadata'}
    if not set(values)<=allowed:raise ValueError('非法任务更新字段')
    with core().connection() as db:db.execute('UPDATE ai3d_jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),job_id))

def representation(value):
    result={**value,'is_mock':value['engine']=='mock','model_url':f"/api/models/{value['asset_id']}/download?format=glb" if value.get('asset_id') else None}
    for key in ('options','stats','metadata'):
        if isinstance(result.get(key),str):result[key]=json.loads(result[key])
    result['original_available']=(core().DATA/value['id']/'original.glb').is_file()
    return result

def register_asset(value,raw,original,stats):
    c=core();asset_id=value['id'];directory=c.DATA/asset_id
    scene_mesh,document=load_glb(raw);actual=inspect_scene(scene_mesh,document)
    if c.storage.usage(c.DATA)+len(raw)+len(original)>c.storage.limits()['max_bytes']:raise RuntimeError('生成产物超过本地磁盘软配额，请清理缓存')
    info=ENGINES[value['engine']].get_model_info();now=datetime.now(timezone.utc).isoformat()
    metadata=AssetMetadata(asset_id=asset_id,generator=value['engine'],model_version=stats.get('inference',{}).get('model',info['version']),source_prompt=value['prompt'],source_image=value['image_id'],generated_at=now,texture_assets=[{'slot':k,'source':'embedded GLB'} for k,v in actual['texture_support'].items() if v],license_metadata=info['license'],provenance={'kind':'mock' if value['engine']=='mock' else 'real_ai','operation':value['operation'],'source_job_id':value.get('source_job_id'),'source':info['source'],'source_revision':info['source_revision'],'sha256':hashlib.sha256(raw).hexdigest(),'source_image_sha256':hashlib.sha256(image_file(value['image_id']).read_bytes()).hexdigest() if value['image_id'] else None,'original_sha256':hashlib.sha256(original).hexdigest(),'test_notice':'Mock 测试几何，非 AI 推理' if value['engine']=='mock' else None})
    with c.connection() as db:reference=db.execute('SELECT prompt,provider FROM ai3d_images WHERE id=?',(value['image_id'],)).fetchone()
    if reference:metadata.provenance.update(reference_image_provider=reference['provider'],reference_image_prompt=reference['prompt'])
    if value['engine']=='meshy':metadata.provenance.update(remote_task=value.get('remote_id'),provider='meshy',model=info['version'],cloud_processing=True)
    if value['engine']!='mock':metadata.provenance.update({'adapter_source_revision':info['source_revision'],'source_revision':stats.get('inference',{}).get('source_revision'),'weights_revision':stats.get('inference',{}).get('weights_revision')})
    obj=SceneObject(id='asset_'+asset_id,name='Mock 测试资产（非 AI）' if value['engine']=='mock' else info['name']+' Asset',type='imported',position=(0,-actual['bounds'][0][1],0),asset=metadata,parameters=Parameters(width=2,depth=2,height=2))
    scene=Scene(name=obj.name,objects=[obj]);directory.mkdir(exist_ok=True)
    (directory/'model.glb').write_bytes(raw);(directory/'original.glb').write_bytes(original)
    (directory/'model.json').write_text(scene.model_dump_json(indent=2),encoding='utf-8')
    (directory/'provenance.json').write_text(metadata.model_dump_json(indent=2),encoding='utf-8')
    statistics={**actual,'glb_bytes':len(raw),'processing':stats}
    with c.connection() as db:
        db.execute('INSERT INTO jobs(id,status,progress,scene) VALUES(?,?,?,?)',(asset_id,'completed',100,scene.model_dump_json()))
        db.execute('INSERT INTO assets VALUES(?,?,?)',(asset_id,asset_id,json.dumps(statistics)))
        db.execute("UPDATE ai3d_jobs SET status='completed',stage='完成',progress=NULL,progress_kind='stage',asset_id=?,stats=?,metadata=? WHERE id=?",(asset_id,json.dumps(statistics),metadata.model_dump_json(),value['id']))

async def orchestrate(job_id,event):
    value=row(job_id);engine=ENGINES[value['engine']];remote_id=None
    try:
        if event.is_set():raise asyncio.CancelledError()
        update(job_id,status='running',stage='提交独立 Worker',progress=None,progress_kind='stage')
        payload={'image_b64':base64.b64encode(image_file(value['image_id']).read_bytes()).decode(),'options':json.loads(value['options']),'operation':value['operation']}
        if value['operation']=='texture':
            source=row(value['source_job_id']);payload['shape_b64']=base64.b64encode(core().asset_file(source['asset_id'],'glb').read_bytes()).decode()
        response=await engine.generate_from_image(payload);remote_id=response['id'];core().safe_id(remote_id)
        update(job_id,remote_id=remote_id)
        deadline=time.monotonic()+int(os.getenv('AI3D_TIMEOUT_SECONDS','1800'))+30
        while True:
            if event.is_set():raise asyncio.CancelledError()
            if time.monotonic()>deadline:
                await engine.cancel(remote_id);raise RuntimeError('AI 任务超时，已请求 Worker 终止进程树')
            state=await engine.get_progress(remote_id)
            if state['status']=='failed':raise RuntimeError(state.get('error') or 'Worker 推理失败')
            if state['status']=='cancelled':raise asyncio.CancelledError()
            if state['status']=='completed':break
            update(job_id,status='running' if state['status']=='running' else 'pending',stage=state.get('stage','等待'),progress=state.get('progress'),progress_kind=state.get('progress_kind','stage'))
            await asyncio.sleep(.3)
        update(job_id,stage='传回并校验真实 Mesh',progress=None,progress_kind='stage')
        raw=await engine.worker.artifact(remote_id,'model');original=await engine.worker.artifact(remote_id,'original')
        with LOCK:
            if event.is_set():raise asyncio.CancelledError()
            register_asset(value,raw,original,state.get('stats',{}))
        try:await engine.cleanup(remote_id)
        except ValueError:pass  # Keep transferable Worker backup if remote cleanup is temporarily unavailable.
    except asyncio.CancelledError:
        if remote_id:
            try:await engine.cancel(remote_id)
            except ValueError:pass
        update(job_id,status='cancelled',stage='已取消',progress=None,error='用户取消；已向 Worker 请求终止进程')
    except Exception as exc:
        if remote_id:
            try:
                state=await engine.get_progress(remote_id)
                if state['status'] in ('pending','running'):await engine.cancel(remote_id)
                log=await engine.worker.json('GET',f'/jobs/{remote_id}/log')
                directory=core().DATA/job_id;directory.mkdir(exist_ok=True);(directory/'ai3d.log').write_text(log.get('log',''),encoding='utf-8')
                try:
                    backup=await engine.worker.artifact(remote_id,'original');load_glb(backup);(directory/'original.glb').write_bytes(backup)
                except ValueError:pass
            except ValueError:pass
        update(job_id,status='failed',stage='失败',progress=None,error=str(exc)[:2000])
    finally:
        with LOCK:CANCELS.pop(job_id,None);FUTURES.pop(job_id,None)
        SLOTS.release()

def execute_async(job_id,event):
    if row(job_id)['engine']=='meshy':
        from .cloud import orchestrate as cloud_orchestrate
        asyncio.run(cloud_orchestrate(job_id,event))
    else:asyncio.run(orchestrate(job_id,event))

def start(value):
    if not SLOTS.acquire(False):raise HTTPException(429,'AI 转交队列已满')
    event=threading.Event()
    try:
        with core().connection() as db:db.execute('INSERT INTO ai3d_jobs(id,engine,image_id,prompt,options,operation,source_job_id,status,stage,progress_kind) VALUES(?,?,?,?,?,?,?,?,?,?)',(value['id'],value['engine'],value['image_id'],value['prompt'],json.dumps(value['options']),value['operation'],value.get('source_job_id'),'pending','排队中','stage'))
        with LOCK:
            CANCELS[value['id']]=event
            FUTURES[value['id']]=POOL.submit(execute_async,value['id'],event)
    except Exception:
        SLOTS.release();raise
    return representation(row(value['id']))

router=APIRouter(prefix='/api/ai3d',tags=['Generative AI 3D'])

@router.get('/engines')
def engines():return [dict(e.get_model_info(),requirements=e.get_requirements()) for e in ENGINES.values()]

def engine_by_id(engine_id):
    if engine_id not in ENGINES:raise HTTPException(404,'引擎不存在')
    return ENGINES[engine_id]

@router.get('/engines/{engine_id}/status')
async def engine_status(engine_id:str):return await engine_by_id(engine_id).check_availability()

@router.post('/engines/{engine_id}/diagnose')
async def diagnose(engine_id:str):
    engine=engine_by_id(engine_id);hardware=await asyncio.to_thread(hardware_report,core().DATA);worker=await engine.check_availability()
    hardware.update(worker_python=worker.get('python'),torch_cuda_available=worker.get('torch_cuda_available'),cuda_available=worker.get('torch_cuda_available'),weights_ready=worker.get('weights_ready'))
    return {'hardware':hardware,'worker':worker,'requirements':engine.get_requirements(),'model':engine.get_model_info()}

@router.post('/images',status_code=201)
def upload(request:ImageUpload):
    try:data,info=decode_image(request.data)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    return save_image(data,info)

@router.get('/images/{image_id}')
def image(image_id:str):return FileResponse(image_file(image_id),media_type='image/png')

@router.get('/text-image/provider')
def text_provider():return provider_info()

@router.post('/text-image',status_code=201)
async def text_to_image(request:TextImageRequest):
    try:data,info=await OpenAICompatibleImageProvider().generate(request.prompt)
    except ValueError as exc:raise HTTPException(503,str(exc)) from exc
    return await asyncio.to_thread(save_image,data,info,request.prompt,'text-to-image')

@router.post('/jobs',status_code=202)
async def create(request:ImageRequest):
    image_file(request.image_id);engine=engine_by_id(request.engine)
    if request.engine=='mock' and not request.mock_acknowledged:raise HTTPException(422,'必须确认 Mock 是测试模式，不是真实 AI')
    if request.engine=='hunyuan3d-2.1' and not request.license_acknowledged:raise HTTPException(422,'请先阅读并确认第三方模型许可证条件')
    status=await engine.check_availability()
    if not status['available']:raise HTTPException(503,'；'.join(status.get('errors',[])) or '引擎不可用')
    return start({'id':str(uuid.uuid4()),'engine':request.engine,'image_id':request.image_id,'prompt':request.prompt,'options':request.options.model_dump(),'operation':'shape'})

@router.post('/jobs/texture',status_code=202)
async def texture(request:TextureRequest):
    source=row(request.source_job_id)
    if source['status']!='completed' or source['engine']!='hunyuan3d-2.1':raise HTTPException(422,'必须选择已完成的真实 Hunyuan Shape，Mock 不可生成 AI 纹理')
    status=await ENGINES['hunyuan3d-2.1'].check_availability()
    if not status.get('texture_ready'):raise HTTPException(503,'独立 Paint 环境 / 权重 / 显存未准备好，原 Shape 不受影响')
    return start({'id':str(uuid.uuid4()),'engine':'hunyuan3d-2.1','image_id':source['image_id'],'prompt':source['prompt'],'options':json.loads(source['options']),'operation':'texture','source_job_id':source['id']})

@router.get('/jobs')
def history():
    with core().connection() as db:return [representation(dict(r)) for r in db.execute('SELECT * FROM ai3d_jobs ORDER BY created DESC LIMIT 50')]

@router.get('/jobs/{job_id}')
async def get(job_id:str):
    value=row(job_id)
    if value.get('error','') and value['error'].startswith('Web 服务重启') and value['remote_id'] and value['engine']!='meshy':
        try:await ENGINES[value['engine']].cancel(value['remote_id'])
        except ValueError:pass
        update(job_id,error='Web 服务重启，已尝试取消 Worker 旧任务')
    if value['engine']=='meshy' and value.get('error','') and value['error'].startswith('Web 服务重启'):
        value['error']='服务重启，本地等待已停止；云端可能继续运行和计费。请恢复获取已有结果，勿重复生成。'
    return representation(value)

@router.post('/jobs/{job_id}/cancel')
async def cancel(job_id:str):
    with LOCK:
        value=row(job_id)
        if value['status'] not in ('pending','running'):raise HTTPException(409,'任务已结束')
        event=CANCELS.get(job_id)
        if event:event.set()
        future=FUTURES.get(job_id)
        if future and future.cancel():
            CANCELS.pop(job_id,None);FUTURES.pop(job_id,None);SLOTS.release()
            update(job_id,status='cancelled',stage='排队任务取消，尚未提交引擎',progress=None)
            return representation(row(job_id))
    if value['engine']=='meshy':return representation(row(job_id))
    if value['remote_id']:
        try:await ENGINES[value['engine']].cancel(value['remote_id'])
        except ValueError as exc:raise HTTPException(503,'取消请求已记录，但 Worker 尚未确认终止：'+str(exc)) from exc
    return representation(row(job_id))

@router.get('/jobs/{job_id}/log')
async def log(job_id:str):
    value=row(job_id)
    if value['engine']=='meshy':return {'log':f"Meshy: {value['stage']}\n{value.get('error') or ''}\n云端任务 {value.get('remote_id') or '创建结果尚未确认'}；不记录密钥、响应正文或签名下载链接。"}
    if value['remote_id']:
        try:return await ENGINES[value['engine']].worker.json('GET',f"/jobs/{value['remote_id']}/log")
        except ValueError:pass
    path=core().DATA/job_id/'ai3d.log'
    return {'log':path.read_text(encoding='utf-8')[-32000:] if path.exists() else value.get('error') or '暂无日志'}

@router.get('/jobs/{job_id}/original')
def original(job_id:str):
    value=row(job_id)
    path=(core().DATA/job_id/'original.glb').resolve()
    if not path.is_relative_to(core().DATA) or not path.is_file():raise HTTPException(404,'原始备份不存在')
    return FileResponse(path,media_type='model/gltf-binary',filename='original.glb')
