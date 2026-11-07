# FORMA · AI Text-to-3D Studio V0.4

本地优先的三维工作台，保留参数化路径并新增独立 Generative AI 工作区：文字 → 受验证的 Scene JSON → Native Three.js / Blender → 真实 Mesh → 交互编辑 → 所见即所得导出。

**基础几何与家具无需 Blender，也不需要 LLM 或 API Key。** 房屋继续使用 Blender。中文为默认界面，可解析常见中英日文关键词，并支持配置本地 Ollama 或 OpenAI-compatible 服务。

## V0.4 Windows 桌面与资产库

本机测试安装包：`release/FORMA-AI-3D-Studio-0.4.0-x64.msi`。安装后双击启动，不需要手动启动 Python、Node 或 FastAPI；需要系统 WebView2 Runtime。当前未签名，尚未通过 Store 认证。

新增资产库、项目引用保护、加载进度/取消、上下文恢复、原生 DPAPI Key 配置与低成本真实 API 验收工具。真实 Meshy 测试默认关闭，无 Key 或未明确授权费用只生成 Skipped 报告；Mock/契约不算推理成功。

构建、目录、安全和安装说明见 [Windows Desktop](docs/DESKTOP-WINDOWS.md)，实际结果与剩余工作见 [V0.4 报告](docs/IMPLEMENTATION.md)。可选 GPU 旧依赖存在已知漏洞，未打包进桌面引擎，见 [GPU 设置](docs/GPU-SETUP.md)。

## V0.3 Generative AI 路径

- **Image-to-3D**：上传 PNG / JPG / WebP → 确认参考图 → 选择已安装的 Hunyuan3D 2.1 → 独立 CUDA Worker → Shape Mesh → GLB → 插入当前场景。
- **Generative Text-to-3D**：主动调用已配置的 Text-to-Image 服务 → 用户确认 / 重新生成参考图 → 同一 Image-to-3D 路径。Text-to-Image 未配置时明确阻止该步骤，允许自行上传参考图，不假装完成文字生成。
- **参数化路径**：V0.1 / V0.2 的 RuleBased / Ollama、Native、Blender 和编辑器继续使用；没有 NVIDIA GPU 也可生成基础几何、家具和房屋（房屋需要 Blender）。

当前环境只有 Intel UHD，未准备 CUDA / PyTorch AI 环境或权重，因此**未通过真实 Hunyuan 推理验收**。Mock 仅用于显式测试，在引擎、状态、资产元数据和对象树中均标记“非 AI”。测试球体不是神经网络生成结果。

先运行 `.\scripts\diagnose-ai3d.ps1`。独立环境及用户确认下载步骤见 [GPU-SETUP](docs/GPU-SETUP.md)，模型和权重条款见 [MODEL-LICENSES](docs/MODEL-LICENSES.md)。不自动安装驱动、不在 API 环境安装 Torch、不随代码分发权重。

API 和 Worker 分别在本机 8000 / 8010 端口，使用相同的随机 `AI3D_WORKER_TOKEN`。Worker 启动后，在 Generative AI 面板查询 GPU、CUDA、依赖、权重和纹理准备状态。无从确认的检测项显示 Unknown。Shape 和 Paint 是独立步骤，纹理失败不会覆盖已完成 Shape。

生成资产可追加到当前已生成场景（保留原有对象），支持变换、PBR、复制、隐藏、删除和撤销。项目保存当前组合 GLB 快照及来源信息，缓存清理保护项目引用的原始 AI 资产和参考图。包含 AI 资产的组合场景暂不整体交给参数化 Builder 重建；变换和材质编辑始终可直接导出。

生成进度仅展示真实扩散步数，加载 / 后处理等阶段不伪造百分比；可取消排队及活动任务，Worker 终止推理进程树并释放模型资源。可下载原始 Mesh 和处理后 GLB，默认不执行破坏性修复。

## 开发环境启动

