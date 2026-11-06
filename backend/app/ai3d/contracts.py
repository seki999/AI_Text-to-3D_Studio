from abc import ABC,abstractmethod
from typing import Literal
from pydantic import Field
from ..schema import Strict

class ProcessingOptions(Strict):
    center:bool=True
    normalize:bool=True
    size:float=Field(2,gt=.01,le=100)
    source_up:Literal['Y','Z']='Y'
    repair_normals:bool=False
    simplify_faces:int|None=Field(None,ge=100,le=500000)

class GenerationOptions(Strict):
    model:Literal['hunyuan3d-dit-v2-1']='hunyuan3d-dit-v2-1'
    seed:int=Field(0,ge=0,le=2147483647)
    steps:int=Field(30,ge=1,le=100)
    octree_resolution:int=Field(256,ge=64,le=512)
    guidance_scale:float=Field(5,ge=0,le=20)
    processing:ProcessingOptions=Field(default_factory=ProcessingOptions)

class ImageRequest(Strict):
    image_id:str
    engine:Literal['hunyuan3d-2.1','mock']='hunyuan3d-2.1'
    prompt:str=Field('',max_length=4000)
    options:GenerationOptions=Field(default_factory=GenerationOptions)
    mock_acknowledged:bool=False
    license_acknowledged:bool=False

class TextureRequest(Strict):
    source_job_id:str
    engine:Literal['hunyuan3d-2.1']='hunyuan3d-2.1'

class CloudRequest(Strict):
    engine:Literal['meshy']='meshy'
    mode:Literal['text','image']
    prompt:str=Field('',max_length=800)
    image_id:str|None=None
    textured:bool=True
    cloud_consent:bool=False
    license_acknowledged:bool=False
    processing:ProcessingOptions=Field(default_factory=ProcessingOptions)

class ImageUpload(Strict):
    data:str=Field(max_length=16*1024*1024)
    filename:str=Field('reference.png',max_length=200)

class TextImageRequest(Strict):
    prompt:str=Field(min_length=1,max_length=4000)

class Generative3DEngine(ABC):
    @abstractmethod
    def get_model_info(self)->dict:...
    @abstractmethod
    def get_requirements(self)->dict:...
    @abstractmethod
    async def check_availability(self)->dict:...
    @abstractmethod
    async def generate_from_image(self,payload:dict)->dict:...
    async def generate_from_text(self,prompt:str):
        raise ValueError('此引擎仅支持图片输入，请先生成并确认参考图')
    @abstractmethod
    async def get_progress(self,job_id:str)->dict:...
    @abstractmethod
    async def cancel(self,job_id:str)->dict:...
    @abstractmethod
    async def cleanup(self,job_id:str)->None:...
