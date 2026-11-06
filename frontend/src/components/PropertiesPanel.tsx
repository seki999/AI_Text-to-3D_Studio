import { SceneTree } from "./SceneTree";
import { useStudio } from "../store";
import { MaterialEditor } from "./MaterialEditor";
import { FacadeEditor } from "./FacadeEditor";
import { AssetInfo } from "./AssetInfo";
export function PropertiesPanel({
  setError,
}: {
  setError: (s: string) => void;
}) {
  const { scene, selected, setScene, select, edit } = useStudio();
  const current = scene.objects.find((o) => o.id === selected);
  const param = (key: string, value: string | number | boolean) =>
    current &&
    edit(current.id, { parameters: { ...current.parameters, [key]: value } });
  return (
    <aside className="right">
      <SceneTree />{" "}
      <div className="section-title spaced">
        对象属性 <span>PROPERTIES</span>
      </div>
      {current ? (
        <>
          <label>名称</label>
          <input
            value={current.name}
            onChange={(e) => edit(current.id, { name: e.target.value })}
          />
          <label>
            <input
              aria-label="锁定对象"
              type="checkbox"
              checked={!!current.locked}
              onChange={(e) => edit(current.id, { locked: e.target.checked })}
            />
            锁定对象
          </label>
          <div className="row">
            <label>
              <input
                type="checkbox"
                checked={current.visible}
                onChange={(e) =>
                  edit(current.id, { visible: e.target.checked })
                }
              />{" "}
              可见
            </label>
            <button onClick={() => useStudio.getState().duplicate()}>
              复制
            </button>
            <button onClick={() => useStudio.getState().remove()}>删除</button>
          </div>
          {(["position", "rotation", "scale"] as const).map((key, i) => (
            <div key={key}>
              <label>{["位置 · m", "旋转 · °", "缩放"][i]}</label>
              <div className="vector">
                {current[key].map((value, j) => (
                  <div key={j}>
                    <span className={"axis-" + j}>{"XYZ"[j]}</span>
                    <input
                      aria-label={key + "-" + "XYZ"[j]}
                      type="number"
                      step="0.1"
                      value={value}
                      onChange={(e) => {
                        const v = [...current[key]] as [number, number, number];
                        v[j] = Number(e.target.value);
                        edit(current.id, { [key]: v });
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}
          <MaterialEditor object={current} />
          {current.asset && <AssetInfo asset={current.asset} />}
          {current.type === "house" && (
            <FacadeEditor object={current} onError={setError} />
          )}
          <div className="section-title spaced">
            程序化参数{" "}
            <span>{current.asset ? "AI Mesh 不反推参数" : "需重建"}</span>
          </div>
          {Object.entries(current.parameters)
            .filter(() => !current.asset)
            .filter(([, v]) => typeof v !== "object")
            .filter(([k]) =>
              current.type === "house"
                ? !["radius", "height", "color"].includes(k)
                : ![
                    "floors",
                    "floor_height",
                    "roof_type",
                    "roof_angle",
                    "wall_color",
                    "roof_color",
                    "windows",
                    "doors",
                    "balcony",
                    "steps",
                    "garage",
                    "yard",
                    "style",
                  ].includes(k),
            )
            .map(([k, v]) => (
              <div className="param" key={k}>
                <label>
                  {(
                    {
                      width: "宽度",
                      depth: "深度",
                      height: "高度",
                      radius: "半径",
                      floors: "楼层",
                      floor_height: "层高",
                      roof_type: "屋顶类型",
                      roof_angle: "屋顶倾角",
                      wall_color: "墙体颜色",
                      roof_color: "屋顶颜色",
                      windows: "窗户数量",
                      doors: "入口数量",
                      balcony: "阳台",
                      steps: "台阶",
                      garage: "车库",
                      yard: "院子",
                      style: "风格",
                      color: "颜色",
                    } as Record<string, string>
                  )[k] || k}
                </label>
                {typeof v === "boolean" ? (
                  <input
                    type="checkbox"
                    checked={v}
                    onChange={(e) => param(k, e.target.checked)}
                  />
                ) : k.includes("color") ? (
                  <input
                    aria-label={k}
                    type="color"
                    value={String(v)}
                    onChange={(e) => param(k, e.target.value)}
                  />
                ) : k === "roof_type" ? (
                  <select
                    value={String(v)}
                    onChange={(e) => param(k, e.target.value)}
                  >
                    {["flat", "gable", "shed", "hip"].map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </select>
                ) : k === "style" ? (
                  <select
                    value={String(v)}
                    onChange={(e) => param(k, e.target.value)}
                  >
                    <option>japanese</option>
                    <option>modern</option>
                  </select>
                ) : k === "balcony_facade" ? (
                  <select
                    value={String(v)}
                    onChange={(e) => param(k, e.target.value)}
                  >
                    {["front", "back", "left", "right"].map((k) => (
                      <option key={k}>{k}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="number"
                    value={Number(v)}
                    onChange={(e) => param(k, Number(e.target.value))}
                  />
                )}
              </div>
            ))}
        </>
      ) : (
        <div className="property-empty">
          选择场景中的对象
          <br />
          查看和编辑属性
        </div>
      )}
    </aside>
  );
}
