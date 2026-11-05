import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { TransformControls, useBounds, Html } from "@react-three/drei";
import * as T from "three";
import { useStudio } from "../store";
import { decomposeLocal } from "./runtime";

export type EditingOptions = {
  mode: "translate" | "rotate" | "scale";
  space: "local" | "world";
  snap: boolean;
  focus: number;
};
export function EditingControls({
  root,
  options,
}: {
  root: T.Group;
  options: EditingOptions;
}) {
  const { selection, scene } = useStudio();
  const [notice, setNotice] = useState("");
  const bounds = useBounds();
  const { controls } = useThree();
  const pivot = useMemo(() => new T.Group(), []),
    dragging = useRef(false),
    start = useRef(new T.Matrix4()),
    initial = useRef(new Map<T.Object3D, T.Matrix4>());
  const nodes = selection
    .map((id) => root.getObjectByName(id))
    .filter((n): n is T.Object3D => !!n)
    .filter((n) => !scene.objects.find((o) => o.id === n.name)?.locked)
    .filter((n) => {
      let p = n.parent;
      while (p && p !== root) {
        if (selection.includes(p.name)) return false;
        p = p.parent;
      }
      return true;
    });
  const shearRisk =
    options.mode !== "translate" &&
    nodes.some((node) => {
      let p = node.parent;
      while (p && p !== root) {
        if (
          Math.abs(p.scale.x - p.scale.y) > 0.0001 ||
          Math.abs(p.scale.y - p.scale.z) > 0.0001
        )
          return true;
        p = p.parent;
      }
      return false;
    });
  useEffect(() => {
    if (dragging.current || !nodes.length) return;
    root.updateMatrixWorld(true);
    const box = new T.Box3();
    nodes.forEach((n) => box.union(new T.Box3().setFromObject(n)));
    box.getCenter(pivot.position);
    pivot.quaternion.copy(
      options.space === "local"
        ? nodes[0].getWorldQuaternion(new T.Quaternion())
        : new T.Quaternion(),
    );
    pivot.scale.set(1, 1, 1);
    pivot.updateMatrixWorld(true);
  }, [root, selection, scene, options.space]);
  useEffect(() => {
    if (options.focus && nodes[0]) bounds.refresh(nodes[0]).clip().fit();
  }, [options.focus]);
  const helpers = useMemo(
    () => nodes.map((n) => new T.BoxHelper(n, "#e8a17c")),
    [root, selection.join("|")],
  );
  useEffect(
    () => () =>
      helpers.forEach((h) => {
        h.geometry.dispose();
        (h.material as T.Material).dispose();
      }),
    [helpers],
  );
  useFrame(() => helpers.forEach((h) => h.update()));
  function orbit(enabled: boolean) {
    if (controls && "enabled" in controls) controls.enabled = enabled;
  }
  useEffect(
    () => () => {
      orbit(true);
      if (dragging.current) useStudio.getState().end();
    },
    [root, controls],
  );
  return (
    <>
      {helpers.map((h) => (
        <primitive key={h.uuid} object={h} />
      ))}
      {shearRisk && (
        <Html position={[0, 0, 0]} center>
          <div className="warning">
            非均匀缩放父节点下，请先统一父级缩放，或在属性栏编辑局部旋转和缩放。
          </div>
        </Html>
      )}
      {notice && (
        <Html position={[0, 0, 0]} center>
          <div className="warning">{notice}</div>
        </Html>
      )}
      {nodes.length > 0 && !shearRisk && (
        <>
          <primitive object={pivot} />
          <TransformControls
            object={pivot}
            mode={options.mode}
            space={options.space}
            translationSnap={options.snap ? 0.5 : null}
            rotationSnap={options.snap ? T.MathUtils.degToRad(15) : null}
            scaleSnap={options.snap ? 0.1 : null}
            onMouseDown={() => {
              setNotice("");
              dragging.current = true;
              orbit(false);
              root.updateMatrixWorld(true);
              pivot.updateMatrixWorld(true);
              start.current.copy(pivot.matrixWorld);
              initial.current = new Map(
                nodes.map((n) => [n, n.matrixWorld.clone()]),
              );
              useStudio.getState().begin();
            }}
            onObjectChange={() => {
              if (!dragging.current) return;
              pivot.updateMatrixWorld(true);
              const delta = pivot.matrixWorld
                .clone()
                .multiply(start.current.clone().invert());
              try {
                const changes = [...initial.current].map(
                  ([node, world]) =>
                    [
                      node.name,
                      decomposeLocal(node, delta.clone().multiply(world)),
                    ] as const,
                );
                for (const [id, patch] of changes)
                  useStudio.getState().edit(id, patch);
              } catch (e) {
                setNotice(String(e));
              }
            }}
            onMouseUp={() => {
              dragging.current = false;
              orbit(true);
              useStudio.getState().end();
              if (notice)
                start.current.decompose(
                  pivot.position,
                  pivot.quaternion,
                  pivot.scale,
                );
            }}
          />
        </>
      )}
    </>
  );
}
