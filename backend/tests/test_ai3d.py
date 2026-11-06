import asyncio,base64,io,json,os,struct,time,uuid
from pathlib import Path
import numpy as np
import pytest,trimesh,httpx
from PIL import Image
from fastapi.testclient import TestClient
from app import main
from app.ai3d import routes
from app.ai3d.adapters import WorkerClient,ENGINES,worker_url
from app.ai3d.images import decode_image
from app.ai3d.mesh import process_glb,load_glb,inspect_scene,glb_document
from app.ai3d.contracts import GenerationOptions
from app.ai3d.diagnostics import hardware_report

def png():
    out=io.BytesIO();Image.new('RGB',(32,32),'red').save(out,format='PNG');return out.getvalue()
def glb():return trimesh.creation.icosphere(subdivisions=1).export(file_type='glb')

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'test.sqlite3');monkeypatch.setattr(main,'DATA',tmp_path)
    with TestClient(main.app) as c:yield c

def wait(client,job_id):
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        result=client.get('/api/ai3d/jobs/'+job_id).json()
        if result['status'] in ('completed','failed','cancelled'):return result
        time.sleep(.03)
    raise AssertionError('AI background task did not finish')

@pytest.fixture
def fake_worker(monkeypatch):
    monkeypatch.setenv('AI3D_ENABLE_MOCK','1');states={};behavior={'running':False,'failure':False}
    async def request(self,method,path,body=None):
        if path=='/health':return {'mock_enabled':True}
        if path=='/diagnose':return {'available':False,'errors':['GPU unavailable'],'torch_cuda_available':False,'weights_ready':False,'texture_ready':False,'gpus':[]}
        if path=='/jobs' and method=='POST':
            job_id=str(uuid.uuid4());states[job_id]='running' if behavior['running'] else 'completed';return {'id':job_id}
        job_id=path.split('/')[2]
        if path.endswith('/cancel'):states[job_id]='cancelled';return {'status':'cancelled'}
        if path.endswith('/log'):return {'log':'mock integration log; not real inference'}
        if method=='DELETE':return {'cleaned':True}
        if behavior['failure']:return {'status':'failed','error':'mock injected failure'}
        return {'status':states[job_id],'stage':'Mock 测试','progress':None,'progress_kind':'stage','stats':{}}
    async def artifact(self,job_id,kind):return glb()
    monkeypatch.setattr(WorkerClient,'json',request);monkeypatch.setattr(WorkerClient,'artifact',artifact)
    return behavior

def upload(client):
    result=client.post('/api/ai3d/images',json={'filename':'../../not-used.exe','data':base64.b64encode(png()).decode()})
    assert result.status_code==201
    return result.json()['id']

def test_image_validation(client):
    image_id=upload(client);assert client.get('/api/ai3d/images/'+image_id).content[:8]==b'\x89PNG\r\n\x1a\n'
    for data in [b'',b'hello',b'\x89PNG\r\n\x1a\nscript',b'x'*(10*1024*1024+1)]:
        with pytest.raises(ValueError):decode_image(data)
    tiny=io.BytesIO();Image.new('RGB',(2,2)).save(tiny,format='PNG')
    with pytest.raises(ValueError):decode_image(tiny.getvalue())
    assert client.get('/api/ai3d/images/not-a-uuid').status_code==400

@pytest.mark.parametrize('format',['PNG','JPEG','WEBP'])
def test_supported_actual_image_formats(format):
    content=io.BytesIO();Image.new('RGB',(32,32),'blue').save(content,format=format)
    data,info=decode_image(content.getvalue());assert data.startswith(b'\x89PNG') and info['format']=='PNG'

def test_decoded_pixel_limit_without_allocating_giant_image(monkeypatch):
    import app.ai3d.images as images
    monkeypatch.setattr(images,'MAX_PIXELS',100)
    with pytest.raises(ValueError,match='像素'):decode_image(png())

def test_jpeg_exif_orientation_is_applied_before_stripping_metadata():
    image=Image.new('RGB',(32,16),'red');exif=Image.Exif();exif[274]=6;content=io.BytesIO();image.save(content,format='JPEG',exif=exif)
    data,info=decode_image(content.getvalue());assert (info['width'],info['height'])==(16,32)

