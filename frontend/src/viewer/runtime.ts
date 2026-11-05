import * as T from "three";
import { applyTransform } from "../engines/native";
import type { Scene } from "../types";
const baselines = new WeakMap<T.Mesh, T.Material[]>();
const registry = globalThis as typeof globalThis & { __formaCamera?: T.Camera };
export function setViewerCamera(camera: T.Camera) {
  registry.__formaCamera = camera;
}
export function getViewerCamera() {
  return registry.__formaCamera ?? null;
}

export function cloneAsset(source: T.Group) {
  const clone = source.clone(true);
  clone.traverse((o) => {
    if (o instanceof T.Mesh) {
      o.geometry = o.geometry.clone();
      const material = (m: T.Material) => {
        const copy = m.clone();
        for (const [key, value] of Object.entries(copy))
          if (value instanceof T.Texture)
            (copy as unknown as Record<string, unknown>)[key] = value.clone();
        return copy;
      };
      o.material = Array.isArray(o.material)
        ? o.material.map(material)
        : material(o.material);
    }
  });
  return clone;
}
// Editable wrappers use the Scene's absolute local TRS. Asset child geometry stays untouched.
export function syncAsset(
  root: T.Group,
  scene: Scene,
  templates: Map<string, T.Object3D>,
) {
  const ids = new Set(scene.objects.map((o) => o.id));
  for (const o of scene.objects) {
    let node = root.getObjectByName(o.id);
    const key = o.source_id ?? o.id;
    if (!node && templates.has(key)) {
      node = cloneAsset(templates.get(key)! as T.Group);
      node.name = o.id;
      root.add(node);
    }
    if (node) {
      node.userData.editorId = o.id;
      const target = o.parent ? root.getObjectByName(o.parent) : root;
      if (target && node.parent !== target) target.add(node);
      applyTransform(node, o);
      node.traverse((child) => {
        if (child instanceof T.Mesh) {
          const materials = Array.isArray(child.material)
            ? child.material
            : [child.material];
          if (!baselines.has(child))
            baselines.set(
              child,
              materials.map((m) => m.clone()),
            );
          for (let i = 0; i < materials.length; i++)
            materials[i].copy(baselines.get(child)![i]);
          for (const mat of Array.isArray(child.material)
            ? child.material
            : [child.material])
            if (o.material && mat instanceof T.MeshStandardMaterial) {
              mat.color.set(o.material!.baseColor);
              mat.metalness = o.material!.metalness;
              mat.roughness = o.material!.roughness;
              mat.opacity = o.material!.opacity;
              mat.transparent = o.material!.transparent;
              mat.side = o.material!.doubleSided ? T.DoubleSide : T.FrontSide;
              mat.emissive.set(o.material!.emissive);
              mat.depthWrite = !mat.transparent;
              mat.needsUpdate = true;
            }
        }
      });
    }
  }
  const removed: T.Object3D[] = [];
  root.traverse((n) => {
    if (n.userData.editorId && !ids.has(n.userData.editorId)) removed.push(n);
  });
  removed.forEach((n) => n.removeFromParent());
  root.updateMatrixWorld(true);
}
export function decomposeLocal(node: T.Object3D, world: T.Matrix4) {
  const local = node.parent
    ? node.parent.matrixWorld.clone().invert().multiply(world)
    : world;
  const position = new T.Vector3(),
    q = new T.Quaternion(),
    scale = new T.Vector3();
  local.decompose(position, q, scale);
  const represented = new T.Matrix4().compose(position, q, scale);
  if (
    local.elements.some((v, i) => Math.abs(v - represented.elements[i]) > 1e-5)
  )
    throw Error(
      "此操作产生不可表示的剪切；请使用 Local、均匀缩放或属性栏编辑。",
    );
  const e = new T.Euler().setFromQuaternion(q, "XYZ");
  return {
    position: position.toArray() as [number, number, number],
    rotation: [e.x, e.y, e.z].map(T.MathUtils.radToDeg) as [
      number,
      number,
      number,
    ],
    scale: scale.toArray().map((v) => Math.max(0.01, Math.min(10, v))) as [
      number,
      number,
      number,
    ],
  };
}
