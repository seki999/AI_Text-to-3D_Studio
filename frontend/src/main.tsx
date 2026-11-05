import React, { useState, useEffect, useCallback, useRef } from "react";
import { createRoot } from "react-dom/client";
import { Viewer } from "./Viewer";
import { useStudio, empty } from "./store";
import { api, downloadText } from "./api";
import type { Scene, Job } from "./types";
import "./style.css";

const initial =
  "生成一栋日本两层独立住宅，白色外墙、灰色双坡屋顶、四个正面窗户、一个入口、二楼阳台。";
function App() {
  const { scene, selected, setScene, select, edit, undo, redo, past, future } =
    useStudio();
  const [text, setText] = useState(initial),
    [provider, setProvider] = useState("rule"),
    [error, setError] = useState(""),
    [status, setStatus] = useState("准备就绪"),
    [busy, setBusy] = useState(false),
    [url, setUrl] = useState<string | null>(null),
    [model, setModel] = useState<string | null>(null),
    [format, setFormat] = useState("glb"),
    [job, setJob] = useState<Job | null>(null),
    [warnings, setWarnings] = useState<string[]>([]),
    [raw, setRaw] = useState(""),
    [showJSON, setShowJSON] = useState(false),
    [projects, setProjects] = useState<any[]>([]),
    [history, setHistory] = useState<any[]>([]),
    [project, setProject] = useState<string | null>(null),
    [library, setLibrary] = useState(false),
    [stats, setStats] = useState<any>(null),
    [health, setHealth] = useState<boolean | null>(null);
  const [grid, setGrid] = useState(true),
    [axes, setAxes] = useState(true),
    [wire, setWire] = useState(false),
    [ortho, setOrtho] = useState(false),
    [view, setView] = useState("perspective"),
    [reset, setReset] = useState(0),
    [shot, setShot] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const current = scene.objects.find((o) => o.id === selected);
  const ready = useCallback(() => setStatus("模型已加载 · 拖动旋转查看"), []);
  const refresh = async () => {
    setProjects(await api<any[]>("/projects"));
    setHistory(await api<any[]>("/jobs"));
  };
  useEffect(() => {
    api<{ blender_available: boolean }>("/health")
      .then((h) => setHealth(h.blender_available))
      .catch(() => setError("无法连接后端，请启动 FastAPI"));
    refresh().catch(() => {});
    const stored = localStorage.getItem("studio-scene");
    if (stored)
      try {
        setScene(JSON.parse(stored));
      } catch {}
  }, []);
  useEffect(
    () => localStorage.setItem("studio-scene", JSON.stringify(scene)),
    [scene],
  );
  useEffect(() => {
    if (!job || !["pending", "running"].includes(job.status)) return;
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const next = await api<Job>("/jobs/" + job.id);
        if (!active) return;
        setJob(next);
        if (next.status === "completed") {
          setModel(next.model_id!);
          setFormat("glb");
          setUrl("/api/models/" + next.model_id + "/download?format=glb");
          setStatus("正在加载 GLB…");
          const asset = await api<any>("/models/" + next.model_id);
          setStats(asset.stats);
          refresh();
        } else if (next.status === "failed") {
          setError(next.error || "生成失败");
          setBusy(false);
          setStatus("生成失败");
        }
      } catch (e) {
        if (active) {
          setError(String(e));
          setBusy(false);
          setJob(null);
        }
      }
    }, 700);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [job]);
  useEffect(() => {
    if (job?.status === "completed") setBusy(false);
  }, [job]);
  async function parse() {
    setBusy(true);
    setError("");
    setStatus("正在解析描述…");
    try {
      const result = await api<{ scene: Scene; warnings: string[] }>(
        "/parse-text",
        "POST",
        { text, provider },
      );
      setScene(result.scene);
      select(result.scene.objects[0]?.id || null);
      setWarnings(result.warnings);
      setStatus("解析完成 · 请检查参数后生成");
    } catch (e) {
      setError(String(e));
      setStatus("解析失败");
    } finally {
      setBusy(false);
    }
  }
  async function generate() {
    setBusy(true);
    setError("");
    setStatus("正在生成真实 Mesh…");
    try {
      const result = await api<{ job_id: string }>(
        "/generate-model",
        "POST",
        scene,
      );
      setJob({
        id: result.job_id,
        status: "pending",
        progress: 0,
        error: null,
      });
    } catch (e) {
      setError(String(e));
      setBusy(false);
      setStatus("生成失败");
    }
  }
  async function save() {
    try {
      const result = await api<{ id: string }>(
        "/projects" + (project ? "/" + project : ""),
        project ? "PUT" : "POST",
        { name: scene.name, scene, prompt: text, model_id: model },
      );
      setProject(result.id);
      setStatus("项目已保存到 SQLite");
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }
  async function importFile(file: File) {
    if (file.size > 50 * 1024 * 1024) {
      setError("文件上限 50 MB");
      return;
    }
    const ext = file.name.split(".").at(-1)?.toLowerCase();
    try {
      if (ext === "json") {
        const data = JSON.parse(await file.text());
        setScene(await api<Scene>("/validate-scene", "POST", data));
        setStatus("Scene JSON 已导入，请生成模型");
      } else if (["glb", "gltf", "obj"].includes(ext || "")) {
        if (url?.startsWith("blob:")) URL.revokeObjectURL(url);
        setUrl(URL.createObjectURL(file));
        setFormat(ext!);
        setModel(null);
        setScene(empty);
        select(null);
        setStats(null);
        setStatus("正在加载导入模型…");
        setWarnings([
          "外部模型不恢复程序化参数。GLTF 需内嵌资源；OBJ 仅导入几何，暂不支持伴随 MTL。",
        ]);
      } else throw Error("支持 JSON、GLB、内嵌 GLTF、OBJ");
    } catch (e) {
      setError("导入失败：" + String(e));
    }
  }
  const param = (key: string, value: string | number | boolean) =>
    current &&
    edit(current.id, { parameters: { ...current.parameters, [key]: value } });
  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="logo">◈</span> FORMA <small>TEXT TO 3D STUDIO</small>
        </div>
        <nav>
          <button
            onClick={() => {
              setScene(empty);
              setUrl(null);
              setModel(null);
              setProject(null);
              select(null);
              setStats(null);
            }}
          >
            ＋ 新建
          </button>
          <button
            onClick={() => {
              refresh();
              setLibrary(!library);
            }}
          >
            打开项目
          </button>
          <button onClick={save}>保存</button>
          <span className="separator" />
          <button onClick={() => input.current?.click()}>↥ 导入</button>
          <button
            onClick={() =>
              downloadText(JSON.stringify(scene, null, 2), "scene.json")
            }
          >
            ↓ JSON
          </button>
          <button
            disabled={!model}
            onClick={() =>
              window.location.assign(
                "/api/models/" + model + "/download?format=glb",
              )
            }
          >
            ↓ GLB
          </button>
          <button
            disabled={!model}
            onClick={() =>
              window.location.assign(
                "/api/models/" + model + "/download?format=obj",
              )
            }
          >
            ↓ OBJ
          </button>
        </nav>
        <span className="local">● 本地工作空间</span>
      </header>
      <div className="workspace">
        <aside className="left">
          <div className="section-title">
            创作工作台 <span>01</span>
          </div>
          <h1>
            让想象，
            <br />
            <em>拥有形状。</em>
          </h1>
          <p className="muted">从一句描述开始，构建真实三维世界。</p>
          <label>
            描述你的模型 <span>中文 / EN / 日本語</span>
          </label>
          <textarea
            aria-label="文字描述"
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={4000}
          />
          <div className="examples">
            <button onClick={() => setText("生成一个红色立方体，边长2米。")}>
              红色立方体
            </button>
            <button
              onClick={() => setText("生成一个蓝色圆柱体，高度3米，半径1米。")}
            >
              蓝色圆柱
            </button>
            <button onClick={() => setText(initial)}>日式住宅</button>
          </div>
          <label>
            解析引擎 <span>PROVIDER</span>
          </label>
          <select
            aria-label="解析引擎"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            <option value="rule">规则解析 · 无需 API Key</option>
            <option value="openai">OpenAI Compatible · 服务端配置</option>
            <option value="ollama">Ollama · 本地模型</option>
          </select>
          <button
            className="secondary wide"
            disabled={busy || !text.trim()}
            onClick={parse}
          >
            ① 解析为 Scene JSON <span>↗</span>
          </button>
          <button
            className="primary wide"
            disabled={busy || !scene.objects.length}
            onClick={generate}
          >
            {busy ? "处理中…" : "② 生成 3D 模型"} <span>✦</span>
          </button>
          <div className="hint">描述 → 参数确认 → Blender Mesh → GLB</div>
          {health === false && (
            <div className="warning">
              未检测到 Blender。可解析、编辑及保存参数；生成需要安装 Blender
              并配置 BLENDER_PATH。
            </div>
          )}
          <div className="section-title spaced">
            场景数据{" "}
            <button
              onClick={() => {
                setRaw(JSON.stringify(scene, null, 2));
                setShowJSON(!showJSON);
              }}
            >
              JSON ↗
            </button>
          </div>
          <label>项目名称</label>
          <input
            aria-label="项目名称"
            value={scene.name}
            onChange={(e) => setScene({ ...scene, name: e.target.value })}
          />
          <p className="muted tiny">
            Y-up 坐标 · 米 · 角度制
            <br />
            参数变更后请点击“生成 3D 模型”重建。
          </p>
          {warnings.map((w) => (
            <div className="warning" key={w}>
              {w}
            </div>
          ))}
          <div className="section-title spaced">
            最近生成 <span>{history.length}</span>
          </div>
          {history.slice(0, 5).map((h) => (
            <button
              className="history"
              key={h.id}
              disabled={h.status !== "completed"}
              onClick={async () => {
                setModel(h.id);
                setFormat("glb");
                setUrl("/api/models/" + h.id + "/download?format=glb");
                const asset = await api<any>("/models/" + h.id);
                setStats(asset.stats);
                setScene(asset.scene);
              }}
            >
              <span>◇ {h.id.slice(0, 8)}</span>
              <small>{h.status}</small>
            </button>
          ))}
        </aside>
        <main>
          <div className="viewport-bar">
            <span>
              <i /> 场景视图 <small> / {scene.name}</small>
            </span>
            <div>
              <button disabled={!past.length} onClick={undo}>
                ↶
              </button>
              <button disabled={!future.length} onClick={redo}>
                ↷
              </button>
              <button onClick={() => setReset(reset + 1)}>适配视角</button>
              <button onClick={() => setShot(shot + 1)}>截图 PNG</button>
            </div>
          </div>
          <div className="viewport">
            <Viewer
              {...{ url, format, grid, axes, wire, ortho, view, reset, shot }}
              onError={setError}
              onReady={ready}
            />
            {!url && (
              <div className="empty">
                <div className="empty-cube">◇</div>
                <h2>你的下一个创意，从这里开始</h2>
                <p>输入描述，解析参数，再生成真实 3D 模型</p>
                <small>或导入 GLB / GLTF / OBJ 文件</small>
              </div>
            )}
            <div className="view-label">
              {ortho ? "ORTHOGRAPHIC" : "PERSPECTIVE"}
              <span>Y ↑</span>
            </div>
            <div className="view-tools">
              <select
                aria-label="视角"
                value={view}
                onChange={(e) => setView(e.target.value)}
              >
                {[
                  ["perspective", "自由视角"],
                  ["front", "正面"],
                  ["back", "背面"],
                  ["left", "左侧"],
                  ["right", "右侧"],
                  ["top", "顶部"],
                ].map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
              <button
                className={grid ? "active" : ""}
                onClick={() => setGrid(!grid)}
              >
                网格
              </button>
              <button
                className={axes ? "active" : ""}
                onClick={() => setAxes(!axes)}
              >
                坐标轴
              </button>
              <button
                className={wire ? "active" : ""}
                onClick={() => setWire(!wire)}
              >
                线框
              </button>
              <button
                className={ortho ? "active" : ""}
                onClick={() => setOrtho(!ortho)}
              >
                正交
              </button>
            </div>
            <div className="mouse-help">
              左键 旋转 <b>·</b> 滚轮 缩放 <b>·</b> 右键 平移
            </div>
          </div>
          <div className="timeline">
            <span className="accent">✦</span>
            <div>
              <strong>{status}</strong>
              <p>
                {job && ["running", "pending"].includes(job.status)
                  ? `任务 ${job.id.slice(0, 8)} · ${job.progress}%`
                  : "所有生成结果保存在本地设备"}
              </p>
            </div>
            {stats && (
              <div className="stats">
                {stats.meshes} Mesh <span> / </span>
                {stats.triangles?.toLocaleString()} 三角面
              </div>
            )}
          </div>
          {error && (
            <div role="alert" className="error">
              {error}
              <button onClick={() => setError("")}>×</button>
            </div>
          )}
        </main>
        <aside className="right">
          <div className="section-title">
            场景对象{" "}
            <span>{String(scene.objects.length).padStart(2, "0")}</span>
          </div>
          <div className="tree">
            <p className="muted tiny">▾ {scene.name}</p>
            {scene.objects.map((o) => (
              <button
                className={selected === o.id ? "selected" : ""}
                key={o.id}
                onClick={() => select(o.id)}
              >
                <span>◇</span>
                {o.name}
                <small>{o.type}</small>
              </button>
            ))}
            {!scene.objects.length && (
              <p className="muted tiny">解析描述后，对象将在这里显示</p>
            )}
          </div>
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
                <button
                  onClick={() => {
                    const id = crypto.randomUUID();
                    setScene({
                      ...scene,
                      objects: [
                        ...scene.objects,
                        {
                          ...structuredClone(current),
                          id,
                          position: [
                            current.position[0] + 2,
                            ...current.position.slice(1),
                          ] as [number, number, number],
                        },
                      ],
                    });
                    select(id);
                  }}
                >
                  复制
                </button>
                <button
                  onClick={() => {
                    setScene({
                      ...scene,
                      objects: scene.objects
                        .filter((o) => o.id !== current.id)
                        .map((o) =>
                          o.parent === current.id ? { ...o, parent: null } : o,
                        ),
                    });
                    select(null);
                  }}
                >
                  删除
                </button>
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
                            const v = [...current[key]] as [
                              number,
                              number,
                              number,
                            ];
                            v[j] = Number(e.target.value);
                            edit(current.id, { [key]: v });
                          }}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              <div className="section-title spaced">
                程序化参数 <span>需重建</span>
              </div>
              {Object.entries(current.parameters)
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
      </div>
      <footer>
        <span>
          <i /> {busy ? "处理中" : "工作空间已就绪"}
        </span>
        <span>
          Blender {health ? "已连接" : "未连接"} <b>·</b> Scene v1.0 <b>·</b>{" "}
          本地优先
        </span>
      </footer>
      <input
        ref={input}
        type="file"
        hidden
        accept=".json,.glb,.gltf,.obj"
        onChange={(e) => {
          if (e.target.files?.[0]) importFile(e.target.files[0]);
          e.target.value = "";
        }}
      />
      {showJSON && (
        <div className="modal">
          <div className="dialog">
            <h2>Scene JSON · 参数预览</h2>
            <textarea value={raw} onChange={(e) => setRaw(e.target.value)} />
            <div className="row">
              <button onClick={() => setShowJSON(false)}>关闭</button>
              <button
                className="primary"
                onClick={async () => {
                  try {
                    const validated = await api<Scene>(
                      "/validate-scene",
                      "POST",
                      JSON.parse(raw),
                    );
                    setScene(validated);
                    setShowJSON(false);
                  } catch (e) {
                    setError(String(e));
                  }
                }}
              >
                校验并应用
              </button>
            </div>
          </div>
        </div>
      )}
      {library && (
        <div className="modal">
          <div className="dialog">
            <h2>本地项目</h2>
            {projects.map((p) => (
              <div className="project" key={p.id}>
                <button
                  onClick={() => {
                    setScene(JSON.parse(p.scene));
                    setText(p.prompt);
                    setProject(p.id);
                    setFormat("glb");
                    setModel(p.model_id);
                    setUrl(
                      p.model_id
                        ? "/api/models/" + p.model_id + "/download?format=glb"
                        : null,
                    );
                    setLibrary(false);
                  }}
                >
                  {p.name}
                  <small>{p.updated}</small>
                </button>
                <button
                  onClick={async () => {
                    await api("/projects/" + p.id, "DELETE");
                    refresh();
                  }}
                >
                  删除
                </button>
              </div>
            ))}
            {!projects.length && <p>尚无保存的项目</p>}
            <button onClick={() => setLibrary(false)}>关闭</button>
          </div>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
