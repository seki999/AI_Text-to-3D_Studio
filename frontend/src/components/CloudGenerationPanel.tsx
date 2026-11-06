import { useEffect, useState } from "react";
import { api } from "../api";
import type { AIEngine, AIImage, AIJob } from "../types";

type Status = {
  available: boolean;
  configured?: boolean;
  errors?: string[];
  notice?: string;
};

export function CloudGenerationPanel({
  engines,
  onEngine,
  onInsert,
  onError,
}: {
  engines: AIEngine[];
  onEngine: (value: string) => void;
  onInsert: (id: string) => Promise<void>;
  onError: (value: string) => void;
}) {
  const [mode, setMode] = useState<"text" | "image">("text");
  const [prompt, setPrompt] = useState("生成一条红色、有翅膀的幻想龙。");
  const [status, setStatus] = useState<Status | null>(null);
  const [image, setImage] = useState<AIImage | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [consent, setConsent] = useState(false);
  const [license, setLicense] = useState(false);
  const [textured, setTextured] = useState(true);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<AIJob | null>(null);
  const [history, setHistory] = useState<AIJob[]>([]);
  const running = !!job && ["pending", "running"].includes(job.status);
  const refresh = async () =>
    setHistory(
      (await api<AIJob[]>("/ai3d/jobs")).filter((j) => j.engine === "meshy"),
    );
  const check = async () =>
    setStatus(await api<Status>("/ai3d/engines/meshy/status"));
  useEffect(() => {
    check().catch((e) => onError(String(e)));
    refresh().catch((e) => onError(String(e)));
  }, []);
  useEffect(() => {
    if (!job || !running) return;
    let active = true,
      polling = false;
    const timer = setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const value = await api<AIJob>("/ai3d/jobs/" + job.id);
        if (active) {
          setJob(value);
          if (!["pending", "running"].includes(value.status)) refresh();
        }
      } catch (e) {
        if (active) onError(String(e));
      } finally {
        polling = false;
      }
    }, 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [job?.id, running]);
  async function action(work: () => Promise<void>) {
    setBusy(true);
    try {
      await work();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function upload(file: File) {
    if (file.size > 10 * 1024 * 1024) throw new Error("参考图上限 10 MB");
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
  }
  return (
    <section className="generative-panel">
      <div className="section-title">
        CLOUD AI 3D <span>Meshy</span>
      </div>
      <h2>文字 / 图片 → 云端 3D Mesh</h2>
      <label>生成引擎</label>
      <select
        aria-label="AI 3D 引擎"
        value="meshy"
        disabled={running || busy}
        onChange={(e) => onEngine(e.target.value)}
      >
        {engines.map((e) => (
          <option key={e.id} value={e.id}>
            {e.name}
          </option>
        ))}
      </select>
      <p className="muted tiny">Meshy 7.1 · 无需本机 GPU · GLB · 最多 50 MB</p>
      <div className="warning">
        <strong>云端推理 · 可能产生费用</strong>
        <p>
          点击生成后，描述或已确认的图片将发送至 Meshy。文字带纹理会创建 preview
          和 refine 两个付费任务。费用和余额以服务账户为准。
        </p>
        <a
          href="https://docs.meshy.ai/en/api/pricing"
          target="_blank"
          rel="noreferrer"
        >
          查看官方费用说明
        </a>
      </div>
      <details open={!status?.configured}>
        <summary>安全配置 API Key</summary>
        <p className="tiny">
          在项目目录的 PowerShell 终端运行，按提示隐藏输入密钥。密钥仅保存在当前
          Windows 用户的 DPAPI 加密配置中，不进入网页或 Git。
        </p>
        <code>.\scripts\configure-meshy.ps1</code>
        <p className="tiny">需使用有 API 权限及余额的个人 Meshy 账户。</p>
      </details>
      <button disabled={busy} onClick={() => action(check)}>
        刷新本地配置状态
      </button>
      <div role="status" className={status?.configured ? "hint" : "warning"}>
        {status?.configured
          ? "密钥已配置；云端授权、余额和服务可用性尚未验证。"
          : (status?.errors?.join("；") ?? "正在检查本地配置")}
      </div>
      <div className="row">
        <button
          className={mode === "text" ? "primary" : ""}
          disabled={running || busy}
          onClick={() => {
            setMode("text");
            setConsent(false);
          }}
        >
          Text-to-3D
        </button>
        <button
          className={mode === "image" ? "primary" : ""}
          disabled={running || busy}
          onClick={() => {
            setMode("image");
            setConsent(false);
          }}
        >
          Image-to-3D
        </button>
      </div>
      {mode === "text" ? (
        <>
          <label>生成描述 · 最多 800 字符</label>
          <textarea
            aria-label="云端生成描述"
            maxLength={800}
            value={prompt}
            disabled={running || busy}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </>
      ) : (
        <>
          <label>本地参考图片 · PNG / JPG / WebP · 每边至少 32 像素</label>
          <input
            type="file"
            aria-label="云端参考图片"
            accept="image/png,image/jpeg,image/webp"
            disabled={running || busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) action(() => upload(file));
              e.target.value = "";
            }}
          />
          <p className="tiny muted">
            选图仅保存到本地服务，点击生成才上传至云端。
          </p>
          {image && (
            <>
              <img
                className="reference-preview"
                alt="云端参考图预览"
                src={image.url}
              />
              <label>
                <input
                  type="checkbox"
                  aria-label="确认云端参考图"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                确认使用这张参考图
              </label>
            </>
          )}
        </>
      )}
      <label>
        <input
          type="checkbox"
          aria-label="生成云端纹理"
          disabled={running || busy}
          checked={textured}
          onChange={(e) => {
            setTextured(e.target.checked);
            setConsent(false);
          }}
        />
        生成 2K PBR 纹理（额外费用；关闭时仅几何，不保证红色外观）
      </label>
      <label>
        <input
          type="checkbox"
          aria-label="确认云端费用和上传"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
        />
        确认发送输入到 Meshy 并承担 API 费用
        {textured && mode === "text" ? "（包含 preview + refine）" : ""}
      </label>
      <a
        href="https://www.meshy.ai/terms-of-use"
        target="_blank"
        rel="noreferrer"
      >
        Meshy 服务条款与输出权利
      </a>
      <label>
        <input
          type="checkbox"
          aria-label="确认云端服务条款"
          checked={license}
          onChange={(e) => setLicense(e.target.checked)}
        />
        已阅读服务条款，确认有权使用输入素材；商用权利以账户方案及条款为准
      </label>
      <button
        className="primary wide"
        disabled={
          busy ||
          running ||
          !status?.available ||
          !consent ||
          !license ||
          (mode === "text" ? !prompt.trim() : !image || !confirmed)
        }
        onClick={() =>
          action(async () => {
            setJob(
              await api<AIJob>("/ai3d/jobs/cloud", "POST", {
                engine: "meshy",
                mode,
                prompt: mode === "text" ? prompt : "",
                image_id: mode === "image" ? image?.id : null,
                textured,
                cloud_consent: consent,
                license_acknowledged: license,
              }),
            );
            await refresh();
          })
        }
      >
        生成云端 3D（可能收费）
      </button>
      {job && (
        <div className="ai-result">
          <strong>
            {job.is_mock
              ? "[API Contract 测试素材 · 非真实 AI] "
              : "[Meshy 云端] "}
            {job.status} · {job.stage}
          </strong>
          {job.progress_kind === "provider" && job.progress !== null && (
            <p>当前云端阶段 {job.progress}%（并非整个流程进度）</p>
          )}
          {job.error && (
            <div role="alert" className="error">
              {job.error}
            </div>
          )}
          {running && (
            <>
              <p className="tiny">
                运行中的云端任务无法中止；停止等待不保证退款，任务可能继续计费。
              </p>
              <button
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    setJob(
                      await api<AIJob>(
                        "/ai3d/jobs/" + job.id + "/cancel",
                        "POST",
                      ),
                    );
                  })
                }
              >
                停止本地等待 / 尝试取消排队
              </button>
            </>
          )}
          {["failed", "cancelled"].includes(job.status) && job.remote_id && (
            <button
              disabled={busy}
              onClick={() =>
                action(async () => {
                  setJob(
                    await api<AIJob>(
                      "/ai3d/jobs/" + job.id + "/resume",
                      "POST",
                    ),
                  );
                })
              }
            >
              恢复已有云端任务（已选纹理时会继续 refine）
            </button>
          )}
          {job.status === "completed" && job.asset_id && (
            <>
              <p>
                {job.stats?.texture_status} · {job.stats?.vertices} 顶点 /{" "}
                {job.stats?.triangles} 三角面
              </p>
              <button
                className="primary wide"
                disabled={busy}
                onClick={() => action(() => onInsert(job.asset_id!))}
              >
                预览 / 插入当前场景
              </button>
              <a
                className="download-link"
                href={job.model_url!}
                download="meshy-model.glb"
              >
                下载生成 GLB
              </a>
              <p className="tiny">
                插入后可拖动旋转查看，修改变换和材质，保存项目并导出当前 GLB。
              </p>
            </>
          )}
          {job.original_available && (
            <a
              href={"/api/ai3d/jobs/" + job.id + "/original"}
              download="original.glb"
            >
              下载云端原始 GLB
            </a>
          )}
          <details>
            <summary>任务来源与处理结果</summary>
            <pre className="diagnostics">
              {JSON.stringify(
                {
                  id: job.id,
                  remote_id: job.remote_id,
                  metadata: job.metadata,
                  stats: job.stats,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </div>
      )}
      <div className="section-title spaced">
        Meshy 历史 <button onClick={() => action(refresh)}>刷新</button>
      </div>
      {history.map((h) => (
        <button key={h.id} className="history" onClick={() => setJob(h)}>
          <span>{h.id.slice(0, 8)}</span>
          <small>{h.status}</small>
        </button>
      ))}
    </section>
  );
}
