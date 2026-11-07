"""Packaged sidecar: prebind a dynamic loopback port and serve compiled React assets."""
import asyncio,json,os,socket,sys,threading,time
from pathlib import Path

def run():
    if '--probe' in sys.argv:
        from ai_worker.probe import diagnose
        print(json.dumps(diagnose(),ensure_ascii=False));return
    if '--runner' in sys.argv:
        from ai_worker.runner import run as inference
        inference(Path(sys.argv[sys.argv.index('--runner')+1]));return
    import uvicorn
    worker='--worker' in sys.argv
    if not worker and len(os.getenv('FORMA_SESSION_TOKEN',''))<32:raise RuntimeError('Desktop session token missing')
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    port=sock.getsockname()[1]
    os.environ['FORMA_ORIGIN']=f'http://127.0.0.1:{port}'
    if worker:
        from ai_worker.service import app
    else:
        from backend.app.main import app
        from fastapi.staticfiles import StaticFiles
        web=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'web'
        if not web.is_dir():raise RuntimeError('Compiled web assets missing; development server is not a desktop release')
        app.mount('/',StaticFiles(directory=web,html=True),name='studio')
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False))
    app.state.desktop_server=server
    parent=int(os.getenv('FORMA_PARENT_PID','0'))
    def monitor():
        import psutil
        initial=psutil.Process(parent).create_time() if parent else None
        while not server.should_exit:
            if server.started:
                print(json.dumps({'ready':True,'port':port,'pid':os.getpid(),'worker':worker}),flush=True);break
            time.sleep(.05)
        while parent and not server.should_exit:
            try:
                if psutil.Process(parent).create_time()!=initial:break
            except psutil.Error:break
            time.sleep(.5)
        if parent:server.should_exit=True
    threading.Thread(target=monitor,daemon=True).start()
    server.run(sockets=[sock])

if __name__=='__main__':run()
