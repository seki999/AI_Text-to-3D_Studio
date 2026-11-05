from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
import math

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Opening(Strict):
    kind: Literal['window','door'] = 'window'
    floor: int = Field(0,ge=0,le=2)
    x: float = Field(0,ge=-50,le=50)
    sill: float = Field(.9,ge=0,le=5)
    width: float = Field(1.2,gt=.15,le=5)
    height: float = Field(1.2,gt=.15,le=4)

class Facades(Strict):
    front: list[Opening] = Field(default_factory=list,max_length=24)
    back: list[Opening] = Field(default_factory=list,max_length=24)
    left: list[Opening] = Field(default_factory=list,max_length=24)
    right: list[Opening] = Field(default_factory=list,max_length=24)

class PBR(Strict):
    baseColor: str = Field('#dc7355',pattern=r'^#[0-9a-fA-F]{6}$')
    metalness: float = Field(0,ge=0,le=1)
    roughness: float = Field(.6,ge=0,le=1)
    opacity: float = Field(1,ge=0,le=1)
    transparent: bool = False
    doubleSided: bool = False
    emissive: str = Field('#000000',pattern=r'^#[0-9a-fA-F]{6}$')

class Parameters(Strict):
    facades: Facades | None = None
    balcony_facade: Literal['front','back','left','right'] = 'front'
    balcony_offset: float = Field(0,ge=-50,le=50)
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

    @model_validator(mode='after')
    def openings(self):
        if self.facades:
            for side in ('front','back','left','right'):
                span=self.width if side in ('front','back') else self.depth
                items=getattr(self.facades,side)
                for i,o in enumerate(items):
                    if o.floor>=self.floors or abs(o.x)+o.width/2+.06>span/2 or o.sill+o.height+.06>self.floor_height:
                        raise ValueError(f'{side} 第 {i+1} 个开口越过墙面、楼层或屋顶边界')
                    for b in items[:i]:
                        if o.floor==b.floor and abs(o.x-b.x)<(o.width+b.width)/2+.12 and o.sill<b.sill+b.height+.12 and b.sill<o.sill+o.height+.12:
                            raise ValueError(f'{side} 开口与边框重叠')
        span=self.width if self.balcony_facade in ('front','back') else self.depth
        if self.balcony and abs(self.balcony_offset)+min(3,span*.7)/2>span/2: raise ValueError('阳台超出墙面范围')
        return self

class SceneObject(Strict):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    name: str = Field('Object', max_length=100)
    type: Literal['house','cube','sphere','cylinder','cone','plane','torus','table','chair','cabinet','bookshelf','bed','imported']
    parent: str | None = None
    position: tuple[float,float,float] = (0,0,0)
    rotation: tuple[float,float,float] = (0,0,0)
    scale: tuple[float,float,float] = (1,1,1)
    visible: bool = True
    locked: bool = False
    source_id: str | None = Field(None,pattern=r'^[A-Za-z0-9_-]{1,64}$')
    material: PBR | None = None
    anchor: Literal['center','bottom'] = 'bottom'
    relation: Literal['left_of','right_of','in_front_of','behind','above','below','next_to'] | None = None
    reference_object_id: str | None = None
    spacing: float = Field(.4,ge=0,le=50)
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
            if obj.reference_object_id and obj.reference_object_id not in objects: raise ValueError('空间关系引用对象不存在')
            seen = {obj.id}; parent = obj.parent
            while parent:
                if parent not in objects or parent in seen: raise ValueError('父对象不存在或层级循环')
                seen.add(parent); parent = objects[parent].parent
        return self
