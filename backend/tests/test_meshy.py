"""API Contract tests use httpx MockTransport. Fixtures are NEVER real AI output."""
import asyncio
import base64
import io
import json
import os
import struct
import time
import uuid
from pathlib import Path
import httpx
import pytest
import trimesh
from PIL import Image
from fastapi.testclient import TestClient
from app import main
from app.ai3d import credentials,routes
from app.ai3d.meshy import MeshyAdapter,RetryLater,task_ref

pytestmark=pytest.mark.api_contract
KEY='test-only-never-a-real-api-key'
PREVIEW='018a210d-8ba4-705c-b111-1f1776f7f578'
REFINE='018a210d-8ba4-705c-b111-1f1776f7f579'


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DATA',tmp_path);monkeypatch.setattr(main,'DB',tmp_path/'studio.sqlite3')
    with TestClient(main.app) as client:yield client


@pytest.fixture
def service(monkeypatch):
    fixture=trimesh.creation.icosphere(subdivisions=1).export(file_type='glb')
    state={'requests':[],'status':'SUCCEEDED','http_error':None,'artifact':fixture,'signed':'not-a-key-signed-download'}
    monkeypatch.setattr(credentials,'get_key',lambda:KEY)
    def handle(request):
        state['requests'].append(request)
        if request.url.host=='assets.meshy.ai':
            assert 'authorization' not in request.headers
            return httpx.Response(200,content=state['artifact'])
        assert request.url.host=='api.meshy.ai'
        assert request.headers['Authorization']=='Bearer '+KEY
        if state['http_error']:return httpx.Response(state['http_error'],json={'message':KEY+' must not leak'},headers={'Retry-After':'2'})
        if request.method=='POST':
            body=json.loads(request.content)
            return httpx.Response(202,json={'result':REFINE if body.get('mode')=='refine' else PREVIEW})
        if request.method=='DELETE':return httpx.Response(409)
        return httpx.Response(200,json={'status':state['status'],'progress':70,'task_error':{'message':KEY},
            'model_urls':{'glb':'https://assets.meshy.ai/output/model.glb?signature='+state['signed']}},headers={'Retry-After':'2'})
    transport=httpx.MockTransport(handle)
    monkeypatch.setattr(MeshyAdapter,'client',lambda self,authenticated=True:httpx.AsyncClient(transport=transport,headers={'Authorization':'Bearer '+credentials.get_key()} if authenticated else {}))
    return state


def create(client,**kwargs):
    return client.post('/api/ai3d/jobs/cloud',json={'mode':'text','prompt':'生成一条红色、有翅膀的幻想龙。','cloud_consent':True,'license_acknowledged':True,**kwargs})


def wait(client,id):
    end=time.monotonic()+12
    while time.monotonic()<end:
        result=client.get('/api/ai3d/jobs/'+id).json()
        if result['status'] not in ('pending','running'):return result
        time.sleep(.03)
    raise AssertionError('Contract task timeout')


def test_no_key_no_network_no_fabricated_model(client,monkeypatch):
    def missing():raise ValueError('尚未配置 Meshy API Key')
    monkeypatch.setattr(credentials,'get_key',missing)
    assert not client.get('/api/ai3d/engines/meshy/status').json()['available']
    assert create(client).status_code==503
    assert client.get('/api/ai3d/jobs').json()==[]


def test_explicit_consent_and_mode_validation(client,service):
    assert create(client,cloud_consent=False).status_code==422
    assert create(client,license_acknowledged=False).status_code==422
    assert create(client,prompt=' ').status_code==422
    assert create(client,prompt='x'*801).status_code==422
    assert create(client,mode='image',image_id=None).status_code==422
    assert not service['requests']


def test_text_preview_refine_glb_persistence_and_provenance(client,service):
    result=create(client);assert result.status_code==202
    finished=wait(client,result.json()['id']);assert finished['status']=='completed',finished
    posts=[json.loads(r.content) for r in service['requests'] if r.method=='POST']
    assert len(posts)==2 and posts[0]['mode']=='preview' and posts[1]['mode']=='refine'
    assert posts[1]['preview_task_id']==PREVIEW and posts[1]['texture_prompt']==posts[0]['prompt']
    assert posts[0]['ai_model']=='meshy-7.1' and posts[0]['target_formats']==['glb']
    assert finished['remote_id']=='refine:'+REFINE
    assert finished['metadata']['source_image'] is None
    assert finished['metadata']['generator']=='meshy' and finished['metadata']['provenance']['cloud_processing']
    assert client.get(finished['model_url']).content.startswith(b'glTF')
    assert client.get('/api/ai3d/jobs/'+finished['id']+'/original').content==service['artifact']
    asset=client.get('/api/models/'+finished['asset_id']).json()
    saved=client.post('/api/projects',json={'name':'Meshy contract fixture NOT real AI','scene':asset['scene'],'model_id':finished['asset_id']})
    assert saved.status_code==201
    serialized=json.dumps(finished)+json.dumps(asset)+client.get('/api/ai3d/jobs/'+finished['id']+'/log').text
    assert KEY not in serialized and service['signed'] not in serialized
    assert not [r for r in service['requests'] if r.method=='DELETE']


