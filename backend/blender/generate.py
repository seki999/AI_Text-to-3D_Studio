"""Trusted Blender worker. Exchange coordinates: Y-up, meters, XYZ degrees."""
import bpy, sys, json, math
from mathutils import Matrix, Euler
from pathlib import Path

MATERIALS={}
def material(color):
    if color in MATERIALS: return MATERIALS[color]
    rgb=tuple(int(color[i:i+2],16)/255 for i in (1,3,5))
    mat=bpy.data.materials.new(color); mat.diffuse_color=(*rgb,1)
    mat.use_nodes=True
    mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*rgb,1)
    mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.6
    MATERIALS[color]=mat
    return mat

def mesh(name,vertices,faces,color,parent):
    data=bpy.data.meshes.new(name); data.from_pydata(vertices,[],faces); data.update()
    obj=bpy.data.objects.new(name,data); bpy.context.collection.objects.link(obj)
    obj.parent=parent; obj.data.materials.append(material(color))
    # Consistent outward normals for every connected shell.
    import bmesh
    bm=bmesh.new(); bm.from_mesh(data); bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(data); bm.free()
    return obj

def box(name,position,size,color,parent):
    x,y,z=position; a,b,c=(s/2 for s in size)
    vertices=[(x+dx*a,y+dy*b,z+dz*c) for dx,dy,dz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    return mesh(name,vertices,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],color,parent)

def frame(name,x,z,w,h,y,parent,door=False):
    color='#634e40' if door else '#bbc6cb'
    box(name+' glass',(x,y,z),(w,.07,h),'#426779',parent)
    for dx in [-w/2,w/2]: box(name+' jamb',(x+dx,y-.03,z),(.07,.15,h+.1),color,parent)
    for dz in [-h/2,h/2]: box(name+' lintel',(x,y-.03,z+dz),(w+.08,.15,.07),color,parent)
    if not door: box(name+' mullion',(x,y-.06,z),(.045,.12,h),color,parent)

