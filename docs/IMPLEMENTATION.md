# FORMA V0.4 增量开发报告

日期：2026-11-07。分支 `codex/v0.4-windows-studio`，基线 V0.3.1 `1c9e96d`。未合并 main，未执行付费请求、购买服务、下载大型模型或发布 Store。V0.3.1 原报告见 IMPLEMENTATION-V031.md。

## 已实现

- .NET 10 + WebView2 正式桌面主机，自包含 FastAPI 引擎和编译后的 React；动态 loopback 端口、Job Object 子进程清理、原生 DPAPI 密钥配置、Blender 选择、可选 Worker、用户日志与数据目录、MSI。
- 本地会话授权、Host/Origin/CSRF 防护，敏感原生 API 不接受网页 cookie 单独调用；默认不公开公网。
- 独立 SQLite 资产库：真实/Mock/本地来源、缩略图、描述、收藏搜索、Mesh/贴图信息、导入导出、项目引用保护。简化须确认并创建副本，保留原始 GLB。
- GLB 有界流式加载、字节进度和取消、资源释放、高面数提示、WebGL context lost 恢复。GLTF parse 已开始时取消会丢弃并释放结果，不能中断同步解析本身。
- 初次启动说明、费用确认、任务恢复/日志、缓存清理、数据导出与明确删除、版本及升级策略。没有自动上传用户内容。
- 真实 Meshy 验收工具：显式费用授权、Key 检查、官方免费 balance、持久任务 ID、一次 meshy-6-lite preview、状态/真实 GLB 下载和校验、报告。低成本估计 5 credits；服务价格可变，账户余额不等于所有生成权限。无 Key/未授权生成 Skipped，绝不回退 Mock。正常 Meshy text/image 功能保留。
- 合法已有外部资产兼容性入口，要求来源/使用权确认；其结果明确不同于本应用发起真实推理。当前没有用户提供的合法云端样本，未声称这部分真实素材验收通过。

## 实测

| 项目 | 结果 |
| --- | --- |
| Python 回归 | 114 passed，3 个 live/real 测试按标记排除 |
| Vitest | 24 passed |
| TypeScript / Vite production | passed，Three.js 主包仍有体积提示 |
| Playwright | 12 passed，真实 Ollama 默认跳过 1 |
| Windows MSI 安装/卸载 | exit 0；正式 React Canvas 与 Native 模型加载通过 |
| 授权/退出 | 未授权请求 401；API/Worker 退出后均停止 |
| 持久化/迁移 | SQLite 备份/拒绝新 schema、库项目引用保护、GLB 保存重开导出通过 |
| Windows DPAPI | 真实当前用户加解密单元测试通过 |
| npm / API Python / NuGet 审计 | 当前锁定运行依赖未发现已知漏洞 |
| 真实 Meshy | Skipped，无本地 Key，未付费调用 |
| Hunyuan CUDA | 未验证，无可用 CUDA/权重 |

Python 回归包含 Native、Blender、Ollama 协议、Mock Worker HTTP/进程、Meshy MockTransport 契约。本次额外运行真实本地 Ollama qwen3-coder:30b：Python 1 passed（80.20 秒）及 Playwright 1 passed（55.0 秒）；没有新增下载。协议测试不算真实推理。Windows 轮询进度文件的瞬时共享冲突已加入有界重试和回归测试。

安装结果见 v04-desktop-test.json；真实请求关闭报告见 v04-real-api-verification.json；审计见 v04-*-audit.json。最新 V0.3.1 CI 已核实 success，run 42305524315；V0.4 远端 CI 必须在推送后单独确认。Windows 打包 CI 仅手动开启；GitHub Actions 不触发付费生成。

## 未完成的外部验收与发布条件

1. 未执行真实 Meshy 付费生成及其 Viewer/编辑/保存/重开/导出全链路。验收报告只记录实际证据，保存/导出证据没有完成时保留 not_verified。
2. 没有合法真实云端 GLB 样本可做兼容性验收，测试 GLB 与 MockTransport 不算真实云端推理成功。
3. 可选上游 GPU 栈审计发现 49 项已知漏洞：transformers 4.46.0 (43)、diffusers 0.30.0 (5)、accelerate 1.1.1 (1)。这些包没有安装/随桌面分发，尚未验证兼容的全栈升级，不应当作可安全发布的 GPU 环境。
4. Pillow 升级 13 后独立 Worker 新环境改用 Python 3.11；上游曾测试的 3.10 组合不同，CUDA/Paint 新组合未实测，旧环境不会被覆盖。
5. 当前 MSI 未签名；全新 Windows、缺失 WebView2 的前置安装、签名自动更新、WACK/Store、升级安装多版本矩阵尚未验收。
6. 资产库列表目前最多 200 项，超大型库的分页及不同云端材质扩展兼容性仍需后续验证。

## 合并方案

保持 main 不动。先审阅 V0.3.1 provider 与安全差异（原分支 CI success）；独立审阅 V0.4 桌面/数据迁移/授权及安装结果，推送后确认新 CI。确认上述未验证项可作为明确发布限制后，再由用户明确决定是否合并 main。不能据本地测试宣称真实收费 API 或 Store 认证通过。
