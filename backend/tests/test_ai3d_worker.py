"""Real HTTP/process integration, explicitly Mock-only; no neural model downloads."""
import base64,json,os,socket,subprocess,sys,time,uuid
from pathlib import Path
import httpx,pytest
from app import job_runtime,main
from app.ai3d.mesh import load_glb,inspect_scene
from test_ai3d import png

@pytest.fixture
def worker(tmp_path):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    token=uuid.uuid4().hex;env={**os.environ,'AI3D_WORKER_TOKEN':token,'AI3D_ENABLE_MOCK':'1','AI3D_MOCK_DELAY':'1','AI3D_WORKER_DATA':str(tmp_path),'PYTHONUTF8':'1'}
    with (tmp_path/'server.log').open('w') as log:
        process=subprocess.Popen([sys.executable,'-m','uvicorn','ai_worker.service:app','--host','127.0.0.1','--port',str(port)],cwd=main.ROOT.parent,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt',creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW) if os.name=='nt' else 0)
        client=httpx.Client(base_url=f'http://127.0.0.1:{port}',headers={'X-Worker-Token':token},timeout=50)
        deadline=time.monotonic()+45
        while True:
            try:
                if client.get('/health').status_code==200:break
            except httpx.HTTPError:pass
            if time.monotonic()>deadline or process.poll() is not None:raise AssertionError((tmp_path/'server.log').read_text())
            time.sleep(.1)
        try:yield client,tmp_path
        finally:client.close();job_runtime.terminate_tree(process)

def await_state(client,job_id):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        result=client.get('/jobs/'+job_id).json()
        if result['status'] in ('completed','failed','cancelled'):return result
        time.sleep(.1)
    raise AssertionError('Mock worker timeout')

@pytest.mark.ai3d_integration
def test_worker_http_mesh_artifact_and_cleanup(worker):
    client,directory=worker
    assert client.get('/health',headers={'X-Worker-Token':'invalid'}).status_code==401
    response=client.post('/jobs',json={'engine':'mock','image_b64':base64.b64encode(png()).decode()})
    assert response.status_code==202
    job_id=response.json()['id'];result=await_state(client,job_id)
    assert result['status']=='completed' and result['progress'] is None
    assert 'Mock' in (directory/job_id/'runner.log').read_text(encoding='utf-8') or result['stats']['after']['vertices']>0
    data=client.get('/jobs/'+job_id+'/artifacts/model').content;scene,doc=load_glb(data)
    assert inspect_scene(scene,doc)['triangles']>0
    assert client.get('/jobs/'+job_id+'/artifacts/original').status_code==200
    assert client.delete('/jobs/'+job_id).status_code==200 and not (directory/job_id).exists()

@pytest.mark.ai3d_integration
def test_worker_actual_cancel_and_cpu_degrade(worker):
    client,directory=worker
    response=client.post('/jobs',json={'engine':'mock','image_b64':base64.b64encode(png()).decode()});job_id=response.json()['id']
    deadline=time.monotonic()+10
    while not (directory/job_id/'process.json').exists() and time.monotonic()<deadline:time.sleep(.05)
    assert (directory/job_id/'process.json').exists()
    queued=client.post('/jobs',json={'engine':'mock','image_b64':base64.b64encode(png()).decode()}).json()['id']
    assert client.post('/jobs/'+queued+'/cancel').json()['status']=='cancelled'
    assert not (directory/queued/'process.json').exists()
    assert client.post('/jobs/'+job_id+'/cancel').status_code==200
    assert await_state(client,job_id)['status']=='cancelled'
    assert not (directory/job_id/'model.glb').exists()
    diagnosis=client.post('/diagnose').json()
    assert isinstance(diagnosis['available'],bool)
    if diagnosis['torch_cuda_available'] is not True:assert not diagnosis['available']

@pytest.mark.real_ai
def test_real_hunyuan_image_to_shape(tmp_path):
    if os.getenv('RUN_HUNYUAN_REAL')!='1':pytest.skip('Real AI inference requires explicit RUN_HUNYUAN_REAL=1 and prepared CUDA worker')
    from app.ai3d.adapters import ENGINES
    import asyncio
    engine=ENGINES['hunyuan3d-2.1'];status=asyncio.run(engine.check_availability())
    if not status['available']:pytest.skip('Real AI unavailable: '+'; '.join(status.get('errors',[])))
    image=Path(os.environ['HUNYUAN_TEST_IMAGE']).read_bytes()
    result=asyncio.run(engine.generate_from_image({'image_b64':base64.b64encode(image).decode(),'options':{'steps':10,'octree_resolution':128},'operation':'shape'}));job_id=result['id']
    try:
        deadline=time.monotonic()+1800
        while time.monotonic()<deadline:
            state=asyncio.run(engine.get_progress(job_id))
            if state['status']=='failed':pytest.fail(state.get('error'))
            if state['status']=='completed':break
            time.sleep(1)
        else:pytest.fail('Real AI inference timeout')
        data=asyncio.run(engine.worker.artifact(job_id,'model'));scene,doc=load_glb(data)
        assert inspect_scene(scene,doc)['triangles']>0
        (tmp_path/'real-hunyuan.glb').write_bytes(data)
    finally:
        try:asyncio.run(engine.cancel(job_id))
        except ValueError:pass
