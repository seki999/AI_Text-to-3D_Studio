# FORMA · AI Text-to-3D Studio

本地优先的参数化三维创作工作台。中文默认界面，React / Three.js 查看器，FastAPI / SQLite 后端，以及独立 Blender headless 建模进程。无需 API Key 即可解析常见中英日文描述。

这是可运行的首版开发实现，**不是已完成商业验收的正式软件**。当前范围及限制见 [实现报告](docs/IMPLEMENTATION.md)。

## 启动（Windows）

需要 Python 3.11+、Node.js 22+，以及 Blender 4.5+。Blender 可使用 [官方便携 ZIP](https://www.blender.org/download/)；不需要安装到系统。当前工作区的 `.tools` 若已有便携版，启动脚本会自动发现。

```powershell
# 在项目根目录运行
# 使用其他位置的 Blender 时，在当前终端设置：
$env:BLENDER_PATH = 'C:\Tools\Blender\blender.exe'
.\scripts\start.ps1
```

打开 http://127.0.0.1:5173 。API 文档为 http://127.0.0.1:8000/docs 。Ctrl+C 关闭前端时，脚本停止它启动的后端进程。缺少 Blender 不影响描述解析、JSON 编辑及项目保存，生成 API 会明确返回 503。

手动启动：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
# 终端一（根目录）
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
# 终端二
cd frontend
npm.cmd ci
npm.cmd run dev
```

## 使用

1. 输入描述，如“生成一个红色立方体，边长2米。”或默认的日式两层住宅示例。
2. 点击“① 解析为 Scene JSON”，在右侧检查参数，或打开 JSON 编辑器校验修改。
3. 点击“② 生成 3D 模型”。后端排队启动 Blender，创建真实 Mesh 并导出 GLB / OBJ。
4. 模型加载后，左键旋转、滚轮缩放、右键平移；点击对象或对象树选择。位置、旋转、缩放即时作用于当前加载模型。
5. 修改尺寸、颜色等源参数后重新生成。下载 GLB / OBJ 导出的是**最近一次生成产物**，请先重建以包含编辑结果。
6. 保存项目将场景、描述及最近生成模型 ID 持久化到 SQLite；打开项目恢复 Scene 和对应 GLB。最近生成面板也可载入历史模型。

外部 GLB / 内嵌 GLTF / OBJ 可在本地浏览器导入。外部模型不恢复程序化参数，OBJ 暂仅导入几何；JSON 导入保留参数编辑能力。PNG 按钮导出当前 WebGL 画布。

## 配置 LLM

环境变量必须在后端启动前设置，`.env.example` 仅作说明，不自动加载。API Key 仅存在服务端环境，不写入前端或数据库。

```powershell
$env:LLM_BASE_URL = 'https://your-provider.example/v1'
$env:LLM_API_KEY = 'your-key'
$env:LLM_MODEL = 'your-model'
# Ollama 走本机 OpenAI 以外的原生 /api/chat 接口
$env:OLLAMA_URL = 'http://localhost:11434'
$env:OLLAMA_MODEL = 'qwen3:8b'
```

切换前端 Provider 后重新解析可比较结果。失败显示错误，不静默回退；可主动选择规则模式。所有 LLM JSON 均经过同一 Pydantic Schema，绝不执行模型生成的脚本。

## 测试

```powershell
.\scripts\test.ps1
# E2E 需要先启动后端；真实闭环还需要 Blender
cd frontend
npx.cmd playwright install chromium
npm.cmd run e2e
```

后端无 Blender 时将明确跳过真实建模测试；E2E 无后端 / Blender 时跳过真实闭环，不算通过。CI 默认不安装 Blender。具体本次运行结果见 [实现报告](docs/IMPLEMENTATION.md)。

直接运行建模器：

```powershell
& $env:BLENDER_PATH --background --factory-startup --python backend/blender/generate.py -- examples/japanese-house.json examples/japanese-house.glb
```

直接脚本输入仅应来自本项目验证通过的 JSON；HTTP 生成接口始终验证输入。Schema 位于 `shared/schemas/scene.schema.json`，示例参数位于 `examples/`。

## 模块

- `frontend/src/`：查看器、状态及撤销重做、编辑面板、API 客户端。
- `backend/app/schema.py`：版本化 Scene、参数、父子层级和复杂度边界。
- `backend/app/providers.py`：规则解析、OpenAI-compatible、Ollama、未来引擎接口。
- `backend/app/main.py`：API、SQLite、任务队列和文件访问。
- `backend/blender/generate.py`：可信建模器、材质复用、GLB / OBJ 输出及统计。
- `backend/tests/`、`frontend/tests/`：单元、API、建模和浏览器测试。

安全边界、坐标系、已知限制和后续计划见 [架构说明](docs/ARCHITECTURE.md)。默认只监听回环地址，无账号系统，不能直接公开部署。
