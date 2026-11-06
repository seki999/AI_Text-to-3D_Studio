import base64,ipaddress,os
from urllib.parse import urlsplit
import httpx
from .contracts import Generative3DEngine
from .mesh import MAX_GLB_BYTES

def worker_url():
    value=os.getenv('AI3D_WORKER_URL','http://127.0.0.1:8010');url=urlsplit(value)
    try:valid=url.hostname=='localhost' or ipaddress.ip_address(url.hostname or '').is_loopback
    except ValueError:valid=False
    if not valid or url.scheme!='http' or url.username or url.password or url.path not in ('','/') or url.query or url.fragment or not url.port:raise ValueError('AI Worker 仅允许带端口的本机回环 HTTP 根地址')
    host='127.0.0.1' if url.hostname=='localhost' else url.hostname
    return f'http://[{host}]:{url.port}' if ':' in host else f'http://{host}:{url.port}'

class WorkerClient:
    def client(self,timeout=50):
        token=os.getenv('AI3D_WORKER_TOKEN','')
        if len(token)<16:raise ValueError('未配置 AI3D_WORKER_TOKEN（至少 16 字符），请先启动独立 Worker')
        return httpx.AsyncClient(base_url=worker_url(),headers={'X-Worker-Token':token},timeout=timeout,trust_env=False,follow_redirects=False)
    async def json(self,method,path,body=None):
        try:
            async with self.client() as client:
                r=await client.request(method,path,json=body)
                if not r.is_success:
                    try:message=r.json().get('detail','Worker 请求失败')
                    except ValueError:message='Worker 返回无效响应'
                    raise ValueError(str(message)[:2000])
                return r.json()
        except httpx.HTTPError as exc:raise ValueError('无法连接独立 AI Worker 或请求超时；请检查服务、端口和令牌') from exc
    async def artifact(self,job_id,kind):
        from uuid import UUID
        if str(UUID(job_id))!=job_id or kind not in ('model','original'):raise ValueError('无效 Worker 产物 ID')
        async with self.client(timeout=120) as client:
            async with client.stream('GET',f'/jobs/{job_id}/artifacts/{kind}') as r:
                if not r.is_success:raise ValueError('Worker 产物未准备好')
                data=bytearray()
                async for chunk in r.aiter_bytes():
                    data.extend(chunk)
                    if len(data)>MAX_GLB_BYTES:raise ValueError('Worker 产物超过 50 MB')
                return bytes(data)

class Hunyuan3D21Adapter(Generative3DEngine):
    id='hunyuan3d-2.1'
    def __init__(self):self.worker=WorkerClient()
    def get_model_info(self):
        return {'id':self.id,'name':'Hunyuan3D 2.1','version':'2.1','kind':'local','is_mock':False,'inputs':['PNG','JPEG','WebP'],'outputs':['GLB'],'models':['hunyuan3d-dit-v2-1'],'texture_capability':'独立可选 Paint 步骤，需另行安装与诊断','license':{'name':'Tencent Hunyuan 3D 2.1 Community License','source':'https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/82920d643c0dc2f7bfd7255f45f62d386edfe60c/LICENSE','restrictions':['代码与权重并非本项目 MIT 许可证；存在地域、用途及商业规模条件','不随项目分发权重；使用前阅读官方条款']},'source':'https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1','source_revision':'82920d643c0dc2f7bfd7255f45f62d386edfe60c'}
    def get_requirements(self):return {'shape_vram_mb':10240,'texture_vram_mb':21504,'tested_python':'3.10','tested_torch':'2.5.1+cu124','gpu':'NVIDIA CUDA','cpu_fallback':False,'weights_downloaded_automatically':False}
    async def check_availability(self):
        try:
            report=await self.worker.json('POST','/diagnose')
            return {**report,'engine':self.id,'worker_connected':True}
        except ValueError as exc:return {'available':False,'engine':self.id,'worker_connected':False,'errors':[str(exc)],'torch_cuda_available':None,'weights_ready':None,'texture_ready':False,'gpus':[]}
    async def generate_from_image(self,payload):return await self.worker.json('POST','/jobs',{**payload,'engine':self.id})
    async def get_progress(self,job_id):return await self.worker.json('GET','/jobs/'+job_id)
    async def cancel(self,job_id):return await self.worker.json('POST',f'/jobs/{job_id}/cancel')
    async def cleanup(self,job_id):await self.worker.json('DELETE','/jobs/'+job_id)

class MockGenerative3DAdapter(Hunyuan3D21Adapter):
    id='mock'
    def get_model_info(self):return {'id':'mock','name':'Mock 测试几何（非 AI 推理）','version':'test-1','kind':'test','is_mock':True,'inputs':['PNG','JPEG','WebP'],'outputs':['GLB'],'models':['test-fixture'],'texture_capability':'无纹理，仅用于测试','license':{'name':'MIT test fixture','source':'local test code','restrictions':['不能作为真实 AI 结果展示']},'source':'local-test-only','source_revision':'test-1'}
    def get_requirements(self):return {'gpu':None,'cpu_fallback':True,'purpose':'仅自动化 / 显式测试模式'}
    async def check_availability(self):
        if os.getenv('AI3D_ENABLE_MOCK')!='1':return {'engine':'mock','available':False,'worker_connected':False,'errors':['Mock 默认关闭；仅通过 AI3D_ENABLE_MOCK=1 显式开启'],'texture_ready':False}
        try:
            report=await self.worker.json('GET','/health')
            return {'engine':'mock','worker_connected':True,'available':report.get('mock_enabled',False),'errors':[] if report.get('mock_enabled') else ['Worker 未开启 Mock 测试模式'],'texture_ready':False}
        except ValueError as exc:return {'engine':'mock','available':False,'worker_connected':False,'errors':[str(exc)],'texture_ready':False}

class FutureGenerative3DAdapter(Generative3DEngine):
    def get_model_info(self):return {'id':'future','name':'未实现的扩展点','available':False}
    def get_requirements(self):return {}
    async def check_availability(self):return {'available':False,'errors':['尚未实现']}
    async def generate_from_image(self,payload):raise NotImplementedError('未实现专业引擎')
    async def get_progress(self,job_id):raise NotImplementedError()
    async def cancel(self,job_id):raise NotImplementedError()
    async def cleanup(self,job_id):raise NotImplementedError()

from .meshy import MeshyAdapter
ENGINES={'hunyuan3d-2.1':Hunyuan3D21Adapter(),'mock':MockGenerative3DAdapter(),'meshy':MeshyAdapter()}
