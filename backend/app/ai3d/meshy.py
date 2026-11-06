"""Meshy official cloud API. No mock fallback, no automatic paid POST retries."""
import math
from urllib.parse import urlsplit, urljoin
from uuid import UUID
import httpx
from . import credentials
from .contracts import Generative3DEngine
from .mesh import MAX_GLB_BYTES

API='https://api.meshy.ai'
MODEL='meshy-7.1'
ENDPOINTS={'text':'/openapi/v2/text-to-3d','refine':'/openapi/v2/text-to-3d','image':'/openapi/v1/image-to-3d'}


class RetryLater(ValueError):
    def __init__(self,delay=5):
        super().__init__('Meshy 暂时限流或服务繁忙；稍后继续查询，不会重建付费任务')
        self.delay=delay


def delay(headers):
    try:return min(60,max(2,float(headers.get('Retry-After',5))))
    except (TypeError,ValueError):return 5


def task_ref(value):
    try:
        kind,task_id=value.split(':',1)
        if kind not in ENDPOINTS or str(UUID(task_id))!=task_id:raise ValueError()
        return kind,task_id
    except (ValueError,AttributeError):raise ValueError('无效 Meshy 任务标识') from None


class MeshyAdapter(Generative3DEngine):
    id='meshy'
    def get_model_info(self):
        return {'id':self.id,'name':'Meshy 云端 AI（可能收费）','version':MODEL,'kind':'cloud','is_mock':False,
                'inputs':['text','PNG','JPEG','WebP'],'outputs':['GLB'],'models':[MODEL],
                'texture_capability':'图片可带纹理；文字为 preview + 可选 refine 两个收费任务',
                'license':{'name':'Meshy service terms / account plan','source':'https://www.meshy.ai/terms-of-use',
                           'restrictions':['云端处理，使用本人 API Key，按账户方案计费','输出权利受账户方案、服务条款及输入素材权利约束；不继承项目 MIT 许可']},
                'source':'https://docs.meshy.ai/en/api/text-to-3d','source_revision':'official-api-reviewed-2026-11-07'}
    def get_requirements(self):
        return {'gpu':None,'internet':True,'api_key':'Windows current-user DPAPI','paid_service':True,'cancel_running_supported':False}
    async def check_availability(self):
        try:credentials.get_key()
        except ValueError as exc:return {'engine':self.id,'available':False,'configured':False,'errors':[str(exc)],'texture_ready':False}
        return {'engine':self.id,'available':True,'configured':True,'errors':[],
                'notice':'本地密钥已配置；尚未验证云端授权或余额。仅点击生成才发送输入。','texture_ready':True}
    def client(self,authenticated=True):
        headers={'Authorization':'Bearer '+credentials.get_key()} if authenticated else {}
        return httpx.AsyncClient(headers=headers,timeout=httpx.Timeout(60,connect=15),follow_redirects=False,trust_env=False)
    async def request(self,method,path,body=None):
        try:
            async with self.client() as client:
                response=await client.request(method,API+path,json=body)
        except httpx.HTTPError:
            if method=='POST':raise ValueError('Meshy 创建请求通信中断，可能已经计费；请先在 Meshy 控制台检查任务，勿直接重复生成') from None
            raise RetryLater() from None
        if method=='GET' and (response.status_code==429 or response.status_code>=500):raise RetryLater(delay(response.headers))
        if response.status_code==409 and method=='DELETE':return {'still_running':True}
        if not response.is_success:
            message={400:'输入或模型参数被拒绝',401:'API Key 无效或已撤销',402:'余额不足或账户方案不支持 API',403:'权限或内容审核拒绝',404:'任务不存在或已过期',429:'请求限流；创建请求不会自动重试'}.get(response.status_code,'远程服务请求失败')
            if method=='POST' and response.status_code>=500:message+='；创建结果未知，可能已计费，请先检查 Meshy 控制台，勿重复生成'
            raise ValueError(f'Meshy HTTP {response.status_code}：{message}')
        if method=='DELETE':return {}
        try:return {'data':response.json(),'retry_after':delay(response.headers)}
        except ValueError:raise ValueError('Meshy 返回无效 JSON；创建任务请在控制台检查后再重试') from None
    async def create(self,kind,body):
        result=await self.request('POST',ENDPOINTS[kind],body)
        ref=kind+':'+str(result['data'].get('result',''));task_ref(ref)
        return {'id':ref}
    async def generate_from_text(self,prompt):
        if not prompt.strip() or len(prompt)>800:raise ValueError('Meshy 描述必须为 1–800 字符')
        return await self.create('text',{'mode':'preview','prompt':prompt,'ai_model':MODEL,'should_remesh':True,'topology':'triangle','target_polycount':100000,'target_formats':['glb']})
    async def generate_from_image(self,payload):
        body={'image_url':'data:image/png;base64,'+payload['image_b64'],'ai_model':MODEL,
              'should_remesh':True,'topology':'triangle','target_polycount':100000,'should_texture':payload.get('textured',True),'target_formats':['glb']}
        if body['should_texture']:body.update(enable_pbr=True,texture_resolution='2k')
        return await self.create('image',body)
    async def refine(self,ref,prompt):
        kind,task_id=task_ref(ref)
        if kind!='text':raise ValueError('仅允许为文字预览创建 refine')
        return await self.create('refine',{'mode':'refine','preview_task_id':task_id,'texture_prompt':prompt,'enable_pbr':True,'texture_resolution':'2k','target_formats':['glb']})
    async def raw_state(self,ref):
        kind,task_id=task_ref(ref)
        return await self.request('GET',ENDPOINTS[kind]+'/'+task_id)
    async def get_progress(self,job_id):
        result=await self.raw_state(job_id);data=result['data'];status=data.get('status')
        mapped={'PENDING':'pending','IN_PROGRESS':'running','SUCCEEDED':'completed','FAILED':'failed','CANCELED':'cancelled'}
        if status not in mapped:raise ValueError('Meshy 返回未知任务状态')
        progress=data.get('progress')
        if not isinstance(progress,(int,float)) or not math.isfinite(progress) or not 0<=progress<=100:progress=None
        kind,_=task_ref(job_id)
        # Do not return echoed prompt, provider error text, signed URLs or authorization data.
        return {'status':mapped[status],'stage':f'Meshy {kind} · {status}','progress':progress,'progress_kind':'provider',
                'retry_after':result['retry_after'],'error':'Meshy 云端生成失败；请在服务控制台查看审核、额度或输入错误' if status=='FAILED' else None}
    async def cancel(self,job_id):
        # DELETE only queued work. Never delete a completed output or pretend running work stopped.
        state=await self.get_progress(job_id)
        if state['status']!='pending':return {'remote_cancelled':False,'notice':'本地已停止等待；云端可能继续运行并计费，可恢复获取结果。'}
        kind,task_id=task_ref(job_id)
        result=await self.request('DELETE',ENDPOINTS[kind]+'/'+task_id)
        return {'remote_cancelled':not result.get('still_running',False),'notice':'排队删除已请求；退款与状态以 Meshy 为准。' if not result.get('still_running') else '云端已开始运行，无法中止；可恢复获取结果。'}
    async def cleanup(self,job_id):
        pass  # Downloaded locally; never silently destroy the user's paid cloud result.
    async def artifact(self,job_id,kind='model'):
        result=await self.raw_state(job_id)
        if result['data'].get('status')!='SUCCEEDED':raise ValueError('Meshy GLB 尚未准备好')
        url=result['data'].get('model_urls',{}).get('glb')
        if not isinstance(url,str):raise ValueError('Meshy 结果不包含 GLB；不会以测试几何替代')
        return await self.download(url)
    async def download(self,url):
        # The official task result uses assets.meshy.ai. Fail closed if the provider changes CDN.
        # A separate client intentionally has NO API Authorization header, including on redirects.
        try:
            async with self.client(authenticated=False) as client:
                for _ in range(4):
                    parsed=urlsplit(url)
                    if parsed.scheme!='https' or parsed.hostname!='assets.meshy.ai' or parsed.port not in (None,443) or parsed.username or parsed.password:raise ValueError('Meshy 下载地址不在受信任的 HTTPS CDN；拒绝下载')
                    async with client.stream('GET',url) as response:
                        if response.is_redirect:
                            url=urljoin(url,response.headers.get('Location',''));continue
                        if not response.is_success:raise ValueError('Meshy 下载失败或签名已过期；可重试下载，若服务保留期已过则无法恢复')
                        if int(response.headers.get('Content-Length',0))>MAX_GLB_BYTES:raise ValueError('云端 GLB 超过本地 50 MB 上限')
                        data=bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data)>MAX_GLB_BYTES:raise ValueError('云端 GLB 超过本地 50 MB 上限')
                        return bytes(data)
                raise ValueError('Meshy CDN 重定向过多')
        except httpx.HTTPError:raise ValueError('Meshy 模型下载通信失败；可恢复任务重新下载') from None
