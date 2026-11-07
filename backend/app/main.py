import os, json, sqlite3, uuid, shutil, subprocess, threading, logging, time, base64, struct
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager,contextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import Field
from .schema import Scene, Strict
from .providers import PROVIDERS
from .ollama import OllamaConfig,list_models
from . import job_runtime,storage
from .spatial import solve_relations

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.getenv('STUDIO_DATA',str(ROOT/'data'))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'studio.sqlite3'
POOL=ThreadPoolExecutor(max_workers=2)
SLOTS=threading.BoundedSemaphore(8)
LOG=logging.getLogger('studio')

@contextmanager
def connection():
    con=sqlite3.connect(DB,timeout=20)
    con.row_factory=sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback();raise
    finally:con.close()

def initialize():
    from . import migrations
    migrations.prepare(DB)
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT,scene TEXT,prompt TEXT,updated TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,status TEXT,progress INTEGER,scene TEXT,error TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,job_id TEXT,stats TEXT);
        CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY,prompt TEXT,scene TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        if 'model_id' not in {r['name'] for r in db.execute('PRAGMA table_info(projects)')}:
            db.execute('ALTER TABLE projects ADD COLUMN model_id TEXT')
        db.execute("UPDATE jobs SET status='failed',error='服务重启，任务已中断' WHERE status IN ('running','pending')")
    from .ai3d.routes import initialize as initialize_ai3d
    initialize_ai3d(connection)
    migrations.finish(connection)
    with connection() as db:
        setting=db.execute("SELECT value FROM app_settings WHERE key='blender_path'").fetchone()
        if setting and Path(setting[0]).is_file():os.environ["BLENDER_PATH"]=setting[0]

def blender_path():
    configured=os.getenv('BLENDER_PATH')
    if configured and Path(configured).is_file(): return configured
    found=shutil.which('blender')
    if found: return found
    portable=next(ROOT.parent.glob('.tools/blender-*/blender.exe'),None)
    if portable: return str(portable)
    base=Path('C:/Program Files/Blender Foundation')
    return next((str(p) for p in base.glob('Blender */blender.exe')),None)

def safe_id(value):
    try:
        if str(uuid.UUID(value))!=value: raise ValueError()
    except ValueError: raise HTTPException(400,'无效 ID')
    return value

def asset_file(model_id,extension):
    safe_id(model_id)
    if extension not in ('glb','obj','json','mtl'): raise HTTPException(400,'不支持的格式')
    path=(DATA/model_id/f'model.{extension}').resolve()
    if not path.is_relative_to(DATA): raise HTTPException(400,'无效路径')
    if not path.is_file():
        alternative=(DATA/'library'/model_id/f'model.{extension}').resolve()
        if alternative.is_relative_to(DATA) and alternative.is_file():return alternative
        raise HTTPException(404,'文件不存在')
    return path

def update_job(job_id,status,progress,error=None):
    with connection() as db: db.execute('UPDATE jobs SET status=?,progress=?,error=? WHERE id=?',(status,progress,error,job_id))

