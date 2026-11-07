"""Explicit, one-create-only real API acceptance. Never enabled by CI flags."""
import asyncio,base64,json,threading,uuid
from datetime import datetime,timezone
from fastapi import APIRouter,HTTPException
from fastapi.responses import JSONResponse
from pydantic import Field
from .schema import Strict
from .ai3d import routes as jobs
from .ai3d.meshy import MeshyAdapter,task_ref
from .ai3d.cloud_mesh import process_cloud_glb
from .ai3d import credentials
router=APIRouter(prefix='/api/acceptance')
LOCKS={};GUARD=threading.Lock()

def save(report):
    with jobs.core().connection() as db:db.execute('INSERT OR REPLACE INTO acceptance_runs VALUES(?,?)',(report['id'],json.dumps(report)))
    return report
def get(id):
    jobs.core().safe_id(id)
    with jobs.core().connection() as db:row=db.execute('SELECT report FROM acceptance_runs WHERE id=?',(id,)).fetchone()
    if not row:raise HTTPException(404,'验收报告不存在')
    return json.loads(row[0])
class Start(Strict):
    id:str
    authorize_paid_test:bool=False
    prompt:str=Field('A simple red ceramic cube',min_length=1,max_length=800)
class Evidence(Strict):viewer_loaded:bool=False
class Compatibility(Strict):model_id:str;provider:str=Field(min_length=1,max_length=100);license_note:str=Field(min_length=3,max_length=1000);rights_confirmed:bool=False

@router.post('/compatibility',status_code=201)
def compatibility(request:Compatibility):
    if not request.rights_confirmed:raise HTTPException(422,'请确认对素材拥有合法使用权')
    from .ai3d.mesh import load_glb,inspect_scene
    raw=jobs.core().asset_file(request.model_id,'glb').read_bytes()
    try:scene,doc=load_glb(raw);stats=inspect_scene(scene,doc)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    return save({'id':str(uuid.uuid4()),'kind':'external_asset_compatibility','status':'completed','asset_id':request.model_id,'provider_claim':request.provider,'license_note':request.license_note,'stats':stats,
                 'checks':{'mesh':True,'materials_inspected':True,'viewer_loaded':False,'real_inference':'not_claimed','save_reopen_export':'not_verified'},'notice':'仅验证用户提供合法素材的兼容性，不证明执行了真实生成任务'})

@router.post('/meshy/account')
async def account():
    try:
        result=await MeshyAdapter().request('GET','/openapi/v1/balance')
        balance=result['data'].get('balance')
        if not isinstance(balance,(int,float)) or balance<0:raise ValueError('余额响应无效')
        return {'key_authenticated':True,'available_credits':balance,'generation_permission':'创建任务时才能最终确认','estimated_test_credits':5,'model':'meshy-6-lite','pricing_checked':'2026-11-07','pricing_url':'https://docs.meshy.ai/en/api/pricing'}
    except ValueError as exc:raise HTTPException(503,str(exc)) from None

@router.post('/meshy',status_code=201)
async def start(request:Start):
    jobs.core().safe_id(request.id)
    # Reserve the ID before any network call: repeated clicks/restarts cannot duplicate a paid create.
    report={'id':request.id,'kind':'real_api_acceptance','created':datetime.now(timezone.utc).isoformat(),'model':'meshy-6-lite','estimated_credits':5,
            'textured':False,'status':'reserved','remote_id':None,'asset_id':None,'checks':{'key':False,'paid_authorized':request.authorize_paid_test,'mesh':False,'materials_inspected':False,'viewer_loaded':False,'save_reopen_export':'not_verified'},'notice':'一次低成本 preview 几何任务；预计 5 credits，实际费用以服务方为准。不会自动 refine 或自动重建。'}
    with jobs.core().connection() as db:
        previous=db.execute('SELECT report FROM acceptance_runs WHERE id=?',(request.id,)).fetchone()
        if previous:return json.loads(previous[0])
        db.execute('INSERT INTO acceptance_runs VALUES(?,?)',(request.id,json.dumps(report)))
    try:credentials.get_key();report['checks']['key']=True
    except ValueError:
        report.update(status='skipped',reason='未配置本地 Key；没有发起真实 API 请求');return save(report)
    if not request.authorize_paid_test:
        report.update(status='skipped',reason='未授权付费测试；没有发起真实 API 请求');return save(report)
    try:
        report['account']=await account()
        if report['account']['available_credits']<5:raise ValueError('余额低于预计测试额度；未创建收费任务')
        report['status']='submitting';save(report)
        engine=MeshyAdapter()
        result=await engine.create('text',{'mode':'preview','prompt':request.prompt,'ai_model':'meshy-6-lite','should_remesh':True,'topology':'triangle','target_polycount':10000,'target_formats':['glb']})
        report.update(status='pending',remote_id=result['id']);save(report)
        with jobs.core().connection() as db:db.execute('INSERT INTO ai3d_jobs(id,engine,image_id,prompt,options,operation,remote_id,status,stage,progress_kind) VALUES(?,?,?,?,?,?,?,?,?,?)',(request.id,'meshy',None,request.prompt,json.dumps({'mode':'text','textured':False,'processing':{'center':True,'normalize':True,'size':2}}),'cloud_acceptance',result['id'],'pending','真实付费验收','stage'))
    except (ValueError,HTTPException) as exc:report.update(status='failed',reason=str(exc.detail) if isinstance(exc,HTTPException) else str(exc))
    return save(report)

@router.get('')
def history():
    with jobs.core().connection() as db:return [json.loads(r[0]) for r in db.execute('SELECT report FROM acceptance_runs ORDER BY rowid DESC LIMIT 30')]
@router.get('/{id}')
def report(id:str):return get(id)
@router.get('/{id}/download')
def download_report(id:str):return JSONResponse(get(id),headers={'Content-Disposition':f'attachment; filename="forma-verification-{id}.json"'})
@router.post('/{id}/refresh')
async def refresh(id:str):
    with GUARD:lock=LOCKS.setdefault(id,threading.Lock())
    if not lock.acquire(False):return get(id)
    try:
        value=get(id)
        if not value['remote_id'] or value['asset_id']:return value
        engine=MeshyAdapter();state=await engine.get_progress(value['remote_id']);value['status']=state['status'];value['stage']=state['stage']
        if state['status']=='failed':value['reason']=state['error']
        if state['status']=='completed':
            original=await engine.artifact(value['remote_id']);raw,stats=await asyncio.to_thread(process_cloud_glb,original,{'center':True,'normalize':True,'size':2})
            stats['inference']={'model':'meshy-6-lite','provider':'meshy'}
            if not jobs.row(id)['asset_id']:jobs.register_asset(jobs.row(id),raw,original,stats)
            value.update(asset_id=id,model_url=f'/api/models/{id}/download?format=glb',stats=stats['after'])
            value['checks'].update(mesh=True,materials_inspected=True)
        elif state['status'] in ('pending','running'):jobs.update(id,status=state['status'],stage=state['stage'],progress=state['progress'],progress_kind='provider')
        return save(value)
    except ValueError as exc:
        value=get(id);value['reason']=str(exc);return save(value)
    finally:lock.release()
@router.post('/{id}/evidence')
def evidence(id:str,request:Evidence):
    value=get(id)
    if not value['asset_id']:raise HTTPException(409,'尚无真实下载并验证的资产')
    value['checks']['viewer_loaded']=request.viewer_loaded
    value['checks']['save_reopen_export']='需要在编辑器保存项目并实际导出；此处不自动声称通过'
    return save(value)
