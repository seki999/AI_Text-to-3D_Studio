import { create } from "zustand";
import type { Scene, Object3DData } from "./types";
export const empty: Scene = {
  version: "1.0",
  name: "未命名项目",
  units: "meters",
  objects: [],
  environment: { ground: true, background: "#181d27" },
};
type State = {
  scene: Scene;
  selected: string | null;
  selection: string[];
  transaction: Scene | null;
  past: Scene[];
  future: Scene[];
  setScene: (s: Scene) => void;
  select: (id: string | null, additive?: boolean) => void;
  edit: (id: string, patch: Partial<Object3DData>) => void;
  undo: () => void;
  redo: () => void;
  begin: () => void;
  end: () => void;
  remove: () => void;
  duplicate: () => void;
};
export const useStudio = create<State>((set) => ({
  scene: empty,
  selected: null,
  selection: [],
  transaction: null,
  past: [],
  future: [],
  setScene: (scene) =>
    set((s) => ({ scene, past: [...s.past.slice(-29), s.scene], future: [] })),
  select: (selected, additive = false) =>
    set((s) => {
      const selection = selected
        ? additive
          ? s.selection.includes(selected)
            ? s.selection.filter((id) => id !== selected)
            : [...s.selection, selected]
          : [selected]
        : [];
      return { selected: selection.at(-1) ?? null, selection };
    }),
  edit: (id, patch) =>
    set((s) => {
      for (const key of ["position", "rotation", "scale"] as const) {
        const values = patch[key];
        if (values) {
          if (values.some((v) => !Number.isFinite(v))) return {};
          patch = {
            ...patch,
            [key]: values.map((v) =>
              key === "position"
                ? Math.max(-500, Math.min(500, v))
                : key === "scale"
                  ? Math.max(0.01, Math.min(10, v))
                  : ((((v + 180) % 360) + 360) % 360) - 180,
            ),
          };
        }
      }
      if (patch.material)
        patch = {
          ...patch,
          material: {
            ...patch.material,
            ...Object.fromEntries(
              (["metalness", "roughness", "opacity"] as const).map((k) => [
                k,
                Math.max(0, Math.min(1, patch.material![k])),
              ]),
            ),
          },
        };
      if (patch.position || patch.rotation || patch.scale)
        patch = { ...patch, relation: null, reference_object_id: null };
      return {
        scene: {
          ...s.scene,
          objects: s.scene.objects.map((o) =>
            o.id === id && (!o.locked || "locked" in patch)
              ? { ...o, ...patch }
              : o,
          ),
        },
        past: s.transaction ? s.past : [...s.past.slice(-29), s.scene],
        future: [],
      };
    }),
  begin: () =>
    set((s) =>
      s.transaction ? {} : { transaction: structuredClone(s.scene) },
    ),
  end: () =>
    set((s) =>
      s.transaction
        ? {
            past:
              JSON.stringify(s.transaction) === JSON.stringify(s.scene)
                ? s.past
                : [...s.past.slice(-29), s.transaction],
            future: [],
            transaction: null,
          }
        : {},
    ),
  remove: () =>
    set((s) => {
      const ids = new Set(
        s.selection.filter(
          (id) => !s.scene.objects.find((o) => o.id === id)?.locked,
        ),
      );
      let changed = true;
      while (changed) {
        changed = false;
        for (const o of s.scene.objects)
          if (o.parent && ids.has(o.parent) && !ids.has(o.id)) {
            ids.add(o.id);
            changed = true;
          }
      }
      if (s.scene.objects.some((o) => ids.has(o.id) && o.locked)) return {};
      return {
        scene: {
          ...s.scene,
          objects: s.scene.objects
            .filter((o) => !ids.has(o.id))
            .map((o) =>
              o.reference_object_id && ids.has(o.reference_object_id)
                ? { ...o, relation: null, reference_object_id: null }
                : o,
            ),
        },
        past: [...s.past.slice(-29), s.scene],
        future: [],
        selected: null,
        selection: [],
      };
    }),
  duplicate: () =>
    set((s) => {
      const ids = new Set(s.selection);
      let changed = true;
      while (changed) {
        changed = false;
        for (const o of s.scene.objects)
          if (o.parent && ids.has(o.parent) && !ids.has(o.id)) {
            ids.add(o.id);
            changed = true;
          }
      }
      const mapping = new Map([...ids].map((id) => [id, crypto.randomUUID()]));
      const copies = s.scene.objects
        .filter((o) => ids.has(o.id))
        .map((o) => ({
          ...structuredClone(o),
          id: mapping.get(o.id)!,
          source_id: o.source_id ?? o.id,
          parent: o.parent ? (mapping.get(o.parent) ?? o.parent) : null,
          position: [
            o.position[0] + (o.parent && ids.has(o.parent) ? 0 : 2),
            o.position[1],
            o.position[2],
          ] as [number, number, number],
        }));
      return {
        scene: { ...s.scene, objects: [...s.scene.objects, ...copies] },
        past: [...s.past.slice(-29), s.scene],
        future: [],
        selection: copies.map((o) => o.id),
        selected: copies.at(-1)?.id ?? null,
      };
    }),
  undo: () =>
    set((s) =>
      s.past.length
        ? {
            scene: s.past.at(-1)!,
            past: s.past.slice(0, -1),
            future: [s.scene, ...s.future],
          }
        : s,
    ),
  redo: () =>
    set((s) =>
      s.future.length
        ? {
            scene: s.future[0],
            future: s.future.slice(1),
            past: [...s.past, s.scene],
          }
        : s,
    ),
}));
