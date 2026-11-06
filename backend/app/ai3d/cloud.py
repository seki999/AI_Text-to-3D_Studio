"""Cloud orchestration reuses local assets/editor; never synthesizes cloud output."""
import asyncio
import base64
import json
import threading
import time
import uuid
from fastapi import APIRouter,HTTPException
from PIL import Image
from . import routes as jobs
from .adapters import ENGINES
from .contracts import CloudRequest
from .cloud_mesh import process_cloud_glb
from .meshy import RetryLater,task_ref

router=APIRouter(prefix='/api/ai3d',tags=['Cloud AI 3D'])


async def orchestrate(job_id,event):
    value=jobs.row(job_id);engine=ENGINES['meshy'];options=json.loads(value['options']);ref=value['remote_id']
    try:
        if event.is_set():raise asyncio.CancelledError()
        if not ref:
            jobs.update(job_id,status='running',stage='提交 Meshy 云端付费任务；创建请求不会自动重试',error=None)
            if options['mode']=='text':result=await engine.generate_from_text(value['prompt'])
            else:result=await engine.generate_from_image({'image_b64':base64.b64encode(jobs.image_file(value['image_id']).read_bytes()).decode(),'textured':options['textured']})
            ref=result['id'];task_ref(ref);jobs.update(job_id,remote_id=ref)
        deadline=time.monotonic()+3600;failures=0
        while True:
            if event.is_set():raise asyncio.CancelledError()
            if time.monotonic()>deadline:raise ValueError('本地等待超过 60 分钟；云端可能继续计费。可恢复已有任务，勿重复创建。')
            try:state=await engine.get_progress(ref);failures=0
            except RetryLater as exc:
                failures+=1
                if failures>12:raise ValueError('云端持续通信失败；任务可能继续计费。请稍后恢复已有任务。') from None
                jobs.update(job_id,stage=str(exc),progress=None,progress_kind='stage')
                await pause(event,exc.delay);continue
            if state['status']=='failed':raise ValueError(state['error'])
            if state['status']=='cancelled':raise ValueError('云端任务已取消')
            if state['status']=='completed':
                if options['mode']=='text' and options['textured'] and task_ref(ref)[0]=='text':
                    if event.is_set():raise asyncio.CancelledError()
                    # A crash/timeout during this POST is ambiguous. Prevent a second paid refine on resume.
                    jobs.update(job_id,stage='文字预览完成；提交已确认的独立纹理任务',metadata=json.dumps({'refine_creation_pending':True}))
                    result=await engine.refine(ref,value['prompt']);ref=result['id'];task_ref(ref)
                    jobs.update(job_id,remote_id=ref,metadata=None);continue
                break
            jobs.update(job_id,status='running',stage=state['stage'],progress=state['progress'],progress_kind='provider')
            await pause(event,state['retry_after'])
        if event.is_set():raise asyncio.CancelledError()
        jobs.update(job_id,stage='下载云端 GLB 并校验；原始文件保留',progress=None,progress_kind='stage')
        original=await engine.artifact(ref)
        raw,stats=await asyncio.to_thread(process_cloud_glb,original,options['processing'])
        with jobs.LOCK:
            if event.is_set():raise asyncio.CancelledError()
            value['remote_id']=ref
            stats['inference']={'provider':'meshy','model':engine.get_model_info()['version'],'remote_task':ref}
            jobs.register_asset(value,raw,original,stats)
    except asyncio.CancelledError:
        notice='尚未提交云端任务。'
        if ref:
            try:notice=(await engine.cancel(ref))['notice']
            except ValueError:notice='云端取消未确认；任务可能继续运行和计费，可恢复获取结果。'
        jobs.update(job_id,status='cancelled',stage='本地等待已停止',progress=None,error=notice)
    except Exception as exc:
        # Only our own sanitized adapter/processing errors are returned; no HTTP response bodies/URLs.
        message=str(exc) if isinstance(exc,ValueError) else '云端任务处理失败；可恢复已有任务，检查本地配额和 GLB 格式'
        jobs.update(job_id,status='failed',stage='Meshy 任务未完成',progress=None,error=message[:2000])
    finally:
        with jobs.LOCK:jobs.CANCELS.pop(job_id,None);jobs.FUTURES.pop(job_id,None)
        jobs.SLOTS.release()


async def pause(event,seconds):
    deadline=time.monotonic()+seconds
    while not event.is_set() and time.monotonic()<deadline:await asyncio.sleep(min(.2,max(0,deadline-time.monotonic())))


@router.post('/jobs/cloud',status_code=202)
async def create(request:CloudRequest):
    if not request.cloud_consent or not request.license_acknowledged:raise HTTPException(422,'请确认云端上传、可能收费及第三方服务条款')
    if request.processing.repair_normals or request.processing.simplify_faces:raise HTTPException(422,'云端 Mesh 保留原始几何、材质与标记，不支持修复或减面')
    if request.mode=='text' and not request.prompt.strip():raise HTTPException(422,'文字生成需要描述')
    if request.mode=='image':
        if not request.image_id:raise HTTPException(422,'图片生成需要本地已上传的参考图片')
        path=jobs.image_file(request.image_id)
        with Image.open(path) as image:
            if min(image.size)<32:raise HTTPException(422,'Meshy 要求图片每边至少 32 像素')
    status=await ENGINES['meshy'].check_availability()
    if not status['available']:raise HTTPException(503,'；'.join(status['errors']))
    return jobs.start({'id':str(uuid.uuid4()),'engine':'meshy','image_id':request.image_id if request.mode=='image' else None,
                       'prompt':request.prompt,'operation':'cloud_'+request.mode,
                       'options':{'mode':request.mode,'textured':request.textured,'processing':request.processing.model_dump()}})


@router.post('/jobs/{job_id}/resume',status_code=202)
async def resume(job_id:str):
    with jobs.LOCK:
        value=jobs.row(job_id)
        if value['engine']!='meshy' or value['status'] not in ('failed','cancelled') or not value['remote_id']:raise HTTPException(409,'仅可恢复已停止且保存云端 ID 的 Meshy 任务')
        metadata=json.loads(value['metadata']) if value['metadata'] else {}
        if metadata.get('refine_creation_pending'):raise HTTPException(409,'纹理创建结果未知，可能已计费。请先在 Meshy 控制台核对；禁止自动重复创建。')
        task_ref(value['remote_id'])
        if not (await ENGINES['meshy'].check_availability())['available']:raise HTTPException(503,'请先配置 Meshy 本地凭证')
        if not jobs.SLOTS.acquire(False):raise HTTPException(429,'AI 转交队列已满')
        event=threading.Event()
        try:
            jobs.update(job_id,status='pending',stage='恢复已有云端任务',error=None)
            jobs.CANCELS[job_id]=event;jobs.FUTURES[job_id]=jobs.POOL.submit(jobs.execute_async,job_id,event)
        except Exception:
            jobs.SLOTS.release();raise
    return jobs.representation(jobs.row(job_id))
