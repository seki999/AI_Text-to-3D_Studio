import {
  Suspense,
  useEffect,
  useMemo,
  useLayoutEffect,
  useState,
  useRef,
  Component,
  type ReactNode,
} from "react";
import { Canvas, useThree, useLoader } from "@react-three/fiber";
import {
  Html,
  OrbitControls,
  Grid,
  Bounds,
  useBounds,
  PerspectiveCamera,
  OrthographicCamera,
} from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { loadGLB } from "./services/assetLoading";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import * as T from "three";
import { useStudio, empty } from "./store";
import { buildNativeScene, disposeModel, nativeTypes } from "./engines/native";
import { setExportModel, snapshot, getExportModel } from "./services/export";
import { cloneAsset, syncAsset, setViewerCamera } from "./viewer/runtime";
import { EditingControls, type EditingOptions } from "./viewer/EditingControls";

class Boundary extends Component<
  { children: ReactNode; onError: (s: string) => void },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  componentDidCatch(e: Error) {
    this.props.onError("模型加载失败：" + e.message);
  }
  render() {
    return this.state.error ? null : this.props.children;
  }
}
function Model({
  root,
  wire,
  onReady,
  editing,
}: {
  root: T.Group;
  wire: boolean;
  onReady: () => void;
  editing: EditingOptions;
}) {
  const source = useStudio((s) => s.scene),
    bounds = useBounds();
  const templates = useMemo(() => {
    const map = new Map<string, T.Object3D>(),
      ids = new Set(source.objects.map((o) => o.id));
    for (const o of source.objects) {
      const node = root.getObjectByName(o.id);
      if (node) {
        const copy = node.clone(true);
        const remove: T.Object3D[] = [];
        copy.traverse((n) => {
          if (n !== copy && ids.has(n.name)) remove.push(n);
        });
        remove.forEach((n) => n.removeFromParent());
        map.set(o.id, copy);
      }
    }
    return map;
  }, [root]);
  useEffect(() => () => templates.forEach((n) => disposeModel(n)), [templates]);
  useEffect(() => {
    for (const o of source.objects) {
      const node = root.getObjectByName(o.id);
      if (node && !templates.has(o.id)) templates.set(o.id, node.clone(true));
    }
    syncAsset(root, source, templates);
  }, [source, root, templates]);
  useEffect(() => {
    setExportModel(root);
    bounds.refresh(root).clip().fit();
    onReady();
    return () => setExportModel(null);
  }, [root, bounds, onReady]);
  useEffect(() => {
    root.traverse((n) => {
      if (n instanceof T.Mesh)
        for (const m of Array.isArray(n.material) ? n.material : [n.material])
          if ("wireframe" in m) m.wireframe = wire;
    });
  }, [wire, root, source]);
  return (
    <>
      <primitive
        object={root}
        onClick={(e: {
          stopPropagation: () => void;
          object: T.Object3D;
          shiftKey: boolean;
        }) => {
          e.stopPropagation();
          let n: T.Object3D | null = e.object;
          while (n && n !== root) {
            if (source.objects.some((o) => o.id === n!.name)) {
              useStudio.getState().select(n.name, e.shiftKey);
              return;
            }
            n = n.parent;
          }
        }}
      />
      <EditingControls root={root} options={editing} />
    </>
  );
}
function Native(props: {
  wire: boolean;
  onReady: () => void;
  editing: EditingOptions;
}) {
  const source = useStudio((s) => s.scene);
  const key = JSON.stringify(
    source.objects.map((o) => [o.id, o.type, o.parent, o.anchor, o.parameters]),
  );
  const root = useMemo(
    () =>
      source.objects.length &&
      source.objects.every((o) => nativeTypes.has(o.type))
        ? buildNativeScene(source)
        : null,
    [key],
  );
  useEffect(
    () => () => {
      if (root) disposeModel(root);
    },
    [root],
  );
  return root ? <Model root={root} {...props} /> : null;
}
function LoadedAsset({
  loaded,
  url,
  format,
  preserveScene,
  ...props
}: {
  loaded: T.Group | { scene: T.Group };
  url: string;
  format: string;
  preserveScene: boolean;
  wire: boolean;
  onReady: () => void;
  editing: EditingOptions;
}) {
  const external = url.startsWith("blob:") && !preserveScene;
  const [initialized, setInitialized] = useState(!external);
  const root = useMemo(() => {
    const clone = "scene" in loaded ? loaded.scene : loaded;
    if (external) {
      clone.traverse((n) => {
        delete n.userData.editorId;
      });
      const children = [...clone.children].filter((child) => {
        let found = false;
        child.traverse((n) => {
          if (n instanceof T.Mesh) found = true;
        });
        return found;
      });
      clone.clear();
      children.forEach((child, i) => {
        const wrapper = new T.Group();
        wrapper.name = "imported_" + i;
        wrapper.add(child);
        clone.add(wrapper);
      });
    }
    return clone;
  }, [loaded, external]);
  useLayoutEffect(() => {
    if (external) {
      const objects = root.children.map((group) => ({
        id: group.name,
        name: group.children[0]?.name || "导入模型",
        type: "imported",
        parent: null,
        visible: true,
        position: [0, 0, 0] as [number, number, number],
        rotation: [0, 0, 0] as [number, number, number],
        scale: [1, 1, 1] as [number, number, number],
        parameters: { width: 2, depth: 2, height: 2, radius: 1 },
      }));
      useStudio.getState().setScene({ ...empty, name: "导入模型", objects });
      setInitialized(true);
    }
  }, [root, external]);
  return initialized ? <Model root={root} {...props} /> : null;
}
function Asset(props: {url:string;format:string;preserveScene:boolean;wire:boolean;onReady:()=>void;editing:EditingOptions}) {
  const [loaded,setLoaded]=useState<T.Group|{scene:T.Group}|null>(null),[progress,setProgress]=useState("准备加载"),[cancelled,setCancelled]=useState(false),[failure,setFailure]=useState(""),[faces,setFaces]=useState(0);
  const cancellation=useRef<AbortController|null>(null);
  useEffect(()=>{
    const controller=new AbortController();cancellation.current=controller;
    let root:T.Group|null=null;
    const run=async()=>{
      try {
        const result=props.format==="obj"?await new OBJLoader().loadAsync(props.url):await loadGLB(props.url,controller.signal,(bytes,total)=>setProgress(total?`下载 ${Math.round(bytes/total*100)}%`:`已下载 ${(bytes/1048576).toFixed(1)} MB`));
        root="scene" in result?result.scene:result;
        if(controller.signal.aborted){disposeModel(root);root=null;return;}
        let count=0;root.traverse(node=>{if(node instanceof T.Mesh)count+=(node.geometry.index?.count??node.geometry.attributes.position.count)/3;});
        setFaces(count);setLoaded(result);
      } catch(e) { if(!controller.signal.aborted)setFailure(String(e)); }
    };
    run();return()=>{controller.abort();if(root)disposeModel(root);};
  },[props.url,props.format]);
  if(failure)return <Html center><div className="load-overlay" role="alert">模型加载失败：{failure}</div></Html>;
  if(cancelled)return <Html center><div className="load-overlay">已取消加载，原始文件未修改。</div></Html>;
  if(!loaded)return <Html center><div className="load-overlay">{progress}<button onClick={()=>{cancellation.current?.abort();setCancelled(true);}}>取消加载</button></div></Html>;
  return <><LoadedAsset {...props} loaded={loaded}/>{faces>250000&&<Html position={[0,4,0]}><div className="load-overlay">高面数：{Math.round(faces).toLocaleString()} 面；可在资产库显式创建简化副本。</div></Html>}</>;
}
function Camera({ view, reset }: { view: string; reset: number }) {
  const { camera, invalidate } = useThree();
  setViewerCamera(camera);
  useEffect(() => {
    const p: Record<string, [number, number, number]> = {
      perspective: [15, 12, 18],
      front: [0, 5, 25],
      back: [0, 5, -25],
      left: [-25, 5, 0],
      right: [25, 5, 0],
      top: [0, 30, 0.01],
    };
    camera.position.set(...p[view]);
    camera.lookAt(0, 3, 0);
    camera.updateProjectionMatrix();
    invalidate();
  }, [camera, view, reset, invalidate]);
  return null;
}
function Capture({ shot }: { shot: number }) {
  const { gl, scene, camera } = useThree();
  useEffect(() => {
    if (shot)
      requestAnimationFrame(() => {
        const model = getExportModel();
        if (!model) return;
        const preview = new T.Scene();
        preview.background = scene.background;
        scene.children.forEach((n) => {
          if (n instanceof T.Light) preview.add(n.clone());
        });
        const copy = snapshot(model);
        preview.add(copy);
        gl.render(preview, camera);
        const a = document.createElement("a");
        a.download = "studio-preview.png";
        a.href = gl.domElement.toDataURL("image/png");
        a.click();
        gl.render(scene, camera);
        copy.traverse((n) => {
          if (n instanceof T.Mesh)
            for (const m of Array.isArray(n.material)
              ? n.material
              : [n.material])
              m.dispose();
        });
      });
  }, [shot, gl]);
  return null;
}
type Props = {
  url: string | null;
  format: string;
  nativeActive?: boolean;
  preserveScene?: boolean;
  grid: boolean;
  axes: boolean;
  wire: boolean;
  ortho: boolean;
  view: string;
  reset: number;
  shot: number;
  onError: (s: string) => void;
  onReady: () => void;
  editing?: EditingOptions;
};
export function Viewer({
  url,
  format,
  nativeActive = false,
  preserveScene = false,
  grid,
  axes,
  wire,
  ortho,
  view,
  reset,
  shot,
  onError,
  onReady,
  editing = { mode: "translate", space: "world", snap: false, focus: 0 },
}: Props) {
  const [epoch,setEpoch]=useState(0),[lost,setLost]=useState(false);
  return (
    <div className="viewer-surface"><Canvas key={epoch}
      onCreated={({gl})=>{gl.domElement.addEventListener("webglcontextlost",event=>{event.preventDefault();setLost(true);});gl.domElement.addEventListener("webglcontextrestored",()=>{setLost(false);setEpoch(value=>value+1);});}}
      gl={{ preserveDrawingBuffer: true, antialias: true }}
      onPointerMissed={() => useStudio.getState().select(null)}
    >
      <color attach="background" args={["#181d27"]} />
      {ortho ? (
        <OrthographicCamera makeDefault position={[15, 12, 18]} zoom={30} />
      ) : (
        <PerspectiveCamera makeDefault position={[15, 12, 18]} fov={42} />
      )}
      <Camera view={view} reset={reset} />
      <Capture shot={shot} />
      <ambientLight intensity={0.8} />
      <directionalLight position={[8, 18, 10]} intensity={2} />
      <directionalLight position={[-10, 6, -5]} intensity={0.8} />
      {grid && (
        <Grid
          infiniteGrid
          cellSize={1}
          sectionSize={5}
          cellColor="#354052"
          sectionColor="#526174"
          fadeDistance={100}
          position={[0, -0.03, 0]}
        />
      )}
      {axes && <axesHelper args={[5]} />}
      <OrbitControls makeDefault minDistance={0.1} maxDistance={600} />
      {(url || nativeActive) && (
        <Boundary key={url ?? "native"} onError={onError}>
          <Suspense fallback={null}>
            <Bounds margin={1.3}>
              {nativeActive ? (
                <Native {...{ wire, onReady, editing }} />
              ) : url ? (
                <Asset
                  {...{ url, format, preserveScene, wire, onReady, editing }}
                />
              ) : null}
            </Bounds>
          </Suspense>
        </Boundary>
      )}
    </Canvas>{lost&&<div className="context-overlay" role="alert">WebGL 上下文已丢失，当前项目数据仍保留。<button onClick={()=>{setLost(false);setEpoch(value=>value+1);}}>重新创建视图</button></div>}</div>
  );
}
