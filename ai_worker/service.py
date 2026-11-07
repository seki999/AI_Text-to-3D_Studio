"""Independent authenticated loopback worker; one inference child at a time."""
import base64,hmac,json,os,shutil,sqlite3,subprocess,sys,threading,uuid
import psutil
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager,contextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI,Depends,Header,HTTPException
from fastapi.responses import FileResponse
from pydantic import Field
from backend.app.schema import Strict
from backend.app.ai3d.contracts import GenerationOptions
from backend.app.ai3d.images import decode_image
from backend.app.ai3d.mesh import glb_document
from backend.app import job_runtime

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.getenv('AI3D_WORKER_DATA',str(ROOT/'.ai3d-worker-data'))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
POOL=ThreadPoolExecutor(max_workers=1)
SLOTS=threading.BoundedSemaphore(4)
FUTURES={}

@contextmanager
def db():
    con=sqlite3.connect(DATA/'worker.sqlite3',timeout=20);con.row_factory=sqlite3.Row
    try:yield con;con.commit()
    except Exception:con.rollback();raise
    finally:con.close()

def authorize(x_worker_token:str=Header('')):
    token=os.getenv('AI3D_WORKER_TOKEN','')
    if len(token)<16 or not hmac.compare_digest(x_worker_token.encode('utf-8'),token.encode('utf-8')):raise HTTPException(401,'Worker token 无效或未配置')

def valid_id(value):
    try:
        if str(uuid.UUID(value))!=value:raise ValueError()
    except ValueError:raise HTTPException(400,'非法 Worker ID')
    path=(DATA/value).resolve()
    if not path.is_relative_to(DATA):raise HTTPException(400,'无效任务目录')
    return path

def update(job_id,status,error=None):
    with db() as con:con.execute('UPDATE worker_jobs SET status=?,error=? WHERE id=?',(status,error,job_id))

def execute(job_id):
    directory=valid_id(job_id)
    try:
        with job_runtime.LOCK:
            if job_id in job_runtime.CANCELLED:raise job_runtime.Cancelled()
            update(job_id,'running')
        with (directory/'runner.log').open('w',encoding='utf-8') as log:
            def started(process):(directory/'process.json').write_text(json.dumps({'pid':process.pid,'create_time':psutil.Process(process.pid).create_time()}),encoding='utf-8')
            command=[sys.executable,'--runner',str(directory)] if getattr(sys,'frozen',False) else [sys.executable,'-m','ai_worker.runner',str(directory)]
            code=job_runtime.run_worker(job_id,command,log,ROOT,timeout=int(os.getenv('AI3D_TIMEOUT_SECONDS','1800')),on_started=started)
        if code:
            error=json.loads((directory/'error.json').read_text(encoding='utf-8'))['error'] if (directory/'error.json').exists() else '推理子进程异常退出，请查看日志'
            raise RuntimeError(error)
        glb_document((directory/'model.glb').read_bytes())
        if sum(p.stat().st_size for d in DATA.iterdir() if d.is_dir() for p in d.iterdir() if p.is_file())>int(os.getenv('AI3D_WORKER_MAX_DISK_MB','2048'))*1048576:raise RuntimeError('Worker 磁盘软配额已满，请清理已传回资产的任务')
        with job_runtime.LOCK:
            if job_id in job_runtime.CANCELLED:raise job_runtime.Cancelled()
            update(job_id,'completed')
    except job_runtime.Cancelled:update(job_id,'cancelled','用户已取消，推理进程树已终止')
    except subprocess.TimeoutExpired:update(job_id,'failed','AI 推理超时，已终止进程树')
    except Exception as exc:update(job_id,'failed',str(exc)[:2000])
    finally:
        with db() as con:row=con.execute('SELECT status FROM worker_jobs WHERE id=?',(job_id,)).fetchone()
        if row and row['status']!='completed':
            for name in ('model.glb','shape.glb','painted.glb','stats.json'):(directory/name).unlink(missing_ok=True)
            if row['status']=='cancelled':(directory/'original.glb').unlink(missing_ok=True)
        with job_runtime.LOCK:FUTURES.pop(job_id,None)
        job_runtime.CANCELLED.discard(job_id);SLOTS.release()

