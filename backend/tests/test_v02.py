import asyncio,json
import httpx,pytest
from pydantic import ValidationError
from app.ollama import OllamaConfig
from app.providers import OllamaProvider,RuleBasedProvider
from app.schema import Scene,SceneObject,Parameters,Facades,Opening
from app.spatial import solve_relations,extents

@pytest.mark.parametrize('url',['https://127.0.0.1:11434','http://evil.example:11434','http://192.168.1.2:11434','http://localhost:11434/api','http://user:pass@localhost:11434'])
def test_ollama_local_only(url):
    with pytest.raises(ValidationError):OllamaConfig(url=url)

def test_cloud_model_rejected():
    with pytest.raises(ValidationError):OllamaConfig(model='qwen3:cloud')

def test_independent_colors_and_relations():
    result=asyncio.run(RuleBasedProvider().parse('创建一张桌子，在桌子左边放一把红色椅子，右边放一个蓝色柜子。'))
    objects=[SceneObject.model_validate(o) for o in result['scene']['objects']];table,chair,cabinet=objects;mapping={o.id:o for o in objects}
    assert len(objects)==3 and chair.parameters.color=='#e34b4b' and cabinet.parameters.color=='#3985ed'
    assert table.parameters.color not in (chair.parameters.color,cabinet.parameters.color)
    assert extents(chair,mapping)[1][0]<extents(table,mapping)[0][0]
    assert extents(cabinet,mapping)[0][0]>extents(table,mapping)[1][0]

def test_relation_cycle():
    a=SceneObject(id='a',type='cube',relation='left_of',reference_object_id='b');b=SceneObject(id='b',type='cube',relation='right_of',reference_object_id='a')
    with pytest.raises(ValueError,match='循环'):solve_relations(Scene(objects=[a,b]))

def test_opening_validation():
    Parameters(facades=Facades(left=[Opening(x=1,floor=1)]))
    with pytest.raises(ValidationError,match='越过'):Parameters(facades=Facades(left=[Opening(x=20)]))
    with pytest.raises(ValidationError,match='重叠'):Parameters(facades=Facades(left=[Opening(),Opening(x=.5)]))
    old=Scene.model_validate({'version':'0.9','units':'m','objects':[{'id':'h','type':'house'}]})
    assert old.objects[0].parameters.facades is None and old.objects[0].locked is False

@pytest.mark.parametrize('mode',['valid','invalid','missing','timeout'])
def test_ollama_mock(monkeypatch,mode):
    original=httpx.AsyncClient
    def respond(request):
        if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'qwen3:8b'}] if mode!='missing' else []})
        if mode=='timeout':raise httpx.ReadTimeout('timeout')
        value={'objects':[{'id':'a','type':'cube','parameters':{'color':'#ff0000'}}]} if mode=='valid' else {'objects':[{'id':'a','type':'run_python','code':'delete everything'}]}
        return httpx.Response(200,json={'message':{'content':json.dumps(value)}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    if mode=='valid':assert asyncio.run(OllamaProvider().parse('cube'))['scene']['objects'][0]['type']=='cube'
    elif mode=='missing':
        with pytest.raises(ValueError,match='未安装'):asyncio.run(OllamaProvider().parse('cube'))
    elif mode=='invalid':
        with pytest.raises(ValueError,match='JSON 无效'):asyncio.run(OllamaProvider().parse('cube'))
    else:
        with pytest.raises(httpx.ReadTimeout):asyncio.run(OllamaProvider().parse('cube'))

def test_running_process_tree_cancel(tmp_path):
    import subprocess,sys,time,threading,uuid
    from app import job_runtime
    job_id=str(uuid.uuid4());finished=[]
    child=tmp_path/'child.py';marker=tmp_path/'should-not-exist'
    child.write_text('import time\nfrom pathlib import Path\ntime.sleep(2)\nPath('+repr(str(marker))+').write_text("alive")\n',encoding='utf-8')
    parent=tmp_path/'parent.py';parent.write_text('import subprocess,sys,time\nsubprocess.Popen([sys.executable,'+repr(str(child))+'])\ntime.sleep(60)\n',encoding='utf-8')
    def worker():
        try:
            with (tmp_path/'worker.log').open('w') as log:job_runtime.run_worker(job_id,[sys.executable,str(parent)],log,tmp_path)
        except job_runtime.Cancelled:finished.append('cancelled')
    thread=threading.Thread(target=worker);thread.start()
    deadline=time.monotonic()+5
    while job_id not in job_runtime.PROCESSES and time.monotonic()<deadline:time.sleep(.01)
    assert job_id in job_runtime.PROCESSES
    time.sleep(.3);job_runtime.cancel(job_id);thread.join(timeout=10)
    assert not thread.is_alive() and finished==['cancelled']
    time.sleep(2.1);assert not marker.exists()
    job_runtime.CANCELLED.discard(job_id)

@pytest.mark.integration
def test_four_facades_and_moved_left_window(tmp_path):
    import struct,subprocess
    from app import main
    executable=main.blender_path()
    if not executable:pytest.skip('Blender executable not installed')
    p=Parameters(facades=Facades(**{s:[Opening(floor=1)] for s in ('front','back','left','right')}),roof_type='hip')
    value=Scene(objects=[SceneObject(id='house',type='house',parameters=p)])
    offsets=[]
    for x in (0,.8):
        value.objects[0].parameters.facades.left[0].x=x
        source=tmp_path/'model.json';output=tmp_path/'model.glb';source.write_text(value.model_dump_json(),encoding='utf-8')
        subprocess.run([executable,'--background','--factory-startup','--python',str(main.ROOT/'blender/generate.py'),'--',str(source),str(output)],timeout=120,check=True,capture_output=True)
        data=output.read_bytes();length=struct.unpack_from('<I',data,12)[0];gltf=json.loads(data[20:20+length])
        for side in ('front','back','left','right'):assert any(n.get('name')==side+' window glass' for n in gltf['nodes'])
        node=next(n for n in gltf['nodes'] if n.get('name')=='left window glass');accessor=gltf['meshes'][node['mesh']]['primitives'][0]['attributes']['POSITION'];offsets.append(gltf['accessors'][accessor]['min'][0])
    assert offsets[1]-offsets[0]==pytest.approx(.8,abs=.0001)

@pytest.mark.live
def test_live_ollama_three_objects():
    import os
    if os.getenv('STUDIO_LIVE_OLLAMA')!='1':pytest.skip('Set STUDIO_LIVE_OLLAMA=1 to run actual local inference')
    config=OllamaConfig(model=os.getenv('STUDIO_LIVE_MODEL','qwen3-coder:30b'),timeout=180,num_ctx=4096)
    result=asyncio.run(OllamaProvider().parse('创建一张桌子，在桌子左边放一把红色椅子，右边放一个蓝色柜子。请分别使用 table、chair、cabinet 类型。椅子 relation 为 left_of，柜子 relation 为 right_of，两者 reference_object_id 均指向桌子。',config))
    objects=result['scene']['objects'];assert len(objects)==3
    table=next(o for o in objects if o['type']=='table');chair=next(o for o in objects if o['type']=='chair');cabinet=next(o for o in objects if o['type']=='cabinet')
    assert chair['parameters']['color']=='#e34b4b' and cabinet['parameters']['color']=='#3985ed'
    assert chair['position'][0]<table['position'][0]<cabinet['position'][0]
