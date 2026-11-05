import { useEffect, useState } from "react";
import type { Object3DData } from "../types";
import { useStudio } from "../store";
import { api } from "../api";
export function FacadeEditor({
  object,
  onError,
}: {
  object: Object3DData;
  onError: (s: string) => void;
}) {
  const [raw, setRaw] = useState("");
  useEffect(
    () =>
      setRaw(
        JSON.stringify(
          object.parameters.facades ?? {
            front: [],
            back: [],
            left: [],
            right: [],
          },
          null,
          2,
        ),
      ),
    [object.id, object.parameters.facades],
  );
  return (
    <section>
      <div className="section-title spaced">
        四面墙开口 <span>需 Blender 重建</span>
      </div>
      <p className="muted tiny">
        各面独立数组；floor 从 0 起，x 为墙面水平坐标，sill
        为该层窗台高度。未启用时保留旧 windows / doors。
      </p>
      <textarea
        aria-label="墙面开口 JSON"
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        style={{ height: 180, fontFamily: "monospace", fontSize: 10 }}
      />
      <button
        onClick={async () => {
          try {
            const s = useStudio.getState().scene;
            const next = {
              ...s,
              objects: s.objects.map((o) =>
                o.id === object.id
                  ? {
                      ...o,
                      parameters: { ...o.parameters, facades: JSON.parse(raw) },
                    }
                  : o,
              ),
            };
            useStudio
              .getState()
              .setScene(await api("/validate-scene", "POST", next));
          } catch (e) {
            onError(String(e));
          }
        }}
      >
        验证并应用开口
      </button>
      <button
        onClick={() =>
          useStudio.getState().edit(object.id, {
            parameters: { ...object.parameters, facades: null },
          })
        }
      >
        恢复旧版开口
      </button>
      <p className="muted tiny">视觉与概念设计模型，不保证建筑施工精度。</p>
    </section>
  );
}
