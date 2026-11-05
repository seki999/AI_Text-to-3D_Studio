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
  past: Scene[];
  future: Scene[];
  setScene: (s: Scene) => void;
  select: (id: string | null) => void;
  edit: (id: string, patch: Partial<Object3DData>) => void;
  undo: () => void;
  redo: () => void;
};
export const useStudio = create<State>((set) => ({
  scene: empty,
  selected: null,
  past: [],
  future: [],
  setScene: (scene) =>
    set((s) => ({ scene, past: [...s.past.slice(-29), s.scene], future: [] })),
  select: (selected) => set({ selected }),
  edit: (id, patch) =>
    set((s) => ({
      scene: {
        ...s.scene,
        objects: s.scene.objects.map((o) =>
          o.id === id ? { ...o, ...patch } : o,
        ),
      },
      past: [...s.past.slice(-29), s.scene],
      future: [],
    })),
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
