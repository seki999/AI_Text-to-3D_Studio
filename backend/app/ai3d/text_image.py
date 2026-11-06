"""Reference-image provider, separate from neural Image-to-3D."""
import base64,os
from urllib.parse import urlsplit
import httpx
from .images import decode_image

def provider_info():
    configured=bool(os.getenv('TEXT_IMAGE_BASE_URL') and os.getenv('TEXT_IMAGE_MODEL'))
    return {'id':'openai-compatible-image','configured':configured,'model':os.getenv('TEXT_IMAGE_MODEL') or None,'remote':configured,'message':'此服务会接收用户主动提交的描述；不自动上传参考图片' if configured else '未配置 Text-to-Image Provider，请上传参考图或在服务端配置兼容服务'}

class OpenAICompatibleImageProvider:
    async def generate(self,prompt):
        if not provider_info()['configured']:raise ValueError(provider_info()['message'])
        url=os.environ['TEXT_IMAGE_BASE_URL'].rstrip('/');parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('Text-to-Image 服务端配置地址无效')
        key=os.getenv('TEXT_IMAGE_API_KEY','')
        async with httpx.AsyncClient(timeout=120,follow_redirects=False) as client:
            try:
                response=await client.post(url+'/images/generations',headers={'Authorization':'Bearer '+key},json={'model':os.environ['TEXT_IMAGE_MODEL'],'prompt':prompt,'n':1,'size':'1024x1024','response_format':'b64_json'})
                response.raise_for_status();data=response.json()['data'][0].get('b64_json')
                if not data:raise ValueError('服务未返回 b64_json；为防止任意 URL 请求，不自动抓取服务返回的 URL')
                return decode_image(data)
            except (httpx.HTTPError,KeyError,IndexError,TypeError) as exc:raise ValueError('参考图服务请求失败，请检查服务配置；不会回退或伪造参考图') from exc
