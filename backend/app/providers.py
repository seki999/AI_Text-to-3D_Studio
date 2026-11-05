import re, json, os
import httpx
from .schema import Scene, SceneObject, Parameters

TYPES = {'house':['住宅','房屋','house','戸建','家'], 'cube':['立方体','cube','キューブ'], 'sphere':['球体','sphere','球'], 'cylinder':['圆柱','cylinder','円柱'], 'cone':['圆锥','cone','円錐'], 'plane':['平面','plane'], 'torus':['圆环','torus'], 'table':['桌','table','テーブル'], 'chair':['椅','chair'], 'cabinet':['柜','cabinet'], 'bookshelf':['书架','bookshelf','本棚'], 'bed':['床','bed','ベッド']}
COLORS = {'红':'#e34b4b','red':'#e34b4b','赤':'#e34b4b','蓝':'#3985ed','blue':'#3985ed','青':'#3985ed','白':'#ffffff','white':'#ffffff','灰':'#666666','gray':'#666666','grey':'#666666','黒':'#222222','黑':'#222222','black':'#222222','绿':'#51aa73','green':'#51aa73'}
NUM = {'一':'1','二':'2','两':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9','十':'10'}

class RuleBasedProvider:
    async def parse(self, text: str) -> dict:
        source=text.lower()
        for word,value in {'one':'1','two':'2','three':'3','four':'4','five':'5'}.items(): source=re.sub(r'\b'+word+r'\b',value,source)
        if re.search(r'(?:宽|深|高|幅|半径|width|height|depth|radius|边长)\s*-\d',source): raise ValueError('尺寸必须为正数')
        for k,v in NUM.items(): source=source.replace(k,v)
        kinds=[k for k,words in TYPES.items() if any(w in source for w in words)]
        if not kinds: raise ValueError('未识别对象，请描述房屋、基础几何体或桌椅等家具')
        objects=[]
        for i,kind in enumerate(kinds):
            p=Parameters()
            fields={'width':r'(?:宽|幅|width)\s*(\d+(?:\.\d+)?)','depth':r'(?:深|长|奥行|depth|length)\s*(\d+(?:\.\d+)?)','height':r'(?:高度|高|height)\s*(\d+(?:\.\d+)?)','radius':r'(?:半径|radius)\s*(\d+(?:\.\d+)?)','floors':r'(\d+)\s*(?:层|階|floors?|stor(?:y|ies))','windows':r'(\d+)\s*(?:个)?\s*(?:正面)?(?:窗|windows?)','doors':r'(\d+)\s*(?:个)?\s*(?:入口|门|doors?)'}
            values=p.model_dump()
            if kind!='house':
                sizes={'table':(1.6,.9,.75),'chair':(.55,.55,1),'bed':(1.6,2,.8),'cabinet':(1.2,.5,1.8),'bookshelf':(1.2,.35,1.8)}
                width,depth,height=sizes.get(kind,(2,2,2))
                values.update(width=width,depth=depth,height=height)
            for field,pattern in fields.items():
                m=re.search(pattern,source)
                if m: values[field]=float(m[1]) if field not in ('floors','windows','doors') else int(m[1])
            edge=re.search(r'(?:边长|side)\s*(\d+(?:\.\d+)?)',source)
            if edge: values.update(width=float(edge[1]),depth=float(edge[1]),height=float(edge[1]))
            for word,color in COLORS.items():
                if word in source:
                    values['color']=color
                    if re.search(re.escape(word)+r'.{0,8}(?:墙|wall|外壁)',source): values['wall_color']=color
                    if re.search(re.escape(word)+r'.{0,8}(?:屋顶|roof|屋根)',source): values['roof_color']=color
            for key,words in {'balcony':['阳台','balcony','バルコニー'],'steps':['台阶','steps','階段'],'garage':['车库','garage'],'yard':['院子','yard']}.items(): values[key]=any(w in source for w in words)
            for roof,words in {'flat':['平屋顶','flat roof','陸屋根'],'shed':['单坡','shed roof'],'hip':['四坡','hip roof'],'gable':['双坡','gable','切妻']}.items():
                if any(w in source for w in words): values['roof_type']=roof
            count=1
            if kind!='house':
                for word in TYPES[kind]:
                    m=re.search(r'(\d+)\s*(?:个|张|把|つ)?\s*'+re.escape(word),source)
                    if m: count=int(m[1]); break
            if count>12: raise ValueError('每类对象最多 12 个')
            for j in range(count): objects.append(SceneObject(id=f'{kind}_{i}_{j}',name=kind,type=kind,position=(i*4+j*2.5,0,0),parameters=Parameters(**values)))
        return {'scene':Scene(name=text[:60],objects=objects).model_dump(),'warnings':['规则模式识别常见关键词；复杂材质、相对位置及未列出的描述可能未被提取，请检查参数。']}

class OpenAICompatibleProvider:
    async def parse(self,text):
        url=os.getenv('LLM_BASE_URL','https://api.openai.com/v1').rstrip('/')
        key=os.getenv('LLM_API_KEY','')
        async with httpx.AsyncClient(timeout=45) as client:
            response=await client.post(url+'/chat/completions',headers={'Authorization':f'Bearer {key}'},json={'model':os.getenv('LLM_MODEL','gpt-4.1-mini'),'messages':[{'role':'system','content':'Return only valid Scene JSON. Y-up, meters, degrees. Schema: '+json.dumps(Scene.model_json_schema())},{'role':'user','content':text}], 'response_format':{'type':'json_object'}})
            response.raise_for_status()
            scene=Scene.model_validate_json(response.json()['choices'][0]['message']['content'])
        return {'scene':scene.model_dump(),'warnings':[]}

class OllamaProvider(OpenAICompatibleProvider):
    async def parse(self,text):
        async with httpx.AsyncClient(timeout=90) as client:
            response=await client.post(os.getenv('OLLAMA_URL','http://localhost:11434')+'/api/chat',json={'model':os.getenv('OLLAMA_MODEL','qwen3:8b'),'stream':False,'format':Scene.model_json_schema(),'messages':[{'role':'user','content':text}]})
            response.raise_for_status()
            return {'scene':Scene.model_validate_json(response.json()['message']['content']).model_dump(),'warnings':[]}

class Future3DProvider:
    async def parse(self,text): raise ValueError('专业 3D 引擎接口尚未实现')

PROVIDERS={'rule':RuleBasedProvider(),'openai':OpenAICompatibleProvider(),'ollama':OllamaProvider()}