def house(p,parent):
    w,d=p['width'],p['depth']; fh=p['floor_height']; h=fh*p['floors']; t=.18
    wall=p['wall_color']; roof=p['roof_color']
    box('foundation',(0,0,.1),(w+.3,d+.3,.2),'#8d9296',parent)
    box('back wall',(0,d/2,h/2),(w,t,h),wall,parent)
    for x in [-w/2,w/2]: box('side wall',(x,0,h/2),(t,d,h),wall,parent)
    # Front facade is tiled around openings, producing genuine window/door holes.
    openings=[]
    per_floor=[p['windows']//p['floors']+(1 if f<p['windows']%p['floors'] else 0) for f in range(p['floors'])]
    for f,n in enumerate(per_floor):
        door_count=p['doors'] if f==0 else 0
        slots=n+door_count
        ww=min(1.2,w/max(slots,1)*.55)
        for i in range(n):
            x=-w/2+w*(i+door_count+1)/(slots+1); z=f*fh+fh*.58
            openings.append((x-ww/2,x+ww/2,z-.6,z+.6,'window'))
    for i in range(p['doors']):
        slots=per_floor[0]+p['doors']
        dw=min(.95,w/(slots+1)*.55); x=-w/2+w*(i+1)/(slots+1)
        openings.append((x-dw/2,x+dw/2,.2,min(2.25,fh-.1),'door'))
    xs=sorted(set([-w/2,w/2]+[v for a in openings for v in a[:2]])); zs=sorted(set([0,h]+[v for a in openings for v in a[2:4]]))
    for a,b in zip(xs,xs[1:]):
        for c,e in zip(zs,zs[1:]):
            if not any(o[0]<(a+b)/2<o[1] and o[2]<(c+e)/2<o[3] for o in openings): box('front wall',((a+b)/2,-d/2,(c+e)/2),(b-a,t,e-c),wall,parent)
    for a,b,c,e,kind in openings: frame(kind,(a+b)/2,(c+e)/2,b-a,e-c,-d/2,parent,kind=='door')
    for f in range(p['floors']): box('floor',(0,0,f*fh+.2),(w,d,.15),'#ac9f8b',parent)
    rw,rd=w/2+.35,d/2+.35; rise=rw*math.tan(math.radians(p['roof_angle']))
    if p['roof_type']=='flat': box('flat roof',(0,0,h+.12),(w+.6,d+.6,.24),roof,parent)
    else:
        if p['roof_type']=='gable':
            vertices=[(-rw,-rd,h),(rw,-rd,h),(rw,rd,h),(-rw,rd,h),(0,-rd,h+rise),(0,rd,h+rise)]
            faces=[(0,3,2,1),(0,1,4),(3,5,2),(0,4,5,3),(1,2,5,4)]
        elif p['roof_type']=='shed':
            vertices=[(-rw,-rd,h),(rw,-rd,h),(rw,rd,h),(-rw,rd,h),(-rw,-rd,h+.15),(rw,-rd,h+rise),(rw,rd,h+rise),(-rw,rd,h+.15)]
            faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        else:
            vertices=[(-rw,-rd,h),(rw,-rd,h),(rw,rd,h),(-rw,rd,h),(0,0,h+rise)]
            faces=[(0,3,2,1),(0,1,4),(1,2,4),(2,3,4),(3,0,4)]
        mesh('roof',vertices,faces,roof,parent)
    if p['balcony'] and p['floors']>1:
        bw=min(3,w*.7); y=-d/2-.8; z=fh+.12
        box('balcony floor',(0,y,z),(bw,1.6,.2),'#b6b6ae',parent)
        box('front rail',(0,y-.75,z+1),(bw,.07,.07),'#454d57',parent)
        for i in range(13): box('baluster',(-bw/2+bw*i/12,y-.75,z+.5),(.045,.045,1),'#454d57',parent)
        for x in [-bw/2,bw/2]:
            box('side rail',(x,y,z+1),(.07,1.5,.07),'#454d57',parent)
            box('support',(x,y-.7,fh/2),(.12,.12,fh),'#a0a3a5',parent)
    if p['steps']:
        for i in range(3): box('step',(0,-d/2-.35-i*.3,.15-i*.04),(1.6,.6,.3-i*.08),'#999b9d',parent)
    if p['garage']:
        box('garage',(w/2+1.6,0,1.35),(3.2,d*.65,2.7),wall,parent)
        box('garage door',(w/2+1.6,-d*.325-.02,1.2),(2.7,.08,2.3),'#7f8790',parent)
    if p['yard']: box('yard',(0,0,-.09),(w+6,d+6,.1),'#6e8c64',parent)

def furniture(kind,p,parent):
    color=p['color']; w,d,h=p['width'],p['depth'],p['height']
    # Furniture defaults are scaled from useful proportions rather than building dimensions.
    w=min(w,3); d=min(d,2); h=min(h,2)
    def b(n,pos,size): return box(n,pos,size,color,parent)
    if kind in ('table','chair','bed'):
        top=.8 if kind=='table' else .45
        if kind=='bed': top=.35
        b('seat / top',(0,0,top),(w,d,.14))
        for x in [-w/2+.12,w/2-.12]:
            for y in [-d/2+.12,d/2-.12]: b('leg',(x,y,top/2),(.12,.12,top))
        if kind=='chair': b('backrest',(0,d/2-.06,.95),(w,.12,1))
        if kind=='bed':
            box('mattress',(0,0,.57),(w*.96,d*.96,.3),'#e7e1d2',parent)
            b('headboard',(0,d/2,.7),(w,.12,1.1))
    else:
        for x in [-w/2,w/2]: b('side',(x,0,h/2),(.12,d,h))
        b('back',(0,d/2,h/2),(w,.1,h))
        for i in range(5): b('shelf',(0,0,h*i/4),(w,d,.1))
        if kind=='cabinet':
            for x in [-w/4,w/4]: b('door',(x,-d/2,h/2),(w/2-.03,.08,h-.1))

def primitive(kind,p,parent):
    if kind=='cube': return box('cube',(0,0,p['height']/2),(p['width'],p['depth'],p['height']),p['color'],parent)
    if kind=='plane': return mesh('plane',[(-p['width']/2,-p['depth']/2,0),(p['width']/2,-p['depth']/2,0),(p['width']/2,p['depth']/2,0),(-p['width']/2,p['depth']/2,0)],[(0,1,2,3)],p['color'],parent)
    if kind=='sphere': bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=16,radius=p['radius'],location=(0,0,p['radius']))
    if kind=='cylinder': bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=p['radius'],depth=p['height'],location=(0,0,p['height']/2))
    if kind=='cone': bpy.ops.mesh.primitive_cone_add(vertices=32,radius1=p['radius'],depth=p['height'],location=(0,0,p['height']/2))
    if kind=='torus': bpy.ops.mesh.primitive_torus_add(major_segments=32,minor_segments=12,major_radius=p['radius'],minor_radius=p['radius']*.25,location=(0,0,p['radius']*.25))
    obj=bpy.context.object; obj.parent=parent; obj.data.materials.append(material(p['color']))

def generate(scene,path):
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    parents={}
    # Y-up -> Blender Z-up: (x,y,z) -> (x,-z,y).
    conversion=Matrix.Rotation(math.pi/2,4,'X')
    for item in scene['objects']:
        root=bpy.data.objects.new(item['id'],None); bpy.context.collection.objects.link(root); parents[item['id']]=root
    for item in scene['objects']:
        parent=parents[item['id']]; p=item['parameters']
        if not item['visible']: continue
        if item['type']=='house': house(p,parent)
        elif item['type'] in ('table','chair','cabinet','bookshelf','bed'): furniture(item['type'],p,parent)
        else: primitive(item['type'],p,parent)
        rotation=Euler(tuple(math.radians(a) for a in item['rotation']),'XYZ').to_matrix().to_4x4()
        transform=Matrix.Translation(item['position']) @ rotation @ Matrix.Diagonal((*item['scale'],1))
        parent.matrix_local=conversion @ transform @ conversion.inverted()
        if item['parent']: parent.parent=parents[item['parent']]
    bpy.context.view_layer.update()
    bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',export_yup=True)
    bpy.ops.wm.obj_export(filepath=str(path.with_suffix('.obj')),forward_axis='NEGATIVE_Z',up_axis='Y')
    objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
    points=[o.matrix_world @ __import__('mathutils').Vector(v) for o in objects for v in o.bound_box]
    dimensions=[max(v[i] for v in points)-min(v[i] for v in points) for i in range(3)] if points else [0,0,0]
    stats={'meshes':len(objects),'vertices':sum(len(o.data.vertices) for o in objects),'triangles':sum(len(p.vertices)-2 for o in objects for p in o.data.polygons),'dimensions_blender_z_up':dimensions,'materials':len(MATERIALS)}
    path.with_name('stats.json').write_text(json.dumps(stats))

if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    generate(json.loads(Path(args[0]).read_text(encoding='utf-8')),Path(args[1]))
