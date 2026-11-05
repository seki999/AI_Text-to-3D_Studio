import type { Engine } from "../engines/native";
import { ProviderSettings, type OllamaConfig } from "./ProviderSettings";
const initial =
  "生成一栋日本两层独立住宅，白色外墙、灰色双坡屋顶、四个正面窗户、一个入口、二楼阳台。";
type Props = {
  text: string;
  setText: (s: string) => void;
  provider: string;
  setProvider: (s: string) => void;
  ollama: OllamaConfig;
  setOllama: (s: OllamaConfig) => void;
  engine: Engine;
  setEngine: (s: Engine) => void;
  busy: boolean;
  hasObjects: boolean;
  health: boolean | null;
  parse: () => void;
  generate: () => void;
};
export function PromptPanel({
  text,
  setText,
  provider,
  setProvider,
  ollama,
  setOllama,
  engine,
  setEngine,
  busy,
  hasObjects,
  health,
  parse,
  generate,
}: Props) {
  return (
    <>
      {" "}
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
      {provider === "ollama" && (
        <ProviderSettings config={ollama} onChange={setOllama} />
      )}
      <label>建模引擎</label>
      <select
        aria-label="建模引擎"
        value={engine}
        onChange={(e) => setEngine(e.target.value as Engine)}
      >
        <option value="auto">Auto · 自动选择</option>
        <option value="native">Native Three.js</option>
        <option value="blender">Blender</option>
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
        disabled={busy || !hasObjects}
        onClick={generate}
      >
        {busy ? "处理中…" : "② 生成 3D 模型"} <span>✦</span>
      </button>
      <div className="hint">描述 → 参数确认 → Native / Blender → GLB</div>
      {health === false && (
        <div className="warning">
          未检测到 Blender。基础几何和家具可使用 Native；房屋请配置
          BLENDER_PATH。
        </div>
      )}
    </>
  );
}
