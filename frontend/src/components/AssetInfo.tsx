import type { AssetMetadata } from "../types";
export function AssetInfo({ asset }: { asset: AssetMetadata }) {
  return (
    <section>
      <div className="section-title spaced">生成资产来源</div>
      {asset.provenance.kind === "mock" && (
        <div className="error">Mock 测试资产 · 非真实 AI 结果</div>
      )}
      <p className="muted tiny">
        {asset.generator} / {asset.model_version}
        <br />
        {asset.generated_at}
        <br />
        GLB ·{" "}
        {asset.texture_assets.length ? "包含实际材质 / 贴图项" : "未生成纹理"}
      </p>
      <p className="muted tiny">{asset.license_metadata.name}</p>
      {asset.license_metadata.source?.startsWith("https://") && (
        <a
          href={asset.license_metadata.source}
          target="_blank"
          rel="noreferrer"
        >
          模型许可证
        </a>
      )}
      <details>
        <summary>来源 / 提示词 / 校验和</summary>
        <pre className="diagnostics">{JSON.stringify(asset, null, 2)}</pre>
      </details>
    </section>
  );
}
