import * as T from "three";
import type { Scene, Object3DData } from "../../types";

export const nativeTypes = new Set([
  "cube",
  "sphere",
  "cylinder",
  "cone",
  "plane",
  "torus",
  "table",
  "chair",
  "cabinet",
  "bookshelf",
  "bed",
]);
export type Engine = "auto" | "native" | "blender";
export function chooseEngine(
  scene: Scene,
  choice: Engine,
): "native" | "blender" {
  const unsupported = scene.objects.filter((o) => !nativeTypes.has(o.type));
  if (choice === "native" && unsupported.length)
    throw Error(
      "Native 暂不支持：" +
        unsupported.map((o) => o.type).join(", ") +
        "；请选择 Blender",
    );
  return choice === "auto"
    ? unsupported.length
      ? "blender"
      : "native"
    : choice;
}
export function applyTransform(group: T.Object3D, o: Object3DData) {
  group.position.set(...o.position);
  group.rotation.set(
    ...(o.rotation.map(T.MathUtils.degToRad) as [number, number, number]),
  );
  group.scale.set(...o.scale);
  group.visible = o.visible;
  group.updateMatrix();
}
export function materialFor(o: Object3DData) {
  const m = o.material;
  return new T.MeshStandardMaterial({
    color: m?.baseColor ?? String(o.parameters.color ?? "#dc7355"),
    roughness: m?.roughness ?? 0.6,
    metalness: m?.metalness ?? 0,
    opacity: m?.opacity ?? 1,
    transparent: m?.transparent ?? false,
    side: m?.doubleSided ? T.DoubleSide : T.FrontSide,
    emissive: m?.emissive ?? "#000000",
    depthWrite: !m?.transparent,
  });
}
export function buildObject(o: Object3DData): T.Group {
  if (!nativeTypes.has(o.type)) throw Error("Native 不支持 " + o.type);
  const g = new T.Group();
  g.name = o.id;
  g.userData.editorId = o.id;
  const p = o.parameters,
    num = (key: string, fallback: number) => Number(p[key] ?? fallback);
  const w = num("width", 2),
    d = num("depth", 2),
    h = num("height", 2),
    r = num("radius", 1);
  const material = materialFor({ ...o, material: undefined });
  const add = (
    geometry: T.BufferGeometry,
    x = 0,
    y = 0,
    z = 0,
    mat = material,
  ) => {
    const mesh = new T.Mesh(geometry, mat);
    mesh.position.set(x, y, z);
    g.add(mesh);
    return mesh;
  };
  const box = (
    x: number,
    y: number,
    z: number,
    a: number,
    b: number,
    c: number,
    mat = material,
  ) => add(new T.BoxGeometry(a, b, c), x, y, z, mat);
  switch (o.type) {
    case "cube":
      box(0, h / 2, 0, w, h, d);
      break;
    case "sphere":
      add(new T.SphereGeometry(r, 32, 20), 0, r);
      break;
    case "cylinder":
      add(new T.CylinderGeometry(r, r, h, 32), 0, h / 2);
      break;
    case "cone":
      add(new T.ConeGeometry(r, h, 32), 0, h / 2);
      break;
    case "plane": {
      const mesh = add(new T.PlaneGeometry(w, d));
      mesh.rotation.x = -Math.PI / 2;
      break;
    }
    case "torus": {
      const mesh = add(new T.TorusGeometry(r, r * 0.25, 12, 32), 0, r * 0.25);
      mesh.rotation.x = -Math.PI / 2;
      break;
    }
    case "table":
    case "chair":
    case "bed": {
      const top =
        o.type === "table" ? h : o.type === "chair" ? h * 0.45 : h * 0.4;
      const t = Math.min(0.12, top * 0.2),
        leg = Math.min(0.1, w * 0.1, d * 0.1);
      box(0, top - t / 2, 0, w, t, d);
      for (const x of [-w / 2 + leg / 2, w / 2 - leg / 2])
        for (const z of [-d / 2 + leg / 2, d / 2 - leg / 2])
          box(x, (top - t) / 2, z, leg, top - t, leg);
      if (o.type === "chair")
        box(0, (top + h) / 2, -d / 2 + t / 2, w, h - top, t);
      if (o.type === "bed") {
        box(
          0,
          top + h * 0.15,
          0,
          w * 0.98,
          h * 0.3,
          d * 0.98,
          new T.MeshStandardMaterial({ color: "#e7e1d2", roughness: 0.9 }),
        );
        box(0, h / 2, -d / 2, w, h, t);
      }
      break;
    }
    case "cabinet":
    case "bookshelf": {
      const t = Math.min(0.1, w * 0.08, d * 0.15, h * 0.06);
      for (const x of [-w / 2 + t / 2, w / 2 - t / 2])
        box(x, h / 2, 0, t, h, d);
      box(0, h / 2, -d / 2 + t / 2, w, h, t);
      for (let i = 0; i < 5; i++) box(0, t / 2 + ((h - t) * i) / 4, 0, w, t, d);
      if (o.type === "cabinet")
        for (const x of [-w / 4, w / 4])
          box(x, h / 2, d / 2 - t / 2, w / 2 - 0.01, h - t * 2, t);
    }
  }
  if (o.anchor === "center") {
    g.updateMatrixWorld(true);
    const center = new T.Box3().setFromObject(g).getCenter(new T.Vector3());
    g.children.forEach((n) => (n.position.y -= center.y));
  }
  applyTransform(g, o);
  return g;
}
export function buildNativeScene(scene: Scene) {
  const root = new T.Group();
  root.name = "Studio Model";
  const groups = new Map<string, T.Group>();
  for (const o of scene.objects) {
    if (groups.has(o.id)) throw Error("对象 ID 重复");
    groups.set(o.id, buildObject(o));
  }
  for (const o of scene.objects) {
    const g = groups.get(o.id)!;
    const visited = new Set([o.id]);
    let parent = o.parent;
    while (parent) {
      if (visited.has(parent) || !groups.has(parent))
        throw Error("无效父子层级");
      visited.add(parent);
      parent = scene.objects.find((a) => a.id === parent)!.parent;
    }
    (o.parent ? groups.get(o.parent)! : root).add(g);
  }
  root.updateMatrixWorld(true);
  return root;
}
export function disposeModel(root: T.Object3D) {
  const geometries = new Set<T.BufferGeometry>(),
    materials = new Set<T.Material>(),
    textures = new Set<T.Texture>();
  root.traverse((o) => {
    if (o instanceof T.Mesh) {
      geometries.add(o.geometry);
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        materials.add(m);
        for (const v of Object.values(m))
          if (v instanceof T.Texture) textures.add(v);
      }
    }
  });
  geometries.forEach((g) => g.dispose());
  materials.forEach((m) => m.dispose());
  textures.forEach((t) => t.dispose());
}
