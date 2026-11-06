# V0.3 执行清单

基线 d0e0295a2832770893ebb8d6e734db6193a4b617，开发分支 codex/v0.3-generative-ai。遵循本次需求，不自动合并或推送 main。

审查：现有 Viewer 使用独立模型 Group、Scene 局部 TRS、实时快照和 SQLite 项目资产；新增生成资产应复用该链路，不能替换 Native/Blender。新增 AI 任务与 Worker 单独管理，禁止在 FastAPI 环境加载 PyTorch 或自动获取权重。

- [x] A：Engine 契约、官方接口 / 许可证审查、真实硬件诊断
- [x] B：回环独立 Worker、单机队列、取消 / 超时 / 子进程清理
- [ ] C：本地 Hunyuan3D 2.1 Image-to-Shape；纹理独立步骤
- [x] D：Mesh 验证、原始备份、GLB、现有场景中插入与编辑
- [x] E：Generative UI、历史、元数据和项目持久化
- [ ] F：Text-to-Image 适配器、参考图确认、文字生成编排
- [ ] G：Mock / Integration / Real / Skipped 分项报告、回归、安全、文档和 CI

环境初查：Windows / Intel UHD，未发现 nvidia-smi。真实推理是否可用由诊断报告决定，绝不将 Mock 结果标记为真实 AI。

C：适配器已实现；真实 Shape/Paint 验收因本机条件不足而未完成。

F：Provider 契约、参考图确认和编排已实现；真实 Provider 未配置，端到端神经生成未验证。

G：本地回归与文档已完成；真实 GPU 验证、真实纹理与远端 CI 仍待执行。详细分类及结果见 IMPLEMENTATION.md。


## V0.3 验收与 V0.3.1 云端增量（2026-11-07）

- [x] 核对 main 已包含 ab2daf5（V0.3），不重复合并。
- [x] Python、Vitest、TypeScript 构建；真实 Native/Blender 和本地 Ollama 回归。
- [x] 官方 Meshy / Tripo 文档研究，选择 Meshy 实现文字/图片 Adapter。
- [x] 本地 Windows DPAPI 凭证、费用/输入上传确认、异步状态/错误/停止等待/恢复。
- [x] 云端 GLB 校验、原始备份、元数据保留、编辑器/保存/导出契约流程。
- [x] Mock、API Contract、Real API 分层测试与明确 Skipped；无 Key 不伪造输出。
- [ ] 有真实 Key 后的付费 API、真实红色幻想龙和供应商 GLB 质量验收。
- [ ] 真实 Hunyuan Shape/Paint（本机 CUDA 条件不足）。

最终结果和剩余限制以 IMPLEMENTATION.md 为准。
