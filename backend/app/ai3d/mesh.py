"""Static AI Mesh processing. No implicit manifold repair, remeshing or decimation."""
import base64,io,json,struct,warnings
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image

MAX_GLB_BYTES=50*1024*1024
MAX_TEXTURE_PIXELS=4096*4096
Image.MAX_IMAGE_PIXELS=32*1024*1024

def glb_document(data:bytes)->dict:
    if len(data)<28 or len(data)>MAX_GLB_BYTES or data[:4]!=b'glTF':raise ValueError('GLB 文件头或大小无效')
    version,total=struct.unpack_from('<II',data,4)
    if version!=2 or total!=len(data):raise ValueError('GLB 长度或版本不正确')
    length,kind=struct.unpack_from('<II',data,12)
    if kind!=0x4e4f534a or length>len(data)-20:raise ValueError('缺少有效 GLB JSON 块')
    try:doc=json.loads(data[20:20+length])
    except (ValueError,UnicodeError) as exc:raise ValueError('GLB JSON 损坏') from exc
    if not isinstance(doc,dict) or not isinstance(doc.get('meshes'),list) or not doc['meshes']:raise ValueError('GLB 不包含 Mesh')
    for key in ('images','buffers'):
        for item in doc.get(key,[]):
            if item.get('uri') and not item['uri'].startswith('data:'):raise ValueError('仅允许内嵌纹理和 buffer，拒绝外部路径或 URL')
    vertices=0;indices=0
    for mesh in doc['meshes']:
        for primitive in mesh.get('primitives',[]):
            if primitive.get('mode',4)!=4:raise ValueError('AI 产物必须是三角面 Mesh')
            try:
                accessor=doc['accessors'][primitive['attributes']['POSITION']]
                vertices+=accessor['count']
                indices+=doc['accessors'][primitive['indices']]['count'] if 'indices' in primitive else accessor['count']
            except (KeyError,IndexError,TypeError) as exc:raise ValueError('Mesh POSITION / 索引无效') from exc
    if vertices<=0 or vertices>2_000_000 or indices>9_000_000:raise ValueError('Mesh 为空或超过顶点 / 三角面限制')
    for view in doc.get('bufferViews',[]):
        if view.get('byteLength',0)<0 or view.get('byteOffset',0)<0 or view.get('byteLength',0)+view.get('byteOffset',0)>len(data):raise ValueError('BufferView 越界')
    return doc

def inspect_scene(scene:trimesh.Scene,doc:dict)->dict:
    meshes=[g for g in scene.geometry.values() if isinstance(g,trimesh.Trimesh)]
    if not meshes or any(len(g.vertices)==0 or len(g.faces)==0 for g in meshes):raise ValueError('模型包含空 Mesh 或没有三角面')
    for g in meshes:
        if not np.isfinite(g.vertices).all():raise ValueError('模型包含 NaN / Infinity 坐标')
        if g.faces.min()<0 or g.faces.max()>=len(g.vertices):raise ValueError('Mesh 索引越界')
    bounds=np.asarray(scene.bounds)
    if bounds.shape!=(2,3) or not np.isfinite(bounds).all():raise ValueError('模型包围盒无效')
    if float(np.max(bounds[1]-bounds[0]))<=1e-9:raise ValueError('模型所有顶点重合')
    normals=all('NORMAL' in p.get('attributes',{}) for m in doc['meshes'] for p in m.get('primitives',[]))
    if normals and any(not np.isfinite(g.vertex_normals).all() for g in meshes):raise ValueError('法线包含非法坐标')
    flags={k:False for k in ('base_color','roughness','metallic','normal','alpha')}
    for mat in doc.get('materials',[]):
        pbr=mat.get('pbrMetallicRoughness',{})
        flags['base_color']|='baseColorTexture' in pbr
        flags['roughness']|='metallicRoughnessTexture' in pbr
        flags['metallic']|='metallicRoughnessTexture' in pbr
        flags['normal']|='normalTexture' in mat
        flags['alpha']|=mat.get('alphaMode','OPAQUE')!='OPAQUE' and 'baseColorTexture' in pbr
    return {'meshes':len(meshes),'vertices':sum(len(g.vertices) for g in meshes),'triangles':sum(len(g.faces) for g in meshes),'bounds':bounds.tolist(),'dimensions':(bounds[1]-bounds[0]).tolist(),'normals_present':normals,'watertight':all(g.is_watertight for g in meshes),'texture_support':flags,'texture_status':'包含实际贴图' if doc.get('textures') else '未生成纹理'}

def load_glb(data:bytes):
    doc=glb_document(data)
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        try:
            # Validate decoded texture size before handing images to trimesh. 4K Paint is allowed.
            json_length=struct.unpack_from('<I',data,12)[0];binary_start=20+json_length+8
            for image in doc.get('images',[]):
                if 'bufferView' in image:
                    index=image['bufferView']
                    if not isinstance(index,int) or index<0:raise ValueError('纹理 bufferView 无效')
                    view=doc['bufferViews'][index];start=binary_start+view.get('byteOffset',0);texture=data[start:start+view['byteLength']]
                elif image.get('uri','').startswith('data:'):texture=base64.b64decode(image['uri'].split(',',1)[1],validate=True)
                else:raise ValueError('纹理不是内嵌图片')
                with Image.open(io.BytesIO(texture)) as decoded:
                    if decoded.width*decoded.height>MAX_TEXTURE_PIXELS:raise ValueError('单张纹理超过 4096×4096 像素上限')
                    decoded.verify()
        except (OSError,IndexError,KeyError,TypeError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:raise ValueError('内嵌纹理损坏、不支持或像素过多') from exc
        if hasattr(trimesh,'load_scene'):scene=trimesh.load_scene(io.BytesIO(data),file_type='glb',process=False)
        else:scene=trimesh.load(io.BytesIO(data),file_type='glb',force='scene',process=False)
    return scene,doc

def process_glb(data:bytes,options:dict)->tuple[bytes,dict]:
    scene,doc=load_glb(data);before=inspect_scene(scene,doc);notes=[]
    if options.get('source_up','Y')=='Z':scene.apply_transform(trimesh.transformations.rotation_matrix(-np.pi/2,[1,0,0]))
    if options.get('center',True):scene.apply_translation(-np.mean(scene.bounds,axis=0))
    if options.get('normalize',True):scene.apply_scale(float(options.get('size',2))/float(np.max(scene.extents)))
    for key,g in list(scene.geometry.items()):
        if not isinstance(g,trimesh.Trimesh):continue
        if options.get('repair_normals',False):g.fix_normals(multibody=True);notes.append('按用户选择修复法线')
        target=options.get('simplify_faces')
        if target and len(g.faces)>target:
            if getattr(g.visual,'kind',None)=='texture':raise ValueError('带纹理模型暂不简化，避免破坏 UV / 材质')
            try:scene.geometry[key]=g.simplify_quadric_decimation(face_count=target)
            except ImportError as exc:raise ValueError('缺少此 trimesh 版本对应的可选简化后端（fast-simplification / open3d）；原始 Mesh 已保留') from exc
    # Export without manifold assumptions. UVs and PBR from trimesh's GLB loader are kept.
    output=scene.export(file_type='glb')
    check,check_doc=load_glb(output);after=inspect_scene(check,check_doc)
    if doc.get('textures') and not check_doc.get('textures'):raise ValueError('处理后纹理丢失，拒绝覆盖原始模型')
    return output,{'before':before,'after':after,'notes':notes,'units':'meters','up_axis':'Y','bytes':len(output),'raw_bytes':len(data)}
