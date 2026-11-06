# 独立 Hunyuan3D 2.1 Worker 安装与诊断

当前机器为 Windows / Intel UHD，没有检测到可用 NVIDIA CUDA GPU。尚未安装独立 AI 环境，也未下载模型。本机真实推理标记为 **Skipped / hardware blocked**，不是 Real AI Inference Passed。实测报告见 `v03-hardware-diagnostics.json`；无法测量的显存等字段为 null（Unknown），没有采用 WMI 的受限宽度 AdapterRAM 冒充真实显存。

## 官方兼容性与本项目策略

[官方 README](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/tree/82920d643c0dc2f7bfd7255f45f62d386edfe60c) 列出 Windows / macOS / Linux，并给出 Python 3.10、PyTorch 2.5.1+cu124 的测试组合。本项目首选 NVIDIA CUDA；不自动启用 CPU、MPS、量化或其他未经验证的回退。官方给出的 Shape / Paint 显存需求分开列出，本适配器采用当前可用显存至少 10 GiB（Shape）和 21 GiB（Paint）的保守准入门槛；通过准入不等于实际推理已经验证。

形状环境与 API 环境完全分开。API 仍使用原 Python 3.11+；Worker 推荐独立 Python 3.10。Paint 还涉及 CUDA / C++ 扩展，上游包含 bash 编译脚本，Windows 原生编译没有在本机验证；有准备好的 Linux / WSL2 CUDA 环境时可按上游说明单独配置。没有自动安装 CUDA toolkit、驱动或 Python 系统版本的代码。

## 1. 先诊断，不下载

```powershell
.\scripts\diagnose-ai3d.ps1
# 已有独立环境时：
.\scripts\diagnose-ai3d.ps1 -WorkerPython 'C:\MyAIEnv\Scripts\python.exe'
```

也可在 UI 点击 Generative AI → GPU / CUDA / 模型诊断。未启动 Worker 时，主机 GPU / RAM / 磁盘检查仍可运行，Torch / CUDA / 权重状态显示 Unknown；启动 Worker 后由其自身 Python 实测。

## 2. 用户主动创建环境

先安装好自己选择的 Python 3.10 和兼容 GPU 驱动，阅读 [模型许可记录](MODEL-LICENSES.md)。以下命令会下载推理依赖，包括较大的 PyTorch 包；**本次开发没有执行这些安装命令**。

```powershell
.\scripts\setup-ai3d-worker.ps1 -InstallDependencies -AcceptModelLicense
```

脚本只创建项目内 `.ai3d-venv`、拉取 `.tools/Hunyuan3D-2.1` 的固定 commit、安装隔离依赖，不修改 API `.venv`。已有源码若与固定版本不同，脚本会停止，不覆盖用户修改。上游 Shape 栈的 trimesh 4.4.7 与 API 的新版本通过兼容加载分支区分；可选简化需要对应版本的额外后端，默认关闭。

## 3. 单独确认大型权重下载

```powershell
.\scripts\setup-ai3d-worker.ps1 -DownloadWeights -AcceptModelLicense
```

还需要在交互提示输入 `DOWNLOAD`。只下载固定权重 revision 的 Shape 文件、配置和许可证；checkpoint 约 7.37 GB，下载前自行确认磁盘和网络。脚本校验 SHA256，并写入本地 `MODEL-SOURCE.json`。模型目录受 `.gitignore` 排除，不加入提交或安装包。

## 4. 两个终端分别启动

使用自己随机生成的 token，在两个终端设置相同值。不要提交真实 token，也不要把它放入前端。

```powershell
# 终端一：独立 Worker
$env:AI3D_WORKER_TOKEN = '<自己生成的至少32字符随机值>'
$env:HUNYUAN3D_REPO = 'C:\path\AI_Text-to-3D_Studio\.tools\Hunyuan3D-2.1'
$env:HUNYUAN3D_WEIGHTS = 'C:\path\AI_Text-to-3D_Studio\models\Hunyuan3D-2.1'
.\scripts\start-ai3d-worker.ps1

# 终端二：原有 API + 前端
$env:AI3D_WORKER_TOKEN = '<与终端一相同的值>'
$env:AI3D_WORKER_URL = 'http://127.0.0.1:8010'
.\scripts\start.ps1
```