def test_mesh_validation_normalization_and_original_unchanged():
    data=glb();backup=bytes(data);output,stats=process_glb(data,GenerationOptions().processing.model_dump())
    assert data==backup and stats['after']['vertices']>0 and stats['after']['triangles']>0
    assert max(stats['after']['dimensions'])==pytest.approx(2)
    assert np.mean(stats['after']['bounds'],axis=0).tolist()==pytest.approx([0,0,0])
    assert stats['after']['texture_status']=='未生成纹理'
    for bad in (b'garbage',data[:-8],data[:12]+struct.pack('<II',99999999,0x4e4f534a)+data[20:]):
        with pytest.raises(ValueError):glb_document(bad)

def test_glb_nan_vertex_is_rejected_after_binary_decode():
    data=bytearray(glb());length=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+length]);a=doc['accessors'][doc['meshes'][0]['primitives'][0]['attributes']['POSITION']];view=doc['bufferViews'][a['bufferView']]
    offset=20+length+8+view.get('byteOffset',0)+a.get('byteOffset',0);struct.pack_into('<f',data,offset,float('nan'))
    with pytest.raises(ValueError,match='NaN|包围盒|坐标'):process_glb(bytes(data),GenerationOptions().processing.model_dump())

def test_textured_glb_keeps_actual_pbr_maps():
    mesh=trimesh.creation.box();material=trimesh.visual.material.PBRMaterial(baseColorTexture=Image.new('RGBA',(16,16),(255,0,0,150)),metallicRoughnessTexture=Image.new('RGB',(16,16),'gray'),normalTexture=Image.new('RGB',(16,16),(128,128,255)),alphaMode='BLEND')
    mesh.visual=trimesh.visual.TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),material=material)
    output,stats=process_glb(mesh.export(file_type='glb'),GenerationOptions().processing.model_dump())
    assert stats['after']['texture_support']=={'base_color':True,'roughness':True,'metallic':True,'normal':True,'alpha':True}

def test_hardware_unknown_is_not_fake_vram(tmp_path,monkeypatch):
    import app.ai3d.diagnostics as diag
    monkeypatch.setattr(diag.shutil,'which',lambda name:None);monkeypatch.setattr(diag.platform,'system',lambda:'Linux')
    result=hardware_report(tmp_path)
    assert result['gpus']==[] and result['torch_cuda_available'] is None and result['cuda_available'] is None
    assert result['ram_available_bytes']>0 and result['disk_free_bytes']>0

def test_nvidia_measurements_mock_does_not_invent_cuda(tmp_path,monkeypatch):
    import app.ai3d.diagnostics as diag
    from types import SimpleNamespace
    monkeypatch.setattr(diag.shutil,'which',lambda name:'nvidia-smi')
    monkeypatch.setattr(diag.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout='Mock NVIDIA, 24576, 19000, 550.0\n',returncode=0))
    result=hardware_report(tmp_path)
    assert result['gpus'][0]['vram_total_mb']==24576 and result['gpus'][0]['vram_available_mb']==19000
    assert result['torch_cuda_available'] is None

@pytest.mark.parametrize('url',['https://127.0.0.1:8010','http://evil.example:8010','http://127.0.0.1:8010/api','http://user@localhost:8010'])
def test_worker_address_restricted(monkeypatch,url):
    monkeypatch.setenv('AI3D_WORKER_URL',url)
    with pytest.raises(ValueError):worker_url()

def test_mock_api_completed_and_project_protects_source(client,fake_worker):
    image_id=upload(client)
    payload={'engine':'mock','image_id':image_id,'mock_acknowledged':True}
    denied=client.post('/api/ai3d/jobs',json={**payload,'mock_acknowledged':False});assert denied.status_code==422
    result=client.post('/api/ai3d/jobs',json=payload);assert result.status_code==202
    result=wait(client,result.json()['id']);assert result['status']=='completed' and result['is_mock'] is True
    assert result['progress'] is None and result['metadata']['provenance']['kind']=='mock'
    asset=client.get('/api/models/'+result['asset_id']).json();assert asset['scene']['objects'][0]['asset']['asset_id']==result['asset_id']
    assert client.get(result['model_url']).content[:4]==b'glTF'
    assert client.get('/api/ai3d/jobs/'+result['id']+'/original').status_code==200
    project=client.post('/api/projects',json={'name':'AI asset reference','scene':asset['scene']}).json()['id']
    client.post('/api/storage/cleanup',json={'older_than_days':0})
    assert client.get('/api/models/'+result['asset_id']).status_code==200
    assert client.get('/api/ai3d/images/'+image_id).status_code==200
    client.delete('/api/projects/'+project)
    client.post('/api/storage/cleanup',json={'older_than_days':0})
    assert client.get('/api/models/'+result['asset_id']).status_code==404
    assert client.get('/api/ai3d/images/'+image_id).status_code==404

