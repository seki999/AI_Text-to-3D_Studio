"""Preserve cloud GLB buffers/materials/vendor metadata; only add a root transform."""
import json
import struct
import numpy as np
import trimesh
from .mesh import load_glb,inspect_scene,MAX_GLB_BYTES


def process_cloud_glb(data,options):
    if options.get('repair_normals') or options.get('simplify_faces'):
        raise ValueError('云端模型仅支持保留原始几何的变换处理，不支持修复或减面')
    scene,doc=load_glb(data);before=inspect_scene(scene,doc)
    matrix=np.eye(4)
    if options.get('source_up','Y')=='Z':
        rotation=trimesh.transformations.rotation_matrix(-np.pi/2,[1,0,0]);scene.apply_transform(rotation);matrix=rotation@matrix
    if options.get('center',True):
        translation=trimesh.transformations.translation_matrix(-np.mean(scene.bounds,axis=0));scene.apply_transform(translation);matrix=translation@matrix
    if options.get('normalize',True):
        scale=float(options.get('size',2))/float(np.max(scene.extents));scaling=np.diag([scale,scale,scale,1]);matrix=scaling@matrix
    nodes=doc.setdefault('nodes',[])
    for item in doc.get('scenes',[]):
        roots=item.get('nodes',[])
        if roots:
            item['nodes']=[len(nodes)]
            nodes.append({'name':'StudioCloudNormalization','children':roots,'matrix':matrix.T.flatten().tolist()})
    serialized=json.dumps(doc,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    serialized+=b' '*((-len(serialized))%4)
    previous_length=struct.unpack_from('<I',data,12)[0];tail=data[20+previous_length:]
    output=b'glTF'+struct.pack('<II',2,20+len(serialized)+len(tail))+struct.pack('<II',len(serialized),0x4e4f534a)+serialized+tail
    if len(output)>MAX_GLB_BYTES:raise ValueError('处理后的云端 GLB 超过 50 MB')
    checked,checked_doc=load_glb(output);after=inspect_scene(checked,checked_doc)
    return output,{'before':before,'after':after,'notes':['保留原始 GLB buffer、材质、纹理与供应商元数据；仅添加根变换'],
                   'units':'meters','up_axis':'Y','bytes':len(output),'raw_bytes':len(data)}
