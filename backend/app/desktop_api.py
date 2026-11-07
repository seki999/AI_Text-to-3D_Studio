import hmac,json,os,threading
from pathlib import Path
from fastapi import APIRouter,HTTPException,Request
from pydantic import Field
from .schema import Strict
from .ai3d import credentials
router=APIRouter(prefix='/api/desktop')

def core():
    from . import main
    return main

def native(request):
    token=os.getenv('FORMA_SESSION_TOKEN','')
    if len(token)<32 or not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+token):raise HTTPException(403,'仅允许桌面宿主操作')

class Key(Strict):key:str=Field(min_length=16,max_length=512,repr=False)
class Blender(Strict):path:str=Field(max_length=1000)
class Worker(Strict):port:int=Field(ge=1024,le=65535);token:str=Field(min_length=32,max_length=128,repr=False)

@router.post('/worker-connection')
def worker(value:Worker,request:Request):
    native(request)
    os.environ['AI3D_WORKER_URL']=f'http://127.0.0.1:{value.port}'
    os.environ['AI3D_WORKER_TOKEN']=value.token
    return {'connected':True}

@router.post('/meshy-key')
def key(value:Key,request:Request):
    native(request)
    try:credentials.save_key(value.key)
    except ValueError:raise HTTPException(422,'密钥格式或 Windows 安全存储不可用') from None
    return {'configured':True}

@router.post('/blender')
def blender(value:Blender,request:Request):
    native(request);path=Path(value.path).resolve()
    if path.name.lower()!='blender.exe' or not path.is_file():raise HTTPException(422,'请选择已安装的 blender.exe')
    with core().connection() as db:db.execute('INSERT OR REPLACE INTO app_settings VALUES(?,?)',('blender_path',str(path)))
    os.environ['BLENDER_PATH']=str(path)
    return {'configured':True}

@router.post('/meshy-key/delete')
def delete_key(request:Request):
    native(request)
    try:credentials.secret_path().unlink(missing_ok=True)
    except OSError:raise HTTPException(503,'本地凭证删除失败') from None
    return {'deleted':True,'cloud_account_unchanged':True}

@router.post('/shutdown')
def shutdown(request:Request):
    native(request)
    server=getattr(request.app.state,'desktop_server',None)
    if server:threading.Timer(.2,lambda:setattr(server,'should_exit',True)).start()
    return {'stopping':bool(server)}

@router.get('/info')
def info():
    c=core();logdir=Path(os.getenv('FORMA_LOG_DIR',str(c.DATA/'logs')))
    return {'version':'0.4.0','desktop':bool(os.getenv('FORMA_SESSION_TOKEN')),'data_directory':str(c.DATA),'log_directory':str(logdir),
            'blender_available':bool(c.blender_path()),'schema_version':4,'updates':'仅用户主动安装经验证签名的新安装包；不静默下载或执行更新',
            'privacy':'本地建模不上传；云端只有在明确点击生成并确认费用后发送输入'}

@router.get('/logs')
def logs():
    path=Path(os.getenv('FORMA_LOG_DIR',str(core().DATA/'logs')))/'desktop.log'
    return {'log':path.read_text(encoding='utf-8',errors='replace')[-24000:] if path.is_file() else '暂无桌面日志'}
