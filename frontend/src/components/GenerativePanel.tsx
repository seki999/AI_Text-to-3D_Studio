import { useEffect, useState } from "react";
import { api } from "../api";
import type { AIEngine, AIImage, AIJob } from "../types";
type Status = {
  available: boolean;
  worker_connected: boolean;
  errors: string[];
  texture_ready: boolean;
};
type Diagnosis = {
  hardware: Record<string, unknown>;
  worker: Status & Record<string, unknown>;
  requirements: Record<string, unknown>;
};
export function GenerativePanel({
  onInsert,
  onError,
}: {
  onInsert: (id: string) => Promise<void>;
  onError: (s: string) => void;
}) {
  const [mode, setMode] = useState<"image" | "text">("image"),
    [prompt, setPrompt] = useState("生成一条有翅膀的红色幻想龙。"),
    [engines, setEngines] = useState<AIEngine[]>([]),
    [engine, setEngine] = useState("hunyuan3d-2.1"),
    [status, setStatus] = useState<Status | null>(null),
    [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null),
    [image, setImage] = useState<AIImage | null>(null),
    [confirmed, setConfirmed] = useState(false),
    [license, setLicense] = useState(false),
    [mockAck, setMockAck] = useState(false),
    [textConsent, setTextConsent] = useState(false),
    [provider, setProvider] = useState<{
      configured: boolean;
      model: string | null;
      message: string;
    } | null>(null),
    [busy, setBusy] = useState(false),
    [job, setJob] = useState<AIJob | null>(null),
    [history, setHistory] = useState<AIJob[]>([]),
    [steps, setSteps] = useState(30),
    [seed, setSeed] = useState(0),
    [resolution, setResolution] = useState(256),
    [repair, setRepair] = useState(false),
    [simplify, setSimplify] = useState(false),
    [faces, setFaces] = useState(20000),
    [log, setLog] = useState("");
  const selected = engines.find((e) => e.id === engine),
    running = job && ["pending", "running"].includes(job.status);
  const refresh = () => api<AIJob[]>("/ai3d/jobs").then(setHistory);
  useEffect(() => {
    api<AIEngine[]>("/ai3d/engines")
      .then(setEngines)
      .catch((e) => onError(String(e)));
    api<typeof provider>("/ai3d/text-image/provider")
      .then(setProvider)
      .catch((e) => onError(String(e)));
    refresh().catch(() => {});
  }, []);
  useEffect(() => {
    let active = true;
    setStatus(null);
    api<Status>("/ai3d/engines/" + engine + "/status")
      .then((value) => {
        if (active) setStatus(value);
      })
      .catch((e) => {
        if (active) onError(String(e));
      });
    return () => {
      active = false;
    };
  }, [engine]);
  useEffect(() => {
    if (!job || !["pending", "running"].includes(job.status)) return;
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const next = await api<AIJob>("/ai3d/jobs/" + job.id);
        if (active) {
          setJob(next);
          if (!["pending", "running"].includes(next.status)) refresh();
        }
      } catch (e) {
        if (active) onError(String(e));
      }
    }, 700);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [job]);
  async function upload(file: File) {
    if (file.size > 10 * 1024 * 1024) {
      onError("参考图上限 10 MB");
      return;
    }
    setBusy(true);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (let i = 0; i < bytes.length; i += 32768)
        binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
      const value = await api<AIImage>("/ai3d/images", "POST", {
        data: btoa(binary),
        filename: file.name,
      });
      setImage(value);
      setConfirmed(false);
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function generate() {
    setBusy(true);
    setLog("");
    try {
      setJob(
        await api<AIJob>("/ai3d/jobs", "POST", {
          image_id: image!.id,
          engine,
          prompt,
          license_acknowledged: license,
          mock_acknowledged: mockAck,
          options: {
            seed,
            steps,
            octree_resolution: resolution,
            guidance_scale: 5,
            processing: {
              center: true,
              normalize: true,
              size: 2,
              source_up: "Y",
              repair_normals: repair,
              simplify_faces: simplify ? faces : null,
            },
          },
        }),
      );
      refresh();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="generative-panel">
      <div className="section-title">
        GENERATIVE AI <span>V0.3</span>
      </div>
      <h2>图片 → 神经网络 → Mesh</h2>
      <p className="muted tiny">
        真实引擎与参数化建模分离；无 GPU 时仍可使用原有工作台。
      </p>
      <div className="row">
        <button
          className={mode === "image" ? "primary" : ""}
          onClick={() => setMode("image")}
        >
          Image-to-3D
        </button>
        <button
          className={mode === "text" ? "primary" : ""}
          onClick={() => setMode("text")}
        >
          Text-to-3D
        </button>
      </div>
      <label>描述 / 资产备注</label>
      <textarea
        aria-label="AI 生成描述"
        value={prompt}
        maxLength={4000}
        onChange={(e) => setPrompt(e.target.value)}
      />
      {mode === "text" && (
        <div className="warning">
          <p>{provider?.message ?? "正在检查参考图服务"}</p>
          <p>
            第一步生成参考图，确认后才提交 Image-to-3D；未配置时可直接上传图片。
          </p>
          {provider?.configured && (
            <label>
              <input
                type="checkbox"
                checked={textConsent}
                onChange={(e) => setTextConsent(e.target.checked)}
              />
              确认发送描述到已配置参考图服务
            </label>
          )}
          <button
            disabled={
              busy || !provider?.configured || !textConsent || !prompt.trim()
            }
            onClick={async () => {
              setBusy(true);
              try {
                setImage(
                  await api<AIImage>("/ai3d/text-image", "POST", { prompt }),
                );
                setConfirmed(false);
              } catch (e) {
                onError(String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            生成 / 重新生成参考图
          </button>
        </div>
      )}
      <label>参考图片 · PNG / JPG / WebP</label>
      <input
        aria-label="AI 参考图片"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        disabled={busy || !!running}
        onChange={(e) => {
          if (e.target.files?.[0]) upload(e.target.files[0]);
          e.target.value = "";
        }}
      />
      {image && (
        <>
          <img
            className="reference-preview"
            alt="AI 参考图片预览"
            src={image.url}
          />
          <p className="muted tiny">
            {image.info.width} × {image.info.height} · 规范化 PNG
          </p>
          <label>
            <input
              aria-label="确认参考图"
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            确认使用这张参考图
          </label>
        </>
      )}
      <label>专业 AI 3D 引擎</label>
      <select
        aria-label="AI 3D 引擎"
        value={engine}
        disabled={!!running}
        onChange={(e) => {
          setEngine(e.target.value);
          setLicense(false);
          setMockAck(false);
        }}
      >
        {engines.map((e) => (
          <option key={e.id} value={e.id}>
            {e.name}
          </option>
        ))}
      </select>
      <label>模型 / 版本</label>
      <select
        aria-label="AI 3D 模型"
        value={selected?.models[0] ?? ""}
        disabled
      >
        {selected?.models.map((m) => (
          <option key={m}>{m}</option>
        ))}
      </select>
      {selected?.is_mock ? (
        <div className="error">
          测试模式：仅生成测试几何，非 AI 神经网络推理。
        </div>
      ) : (
        <p className="muted tiny">
          Image-to-Shape 优先；纹理在 Shape 完成后单独提交。
        </p>
      )}
      <button
        className="secondary wide"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const r = await api<Diagnosis>(
              "/ai3d/engines/" + engine + "/diagnose",
              "POST",
            );
            setDiagnosis(r);
            setStatus(r.worker);
          } catch (e) {
            onError(String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        GPU / CUDA / 模型诊断
      </button>
      {status && (
        <div className={status.available ? "hint" : "warning"}>
          {status.available
            ? selected?.is_mock
              ? "Mock 测试 Worker 可用（非 AI）"
              : "真实引擎准备就绪"
            : status.errors?.join("；") || "引擎不可用"}
        </div>
      )}
      {diagnosis && (
        <details open>
          <summary>硬件检测结果（null = Unknown）</summary>
          <pre className="diagnostics">
            {JSON.stringify(diagnosis, null, 2)}
          </pre>
        </details>
      )}
      {selected && !selected.is_mock && (
        <>
          <p className="muted tiny">
            {selected.license.name}
            <br />
            {selected.license.restrictions.join("；")}
          </p>
          <a href={selected.license.source} target="_blank" rel="noreferrer">
            查看模型许可证
          </a>
          <label>
            <input
              aria-label="确认模型许可证"
              type="checkbox"
              checked={license}
              onChange={(e) => setLicense(e.target.checked)}
            />
            已阅读并确认模型许可条件
          </label>
        </>
      )}
      {selected?.is_mock && (
        <label>
          <input
            aria-label="确认 Mock 测试模式"
            type="checkbox"
            checked={mockAck}
            onChange={(e) => setMockAck(e.target.checked)}
          />
          确认这是 Mock 测试，不是真实 AI
        </label>
      )}
      <div className="param">
        <label>扩散步数</label>
        <input
          aria-label="AI 扩散步数"
          type="number"
          min="1"
          max="100"
          value={steps}
          onChange={(e) => setSteps(Number(e.target.value))}
        />
      </div>
      <div className="param">
        <label>Seed</label>
        <input
          aria-label="AI Seed"
          type="number"
          min="0"
          value={seed}
          onChange={(e) => setSeed(Number(e.target.value))}
        />
      </div>
      <div className="param">
        <label>Octree</label>
        <select
          value={resolution}
          onChange={(e) => setResolution(Number(e.target.value))}
        >
          {[64, 128, 256, 384, 512].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>
      <label>
        <input
          type="checkbox"
          checked={repair}
          onChange={(e) => setRepair(e.target.checked)}
        />
        可选法线修复（默认关闭）
      </label>
      <label>
        <input
          type="checkbox"
          checked={simplify}
          onChange={(e) => setSimplify(e.target.checked)}
        />
        可选简化（可能改变几何，带纹理时拒绝）
      </label>
      {simplify && (
        <input
          aria-label="目标三角面"
          type="number"
          min="100"
          max="500000"
          value={faces}
          onChange={(e) => setFaces(Number(e.target.value))}
        />
      )}
      <button
        className="primary wide"
        disabled={
          busy ||
          !!running ||
          !image ||
          !confirmed ||
          !status?.available ||
          (selected?.is_mock ? !mockAck : !license)
        }
        onClick={generate}
      >
        {selected?.is_mock ? "生成 Mock 测试 Mesh" : "生成真实 AI 3D Mesh"}
      </button>
      {job && (
        <div className="ai-result">
          <strong>
            {job.is_mock ? "[Mock 测试] " : ""}
            {job.status} · {job.stage}
          </strong>
          {job.progress_kind === "diffusion_steps" && job.progress !== null ? (
            <p>实际扩散采样进度 {job.progress}%（不是整体任务百分比）</p>
          ) : (
            <p className="muted tiny">阶段状态 · 无可测百分比</p>
          )}
          {job.error && (
            <div role="alert" className="error">
              {job.error}
            </div>
          )}
          {running && (
            <button
              onClick={async () => {
                try {
                  setJob(
                    await api<AIJob>(
                      "/ai3d/jobs/" + job.id + "/cancel",
                      "POST",
                    ),
                  );
                } catch (e) {
                  onError(String(e));
                }
              }}
            >
              取消 AI 任务
            </button>
          )}
          {job.status === "completed" && job.asset_id && (
            <>
              <p>
                {job.stats?.texture_status ?? "未生成纹理"} ·{" "}
                {job.stats?.vertices} 顶点 / {job.stats?.triangles} 三角面
              </p>
              <button
                className="primary wide"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await onInsert(job.asset_id!);
                  } catch (e) {
                    onError(String(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                预览 / 插入当前场景
              </button>
              <a
                className="download-link"
                href={job.model_url!}
                download={job.is_mock ? "mock-test.glb" : "ai-model.glb"}
              >
                下载生成 GLB
              </a>
              {!job.is_mock && (
                <button
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      setJob(
                        await api<AIJob>("/ai3d/jobs/texture", "POST", {
                          source_job_id: job.id,
                          engine: "hunyuan3d-2.1",
                        }),
                      );
                    } catch (e) {
                      onError(String(e));
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  单独生成 AI 纹理
                </button>
              )}
              <details>
                <summary>处理前 / 后与来源</summary>
                <pre className="diagnostics">
                  {JSON.stringify(
                    { stats: job.stats, provenance: job.metadata },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </>
          )}
          {job.original_available && (
            <a
              href={"/api/ai3d/jobs/" + job.id + "/original"}
              download="original.glb"
            >
              下载原始 Mesh 备份
            </a>
          )}
          <button
            onClick={async () => {
              try {
                setLog(
                  (await api<{ log: string }>("/ai3d/jobs/" + job.id + "/log"))
                    .log,
                );
              } catch (e) {
                onError(String(e));
              }
            }}
          >
            查看任务日志
          </button>
          {log && <pre className="diagnostics">{log}</pre>}
        </div>
      )}
      <div className="section-title spaced">
        AI 生成历史 <button onClick={refresh}>刷新</button>
      </div>
      {history.map((h) => (
        <button key={h.id} className="history" onClick={() => setJob(h)}>
          <span>
            {h.is_mock ? "[Mock 非 AI]" : "[AI]"} {h.id.slice(0, 8)}
          </span>
          <small>{h.status}</small>
        </button>
      ))}
    </section>
  );
}