def test_mock_cancel_and_failure_recovery(client,fake_worker):
    fake_worker['running']=True;image_id=upload(client)
    result=client.post('/api/ai3d/jobs',json={'engine':'mock','image_id':image_id,'mock_acknowledged':True}).json()
    deadline=time.monotonic()+3
    while not routes.row(result['id'])['remote_id'] and time.monotonic()<deadline:time.sleep(.02)
    assert client.post('/api/ai3d/jobs/'+result['id']+'/cancel').status_code==200
    assert wait(client,result['id'])['status']=='cancelled'
    fake_worker['running']=False;fake_worker['failure']=True
    second=client.post('/api/ai3d/jobs',json={'engine':'mock','image_id':image_id,'mock_acknowledged':True}).json()
    assert wait(client,second['id'])['status']=='failed'
    fake_worker['failure']=False
    third=client.post('/api/ai3d/jobs',json={'engine':'mock','image_id':image_id,'mock_acknowledged':True}).json()
    assert wait(client,third['id'])['status']=='completed'

def test_pending_queue_cancel_releases_slot_without_starting_worker(client,fake_worker):
    fake_worker['running']=True;image_id=upload(client)
    jobs=[client.post('/api/ai3d/jobs',json={'engine':'mock','image_id':image_id,'mock_acknowledged':True}).json()['id'] for _ in range(3)]
    deadline=time.monotonic()+3
    while (not routes.row(jobs[0])['remote_id'] or not routes.row(jobs[1])['remote_id']) and time.monotonic()<deadline:time.sleep(.02)
    assert routes.row(jobs[2])['remote_id'] is None
    result=client.post('/api/ai3d/jobs/'+jobs[2]+'/cancel')
    assert result.json()['status']=='cancelled' and routes.row(jobs[2])['remote_id'] is None
    for job_id in jobs[:2]:client.post('/api/ai3d/jobs/'+job_id+'/cancel');assert wait(client,job_id)['status']=='cancelled'

def test_no_gpu_and_unconfigured_text_image(client,fake_worker,monkeypatch):
    for key in ('TEXT_IMAGE_BASE_URL','TEXT_IMAGE_MODEL'):monkeypatch.delenv(key,raising=False)
    diagnostic=client.post('/api/ai3d/engines/hunyuan3d-2.1/diagnose').json()
    assert diagnostic['worker']['available'] is False and diagnostic['hardware']['torch_cuda_available'] is False
    assert client.post('/api/ai3d/jobs',json={'engine':'hunyuan3d-2.1','image_id':upload(client),'license_acknowledged':True}).status_code==503
    assert client.get('/api/health').json()['status']=='ok'
    assert client.post('/api/parse-text',json={'text':'红色立方体边长2米'}).status_code==200
    assert client.get('/api/ai3d/text-image/provider').json()['configured'] is False
    assert client.post('/api/ai3d/text-image',json={'prompt':'a red dragon'}).status_code==503

def test_text_image_provider_mock(client,monkeypatch):
    from app.ai3d.text_image import OpenAICompatibleImageProvider
    async def generate(self,prompt):return decode_image(png())
    monkeypatch.setattr(OpenAICompatibleImageProvider,'generate',generate)
    result=client.post('/api/ai3d/text-image',json={'prompt':'reference test'})
    assert result.status_code==201 and result.json()['provider']=='text-to-image'

@pytest.mark.parametrize('valid',[True,False])
def test_text_image_compatible_http_contract(monkeypatch,valid):
    from app.ai3d.text_image import OpenAICompatibleImageProvider
    monkeypatch.setenv('TEXT_IMAGE_BASE_URL','http://127.0.0.1:9999/v1');monkeypatch.setenv('TEXT_IMAGE_MODEL','configured-image-model')
    original=httpx.AsyncClient
    def respond(request):
        assert request.url.path=='/v1/images/generations';body=json.loads(request.content);assert body['prompt']=='test reference' and body['response_format']=='b64_json'
        return httpx.Response(200,json={'data':[{'b64_json':base64.b64encode(png()).decode()} if valid else {'url':'http://must-not-fetch.example/image.png'}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    if valid:assert asyncio.run(OpenAICompatibleImageProvider().generate('test reference'))[0][:4]==b'\x89PNG'
    else:
        with pytest.raises(ValueError,match='不自动抓取'):asyncio.run(OpenAICompatibleImageProvider().generate('test reference'))
