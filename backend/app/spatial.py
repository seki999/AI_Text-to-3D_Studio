"""Declarative AABB relations. Rotation, scale and parent transforms included."""
import math
from .schema import Scene

def matmul(a,b): return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def local(o):
    x,y,z=[math.radians(a) for a in o.rotation];cx,sx,cy,sy,cz,sz=math.cos(x),math.sin(x),math.cos(y),math.sin(y),math.cos(z),math.sin(z)
    r=[[cy*cz,-cy*sz,sy,0],[sx*sy*cz+cx*sz,-sx*sy*sz+cx*cz,-sx*cy,0],[-cx*sy*cz+sx*sz,cx*sy*sz+sx*cz,cx*cy,0],[0,0,0,1]]
    for i in range(3):
        for j in range(3): r[i][j]*=o.scale[j]
        r[i][3]=o.position[i]
    return r
def world(o,objects): return matmul(world(objects[o.parent],objects),local(o)) if o.parent else local(o)
def extents(o,objects):
    p=o.parameters
    if o.type=='house': w,d,h=p.width+.7,p.depth+.7,p.floors*p.floor_height+(p.width/2+.35)*math.tan(math.radians(p.roof_angle))
    elif o.type=='sphere': w=d=h=p.radius*2
    elif o.type in ('cylinder','cone'): w=d=p.radius*2;h=p.height
    elif o.type=='torus': w=d=p.radius*2.5;h=p.radius*.5
    else: w,d,h=p.width,p.depth,p.height
    vertical=(-h/2,h/2) if o.anchor=='center' else (0,h)
    matrix=world(o,objects);points=[[sum(matrix[i][j]*v[j] for j in range(4)) for i in range(3)] for v in [(x,y,z,1) for x in (-w/2,w/2) for y in vertical for z in (-d/2,d/2)]]
    return [min(v[i] for v in points) for i in range(3)],[max(v[i] for v in points) for i in range(3)]
def solve_relations(scene:Scene):
    objects={o.id:o for o in scene.objects};done=set();visiting=set();warnings=[]
    def solve(o):
        if o.id in done:return
        if o.id in visiting:raise ValueError('空间关系形成循环约束，请移除冲突关系')
        visiting.add(o.id)
        if o.parent:solve(objects[o.parent])
        if o.relation:
            if not o.reference_object_id:raise ValueError('空间关系缺少参考对象')
            ref=objects[o.reference_object_id];solve(ref)
            low,high=extents(o,objects);a,b=extents(ref,objects)
            axis,sign={'left_of':(0,-1),'right_of':(0,1),'next_to':(0,1),'in_front_of':(2,1),'behind':(2,-1),'above':(1,1),'below':(1,-1)}[o.relation]
            delta=[0.,0.,0.];delta[axis]=(b[axis]+o.spacing-low[axis]) if sign>0 else (a[axis]-o.spacing-high[axis])
            if o.parent:
                # Invert parent's linear 3x3 via adjugate (nonzero scale enforced by Schema).
                m=world(objects[o.parent],objects);a0,b0,c0=m[0][:3];d,e,f=m[1][:3];g,h,i=m[2][:3]
                det=a0*(e*i-f*h)-b0*(d*i-f*g)+c0*(d*h-e*g)
                inv=[[e*i-f*h,c0*h-b0*i,b0*f-c0*e],[f*g-d*i,a0*i-c0*g,c0*d-a0*f],[d*h-e*g,b0*g-a0*h,a0*e-b0*d]]
                delta=[sum(inv[r][c]*delta[c] for c in range(3))/det for r in range(3)]
            o.position=tuple(o.position[j]+delta[j] for j in range(3))
        visiting.remove(o.id);done.add(o.id)
    for o in scene.objects:solve(o)
    # Revalidate positions after solving so constraints cannot exceed scene limits.
    scene=Scene.model_validate(scene.model_dump())
    for i,o in enumerate(scene.objects):
        lo,hi=extents(o,objects)
        for other in scene.objects[:i]:
            if o.parent==other.id or other.parent==o.id:continue
            a,b=extents(other,objects)
            if all(min(hi[k],b[k])-max(lo[k],a[k])>.01 for k in range(3)):warnings.append(f'{o.name} 与 {other.name} 的包围盒重叠，请检查空间约束')
    return scene,warnings
