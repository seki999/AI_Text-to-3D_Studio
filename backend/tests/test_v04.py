import base64,io,json,sqlite3,uuid,zipfile
import httpx,pytest
from fastapi.testclient import TestClient
from app import main,migrations
from app.ai3d import credentials
from app.ai3d.meshy import MeshyAdapter
from test_ai3d import client,glb

def snapshot(client):
    scene={'version':'1.0','name':'Local library fixture','objects':[{'id':'cube_0_0','type':'cube','parameters':{}}]}
    response=client.post('/api/models/snapshot',json={'scene':scene,'glb':base64.b64encode(glb()).decode()})
    assert response.status_code==201;return response.json()['id']

def test_library_independent_files_search_favorite_reference_protection(client):
    source=snapshot(client);result=client.post('/api/library',json={'model_id':source,'description':'Red reference fixture'})
    assert result.status_code==201;id=result.json()['id']
    assert (main.DATA/'library'/id/'original.glb').is_file()
    assert client.get('/api/library?q=reference').json()[0]['id']==id
    assert client.patch('/api/library/'+id,json={'favorite':True}).status_code==200
    assert len(client.get('/api/library?favorite=true').json())==1
    asset=client.get('/api/models/'+id).json()
    assert asset['scene']['objects'][0]['type']=='imported'
    assert asset['scene']['objects'][0]['asset']['asset_id']==id
    saved=client.post('/api/projects',json={'name':'Protect library','scene':asset['scene'],'model_id':id}).json()['id']
    assert client.delete('/api/library/'+id).status_code==409
    client.post('/api/storage/cleanup',json={'older_than_days':0})
    assert client.get('/api/models/'+id+'/download?format=glb').content.startswith(b'glTF')
    assert client.get('/api/library').json()[0]['protected']
    client.delete('/api/projects/'+saved)
    assert client.delete('/api/library/'+id).status_code==200
    assert not (main.DATA/'library'/id).exists()

def test_library_thumbnail_and_simplification_require_explicit_request(client):
    source=snapshot(client);id=client.post('/api/library',json={'model_id':source}).json()['id']
    assert client.get('/api/library/'+id+'/thumbnail').content.startswith(b'\x89PNG')
    assert client.put('/api/library/'+id+'/thumbnail',json={'data':base64.b64encode(b'bad').decode()}).status_code==422
    original=(main.DATA/'library'/id/'model.glb').read_bytes()
    assert client.post('/api/library/'+id+'/simplify',json={'confirmed':False}).status_code==422
    derived=client.post('/api/library/'+id+'/simplify',json={'confirmed':True,'target_faces':100})
    assert derived.status_code==201
    assert (main.DATA/'library'/id/'model.glb').read_bytes()==original
    assert (main.DATA/'library'/derived.json()['id']/'original.glb').read_bytes()==original

def test_migration_backup_and_newer_version_refusal(tmp_path):
    db=tmp_path/'studio.sqlite3'
    with sqlite3.connect(db) as c:c.execute('CREATE TABLE preserved(value TEXT)');c.execute("INSERT INTO preserved VALUES('keep')")
    migrations.prepare(db)
    with sqlite3.connect(tmp_path/'backups/studio-before-v4.sqlite3') as c:assert c.execute('SELECT value FROM preserved').fetchone()[0]=='keep'
    with sqlite3.connect(db) as c:c.execute('PRAGMA user_version=99')
    with pytest.raises(RuntimeError,match='禁止自动降级'):migrations.prepare(db)

