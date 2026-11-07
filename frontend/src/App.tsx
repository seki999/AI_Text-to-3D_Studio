import React, { useState, useEffect, useCallback, useRef } from "react";
import { PropertiesPanel } from "./components/PropertiesPanel";
import { PromptPanel } from "./components/PromptPanel";
import { Viewer } from "./Viewer";
import { useStudio, empty } from "./store";
import { api, downloadText } from "./api";
import type { Scene, Job, Project, ModelStats, ModelAsset } from "./types";
import "./style.css";
import { chooseEngine, type Engine } from "./engines/native";
import { ExportPanel } from "./components/ExportPanel";
import { EditToolbar } from "./components/EditToolbar";
import { defaultOllama } from "./components/ProviderSettings";
import { StoragePanel } from "./components/StoragePanel";
import * as THREE from "three";
import { getExportModel } from "./services/export";
import { exportGLTF } from "./services/export";
import type { EditingOptions } from "./viewer/EditingControls";
import { AssetLibrary, StudioSettings, FirstRun } from "./components/StudioTools";
import { GenerativePanel } from "./components/GenerativePanel";
import { prepareAssetInsertion } from "./services/insertAsset";

const initial =
  "生成一栋日本两层独立住宅，白色外墙、灰色双坡屋顶、四个正面窗户、一个入口、二楼阳台。";