def generate(job_id,scene):
    directory=DATA/job_id
    try:
        if job_id in job_runtime.CANCELLED:raise job_runtime.Cancelled()
        update_job(job_id,'running',10)
        directory.mkdir()
        source=directory/'model.json'; source.write_text(scene.model_dump_json(indent=2),encoding='utf-8')
        executable=blender_path()
        if not executable: raise RuntimeError('未找到 Blender。安装 Blender 后配置 BLENDER_PATH，并重新生成。')
        command=[executable,'--background','--factory-startup','--threads','2','--python',str(ROOT/'blender/generate.py'),'--',str(source),str(directory/'model.glb')]
        with (directory/'blender.log').open('w',encoding='utf-8') as log:
            result=job_runtime.run_worker(job_id,command,log,directory)
        if result: raise RuntimeError('Blender 建模失败，请检查本地 blender.log')
        output=directory/'model.glb'
        if not output.is_file() or output.stat().st_size<100: raise RuntimeError('Blender 未输出有效 GLB')
        stats=json.loads((directory/'stats.json').read_text())
        stats['glb_bytes']=output.stat().st_size
        if storage.usage(DATA)>storage.limits()['max_bytes']:raise RuntimeError('磁盘配额已满，请清理未引用缓存后重试')
        with job_runtime.LOCK:
            if job_id in job_runtime.CANCELLED:raise job_runtime.Cancelled()
            with connection() as db: db.execute('INSERT INTO assets VALUES(?,?,?)',(job_id,job_id,json.dumps(stats)))
            update_job(job_id,'completed',100)
    except job_runtime.Cancelled:
        update_job(job_id,'cancelled',0,'用户已取消，相关进程已终止')
    except subprocess.TimeoutExpired:
        update_job(job_id,'failed',0,'生成超过 120 秒，进程已终止')
    except Exception as exc:
        LOG.warning('Generation failed for %s: %s',job_id,type(exc).__name__)
        update_job(job_id,'failed',0,str(exc))
    finally:
        with connection() as db:row=db.execute('SELECT status FROM jobs WHERE id=?',(job_id,)).fetchone()
        if row and row['status'] in ('failed','cancelled'):
            for filename in ('model.glb','model.obj','model.mtl','stats.json'):
                (directory/filename).unlink(missing_ok=True)
        job_runtime.CANCELLED.discard(job_id)
        SLOTS.release()

@asynccontextmanager
async def lifespan(app):
    initialize()
    from .ai3d.routes import recover,shutdown
    await recover()
    try:yield
    finally:
        shutdown()
        for job_id in list(job_runtime.PROCESSES):
            job_runtime.cancel(job_id)

app=FastAPI(title='AI Text-to-3D Studio',version='0.4.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Content-Type'])

@app.middleware('http')
async def limit_body(request,call_next):
    if request.method in ('POST','PUT'):
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            limit=70*1024*1024 if request.url.path=='/api/models/snapshot' else (16*1024*1024 if request.url.path=='/api/ai3d/images' else 512*1024)
            if len(body)>limit:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'请求体超过大小上限'},status_code=413)
        request._body=bytes(body)
    return await call_next(request)

class ParseRequest(Strict):
    text: str = Field(min_length=1,max_length=4000)
    provider: str = 'rule'
    ollama: OllamaConfig | None = None

class ProjectRequest(Strict):
    name: str = Field(min_length=1,max_length=100)
    scene: Scene
    prompt: str = Field('',max_length=4000)
    model_id: str | None = None

@app.get('/api/health')
def health(): return {'status':'ok','blender_available':bool(blender_path()),'version':'0.4.0'}

@app.post('/api/providers/ollama/check')
async def ollama_check(config:OllamaConfig):
    try:return {'connected':True,'models':await list_models(config)}
    except ValueError as exc:raise HTTPException(503,str(exc)) from exc

@app.get('/api/schema')
def schema(): return Scene.model_json_schema()

@app.post('/api/validate-scene')
def validate_scene(scene:Scene):
    try:return solve_relations(scene)[0]
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

@app.post('/api/parse-text')
async def parse_text(request:ParseRequest):
    if request.provider not in PROVIDERS: raise HTTPException(400,'未知 Provider')
    started=time.monotonic()
    try: result=await PROVIDERS[request.provider].parse(request.text,request.ollama) if request.provider=='ollama' else await PROVIDERS[request.provider].parse(request.text)
    except Exception as exc:
        LOG.warning('Provider failed: %s',type(exc).__name__)
        message=str(exc)[:500] if isinstance(exc,ValueError) else ('Ollama 请求超时，请调高超时或选择较小模型' if isinstance(exc,TimeoutError) or type(exc).__name__.endswith('Timeout') else '请检查描述、参数范围或服务端 Provider 配置')
        raise HTTPException(422,'解析失败：'+message) from exc
    result['elapsed_ms']=round((time.monotonic()-started)*1000)
    with connection() as db: db.execute('INSERT INTO history(id,prompt,scene) VALUES(?,?,?)',(str(uuid.uuid4()),request.text,json.dumps(result['scene'])))
    return result

