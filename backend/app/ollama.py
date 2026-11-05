import os,ipaddress
from urllib.parse import urlsplit
import httpx
from pydantic import Field,field_validator
from .schema import Strict

class OllamaConfig(Strict):
    url: str = Field(default_factory=lambda:os.getenv('OLLAMA_URL','http://localhost:11434'),max_length=200)
    model: str = Field(default_factory=lambda:os.getenv('OLLAMA_MODEL','qwen3:8b'),min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_.:/-]+$')
    timeout: float = Field(90,ge=5,le=300)
    temperature: float = Field(.1,ge=0,le=2)
    num_ctx: int = Field(8192,ge=1024,le=32768)

    @field_validator('model')
    @classmethod
    def no_cloud_model(cls,value):
        if 'cloud' in value.lower():raise ValueError('本地 Provider 不允许云端模型')
        return value

    @field_validator('url')
    @classmethod
    def local_only(cls,value):
        url=urlsplit(value)
        if url.scheme!='http' or url.username or url.password or url.path not in ('','/') or url.query or url.fragment:raise ValueError('Ollama 仅允许无认证信息的本机 HTTP 根地址')
        host=url.hostname
        try:valid=host=='localhost' or ipaddress.ip_address(host or '').is_loopback
        except ValueError:valid=False
        if not valid:raise ValueError('Ollama 地址必须为 localhost 或回环 IP，禁止云端地址')
        if not url.port or not 1<=url.port<=65535:raise ValueError('Ollama 地址必须带有效端口')
        # Normalize localhost to a literal loopback address, preventing DNS rebinding.
        return f'http://[{host}]:{url.port}' if ':' in (host or '') else f'http://{"127.0.0.1" if host=="localhost" else host}:{url.port}'

async def list_models(config:OllamaConfig):
    try:
        async with httpx.AsyncClient(timeout=min(config.timeout,10),trust_env=False,follow_redirects=False) as client:
            result=await client.get(config.url+'/api/tags');result.raise_for_status()
            return [m['name'] for m in result.json()['models'] if isinstance(m.get('name'),str) and not m.get('remote_host') and not m.get('remote_model') and 'cloud' not in m['name'].lower()]
    except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:raise ValueError('无法连接本机 Ollama：请启动服务并检查端口') from exc

async def check_models(config):
    models=await list_models(config)
    if config.model not in models and config.model+':latest' not in models:raise ValueError(f'模型 {config.model} 未安装，请先在本机执行 ollama pull {config.model}')