export default function App() {
  const [workspace, setWorkspace] = useState<"parametric" | "generative" | "library" | "settings">(
      "parametric",
    ),
    [preserveScene, setPreserveScene] = useState(false);
  const [ollama, setOllama] = useState(defaultOllama);
  const [engine, setEngine] = useState<Engine>("auto"),
    [nativeActive, setNativeActive] = useState(false),
    [hasModel, setHasModel] = useState(false);
  const [editing, setEditing] = useState<EditingOptions>({
    mode: "translate",
    space: "world",
    snap: false,
    focus: 0,
  });
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
    [projects, setProjects] = useState<Project[]>([]),
    [history, setHistory] = useState<Job[]>([]),
    [project, setProject] = useState<string | null>(null),
    [library, setLibrary] = useState(false),
    [stats, setStats] = useState<ModelStats | null>(null),
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
  const ready = useCallback(() => {
    setHasModel(true);
    const root = getExportModel();
    if (root) {
      let meshes = 0,
        vertices = 0,
        triangles = 0;
      root.traverse((n) => {
        if (n instanceof THREE.Mesh) {
          meshes++;
          vertices += n.geometry.attributes.position?.count ?? 0;
          triangles +=
            (n.geometry.index?.count ??
              n.geometry.attributes.position?.count ??
              0) / 3;
        }
      });
      setStats((previous) => ({ ...previous, meshes, vertices, triangles }));
    }
    setStatus("模型已加载 · 拖动旋转查看");
  }, []);
  const refresh = async () => {
    setProjects(await api<Project[]>("/projects"));
    setHistory(await api<Job[]>("/jobs"));
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
          const asset = await api<ModelAsset>("/models/" + next.model_id);
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
    if (job?.status === "cancelled") {
      setBusy(false);
      setStatus("生成已取消");
    }
  }, [job]);
  async function parse() {
    setBusy(true);
    setError("");
    setStatus("正在解析描述…");
    try {
      const result = await api<{
        scene: Scene;
        warnings: string[];
        elapsed_ms?: number;
      }>("/parse-text", "POST", {
        text,
        provider,
        ...(provider === "ollama" ? { ollama } : {}),
      });
      setNativeActive(false);
      setUrl(null);
      setHasModel(false);
      setModel(null);
      setScene(result.scene);
      select(result.scene.objects[0]?.id || null);
      setWarnings([
        ...result.warnings,
        `解析耗时 ${result.elapsed_ms ?? 0} ms`,
      ]);
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
      const validated = await api<Scene>("/validate-scene", "POST", scene);
      setScene(validated);
      if (chooseEngine(validated, engine) === "native") {
        setStats(null);
        setNativeActive(true);
        setUrl(null);
        setModel(null);
        setJob(null);
        setBusy(false);
        setStatus("Native 模型已生成");
        return;
      }
      setNativeActive(false);
      const result = await api<{ job_id: string }>(
        "/generate-model",
        "POST",
        validated,
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
      let savedModel = model;
      if (hasModel) {
        const buffer = (await exportGLTF(
          true,
          getExportModel(),
          true,
        )) as ArrayBuffer;
        const bytes = new Uint8Array(buffer);
        let binary = "";
        for (let i = 0; i < bytes.length; i += 32768)
          binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
        const snapshot = await api<{ id: string }>("/models/snapshot", "POST", {
          scene,
          glb: btoa(binary),
        });
        savedModel = snapshot.id;
        setModel(savedModel);
      }
      const result = await api<{ id: string }>(
        "/projects" + (project ? "/" + project : ""),
        project ? "PUT" : "POST",
        { name: scene.name, scene, prompt: text, model_id: savedModel },
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
        setNativeActive(false);
        setUrl(null);
        setHasModel(false);
        setModel(null);
        setScene(await api<Scene>("/validate-scene", "POST", data));
        setStatus("Scene JSON 已导入，请生成模型");
      } else if (["glb", "gltf", "obj"].includes(ext || "")) {
        setPreserveScene(false);
        setNativeActive(false);
        setHasModel(false);
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
  async function insertAIAsset(id: string) {
    setError("");
    const prepared = await prepareAssetInsertion(id);
    if (url?.startsWith("blob:")) URL.revokeObjectURL(url);
    setNativeActive(false);
    setPreserveScene(true);
    setHasModel(false);
    setModel(null);
    setFormat("glb");
    setUrl(prepared.url);
    setScene(prepared.scene);
    select(prepared.selected);
    setStatus("正在加载 AI 资产 Mesh…");
  }
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
              setNativeActive(false);
              setHasModel(false);
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
          <ExportPanel enabled={hasModel} onError={setError} />
        </nav>
        <span className="local">● 本地工作空间</span>
      </header>
      <FirstRun />
      <div className="workspace">
        <aside className="left">
          <div className="workspace-tabs">
            <button
              className={workspace === "parametric" ? "primary" : ""}
              onClick={() => setWorkspace("parametric")}
            >
              参数化建模
            </button>
            <button
              className={workspace === "generative" ? "primary" : ""}
              onClick={() => setWorkspace("generative")}
            >
              Generative AI
            </button>
          </div>
          <div className="row"><button onClick={() => setWorkspace("library")}>资产库</button><button onClick={() => setWorkspace("settings")}>设置 / 验收</button></div>
          {workspace === "library" ? <AssetLibrary onInsert={insertAIAsset} onError={setError} /> : workspace === "settings" ? <StudioSettings onInsert={insertAIAsset} onError={setError} /> : workspace === "generative" ? (
            <GenerativePanel onInsert={insertAIAsset} onError={setError} />
          ) : (
            <PromptPanel
              {...{
                text,
                setText,
                provider,
                setProvider,
                ollama,
                setOllama,
                engine,
                setEngine,
                busy,
                health,
                parse,
                generate,
              }}
              hasObjects={!!scene.objects.length}
            />
          )}{" "}
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
          <StoragePanel />
          <div className="section-title spaced">
            最近生成 <span>{history.length}</span>
          </div>
          {history.slice(0, 5).map((h) => (
            <button
              className="history"
              key={h.id}
              disabled={h.status !== "completed"}
              onClick={async () => {
                setNativeActive(false);
                setModel(h.id);
                setFormat("glb");
                setUrl("/api/models/" + h.id + "/download?format=glb");
                const asset = await api<ModelAsset>("/models/" + h.id);
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
          <EditToolbar options={editing} setOptions={setEditing} />
          <div className="viewport">
            <Viewer
              preserveScene={preserveScene}
              nativeActive={nativeActive}
              editing={editing}
              {...{ url, format, grid, axes, wire, ortho, view, reset, shot }}
              onError={setError}
              onReady={ready}
            />
            {!url && !nativeActive && (
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
            {job && ["pending", "running"].includes(job.status) && (
              <button
                onClick={async () => {
                  try {
                    setJob(
                      await api<Job>("/jobs/" + job.id + "/cancel", "POST"),
                    );
                  } catch (e) {
                    setError(String(e));
                  }
                }}
              >
                取消生成
              </button>
            )}
            {job?.status === "failed" && (
              <button
                onClick={async () => {
                  const r = await api<{ log: string }>(
                    "/jobs/" + job.id + "/log",
                  );
                  setError(r.log);
                }}
              >
                查看失败日志
              </button>
            )}
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
        <PropertiesPanel setError={setError} />
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
                    setNativeActive(
                      !p.model_id &&
                        !JSON.parse(p.scene).objects.some(
                          (o: { type: string }) =>
                            o.type === "house" || o.type === "imported",
                        ),
                    );
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
