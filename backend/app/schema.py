from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
import math

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Parameters(Strict):
    width: float = Field(8, gt=0, le=100)
    depth: float = Field(10, gt=0, le=100)
    height: float = Field(2, gt=0, le=100)
    radius: float = Field(1, gt=0, le=50)
    floors: int = Field(2, ge=1, le=3)
    floor_height: float = Field(3, ge=2, le=5)
    roof_type: Literal['flat','gable','shed','hip'] = 'gable'
    roof_angle: float = Field(30, ge=5, le=60)
    wall_color: str = Field('#ecebe4', pattern=r'^#[0-9a-fA-F]{6}$')
    roof_color: str = Field('#515967', pattern=r'^#[0-9a-fA-F]{6}$')
    color: str = Field('#dc7355', pattern=r'^#[0-9a-fA-F]{6}$')
    windows: int = Field(4, ge=0, le=24)
    doors: int = Field(1, ge=0, le=3)
    balcony: bool = False
    steps: bool = False
    garage: bool = False
    yard: bool = False
    style: Literal['modern','japanese'] = 'japanese'

class SceneObject(Strict):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    name: str = Field('Object', max_length=100)
    type: Literal['house','cube','sphere','cylinder','cone','plane','torus','table','chair','cabinet','bookshelf','bed']
    parent: str | None = None
    position: tuple[float,float,float] = (0,0,0)
    rotation: tuple[float,float,float] = (0,0,0)
    scale: tuple[float,float,float] = (1,1,1)
    visible: bool = True
    parameters: Parameters = Field(default_factory=Parameters)

    @model_validator(mode='after')
    def transforms(self):
        if self.type=='house' and (self.parameters.width<3 or self.parameters.depth<3):
            raise ValueError('房屋宽度和深度至少 3 米')
        if any(abs(x)>500 for x in self.position) or any(abs(x)>360 for x in self.rotation):
            raise ValueError('位置必须在 ±500 米内，旋转使用 ±360 度')
        if any(x<=0 or x>10 for x in self.scale): raise ValueError('缩放必须大于 0 且不超过 10')
        return self

class Environment(Strict):
    ground: bool = True
    background: str = Field('#181d27', pattern=r'^#[0-9a-fA-F]{6}$')

class Scene(Strict):
    version: Literal['1.0'] = '1.0'
    name: str = Field('Untitled', max_length=100)
    units: Literal['meters'] = 'meters'
    objects: list[SceneObject] = Field(max_length=50)
    environment: Environment = Field(default_factory=Environment)

    @model_validator(mode='before')
    @classmethod
    def migrate(cls,value):
        if isinstance(value,dict) and value.get('version')=='0.9':
            value={**value,'version':'1.0'}
            if value.get('units')=='m': value['units']='meters'
        return value

    @model_validator(mode='after')
    def hierarchy(self):
        objects = {o.id:o for o in self.objects}
        if len(objects)!=len(self.objects): raise ValueError('对象 ID 必须唯一')
        for obj in self.objects:
            seen = {obj.id}; parent = obj.parent
            while parent:
                if parent not in objects or parent in seen: raise ValueError('父对象不存在或层级循环')
                seen.add(parent); parent = objects[parent].parent
        return self
