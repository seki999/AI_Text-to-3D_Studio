# 云端 3D Provider：Meshy

核查日期：2026-11-07（Asia/Tokyo）。本次为 V0.3.1 增量，不替换本地 Hunyuan3D、Mock、Native、Blender 或 Ollama。

## 官方 API 研究与选择

| 服务 | 当前公开接口 | 本次状态 |
| --- | --- | --- |
| Meshy | [Text v2](https://docs.meshy.ai/en/api/text-to-3d)、[Image v1](https://docs.meshy.ai/en/api/image-to-3d)、[生命周期](https://docs.meshy.ai/en/api/task-lifecycle) | 已实现官方 Adapter，选择明确的 meshy-7.1，输出 GLB |
| Tripo | [官方入口](https://docs.tripo3d.ai/get-started/introduction.html)、[Text P1](https://docs.tripo3d.ai/model-generation/text-to-model-p1-20260311.html)、[Image P1](https://docs.tripo3d.ai/model-generation/image-to-model-p1-20260311.html) | 文档确认支持文字/图片和异步任务，本次不额外实现第二套 Provider |

Meshy 文字采用 `POST /openapi/v2/text-to-3d` preview，带纹理时再以 preview_task_id 创建 refine；图片采用 `POST /openapi/v1/image-to-3d`，发送规范化 PNG data URI。两者均通过任务 GET 轮询，最后仅下载 GLB。请求采用文档化的参数，100000 面三角重网格，纹理为 2K PBR，不启用 8K、Ultra 或额外付费功能。真实几何细节、红色外观及质量由云端模型决定；仅几何模式不承诺颜色。

公开 API 的无认证只读 GET 已实测返回 **401**，见 [连接记录](cloud-api-connectivity.json)。它只证明端点可达且需要认证，不证明账户可用、余额足够或推理成功。当前无真实密钥，所有生成协议验证均是 **API Contract**，不是 **Real API Inference Passed**。

## 密钥配置（Windows）

在项目目录的真实交互式 PowerShell 中执行：

```powershell
.\scripts\configure-meshy.ps1
# 隐藏输入真实 API Key，不把密钥粘贴到命令参数或本聊天中。
.\scripts\configure-meshy.ps1 -Action status
.\scripts\configure-meshy.ps1 -Action delete
```

后端 `.venv` 需按 README 准备。脚本使用 Python getpass 隐藏输入；Windows DPAPI 使用当前用户作用域（非机器共享），加密文件位于 `%LOCALAPPDATA%/AITextTo3DStudio/secrets/meshy.dpapi`。Git 忽略 *.dpapi 和 *.secret。设置/删除不调用云端；刷新状态只检查本地配置，不验证密钥有效性。其他系统安全凭证存储尚未实现，会明确不可用，不降级明文。DPAPI 往返测试在本机真实执行，但使用的只是测试密钥。

后端只向固定 `https://api.meshy.ai` 发送 Bearer；网页中没有密钥输入、读取接口、localStorage 或环境变量打包。凭证只在后端解密供请求使用；程序不记录上游响应正文、Authorization、回显输入或签名链接。重启服务后同一 Windows 用户可继续使用；换密钥或账户可能无法查询旧任务。

## 用户流程与费用

1. 打开 Generative AI，选择 Meshy，刷新本地配置状态。
2. 文字模式输入描述（最多 800 字符），或上传本地参考图片（每边至少 32 像素，沿用 10 MB/1600 万像素上限）。选图只保存至本地 API。
3. 选择是否生成纹理，阅读第三方条款，勾选云端上传和费用确认，点击生成后才向云端发送输入。带纹理文字明确包含 preview + refine 两个收费任务；变更模式/纹理后需重新确认费用。
4. 查看真实服务状态与当前阶段百分比；阶段进度不是整个流程百分比。失败显示本地安全错误，具体审核详情可在本人服务控制台查询。
5. 完成后插入当前场景；变换、材质编辑、GLB 导出和 SQLite 保存/重开沿用原有编辑器。

计费和权限见 [官方费用](https://docs.meshy.ai/en/api/pricing)，不在界面承诺固定金额或免费额度。没有 Key 时生成被阻止，不回退到 Mock。

## 异步、取消、恢复

本地 SQLite 保存云端任务 ID（带 text/image/refine 阶段），无须 Worker 或 GPU。轮询遵循 Retry-After（限制在 2–60 秒以保护本地调度），GET 的 429/5xx/通信错误有界重试，创建 POST 从不自动重试。创建请求超时/5xx 可能已经产生任务或费用，提示先检查控制台。

Meshy 文档没有为运行中的这些任务提供强制中止。应用在用户停止等待时查询状态：仅排队任务尝试 DELETE，运行中不删除；DELETE 的竞态 409 明确报告云端仍运行，不能承诺退款。完成的云端资产不会被应用自动删除。停止、超时或重启后保留任务 ID，可显式恢复已有任务，避免重建付费任务；恢复文字预览可能继续用户原先确认的 refine。若 refine POST 中断/重启导致结果不明，应用禁止自动重复创建，需要用户先在控制台核对。

云端期限以 [官方保留策略](https://docs.meshy.ai/en/api/asset-retention) 为准，非 Enterprise 通常仅保留 3 天；过期后恢复可能得到 404，重新 GET 不保证刷新签名有效期。

## GLB 与安全边界

结果仅从官方 `assets.meshy.ai` 的 HTTPS 默认端口获取，独立下载客户端不带 API Key。每次重定向重新检查域名，拒绝本地/私网 URL、自定义端口及用户名密码 URL；不接收用户自定义 API 地址或任意下载路径。

流式下载最多 50 MB，再进行实际 GLB、三角面、顶点/索引、有限坐标、包围盒、嵌入纹理与像素限制检查。服务器保留原始 GLB；处理仅添加 Y-up/居中/2 米归一化根变换，保留原始 buffer、材质、纹理和供应商标记，不调用规则 Builder 生成替代品。云端不提供破坏拓扑的修复/减面。生成源文件与项目均含本项目的来源元数据；插入/导出时保留 GLB asset 声明至 extras，并保存原始备份。未知扩展、动画/骨骼、DRACO、厂商专用标记在编辑器往返中的完整支持尚未经过真实供应商资产验证；正式使用时保留原始文件，不移除 AI 标识。

应用仍定位为可信本机的单用户工作台，绑定回环地址。当前配额为应用级软限制；服务变更 CDN/协议会明确拒绝或报错，不放宽到任意 URL，不伪造结果。

## 测试层级

```powershell
# 仓库根目录，包含 Blender 和轻量 Mock Worker；不发送真实付费请求
.\.venv\Scripts\python.exe -m pytest backend/tests -c backend/pytest.ini -m "not live and not real_ai and not real_api"
# 仅 HTTP MockTransport 契约，不使用真实账户
.\.venv\Scripts\python.exe -m pytest backend/tests/test_meshy.py -c backend/pytest.ini -m "api_contract and not real_api"
```

真实付费测试需先安全配置本人密钥，再在自行接受费用时显式设置下列开关。**本次未运行付费生成**，测试默认 Skipped，CI 明确排除 real_api：

```powershell
$env:RUN_MESHY_REAL='1'
$env:MESHY_ACCEPT_CHARGES='YES'
.\.venv\Scripts\python.exe -m pytest backend/tests/test_meshy.py -c backend/pytest.ini -m real_api -q -rs
```

真实测试会生成默认红色幻想龙的 preview + refine 并保存到 pytest 临时目录；它会产生费用。API 契约测试与浏览器夹具不依赖真实密钥、不发出真实云端生成请求，不得用其截图代替真实结果。

浏览器回归可在 frontend 目录运行 `npm run e2e -- --workers=1`；先按原有文档启动 API，Mock 用例另需 API 与 Worker 同时显式开启测试模式。云端浏览器契约使用已标注的本地素材，真实付费请求不会由 Playwright 自动发起。在内存受限机器上，完成真实 Ollama 测试后先卸载测试模型，再运行浏览器套件。
