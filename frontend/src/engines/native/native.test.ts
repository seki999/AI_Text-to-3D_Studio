import { describe, it, expect } from "vitest";
import * as T from "three";
import { buildNativeScene, chooseEngine, disposeModel } from "./index";
import { empty, useStudio } from "../../store";
import { decomposeLocal, syncAsset } from "../../viewer/runtime";
import { snapshot, exportOBJ } from "../../services/export";
import type { Object3DData, Scene } from "../../types";
const object = (id = "a", type = "cube"): Object3DData => ({
  id,
  name: id,
  type,
  parent: null,
  visible: true,
  position: [0, 0, 0],
  rotation: [0, 0, 0],
  scale: [1, 1, 1],
  parameters: { width: 2, height: 3, depth: 4, radius: 1, color: "#ff0000" },
});
describe("Native real geometry", () => {
  it("preserves hidden geometry in project snapshots while visible-only exports reject an empty scene", () => {
    const root = buildNativeScene({
      ...empty,
      objects: [{ ...object(), visible: false }],
    });
    expect(() => snapshot(root)).toThrow("可见 Mesh");
    expect(snapshot(root, true).getObjectByName("a")!.children).toHaveLength(1);
  });
  it("rejects unrepresentable hierarchy shear instead of corrupting exported TRS", () => {
    const parent = new T.Group(),
      child = new T.Group();
    parent.scale.set(2, 1, 1);
    parent.add(child);
    parent.updateMatrixWorld(true);
    const desired = new T.Matrix4()
      .makeRotationY(0.4)
      .multiply(child.matrixWorld);
    expect(() => decomposeLocal(child, desired)).toThrow("剪切");
    expect(
      decomposeLocal(
        child,
        new T.Matrix4().makeTranslation(0, 2, 0).multiply(child.matrixWorld),
      ).position[1],
    ).toBeCloseTo(2);
  });
  for (const type of [
    "cube",
    "cylinder",
    "sphere",
    "cone",
    "plane",
    "torus",
    "table",
    "chair",
    "cabinet",
    "bookshelf",
    "bed",
  ])
    it(type, () => {
      const root = buildNativeScene({ ...empty, objects: [object("a", type)] });
      let meshes = 0;
      root.traverse((o) => {
        if (o instanceof T.Mesh) {
          meshes++;
          expect(o.geometry.attributes.position.count).toBeGreaterThan(0);
        }
      });
      expect(meshes).toBeGreaterThan(type === "table" ? 4 : 0);
      disposeModel(root);
    });
  it("uses exact dimensions and sRGB colors", () => {
    const root = buildNativeScene({ ...empty, objects: [object()] });
    const size = new T.Box3().setFromObject(root).getSize(new T.Vector3());
    expect(size.toArray()).toEqual([2, 3, 4]);
    const mat = (root.children[0].children[0] as T.Mesh)
      .material as T.MeshStandardMaterial;
    expect(mat.color.getHexString()).toBe("ff0000");
  });
  it("resolves hierarchy and local/world edits without double transforms", () => {
    const parent = object("p"),
      child = {
        ...object("c"),
        parent: "p",
        position: [1, 0, 0] as [number, number, number],
      };
    parent.position = [4, 0, 0];
    parent.rotation = [0, 90, 0];
    const root = buildNativeScene({ ...empty, objects: [parent, child] });
    const c = root.getObjectByName("c")!;
    expect(c.getWorldPosition(new T.Vector3()).toArray()[2]).toBeCloseTo(-1);
    const patch = decomposeLocal(
      c,
      new T.Matrix4().makeTranslation(0, 2, 0).multiply(c.matrixWorld),
    );
    expect(patch.position[0]).toBeCloseTo(1);
    expect(patch.position[1]).toBeCloseTo(2);
  });
  it("auto does not require Blender for supported objects", () => {
    expect(chooseEngine({ ...empty, objects: [object()] }, "auto")).toBe(
      "native",
    );
    expect(() =>
      chooseEngine({ ...empty, objects: [object("h", "house")] }, "native"),
    ).toThrow("Blender");
  });
  it("keeps export transforms and excludes hidden objects from OBJ", () => {
    const root = buildNativeScene({
      ...empty,
      objects: [
        { ...object(), position: [5, 0, 0] },
        { ...object("hidden"), visible: false },
      ],
    });
    expect(snapshot(root).getObjectByName("a")!.position.x).toBe(5);
    const { obj, mtl } = exportOBJ(root);
    expect(obj).toContain("v 4 ");
    expect(mtl).toContain("Kd 0.999");
    expect(obj).not.toContain("hidden");
  });
  it("coalesces many drag updates into one undo transaction", () => {
    const s = useStudio.getState();
    s.setScene({ ...empty, objects: [object()] });
    const count = useStudio.getState().past.length;
    s.begin();
    for (let i = 1; i <= 20; i++) s.edit("a", { position: [i, 0, 0] });
    s.end();
    expect(useStudio.getState().past.length).toBe(count + 1);
    s.undo();
    expect(useStudio.getState().scene.objects[0].position[0]).toBe(0);
    s.redo();
    expect(useStudio.getState().scene.objects[0].position[0]).toBe(20);
  });
  it("multi-object transforms, copy subtree, lock and delete preserve hierarchy", () => {
    const parent = object("parent"),
      child = { ...object("child"), parent: "parent" };
    const state = useStudio.getState();
    state.setScene({ ...empty, objects: [parent, child] });
    state.select("parent");
    state.duplicate();
    const copies = useStudio.getState().scene.objects.slice(2);
    expect(copies).toHaveLength(2);
    expect(copies[1].parent).toBe(copies[0].id);
    state.remove();
    expect(useStudio.getState().scene.objects).toHaveLength(2);
    state.select("child");
    state.edit("child", { locked: true });
    state.remove();
    expect(useStudio.getState().scene.objects).toHaveLength(2);
  });
  it("PBR undo restores original material and releases shared GPU resources once", () => {
    const o = object(),
      scene = { ...empty, objects: [o] },
      root = buildNativeScene(scene);
    const mat = (root.children[0].children[0] as T.Mesh)
      .material as T.MeshStandardMaterial;
    syncAsset(root, scene, new Map());
    syncAsset(
      root,
      {
        ...scene,
        objects: [
          {
            ...o,
            material: {
              baseColor: "#0000ff",
              roughness: 0.1,
              metalness: 1,
              opacity: 1,
              transparent: false,
              doubleSided: false,
              emissive: "#000000",
            },
          },
        ],
      },
      new Map(),
    );
    expect(mat.color.getHexString()).toBe("0000ff");
    syncAsset(root, scene, new Map());
    expect(mat.color.getHexString()).toBe("ff0000");
    let disposed = 0;
    mat.addEventListener("dispose", () => disposed++);
    disposeModel(root);
    expect(disposed).toBe(1);
  });
});