@asynccontextmanager
async def lifespan(app):
    if len(os.getenv('AI3D_WORKER_TOKEN',''))<16:raise RuntimeError('必须设置至少 16 字符 AI3D_WORKER_TOKEN')
    with db() as con:
        con.execute('CREATE TABLE IF NOT EXISTS worker_jobs(id TEXT PRIMARY KEY,status TEXT,error TEXT,engine TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP)')
        for row in con.execute("SELECT id FROM worker_jobs WHERE status IN ('pending','running')").fetchall():
            directory=valid_id(row['id'])
            try:
                state=json.loads((directory/'process.json').read_text(encoding='utf-8'));process=psutil.Process(state['pid'])
                if abs(process.create_time()-state['create_time'])<.01 and (process.cmdline()[-3:]==['-m','ai_worker.runner',str(directory)] or (getattr(sys,'frozen',False) and process.exe()==sys.executable and process.cmdline()[-2:]==['--runner',str(directory)])):
                    children=process.children(recursive=True)
                    for child in children:child.kill()
                    process.kill();psutil.wait_procs(children+[process],timeout=5)
            except (OSError,ValueError,KeyError,psutil.Error):pass
        con.execute("UPDATE worker_jobs SET status='failed',error='Worker 重启，旧任务已中断' WHERE status IN ('pending','running')")
    try:yield
    finally:
        for job_id in list(FUTURES):
            try:cancel(job_id)
            except HTTPException:pass

app=FastAPI(title='FORMA independent AI3D Worker',version='0.3.0',lifespan=lifespan,dependencies=[Depends(authorize)])

@app.post('/shutdown')
def shutdown_desktop():
    server=getattr(app.state,'desktop_server',None)
    if not server:raise HTTPException(404,'非受管理的桌面 Worker')
    threading.Timer(.2,lambda:setattr(server,'should_exit',True)).start()
    return {'stopping':True}

@app.middleware('http')
async def body_limit(request,call_next):
    if request.method=='POST':
        content=bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content)>85*1024*1024:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'Worker 请求超过上限'},status_code=413)
        request._body=bytes(content)
    return await call_next(request)

def probe():
    try:
        command=[sys.executable,'--probe'] if getattr(sys,'frozen',False) else [sys.executable,'-m','ai_worker.probe']
        result=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if result.returncode:raise ValueError()
        return json.loads(result.stdout.decode('utf-8'))
    except (ValueError,OSError,subprocess.SubprocessError):return {'available':False,'errors':['独立 Python CUDA 诊断失败或超时'],'torch_cuda_available':None,'weights_ready':None,'gpus':[],'texture_ready':False}

@app.get('/health')
def health():return {'status':'ok','version':'0.3.0','worker_python':sys.version.split()[0],'mock_enabled':os.getenv('AI3D_ENABLE_MOCK')=='1'}

@app.post('/diagnose')
def diagnose():
    return {**probe(),'worker_storage':{'used_bytes':sum(p.stat().st_size for d in DATA.iterdir() if d.is_dir() for p in d.iterdir() if p.is_file()),'max_bytes':int(os.getenv('AI3D_WORKER_MAX_DISK_MB','2048'))*1048576}}

class Request(Strict):
    engine:Literal['hunyuan3d-2.1','mock']
    image_b64:str=Field(max_length=16*1024*1024)
    options:GenerationOptions=Field(default_factory=GenerationOptions)
    operation:Literal['shape','texture']='shape'
    shape_b64:str|None=Field(None,max_length=70*1024*1024)