@app.post('/api/generate-model',status_code=202)
def generate_model(scene:Scene):
    try:scene=solve_relations(scene)[0]
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    if any(o.type=='imported' for o in scene.objects):raise HTTPException(422,'导入的模型请直接导出，不可通过 Blender 参数重建')
    if not blender_path(): raise HTTPException(503,'未找到 Blender，请安装并设置 BLENDER_PATH')
    if storage.usage(DATA)>=storage.limits()['max_bytes']:
        storage.cleanup(DATA,connection,storage.limits()['retention_days'])
        if storage.usage(DATA)>=storage.limits()['max_bytes']:raise HTTPException(507,'磁盘配额已满，请清理未引用缓存')
    if not SLOTS.acquire(blocking=False): raise HTTPException(429,'生成队列已满，请稍后重试')
    job_id=str(uuid.uuid4())
    try:
        with connection() as db: db.execute('INSERT INTO jobs(id,status,progress,scene) VALUES(?,?,?,?)',(job_id,'pending',0,scene.model_dump_json()))
        POOL.submit(generate,job_id,scene)
    except Exception:
        SLOTS.release(); raise
    return {'job_id':job_id}

@app.get('/api/jobs/{job_id}')
def get_job(job_id:str):
    safe_id(job_id)
    with connection() as db: row=db.execute('SELECT id,status,progress,error,created FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not row: raise HTTPException(404,'任务不存在')
    return {**dict(row),'model_id':job_id if row['status']=='completed' else None}

@app.post('/api/jobs/{job_id}/cancel')
def cancel_job(job_id:str):
    safe_id(job_id)
    with job_runtime.LOCK:
        result=get_job(job_id)
        if result['status'] not in ('pending','running'):raise HTTPException(409,'任务已经结束，不能取消')
        job_runtime.cancel(job_id)
        update_job(job_id,'cancelled',0,'用户已取消')
    return get_job(job_id)

@app.get('/api/jobs/{job_id}/log')
def job_log(job_id:str):
    get_job(job_id);path=(DATA/job_id/'blender.log').resolve()
    if not path.is_relative_to(DATA):raise HTTPException(400,'无效日志路径')
    if not path.is_file():return {'log':'尚无日志'}
    with path.open('rb') as handle:
        handle.seek(max(0,path.stat().st_size-32000));return {'log':handle.read().decode('utf-8',errors='replace')}

@app.get('/api/storage')
def get_storage():return storage.inventory(DATA,connection)

class CleanupRequest(Strict):
    older_than_days:int=Field(30,ge=0,le=3650)

@app.post('/api/storage/cleanup')
def cleanup_storage(request:CleanupRequest):
    return storage.cleanup(DATA,connection,request.older_than_days)

@app.get('/api/models/{model_id}')
def get_model(model_id:str):
    safe_id(model_id)
    with connection() as db: row=db.execute('SELECT assets.*,jobs.scene FROM assets JOIN jobs ON jobs.id=assets.job_id WHERE assets.id=?',(model_id,)).fetchone()
    if not row: raise HTTPException(404,'模型不存在')
    return {'id':model_id,'stats':json.loads(row['stats']),'scene':json.loads(row['scene']),'url':f'/api/models/{model_id}/download?format=glb'}

class SnapshotRequest(Strict):
    scene:Scene
    glb:str=Field(max_length=70*1024*1024)

@app.post('/api/models/snapshot',status_code=201)
def save_snapshot(request:SnapshotRequest):
    try:
        data=base64.b64decode(request.glb,validate=True)
        if len(data)>50*1024*1024 or len(data)<28 or data[:4]!=b'glTF' or struct.unpack_from('<II',data,4)!=(2,len(data)):raise ValueError()
        length,kind=struct.unpack_from('<II',data,12)
        if kind!=0x4E4F534A or length>len(data)-20:raise ValueError()
        gltf=json.loads(data[20:20+length])
        if not isinstance(gltf,dict) or not isinstance(gltf.get('meshes'),list) or not gltf['meshes']:raise ValueError()
        if any(resource.get('uri') and not resource['uri'].startswith('data:') for key in ('buffers','images') for resource in gltf.get(key,[])):raise ValueError()
    except (ValueError,TypeError,AttributeError,struct.error):raise HTTPException(422,'无效 GLB 快照或文件超出 50 MB，仅允许内嵌资源')
    with job_runtime.LOCK:
        if storage.usage(DATA)+len(data)>storage.limits()['max_bytes']:raise HTTPException(507,'保存将超过磁盘配额，请清理缓存')
        model_id=str(uuid.uuid4());directory=DATA/model_id;directory.mkdir()
        stats={'meshes':len(gltf['meshes']),'glb_bytes':len(data)}
        try:
            (directory/'model.glb').write_bytes(data)
            (directory/'model.json').write_text(request.scene.model_dump_json(),encoding='utf-8')
            with connection() as db:
                db.execute('INSERT INTO jobs(id,status,progress,scene) VALUES(?,?,?,?)',(model_id,'completed',100,request.scene.model_dump_json()))
                db.execute('INSERT INTO assets VALUES(?,?,?)',(model_id,model_id,json.dumps(stats)))
        except Exception:
            shutil.rmtree(directory);raise
    return {'id':model_id}

@app.get('/api/models/{model_id}/download')
def download(model_id:str,format:str='glb'):
    return FileResponse(asset_file(model_id,format),filename=f'model.{format}',media_type='model/gltf-binary' if format=='glb' else 'application/octet-stream')

@app.get('/api/history')
def history():
    with connection() as db: return [dict(r) for r in db.execute('SELECT * FROM history ORDER BY created DESC LIMIT 30')]

@app.get('/api/jobs')
def jobs():
    with connection() as db: return [dict(r) for r in db.execute('SELECT id,status,progress,error,created FROM jobs ORDER BY created DESC LIMIT 30')]

@app.get('/api/projects')
def projects():
    with connection() as db: return [dict(r) for r in db.execute('SELECT * FROM projects ORDER BY updated DESC')]

@app.post('/api/projects',status_code=201)
def create_project(request:ProjectRequest):
    project_id=str(uuid.uuid4())
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if request.model_id:asset_file(request.model_id,'glb')
        db.execute('INSERT INTO projects(id,name,scene,prompt,model_id) VALUES(?,?,?,?,?)',(project_id,request.name,request.scene.model_dump_json(),request.prompt,request.model_id))
    return {'id':project_id}

@app.put('/api/projects/{project_id}')
def put_project(project_id:str,request:ProjectRequest):
    safe_id(project_id)
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if request.model_id:asset_file(request.model_id,'glb')
        result=db.execute('UPDATE projects SET name=?,scene=?,prompt=?,model_id=?,updated=CURRENT_TIMESTAMP WHERE id=?',(request.name,request.scene.model_dump_json(),request.prompt,request.model_id,project_id))
        if result.rowcount==0: raise HTTPException(404,'项目不存在')
    return {'id':project_id}

@app.delete('/api/projects/{project_id}')
def delete_project(project_id:str):
    safe_id(project_id)
    with connection() as db:
        result=db.execute('DELETE FROM projects WHERE id=?',(project_id,))
        if not result.rowcount: raise HTTPException(404,'项目不存在')
    return {'deleted':True}

from .ai3d.routes import router as ai3d_router
app.include_router(ai3d_router)
from .ai3d.cloud import router as cloud3d_router
app.include_router(cloud3d_router)

from .security import install as install_security
install_security(app)

from .desktop_api import router as desktop_router
from .library import router as library_router
app.include_router(desktop_router)
app.include_router(library_router)

from .acceptance import router as acceptance_router
app.include_router(acceptance_router)

from .privacy import router as privacy_router
app.include_router(privacy_router)