Worker 必须只绑定回环地址、单 worker 运行；API 也不要使用多 Uvicorn worker 共享内存队列。Worker 请求有令牌校验，无浏览器直连路径。服务端只接受回环 Worker URL，禁用代理与重定向。推理时设定 HF / Transformers 离线模式，缺失权重立即报错而不是下载。官方 checkpoint 使用固定 SHA256 和上游 `weights_only=True` 路径；这不代表允许加载任意不可信文件。

Linux / WSL2 可以使用 `python3.10 -m venv .ai3d-venv`，按脚本相同版本安装，然后在项目根目录执行 `.ai3d-venv/bin/python -m uvicorn ai_worker.service:app --host 127.0.0.1 --port 8010`，设置相同环境变量即可。Linux 安装和真实 CUDA 推理未在本机验证。

## 5. Shape 与 Paint 分开

Shape 先完成并保存原始及处理后的 GLB。Paint 必须由用户对已有真实 Shape 另行点击“单独生成 AI 纹理”，不能对 Mock 夹具生成“AI 纹理”。需额外配置 `HUNYUAN3D_ENABLE_TEXTURE=1`、Paint 权重目录、`HUNYUAN3D_DINO_WEIGHTS`、Real-ESRGAN 权重及上游编译扩展。诊断检查常见依赖与编译模块存在性；仍需实际 GPU 验证，不能将依赖存在宣称为 Paint 推理成功。

Paint 的阶段未提供可测扩散回调时仅显示阶段状态，不生成假百分比。任何失败都不修改原 Shape 资产。GLB 中实际贴图以 Base Color / MR / Normal / Alpha 检测结果展示，纯色 Mesh 显示“未生成纹理”。

## 6. 显式 Mock 集成测试

仅在明确要测试 UI / Worker 通信时，在 API 和 Worker 终端均设置 `AI3D_ENABLE_MOCK=1`，然后：

```powershell
.\scripts\start-ai3d-worker.ps1 -Python '.\.venv\Scripts\python.exe' -MockTestMode
```

这个参数明确复用 API Python 只运行测试几何，不代表独立 AI 环境已安装。Mock 不调用 Hunyuan 或任何神经网络，不能作为模型质量示例。默认环境变量未设置时 Mock 不可用；UI 还要求勾选测试确认。

## 7. 超时、取消与缓存

`AI3D_TIMEOUT_SECONDS` 默认 1800 秒；一个 Worker 只有一个活动推理进程，排队数受限。取消活动任务终止进程树；取消排队任务释放队列槽位。Worker 重启会核对旧 PID、启动时间和完整 runner 命令，回收属于本 Worker 的遗留进程，避免误杀其他进程。Web 服务重启也尝试取消遗留 Worker 任务。

`AI3D_WORKER_MAX_DISK_MB` 默认 2048，限制 Worker 产物软配额。传回并验证成功后清理 Worker 临时产物；失败时保留日志和可用原始备份。主 API 使用原 `STUDIO_MAX_DISK_MB` 和保留策略，保护项目快照、其引用的源 AI GLB 和参考图。用户主动清理无引用缓存后，相应旧任务或尚未提交的参考图可能需要重新上传。没有 OS 级 GPU / RAM / 硬磁盘配额，也没有公网上传服务安全沙箱。

## 8. 可选真实 GPU 验证

```powershell
$env:RUN_HUNYUAN_REAL='1'
$env:HUNYUAN_TEST_IMAGE='C:\my-fixtures\reference.png'
cd backend
..\.venv\Scripts\python.exe -m pytest -q -ra -m real_ai
```

只有真实 Worker、CUDA、固定本地权重和图片准备好后才可能通过。硬件不满足时报告 Skipped。CI 不下载模型；可手动选择准备好的 self-hosted GPU runner，见工作流 `run_hunyuan_real` 输入。
