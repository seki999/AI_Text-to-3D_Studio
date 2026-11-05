import { useState } from "react";
import { api } from "../api";
export type OllamaConfig = {
  url: string;
  model: string;
  timeout: number;
  temperature: number;
  num_ctx: number;
};
export const defaultOllama: OllamaConfig = {
  url: "http://127.0.0.1:11434",
  model: "qwen3:8b",
  timeout: 90,
  temperature: 0.1,
  num_ctx: 8192,
};
export function ProviderSettings({
  config,
  onChange,
}: {
  config: OllamaConfig;
  onChange: (c: OllamaConfig) => void;
}) {
  const [models, setModels] = useState<string[]>([]),
    [message, setMessage] = useState("仅连接本机回环地址，不上传到云端"),
    [busy, setBusy] = useState(false);
  return (
    <div className="provider-settings">
      <label>本地 Ollama 地址</label>
      <input
        aria-label="Ollama 地址"
        value={config.url}
        onChange={(e) => onChange({ ...config, url: e.target.value })}
      />
      <button
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const r = await api<{ models: string[] }>(
              "/providers/ollama/check",
              "POST",
              config,
            );
            setModels(r.models);
            setMessage(
              r.models.length
                ? "连接成功，请选择已安装模型"
                : "服务已连接，但未安装模型",
            );
          } catch (e) {
            setMessage(String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        检查连接 / 刷新模型
      </button>
      <p className="muted tiny" role="status">
        {message}
      </p>
      <label>模型</label>
      {models.length ? (
        <select
          aria-label="Ollama 模型"
          value={config.model}
          onChange={(e) => onChange({ ...config, model: e.target.value })}
        >
          {!models.includes(config.model) && (
            <option value={config.model}>{config.model}（未安装）</option>
          )}
          {models.map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>
      ) : (
        <input
          aria-label="Ollama 模型"
          value={config.model}
          onChange={(e) => onChange({ ...config, model: e.target.value })}
        />
      )}
      {(["timeout", "temperature", "num_ctx"] as const).map((k, i) => (
        <div className="param" key={k}>
          <label>{["超时（秒）", "Temperature", "Context"][i]}</label>
          <input
            aria-label={k}
            type="number"
            value={config[k]}
            onChange={(e) =>
              onChange({ ...config, [k]: Number(e.target.value) })
            }
          />
        </div>
      ))}
    </div>
  );
}
