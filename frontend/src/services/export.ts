import * as T from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import { OBJExporter } from "three/examples/jsm/exporters/OBJExporter.js";

// Only model geometry enters this registry. Grid, gizmos and selection helpers never do.
const registry = globalThis as typeof globalThis & {
  __formaModel?: T.Group | null;
};
export function setExportModel(root: T.Group | null) {
  registry.__formaModel = root;
}
export function getExportModel() {
  return registry.__formaModel ?? null;
}
export function snapshot(root = getExportModel(), includeHidden = false) {
  if (!root) throw Error("尚无可导出的模型");
  let mesh = false;
  const visit = (n: T.Object3D) => {
    if (n instanceof T.Mesh) mesh = true;
  };
  if (includeHidden) root.traverse(visit);
  else root.traverseVisible(visit);
  if (!mesh) throw Error("场景中没有可见 Mesh，无法导出");
  root.updateMatrixWorld(true);
  const result = root.clone(true);
  result.traverse((o) => {
    if (o instanceof T.Mesh) {
      o.material = Array.isArray(o.material)
        ? o.material.map((m) => m.clone())
        : o.material.clone();
      for (const m of Array.isArray(o.material) ? o.material : [o.material])
        if ("wireframe" in m) m.wireframe = false;
    }
  });
  return result;
}
export async function exportGLTF(
  binary = true,
  root = getExportModel(),
  includeHidden = false,
) {
  const copy = snapshot(root, includeHidden);
  try {
    return await new GLTFExporter().parseAsync(copy, {
      binary,
      onlyVisible: !includeHidden,
      trs: true,
    });
  } finally {
    copy.traverse((o) => {
      if (o instanceof T.Mesh)
        for (const m of Array.isArray(o.material) ? o.material : [o.material])
          m.dispose();
    });
  }
}
export function exportOBJ(root = getExportModel()) {
  const copy = snapshot(root);
  const mtl: string[] = [];
  let index = 0;
  // Bake transforms and filter hidden subtrees for OBJ's flattened scene representation.
  const flat = new T.Group();
  copy.updateMatrixWorld(true);
  copy.traverseVisible((o) => {
    if (o instanceof T.Mesh) {
      const mesh = o.clone();
      mesh.geometry = o.geometry.clone().applyMatrix4(o.matrixWorld);
      mesh.position.set(0, 0, 0);
      mesh.quaternion.identity();
      mesh.scale.set(1, 1, 1);
      const mats = Array.isArray(mesh.material)
        ? mesh.material
        : [mesh.material];
      for (const mat of mats) {
        mat.name = "material_" + index++;
        if (mat instanceof T.MeshStandardMaterial) {
          const c = mat.color.clone().convertLinearToSRGB();
          mtl.push(
            `newmtl ${mat.name}\nKd ${c.r} ${c.g} ${c.b}\nd ${mat.opacity}\nNs ${(1 - mat.roughness) * 100}\n`,
          );
        }
      }
      flat.add(mesh);
    }
  });
  flat.updateMatrixWorld(true);
  const obj = "mtllib model.mtl\n" + new OBJExporter().parse(flat);
  flat.traverse((o) => {
    if (o instanceof T.Mesh) {
      o.geometry.dispose();
      for (const m of Array.isArray(o.material) ? o.material : [o.material])
        m.dispose();
    }
  });
  return { obj, mtl: mtl.join("\n") };
}
export function saveBlob(
  data: BlobPart,
  name: string,
  type = "application/octet-stream",
) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
