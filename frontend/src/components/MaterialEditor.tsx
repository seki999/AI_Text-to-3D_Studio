import type { PBR, Object3DData } from "../types";
import { useStudio } from "../store";
const presets: Record<string, Partial<PBR>> = {
  Matte: { metalness: 0, roughness: 0.9, opacity: 1, transparent: false },
  Metal: { metalness: 1, roughness: 0.22, opacity: 1, transparent: false },
  Glass: {
    metalness: 0,
    roughness: 0.05,
    opacity: 0.28,
    transparent: true,
    doubleSided: true,
  },
  Plastic: { metalness: 0, roughness: 0.3, opacity: 1, transparent: false },
  "Wood-like": {
    metalness: 0,
    roughness: 0.8,
    baseColor: "#8b6043",
    transparent: false,
    opacity: 1,
  },
};
export function MaterialEditor({ object }: { object: Object3DData }) {
  const material: PBR = {
    baseColor: String(
      object.parameters[object.type === "house" ? "wall_color" : "color"] ??
        "#dc7355",
    ),
    metalness: 0,
    roughness: 0.6,
    opacity: 1,
    transparent: false,
    doubleSided: false,
    emissive: "#000000",
    ...object.material,
  };
  const change = (patch: Partial<PBR>) =>
    useStudio
      .getState()
      .edit(object.id, { material: { ...material, ...patch } });
  return (
    <section>
      <div className="section-title spaced">
        PBR 材质 <span>实时 / 导出保留</span>
      </div>
      <button
        onClick={() =>
          useStudio.getState().edit(object.id, { material: undefined })
        }
      >
        恢复模型原始材质
      </button>
      <select
        aria-label="材质预设"
        defaultValue=""
        onChange={(e) => {
          if (presets[e.target.value]) change(presets[e.target.value]);
        }}
      >
        <option value="">选择预设</option>
        {Object.keys(presets).map((k) => (
          <option key={k}>{k}</option>
        ))}
      </select>
      {(Object.keys(material) as (keyof PBR)[]).map((k) => (
        <div className="param" key={k}>
          <label>{k}</label>
          {typeof material[k] === "boolean" ? (
            <input
              aria-label={"material-" + k}
              type="checkbox"
              checked={Boolean(material[k])}
              onChange={(e) => change({ [k]: e.target.checked })}
            />
          ) : typeof material[k] === "string" ? (
            <input
              aria-label={"material-" + k}
              type="color"
              value={String(material[k])}
              onChange={(e) => change({ [k]: e.target.value })}
            />
          ) : (
            <input
              aria-label={"material-" + k}
              type="number"
              min="0"
              max="1"
              step=".05"
              value={Number(material[k])}
              onChange={(e) => change({ [k]: Number(e.target.value) })}
            />
          )}
        </div>
      ))}
      <p className="muted tiny">Wood-like 仅为纯色粗糙材质，无木纹贴图。</p>
    </section>
  );
}