def test_image_upload_only_local_until_generate(client,service):
    stream=io.BytesIO();Image.new('RGB',(32,32),'red').save(stream,format='PNG')
    uploaded=client.post('/api/ai3d/images',json={'data':base64.b64encode(stream.getvalue()).decode()}).json()
    assert service['requests']==[]
    response=create(client,mode='image',image_id=uploaded['id'])
    result=wait(client,response.json()['id']);assert result['status']=='completed',result
    posts=[json.loads(r.content) for r in service['requests'] if r.method=='POST']
    assert len(posts)==1 and posts[0]['image_url'].startswith('data:image/png;base64,')
    assert posts[0]['should_texture'] and posts[0]['enable_pbr']
    assert result['metadata']['source_image']==uploaded['id']


def test_image_minimum_size(client,service):
    stream=io.BytesIO();Image.new('RGB',(16,16)).save(stream,format='PNG')
    image_id=client.post('/api/ai3d/images',json={'data':base64.b64encode(stream.getvalue()).decode()}).json()['id']
    assert create(client,mode='image',image_id=image_id).status_code==422
    assert not service['requests']


@pytest.mark.parametrize('status',[401,402,403,429,500])
def test_create_errors_no_retry_or_key_leak(client,service,status):
    service['http_error']=status
    result=wait(client,create(client,textured=False).json()['id'])
    assert result['status']=='failed' and str(status) in result['error']
    assert len(service['requests'])==1
    assert KEY not in json.dumps(result) and not result['asset_id']


def test_invalid_cloud_glb_never_replaced_with_fixture(client,service):
    service['artifact']=b'invalid glb'
    result=wait(client,create(client,textured=False).json()['id'])
    assert result['status']=='failed' and result['asset_id'] is None


def test_cloud_processing_preserves_binary_and_vendor_identifiers(service):
    from app.ai3d.cloud_mesh import process_cloud_glb
    from app.ai3d.mesh import glb_document
    data=service['artifact'];old_length=struct.unpack_from('<I',data,12)[0];doc=glb_document(data)
    doc['asset']['extras']={'AI_generated':True,'vendor':'contract fixture'}
    doc['extras']={'provider_identifier':'keep-this-marker'}
    encoded=json.dumps(doc).encode();encoded+=b' '*((-len(encoded))%4)
    original=b'glTF'+struct.pack('<II',2,20+len(encoded)+len(data[20+old_length:]))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+data[20+old_length:]
    result,stats=process_cloud_glb(original,{'center':True,'normalize':True,'size':2})
    new_doc=glb_document(result);new_length=struct.unpack_from('<I',result,12)[0]
    assert result[20+new_length:]==data[20+old_length:]
    assert new_doc['asset']==doc['asset'] and new_doc['extras']==doc['extras']
    assert max(stats['after']['dimensions'])==pytest.approx(2)
    assert stats['after']['triangles']==stats['before']['triangles']


def test_post_timeout_never_automatically_retries(service,monkeypatch):
    count=[]
    def handler(request):count.append(request);raise httpx.ReadTimeout('must not leak '+KEY,request=request)
    monkeypatch.setattr(MeshyAdapter,'client',lambda self,authenticated=True:httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError,match='可能已经计费') as error:asyncio.run(MeshyAdapter().generate_from_text('dragon'))
    assert KEY not in str(error.value) and len(count)==1


def test_download_redirect_does_not_forward_credentials_or_allow_private_host(service,monkeypatch):
    seen=[]
    def handler(request):
        seen.append(request);assert 'authorization' not in request.headers
        return httpx.Response(302,headers={'Location':'http://127.0.0.1/private'})
    monkeypatch.setattr(MeshyAdapter,'client',lambda self,authenticated=True:httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError,match='HTTPS CDN'):asyncio.run(MeshyAdapter().download('https://assets.meshy.ai/file'))
    assert len(seen)==1


