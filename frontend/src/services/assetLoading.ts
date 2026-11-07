import * as T from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { disposeModel } from "../engines/native";
export async function loadGLB(url: string, signal: AbortSignal, progress: (bytes: number, total: number) => void = () => {}) {
  const response = await fetch(url, { signal });
  if (!response.ok) throw Error("GLB 下载失败：" + response.status);
  const total = Number(response.headers.get("Content-Length") ?? 0);
  if (total > 50 * 1024 * 1024) throw Error("GLB 超过 50 MB 上限");
  const reader = response.body!.getReader(), chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { value, done } = await reader.read(); if (done) break;
    size += value.length; if (size > 50 * 1024 * 1024) { await reader.cancel(); throw Error("GLB 超过 50 MB 上限"); }
    chunks.push(value); progress(size, total);
  }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  signal.throwIfAborted();
  const result = await new GLTFLoader().parseAsync(bytes.buffer, "");
  if (signal.aborted) { disposeModel(result.scene); signal.throwIfAborted(); }
  return result;
}
export async function previewPNG(url: string) {
  const controller = new AbortController(), gltf = await loadGLB(url, controller.signal);
  const renderer = new T.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
  try {
    renderer.setSize(256,192);renderer.setPixelRatio(1);
    const scene = new T.Scene();scene.background = new T.Color("#202938");scene.add(gltf.scene);
    scene.add(new T.HemisphereLight(0xffffff,0x667788,2));const light = new T.DirectionalLight(0xffffff,3);light.position.set(4,8,5);scene.add(light);
    const box = new T.Box3().setFromObject(gltf.scene), center = box.getCenter(new T.Vector3()), extent = box.getSize(new T.Vector3()).length();
    const camera = new T.PerspectiveCamera(40,256/192,.01,Math.max(1000,extent*20));camera.position.copy(center).add(new T.Vector3(1,.7,1).multiplyScalar(extent*1.2));camera.lookAt(center);
    renderer.render(scene,camera);return renderer.domElement.toDataURL("image/png").split(",")[1];
  } finally {disposeModel(gltf.scene);renderer.dispose();renderer.forceContextLoss();}
}