def test_desktop_session_origin_csrf_and_native_boundary(client,monkeypatch):
    token='test-session-'+'a'*48
    monkeypatch.setenv('FORMA_SESSION_TOKEN',token);monkeypatch.setenv('FORMA_ORIGIN','http://testserver')
    assert client.get('/api/health').status_code==401
    client.cookies.set('forma_session',token)
    assert client.get('/api/health').status_code==200
    assert client.get('/api/projects',headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/projects',headers={'Sec-Fetch-Site':'same-site'}).status_code==401
    assert client.post('/api/storage/cleanup',json={'older_than_days':30}).status_code==403
    assert client.post('/api/storage/cleanup',json={'older_than_days':30},headers={'Origin':'http://testserver'}).status_code==200
    assert client.post('/api/desktop/meshy-key',json={'key':'test-not-real-meshy-key'},headers={'Origin':'http://testserver'}).status_code==403
    assert client.get('/api/health',headers={'Host':'attacker.example'}).status_code==403

def test_no_fee_or_no_key_acceptance_saves_skipped_report_no_network(client,monkeypatch):
    def missing():raise ValueError('missing')
    monkeypatch.setattr(credentials,'get_key',missing)
    response=client.post('/api/acceptance/meshy',json={'id':str(uuid.uuid4()),'authorize_paid_test':True})
    assert response.status_code==201 and response.json()['status']=='skipped'
    assert response.json()['remote_id'] is None
    monkeypatch.setattr(credentials,'get_key',lambda:'test-key-only')
    response=client.post('/api/acceptance/meshy',json={'id':str(uuid.uuid4()),'authorize_paid_test':False})
    assert response.json()['status']=='skipped'
    assert client.get('/api/acceptance').json()

def test_acceptance_contract_single_paid_create_and_real_mesh_validation(client,monkeypatch):
    calls=[];task=str(uuid.uuid4());monkeypatch.setattr(credentials,'get_key',lambda:'test-key-only')
    def handler(request):
        calls.append(request)
        if request.url.host=='assets.meshy.ai':return httpx.Response(200,content=glb())
        if request.url.path.endswith('/balance'):return httpx.Response(200,json={'balance':10})
        if request.method=='POST':
            body=json.loads(request.content);assert body['ai_model']=='meshy-6-lite' and body['mode']=='preview'
            return httpx.Response(202,json={'result':task})
        return httpx.Response(200,json={'status':'SUCCEEDED','progress':100,'model_urls':{'glb':'https://assets.meshy.ai/contract.glb'}})
    monkeypatch.setattr(MeshyAdapter,'client',lambda self,authenticated=True:httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    id=str(uuid.uuid4());body={'id':id,'authorize_paid_test':True}
    first=client.post('/api/acceptance/meshy',json=body).json()
    assert first['remote_id']=='text:'+task
    client.post('/api/acceptance/meshy',json=body)
    result=client.post('/api/acceptance/'+id+'/refresh').json()
    assert result['checks']['mesh'] and result['checks']['materials_inspected']
    assert not result['checks']['viewer_loaded']
    assert client.get('/api/models/'+id).json()['scene']['objects'][0]['asset']['model_version']=='meshy-6-lite'
    assert len([r for r in calls if r.method=='POST'])==1
    assert client.post('/api/acceptance/'+id+'/evidence',json={'viewer_loaded':True}).json()['checks']['viewer_loaded']

def test_privacy_export_and_explicit_delete(client):
    snapshot(client)
    response=client.get('/api/privacy/export')
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert 'studio.sqlite3' in archive.namelist()
        assert any(name.endswith('.glb') for name in archive.namelist())
        assert not any(name.endswith('.dpapi') for name in archive.namelist())
    assert client.post('/api/privacy/delete',json={'confirmation':'no'}).status_code==422
    assert client.post('/api/privacy/delete',json={'confirmation':'DELETE ALL LOCAL DATA'}).status_code==200
    assert client.get('/api/projects').json()==[]


def test_worker_progress_retries_windows_sharing_violation(tmp_path,monkeypatch):
    from pathlib import Path
    from ai_worker.runner import progress
    original=Path.replace;calls=[]
    def replace(path,target):
        calls.append(path)
        if len(calls)<3:raise PermissionError('Windows sharing violation')
        return original(path,target)
    monkeypatch.setattr(Path,'replace',replace)
    progress(tmp_path,'complete')
    assert len(calls)==3
    assert json.loads((tmp_path/'progress.json').read_text())['stage']=='complete'