def test_cloud_stop_running_then_resume_without_new_paid_post(client,service):
    service['status']='IN_PROGRESS'
    id=create(client,textured=False).json()['id'];deadline=time.monotonic()+5
    while not routes.row(id)['remote_id'] and time.monotonic()<deadline:time.sleep(.01)
    client.post('/api/ai3d/jobs/'+id+'/cancel');stopped=wait(client,id)
    assert stopped['status']=='cancelled' and '计费' in stopped['error']
    assert not [r for r in service['requests'] if r.method=='DELETE']
    service['status']='SUCCEEDED'
    assert client.post('/api/ai3d/jobs/'+id+'/resume').status_code==202
    assert wait(client,id)['status']=='completed'
    assert len([r for r in service['requests'] if r.method=='POST'])==1


def test_pending_delete_races_running_no_false_cancellation(service):
    service['status']='PENDING'
    result=asyncio.run(MeshyAdapter().cancel('text:'+PREVIEW))
    assert not result['remote_cancelled'] and '无法中止' in result['notice']


def test_refine_timeout_blocks_automatic_duplicate_paid_task(client,service,monkeypatch):
    async def ambiguous(self,ref,prompt):raise ValueError('通信中断，纹理可能已创建')
    monkeypatch.setattr(MeshyAdapter,'refine',ambiguous)
    id=create(client).json()['id'];assert wait(client,id)['status']=='failed'
    assert client.post('/api/ai3d/jobs/'+id+'/resume').status_code==409
    assert len([r for r in service['requests'] if r.method=='POST'])==1


def test_restart_does_not_cancel_or_recreate_paid_task(client,service):
    id=str(uuid.uuid4())
    with main.connection() as db:
        db.execute('INSERT INTO ai3d_jobs(id,engine,remote_id,status) VALUES(?,?,?,?)',(id,'meshy','text:'+PREVIEW,'running'))
    routes.initialize(main.connection);asyncio.run(routes.recover())
    result=client.get('/api/ai3d/jobs/'+id).json()
    assert result['status']=='failed' and '恢复' in result['error']
    assert not service['requests']


@pytest.mark.parametrize('url',['http://assets.meshy.ai/a','https://localhost/a','https://assets.meshy.ai.evil.test/a','https://assets.meshy.ai:444/a','https://user:password@assets.meshy.ai/a'])
def test_download_rejects_untrusted_urls(service,url):
    with pytest.raises(ValueError,match='HTTPS CDN'):asyncio.run(MeshyAdapter().download(url))
    assert not service['requests']


def test_rate_limit_query_is_retryable_and_task_error_body_not_leaked(service):
    service['http_error']=429
    with pytest.raises(RetryLater):asyncio.run(MeshyAdapter().get_progress('text:'+PREVIEW))
    service['http_error']=None;service['status']='FAILED'
    result=asyncio.run(MeshyAdapter().get_progress('text:'+PREVIEW))
    assert KEY not in json.dumps(result) and result['status']=='failed'


@pytest.mark.skipif(os.name!='nt',reason='Windows current-user DPAPI only')
def test_windows_dpapi_roundtrip_not_plaintext(tmp_path,monkeypatch):
    path=tmp_path/'meshy.dpapi';monkeypatch.setattr(credentials,'secret_path',lambda:path)
    credentials.save_key(KEY)
    assert KEY.encode() not in path.read_bytes()
    assert credentials.get_key()==KEY
    with pytest.raises(ValueError):credentials.save_key('bad\nkey')


@pytest.mark.real_api
def test_real_meshy_billable_request(client):
    if os.getenv('RUN_MESHY_REAL')!='1' or os.getenv('MESHY_ACCEPT_CHARGES')!='YES':
        pytest.skip('Real API request not authorized/configured: requires RUN_MESHY_REAL=1 and MESHY_ACCEPT_CHARGES=YES; may incur charges')
    try:credentials.get_key()
    except ValueError:pytest.skip('No secure local Meshy API Key; no real request sent')
    id=create(client).json()['id'];deadline=time.monotonic()+3600
    while time.monotonic()<deadline:
        result=client.get('/api/ai3d/jobs/'+id).json()
        if result['status'] not in ('pending','running'):break
        time.sleep(3)
    assert result['status']=='completed',result
    assert client.get(result['model_url']).content.startswith(b'glTF')
