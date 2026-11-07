"""Loopback desktop session boundary, independent from third-party API credentials."""
import hmac,os
from fastapi.responses import JSONResponse

def install(app):
    @app.middleware('http')
    async def protect(request,call_next):
        token=os.getenv('FORMA_SESSION_TOKEN','')
        origin=os.getenv('FORMA_ORIGIN','')
        supplied=request.headers.get('origin')
        allowed={origin} if token else {'http://localhost:5173','http://127.0.0.1:5173','http://127.0.0.1:5174','http://localhost:5174'}
        if supplied and supplied not in allowed:return JSONResponse({'detail':'Origin 不被允许'},403)
        if token:
            from urllib.parse import urlsplit
            if len(token)<32 or not origin or request.headers.get('host')!=urlsplit(origin).netloc:return JSONResponse({'detail':'本地会话地址无效'},403)
            bearer=request.headers.get('authorization','')
            native=hmac.compare_digest(bearer,'Bearer '+token)
            cookie=hmac.compare_digest(request.cookies.get('forma_session',''),token)
            if not native and (not cookie or request.headers.get('sec-fetch-site') in ('cross-site','same-site')):return JSONResponse({'detail':'需要桌面应用授权'},401)
            if not native and request.method not in ('GET','HEAD') and supplied!=origin:return JSONResponse({'detail':'CSRF 校验失败'},403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        if token:
            response.headers['Cache-Control']='no-store'
            response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        return response
