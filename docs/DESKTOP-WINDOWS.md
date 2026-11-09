# Windows Desktop V0.4

## 路线评估

| 路线 | 运行时与体积 | 本次选择 |
| --- | --- | --- |
| Tauri 2 | Windows 使用 WebView2，需 Rust 工具链，FastAPI 仍需独立打包 | 当前无 Rust；保留未来评估 |
| .NET 10 + WebView2 | 复用系统浏览器，自包含 .NET，无需用户安装 Python/Node | 采用 WinForms 主机 + PyInstaller sidecar |
| Electron | 需要额外分发 Chromium/Node | 本次不采用，尚未做同功能实测内存对比 |

当前为 Windows x64 本机测试 MSI，尚未签名。需要系统已有 Evergreen WebView2 Runtime；没有捆绑或静默下载该运行时。缺失时启动提示错误，请通过 Microsoft 官方渠道安装。安装程序不需要启动 Vite，也不依赖用户的 Python、Node 或 .NET。

## 使用

双击 `release/FORMA-AI-3D-Studio-0.4.0-x64.msi`，从开始菜单启动 FORMA。Native 即可使用；设置中选择本机 Blender。Meshy Key 在原生密码窗口输入，Windows 当前用户 DPAPI 加密保存于 `%LOCALAPPDATA%/AITextTo3DStudio/secrets/meshy.dpapi`，不写入网页、日志或项目。

数据为 `%LOCALAPPDATA%/FORMAStudio/data`，日志为其同级 `logs`，WebView2 用户目录为 `webview`。卸载保留数据与独立密钥；清空数据须在设置输入确认文字，密钥另行明确删除。

主机每次生成会话密钥，通过私有子进程环境传递；随机 loopback 端口，严格 Host/Origin、HttpOnly SameSite cookie、跨站请求拒绝、写操作 Origin 校验。密钥配置、Worker 连接、关闭仅接受原生主机 Bearer。浏览器脚本拿不到会话密钥。这里防护的是其他网页访问，不隔离已控制当前 Windows 用户的恶意进程。

Windows Job Object 管理进程树，正常退出先请求 API/Worker 停止，超时终止；父进程监控提供额外退出保护。可选打包 Worker 仅包含服务与诊断代码，不包含 Torch/CUDA/模型权重，不能将启动服务视为真实 AI 可用。

## 构建和测试

构建机需要 Node 24、Python 3.13、.NET 10 SDK、WiX 6.0.2；运行安装后的软件不需要这些工具。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-desktop.txt
cd frontend
npm ci
cd ..
dotnet tool install wix --tool-path .tools/wix --version 6.0.2
./scripts/build-desktop.ps1
./scripts/test-desktop.ps1
```

测试脚本拒绝覆盖已存在的用户安装。仅对本次 MSI 安装/卸载，每次生成独立 `.tools/v04-installed-smoke/{run_id}` 数据目录并核对报告时间，拒绝读取历史成功报告。验证正式 Canvas、Native 模型、401、两个 sidecar / WebView2 浏览器退出和数据保留。测试截图位于本轮报告 `test_home` 下的 `desktop-native.png`。无论成功或失败，均在 finally 中卸载本次脚本安装的软件并恢复原 FORMA_TEST_HOME；不会卸载已有用户安装。

可执行 `./scripts/test-desktop.ps1 -SimulateFailureAfterInstall` 验证故障清理路径：预期抛出明确的注入错误，`docs/v04-desktop-failure-test.json` 中应记录 `failure_injected=true`、卸载返回 0、`application_removed=true`，未执行的检查为 null。此报告的 failed 是故意触发的测试结果，不代表真实生成或正常安装失败。正常验收仍需独立运行且 status=passed。

数据库 user_version=4，升级前用 SQLite backup 保存旧数据库，拒绝打开更新的 schema。安装包 MajorUpgrade 保持组件身份，拒绝降级。当前不执行自动更新；安全升级路线为用户下载并核验正式签名安装包后升级，先保留数据备份。签名/可信发布源未配置，因此自动更新尚未实现。

## Store 发布前的剩余条件

本次仅本机安装验收，未提交 Store、未执行 WACK、未在全新 Windows/无 WebView2 系统测试、未做 ARM64 包。

- 正式发行需发布者身份和受信任签名，签署安装包及 PE 文件。
- 需明确隐私政策、第三方生成服务费用及条款，准备 Store 素材和认证测试。
- 需确定 WebView2 缺失时的受信任前置安装分发策略，以及签名升级/恢复流程。
- MSI 已支持静默安装和卸载，但这不等于 Store 认证通过。

官方依据：[分发路线](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/choose-distribution-path)、[WebView2 分发](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)。Tauri/Electron 的本次选择是工程判断，没有宣称未经测量的内存指标。