@app.post('/jobs',status_code=202)
def create(request:Request):
    if request.engine=='mock' and os.getenv('AI3D_ENABLE_MOCK')!='1':raise HTTPException(403,'测试 Mock 未启用')
    if request.engine=='hunyuan3d-2.1':
        status=probe()
        if not status['available']:raise HTTPException(503,'；'.join(status['errors']))
        if request.operation=='texture' and not status['texture_ready']:raise HTTPException(503,'纹理环境未准备好，Shape 仍可单独使用')
    if not SLOTS.acquire(False):raise HTTPException(429,'Worker 队列已满（单机并发 1）')
    job_id=str(uuid.uuid4());directory=valid_id(job_id)
    try:
        image,_=decode_image(request.image_b64);shape=None
        if request.operation=='texture':
            if not request.shape_b64:raise ValueError('纹理步骤需要已有 Shape')
            shape=base64.b64decode(request.shape_b64,validate=True);glb_document(shape)
        directory.mkdir();(directory/'reference.png').write_bytes(image)
        if shape:(directory/'shape.glb').write_bytes(shape)
        (directory/'request.json').write_text(json.dumps({'engine':request.engine,'operation':request.operation,'options':request.options.model_dump()}),encoding='utf-8')
        with db() as con:con.execute('INSERT INTO worker_jobs(id,status,engine) VALUES(?,?,?)',(job_id,'pending',request.engine))
        with job_runtime.LOCK:FUTURES[job_id]=POOL.submit(execute,job_id)
    except Exception as exc:
        if directory.exists():shutil.rmtree(directory)
        SLOTS.release()
        if isinstance(exc,ValueError):raise HTTPException(422,str(exc)) from exc
        raise
    return {'id':job_id,'status':'pending'}

@app.get('/jobs/{job_id}')
def get(job_id:str):
    directory=valid_id(job_id)
    with db() as con:row=con.execute('SELECT * FROM worker_jobs WHERE id=?',(job_id,)).fetchone()
    if not row:raise HTTPException(404,'Worker 任务不存在')
    state=dict(row);state.update(progress=None,progress_kind='stage',stage='排队中')
    try:state.update(json.loads((directory/'progress.json').read_text(encoding='utf-8')))
    except (OSError,ValueError):pass
    if state['status']=='completed':state['stats']=json.loads((directory/'stats.json').read_text(encoding='utf-8'))
    return state

@app.post('/jobs/{job_id}/cancel')
def cancel(job_id:str):
    with job_runtime.LOCK:
        state=get(job_id)
        if state['status'] not in ('pending','running'):raise HTTPException(409,'任务已结束')
        future=FUTURES.get(job_id)
        if future and future.cancel():
            FUTURES.pop(job_id,None);SLOTS.release();update(job_id,'cancelled','排队任务取消，未启动推理进程')
            return get(job_id)
        job_runtime.cancel(job_id);update(job_id,'cancelled','用户取消')
    return get(job_id)

@app.get('/jobs/{job_id}/artifacts/{kind}')
def artifact(job_id:str,kind:Literal['model','original']):
    state=get(job_id)
    if state['status']!='completed' and not (kind=='original' and state['status']=='failed' and (valid_id(job_id)/'original.glb').is_file()):raise HTTPException(409,'任务未完成或原始模型不存在')
    return FileResponse(valid_id(job_id)/(kind+'.glb'),media_type='model/gltf-binary')

@app.get('/jobs/{job_id}/log')
def log(job_id:str):
    get(job_id);file=valid_id(job_id)/'runner.log'
    if not file.exists():return {'log':'尚无日志'}
    with file.open('rb') as handle:handle.seek(max(0,file.stat().st_size-32000));return {'log':handle.read().decode('utf-8',errors='replace')}

@app.delete('/jobs/{job_id}')
def cleanup(job_id:str):
    with job_runtime.LOCK:
        if get(job_id)['status'] in ('running','pending') or job_id in job_runtime.PROCESSES:raise HTTPException(409,'运行中的任务不可删除')
        directory=valid_id(job_id)
        if directory.exists():shutil.rmtree(directory)
        with db() as con:con.execute('DELETE FROM worker_jobs WHERE id=?',(job_id,))
    return {'cleaned':True}
