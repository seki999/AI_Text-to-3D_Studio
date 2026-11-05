import os, json, sqlite3, uuid, shutil, subprocess, threading, logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import Field
from .schema import Scene, Strict
from .providers import PROVIDERS

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.getenv('STUDIO_DATA',str(ROOT/'data'))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'studio.sqlite3'
POOL=ThreadPoolExecutor(max_workers=2)
SLOTS=threading.BoundedSemaphore(8)
LOG=logging.getLogger('studio')

def connection():
    con=sqlite3.connect(DB,timeout=20)
    con.row_factory=sqlite3.Row
    return con

def initialize():
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
    if not path.is_file(): raise HTTPException(404,'文件不存在')
    return path

def update_job(job_id,status,progress,error=None):
    with connection() as db: db.execute('UPDATE jobs SET status=?,progress=?,error=? WHERE id=?',(status,progress,error,job_id))

def generate(job_id,scene):
    directory=DATA/job_id
    try:
        update_job(job_id,'running',10)
        directory.mkdir()
        source=directory/'model.json'; source.write_text(scene.model_dump_json(indent=2),encoding='utf-8')
        executable=blender_path()
        if not executable: raise RuntimeError('未找到 Blender。安装 Blender 后配置 BLENDER_PATH，并重新生成。')
        command=[executable,'--background','--factory-startup','--threads','2','--python',str(ROOT/'blender/generate.py'),'--',str(source),str(directory/'model.glb')]
        with (directory/'blender.log').open('w',encoding='utf-8') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120,cwd=directory,env={**os.environ,'PYTHONNOUSERSITE':'1'})
        if result.returncode: raise RuntimeError('Blender 建模失败，请检查本地 blender.log')
        output=directory/'model.glb'
        if not output.is_file() or output.stat().st_size<100: raise RuntimeError('Blender 未输出有效 GLB')
        stats=json.loads((directory/'stats.json').read_text())
        with connection() as db: db.execute('INSERT INTO assets VALUES(?,?,?)',(job_id,job_id,json.dumps(stats)))
        update_job(job_id,'completed',100)
    except subprocess.TimeoutExpired:
        update_job(job_id,'failed',0,'生成超过 120 秒，进程已终止')
    except Exception as exc:
        LOG.warning('Generation failed for %s: %s',job_id,type(exc).__name__)
        update_job(job_id,'failed',0,str(exc))
    finally: SLOTS.release()

@asynccontextmanager
async def lifespan(app):
    initialize()
    yield

app=FastAPI(title='AI Text-to-3D Studio',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Content-Type'])

@app.middleware('http')
async def limit_body(request,call_next):
    if request.method in ('POST','PUT'):
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>512*1024:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'请求体超过 512 KB'},status_code=413)
        request._body=bytes(body)
    return await call_next(request)

class ParseRequest(Strict):
    text: str = Field(min_length=1,max_length=4000)
    provider: str = 'rule'

class ProjectRequest(Strict):
    name: str = Field(min_length=1,max_length=100)
    scene: Scene
    prompt: str = Field('',max_length=4000)
    model_id: str | None = None

@app.get('/api/health')
def health(): return {'status':'ok','blender_available':bool(blender_path()),'version':'0.1.0'}

@app.get('/api/schema')
def schema(): return Scene.model_json_schema()

@app.post('/api/validate-scene')
def validate_scene(scene:Scene): return scene

@app.post('/api/parse-text')
async def parse_text(request:ParseRequest):
    if request.provider not in PROVIDERS: raise HTTPException(400,'未知 Provider')
    try: result=await PROVIDERS[request.provider].parse(request.text)
    except Exception as exc:
        LOG.warning('Provider failed: %s',type(exc).__name__)
        raise HTTPException(422,'解析失败：请检查描述、参数范围或服务端 Provider 配置') from exc
    with connection() as db: db.execute('INSERT INTO history(id,prompt,scene) VALUES(?,?,?)',(str(uuid.uuid4()),request.text,json.dumps(result['scene'])))
    return result

@app.post('/api/generate-model',status_code=202)
def generate_model(scene:Scene):
    if not blender_path(): raise HTTPException(503,'未找到 Blender，请安装并设置 BLENDER_PATH')
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

@app.get('/api/models/{model_id}')
def get_model(model_id:str):
    safe_id(model_id)
    with connection() as db: row=db.execute('SELECT assets.*,jobs.scene FROM assets JOIN jobs ON jobs.id=assets.job_id WHERE assets.id=?',(model_id,)).fetchone()
    if not row: raise HTTPException(404,'模型不存在')
    return {'id':model_id,'stats':json.loads(row['stats']),'scene':json.loads(row['scene']),'url':f'/api/models/{model_id}/download?format=glb'}

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
    if request.model_id: asset_file(request.model_id,'glb')
    project_id=str(uuid.uuid4())
    with connection() as db: db.execute('INSERT INTO projects(id,name,scene,prompt,model_id) VALUES(?,?,?,?,?)',(project_id,request.name,request.scene.model_dump_json(),request.prompt,request.model_id))
    return {'id':project_id}

@app.put('/api/projects/{project_id}')
def put_project(project_id:str,request:ProjectRequest):
    safe_id(project_id)
    if request.model_id: asset_file(request.model_id,'glb')
    with connection() as db:
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