需要 Python 3.11+、Node.js 22+。房屋建模需要 Blender 4.5+，可使用 [官方便携版](https://www.blender.org/download/)，已有 `.tools/blender-*/blender.exe` 会自动发现。

```powershell
# 在项目根目录启动；只有房屋或指定 Blender 引擎才需要此变量
$env:BLENDER_PATH = 'C:\Tools\Blender\blender.exe'
.\scripts\start.ps1
```

打开 [本地工作台](http://127.0.0.1:5173/)；[API 文档](http://127.0.0.1:8000/docs)。脚本 Ctrl+C 退出前端时停止它启动的后端。后端只使用一个 worker，不要启用多 worker 共享内存队列。

手动启动：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
# 终端一
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
# 终端二
cd frontend
npm.cmd ci
npm.cmd run dev
```

## 使用与编辑

1. 输入“生成一个红色立方体，边长2米”，点击“① 解析为 Scene JSON”，检查右侧参数。
2. 建模引擎 Auto 对基础几何和家具使用 Native，对含房屋的场景使用 Blender。Native 不支持房屋时会说明原因，不以方块代替房屋。
3. 点击“② 生成 3D 模型”。Native 在浏览器生成真实 BufferGeometry；Blender 在本机独立进程建模。
4. 点击模型或对象树选择，Shift+点击进行多选。W 移动、E 旋转、R 缩放，支持 Local / World，吸附为 0.5 米、15°、0.1 倍缩放。拖拽期间禁用相机 OrbitControls。
5. F 聚焦选中、Delete 删除、Ctrl+Z 撤销、Ctrl+Y 重做。一次连续拖拽仅记录一个撤销事务。可复制、隐藏、锁定对象及编辑属性数值。
6. PBR 面板修改颜色、金属度、粗糙度、透明度等，立即作用于模型。提供 Matte、Metal、Glass、Plastic、Wood-like；Wood-like 不是木纹贴图。“恢复模型原始材质”移除外观覆盖。
7. GLB / GLTF / OBJ 导出当前场景快照，**无需再次运行 Blender**。导出不含网格、坐标轴、选框和变换控件。PNG 同样仅渲染模型及灯光。
8. 保存项目会将当前 GLB 快照、Scene 参数、编辑属性及描述保存在本地。重新打开项目可恢复原生、Blender 或导入模型的编辑效果。

Native 参数变化即时重建几何；Blender 的尺寸、屋顶、墙面开口等源参数仍需点击生成重建。变换和 PBR 材质修改始终可直接导出。手动移动对象会解除其声明式空间关系，以避免下次生成时约束将其移回。

## 导入与导出范围

- GLB：主要格式，保留 Mesh、材质、层级和变换。
- GLTF：导出内嵌 buffer / image 的单文件 JSON；导入支持内嵌资源。暂不提供外部 `.bin` / 贴图文件包管理。
- OBJ + MTL：分两次下载，放在同一目录；保留可见三角网格、烘焙后的世界坐标、基础漫反射和透明度。暂不导出纹理图、动画或完整 PBR，OBJ 导入暂不读取伴随 MTL。
- Scene JSON：保留程序化参数和编辑属性。外部模型以编辑包装节点表示，不反推程序化参数；单独 JSON 不包含导入网格，保存项目时通过 GLB 快照保留。
- PNG：当前相机下的模型预览。

导入文件上限 50 MB。外部模型在载入后可以变换和覆盖 PBR，并再次导出；不支持用参数建模器重建任意导入 Mesh。

## 本地 Ollama / Qwen

在 Ollama 终端启用离线限制并启动服务：

```powershell
$env:OLLAMA_NO_CLOUD = '1'
ollama serve
```

在工作台选择 Ollama，检查连接、查询已安装模型并选择模型，可设置超时、temperature、context。**不自动下载模型**。未安装的模型会给出明确错误。30B 模型在 CPU 上可能需要较长时间，可将超时设为 180 秒。

本地 Provider 仅允许 `http://localhost:<port>` 或回环 IP；禁用重定向和代理环境，拒绝 cloud 模型及远程模型标签。Ollama 自身的离线开关是额外防护，见 [官方说明](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)。每个对象显式输出独立颜色与尺寸，输出经过 Schema 和空间关系求解。API Key 不用于本地 Ollama。

远程 OpenAI-compatible 仍需用户主动选择并设置后端环境变量；`.env.example` 仅说明配置，不会自动加载。

```powershell
$env:LLM_BASE_URL = 'https://your-provider.example/v1'
$env:LLM_API_KEY = 'your-key'
$env:LLM_MODEL = 'your-model'
$env:STUDIO_MAX_DISK_MB = '2048'
$env:STUDIO_RETENTION_DAYS = '30'
```

## 四面墙开口

房屋属性中可编辑并校验 `facades.front/back/left/right` 数组，例如：

```json
{
  "front": [{"kind":"door","floor":0,"x":-2,"sill":0.2,"width":0.9,"height":2}],
  "back": [{"kind":"window","floor":1,"x":0,"sill":0.9,"width":1.2,"height":1.2}],
  "left": [{"kind":"window","floor":1,"x":0.8,"sill":0.9,"width":1.2,"height":1.2}],
  "right": []
}
```

楼层从 0 起，x 为该墙面自身水平坐标，sill 为该层窗台高度，单位米。校验越界、重叠及与楼层 / 屋顶边界冲突。启用 facades 后各面以数组为准；设为 null 恢复旧版 windows / doors 布局。房屋只用于视觉和概念设计，不保证建筑施工精度。

## 测试

```powershell
.\scripts\test.ps1
# 浏览器测试先启动后端
cd frontend
npx.cmd playwright install chromium
npm.cmd run e2e
# 显式选择真实本地 LLM 测试，不在默认 CI 中运行
$env:STUDIO_LIVE_OLLAMA = '1'
$env:STUDIO_LIVE_MODEL = 'qwen3-coder:30b'
npm.cmd run e2e -- --grep 'live local'
```

Python 真实 LLM 测试：在相同环境变量下，于 backend 目录执行 `..\.venv\Scripts\python.exe -m pytest -m live -q`。快速测试使用 `-m "not integration and not live and not real_ai"`；Blender 集成使用 `-m integration`。缺失条件的测试明确显示跳过，不视为通过。

本次结果、逐 Milestone 状态及未完成事项见 [实现报告](docs/IMPLEMENTATION.md)。架构、安全边界见 [ARCHITECTURE](docs/ARCHITECTURE.md)。V0.1 报告保存在 [历史报告](docs/IMPLEMENTATION-V01.md)。

V0.3 完整后端回归使用 `python -m pytest -m "not live and not real_ai"`（backend 目录）；轻量 Worker Mock 集成独立标记为 `ai3d_integration`。浏览器 Mock 用例需要 API 与 Worker 同时显式开启 `AI3D_ENABLE_MOCK=1` 并配置相同测试令牌，否则明确跳过；它不代表真实 AI。真实 GPU 测试和环境准备见 [GPU-SETUP](docs/GPU-SETUP.md)，V0.2 历史见 [IMPLEMENTATION-V02](docs/IMPLEMENTATION-V02.md)。


## 云端 3D：没有独立显卡的 Windows

现已接入 Meshy 官方 API，保留 Hunyuan3D 与 Mock。使用本人有权限和余额的 Meshy 账户，在项目目录的交互式 PowerShell 终端运行：

```powershell
.\scripts\configure-meshy.ps1
```

按提示隐藏输入 API Key。密钥由 Windows 当前用户 DPAPI 加密存放在仓库外，不放入 .env、网页、命令行参数或日志。在 Generative AI 选择“Meshy 云端 AI”，刷新配置状态，选择 Text-to-3D 或 Image-to-3D，确认费用/素材权利后点击生成。

默认文字示例是“生成一条红色、有翅膀的幻想龙。”；默认带纹理时会创建 preview 和 refine 两个收费任务。图片模式直接生成带 2K PBR 的 GLB。完成后点击“预览 / 插入当前场景”，可旋转查看、修改材质/变换、保存项目及导出 GLB。停止本地等待不保证停止云端计费；可恢复查询已保存的任务 ID。

**本次没有真实 API Key，未调用付费生成，未验证真实龙模型或云端生成质量。** API 契约测试使用标记为非 AI 的夹具；真实 Hunyuan Shape/Paint 也仍未验证。官方服务的公开文档及无密钥 HTTP 401 连通性检查不能替代有密钥推理验收。

配置、取消/恢复、真实测试与当前限制见 [CLOUD-PROVIDERS](docs/CLOUD-PROVIDERS.md)，验收结果见 [IMPLEMENTATION](docs/IMPLEMENTATION.md)。不需下载大型模型或安装 CUDA。
