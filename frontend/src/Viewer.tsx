import {
  Suspense,
  useEffect,
  useMemo,
  useRef,
  Component,
  type ReactNode,
} from "react";
import { Canvas, useThree } from "@react-three/fiber";
import {
  OrbitControls,
  Grid,
  Bounds,
  useBounds,
  PerspectiveCamera,
  OrthographicCamera,
} from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { useLoader } from "@react-three/fiber";
import * as THREE from "three";
import type { Scene } from "./types";
import { useStudio } from "./store";

class Boundary extends Component<
  { children: ReactNode; onError: (s: string) => void },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  componentDidCatch(error: Error) {
    this.props.onError("模型加载失败：" + error.message);
  }
  render() {
    return this.state.error ? null : this.props.children;
  }
}

function Asset({
  url,
  format,
  wire,
  selected,
  onReady,
}: {
  url: string;
  format: string;
  wire: boolean;
  selected: string | null;
  onReady: () => void;
}) {
  const loaded = useLoader(format === "obj" ? OBJLoader : GLTFLoader, url) as
    THREE.Group | { scene: THREE.Group };
  const original = "scene" in loaded ? loaded.scene : loaded;
  const scene = useMemo(() => original.clone(true), [original]);
  const select = useStudio((s) => s.select);
  const source = useStudio((s) => s.scene);
  const bounds = useBounds();
  useEffect(() => {
    bounds.refresh(scene).clip().fit();
    onReady();
  }, [scene, bounds, onReady]);
  useEffect(() => {
    scene.traverse((node) => {
      if (node instanceof THREE.Mesh) {
        const clone = (m: THREE.Material) => {
          const c = m.clone();
          if ("wireframe" in c) c.wireframe = wire;
          return c;
        };
        node.material = Array.isArray(node.material)
          ? node.material.map(clone)
          : clone(node.material);
      }
    });
  }, [scene, wire]);
  useEffect(() => {
    for (const o of source.objects) {
      const group = scene.getObjectByName(o.id);
      if (group) {
        group.position.set(...o.position);
        group.rotation.set(
          ...(o.rotation.map((v) => (v * Math.PI) / 180) as [
            number,
            number,
            number,
          ]),
        );
        group.scale.set(...o.scale);
        group.visible = o.visible;
      }
    }
  }, [scene, source]);
  useEffect(() => {
    scene.traverse((node) => {
      if (node instanceof THREE.Mesh) {
        let p: THREE.Object3D | null = node;
        let active = false;
        while (p) {
          if (p.name === selected) active = true;
          p = p.parent;
        }
        for (const mat of Array.isArray(node.material)
          ? node.material
          : [node.material])
          if (mat instanceof THREE.MeshStandardMaterial)
            mat.emissive.set(active ? "#254c61" : "#000000");
      }
    });
  }, [scene, selected]);
  return (
    <primitive
      object={scene}
      onClick={(e: { stopPropagation: () => void; object: THREE.Object3D }) => {
        e.stopPropagation();
        let p: THREE.Object3D | null = e.object;
        while (p) {
          if (source.objects.some((o) => o.id === p!.name)) {
            select(p.name);
            return;
          }
          p = p.parent;
        }
        select(null);
      }}
    />
  );
}
function Camera({ view, reset }: { view: string; reset: number }) {
  const { camera, invalidate } = useThree();
  useEffect(() => {
    const positions: Record<string, number[]> = {
      perspective: [15, 12, 18],
      front: [0, 5, 25],
      back: [0, 5, -25],
      left: [-25, 5, 0],
      right: [25, 5, 0],
      top: [0, 30, 0.01],
    };
    camera.position.set(...(positions[view] as [number, number, number]));
    camera.lookAt(0, 3, 0);
    camera.updateProjectionMatrix();
    invalidate();
  }, [camera, view, reset, invalidate]);
  return null;
}
function Capture({ shot }: { shot: number }) {
  const { gl } = useThree();
  useEffect(() => {
    if (!shot) return;
    requestAnimationFrame(() => {
      const a = document.createElement("a");
      a.download = "studio-preview.png";
      a.href = gl.domElement.toDataURL("image/png");
      a.click();
    });
  }, [shot, gl]);
  return null;
}
export function Viewer({
  url,
  format,
  grid,
  axes,
  wire,
  ortho,
  view,
  reset,
  shot,
  onError,
  onReady,
}: {
  url: string | null;
  format: string;
  grid: boolean;
  axes: boolean;
  wire: boolean;
  ortho: boolean;
  view: string;
  reset: number;
  shot: number;
  onError: (s: string) => void;
  onReady: () => void;
}) {
  const selected = useStudio((s) => s.selected);
  return (
    <Canvas
      gl={{ preserveDrawingBuffer: true, antialias: true }}
      shadows
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
      <ambientLight intensity={1.2} />
      <directionalLight position={[8, 18, 10]} intensity={2.5} />
      <directionalLight position={[-10, 6, -5]} intensity={1} />
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
      {url && (
        <Boundary key={url} onError={onError}>
          <Suspense fallback={null}>
            <Bounds margin={1.3}>
              <Asset
                url={url}
                format={format}
                wire={wire}
                selected={selected}
                onReady={onReady}
              />
            </Bounds>
          </Suspense>
        </Boundary>
      )}
      <OrbitControls makeDefault minDistance={0.1} maxDistance={600} />
    </Canvas>
  );
}
