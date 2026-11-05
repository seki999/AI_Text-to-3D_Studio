# V0.2 架构与边界

## 增量演进

基线为 d5ec982d18958763b5724f52e0bb531d26efe3bb。React / FastAPI / SQLite / Blender 均沿用。main.tsx 现在仅挂载 App；PromptPanel、PropertiesPanel、SceneTree、MaterialEditor、FacadeEditor、ProviderSettings、ExportPanel 和 StoragePanel 分离 UI。原有 API、项目表、历史和 Blender 入口保持兼容。

统一数据流：Provider → Pydantic Scene → AABB 关系求解 → 参数预览 → Auto / Native / Blender → 独立模型 Group → Scene 状态驱动编辑 → Export Service 快照。

## Scene、坐标及变换

Scene version 保留 1.0，通过可选字段扩展兼容：locked、source_id、material、anchor、relation、reference_object_id、spacing 和 parameters.facades。0.9 的单位 `m` 迁移到 meters；旧 Scene 缺少新字段时补默认值。共享 JSON Schema 从 Pydantic 生成，TypeScript 使用相同字段约定。

交换为 Y-up、米、XYZ 欧拉角（度）；父子节点采用局部 TRS。Native 直接生成 Y-up Mesh。Blender 用 C=Rx(90°) 将输入局部 TRS 变换为 Z-up 再导出 Y-up。导入 Blender GLB 后，匹配 ID 的编辑组使用 Scene 绝对局部 TRS，替换原值而不是再乘一遍；子部件几何不变。

外部 GLB / GLTF / OBJ 由独立包装节点接收编辑 TRS，内部原始层级和变换保留。外部编辑器 ID 在包装前清除，避免与本项目的删除同步冲突。保存快照后包装节点和对应 Scene 一起恢复。source_id 用于 Blender / 导入模型复制和撤销删除时恢复几何模板。

多选操作只变换选中层级中的最上层节点，避免父子重复变换。TransformControls 操作公共 pivot，通过世界矩阵差量再转换到每个节点父坐标。拖拽 begin / end 将所有中间状态合并成一个撤销事务。父级非均匀缩放下的旋转 / 缩放手柄暂禁用，可通过属性栏编辑局部 TRS 或先统一父级缩放。所有矩阵差量在应用前检查是否能无损表达为 TRS；会产生剪切的操作明确拒绝，不静默分解丢失。

## 引擎和资源

Native 支持六类几何及五类家具。由参数生成 BufferGeometry、独立 Group 和 MeshStandardMaterial；房屋不被替代为简单方块。Auto 如包含房屋则使用 Blender 整体构建；暂不混合调度单场景的两种生成引擎。

Viewer 只载入和管理模型，建模逻辑在 engines/native，模型复制及局部变换在 viewer/runtime，交互在 EditingControls。几何参数变化重建 Native 模型；变换 / PBR 不重建几何。资源去重后释放 geometry、material、texture，复制的外部资源与 loader 缓存隔离。选中使用独立 BoxHelper，不修改 emissive；wireframe 导出时复位。

## 导出与持久化

Export Service 的模型 Group 不含编辑辅助对象。GLTFExporter 从快照输出二进制 GLB 或内嵌 GLTF，处理可见性、层级、变换和 PBR。OBJ 将可见网格的 world matrix 烘焙到几何，然后归零变换，避免二次应用。MTL 仅基本漫反射、透明度与近似高光，不支持纹理图及完整 PBR。PNG 使用独立场景加模型和灯光渲染。

SQLite 延用项目聚合 JSON、jobs、assets、history 表。保存项目使用包含隐藏几何的内部 GLB 快照（由 Scene 可见性在载入时恢复），再关联项目；用户下载导出仍只包含可见对象；外部几何不塞入 Scene JSON。数据库只存路径 ID、状态、参数和统计。快照 API 限制 50 MB GLB、检查头部、JSON 块、Mesh 和内嵌资源。项目创建 / 更新与缓存清理使用 SQLite 写事务协调引用，防止误删受保护资产。

## Provider 与关系

规则解析增量复用原解析器，按对象描述分段，分别解析尺寸 / 颜色；声明左右、前后、上下、旁边关系。空间求解考虑对象包围盒、缩放、旋转和父级矩阵，输出局部位置；循环约束报错，包围盒重叠警告。原生形状的包围盒采用生成参数，房屋 / 附属构件仍使用概念包围盒估计，不是精确碰撞求解。复杂同类连续描述、否定和语义歧义仍需检查。

Ollama 仅访问回环 HTTP 端口，将 localhost 归一化成字面 IP，禁止代理、重定向、用户名及任意路径。查询本地模型、过滤 remote_host / remote_model / cloud 标签，校验模型存在。推理使用严格 JSON Schema，强制显式独立颜色 / 尺寸及关系字段；随后 Pydantic 和关系求解二次验证。使用本机现有可信 Ollama 服务，建议 OLLAMA_NO_CLOUD=1 进一步禁止服务自身的远程推理。超时、非法 JSON 和未安装模型单独说明；不会自动回退到云端或下载模型。

## 队列、取消与磁盘

仍为单 FastAPI 进程、两个生成线程、最多八个排队 / 运行任务。每任务独立 Blender factory-startup 进程和 UUID 目录。Windows taskkill /T /F 终止自己创建的进程树；POSIX 独立进程组并 killpg。取消实际终止进程，状态可为 cancelled；超时与服务正常退出也清理活动进程。未完成任务在重新启动时标记失败，不自动重试。

失败 / 取消产物删除，保留 Scene 与尾部可查看日志。磁盘管理只清理符合规范 UUID、位于数据根目录内的非符号链接目录；跳过项目引用和活动任务。STUDIO_MAX_DISK_MB 控制准入及最终产物检查，生成期间临时文件可能短暂超过软配额；它不是操作系统硬磁盘限制。STUDIO_RETENTION_DAYS 用于超配额时的保留策略，UI 可指定清理天数。没有后台定时清理服务。

## 仍有的限制

不支持账号 / 公网多租户、多个 Uvicorn worker、OS 级内存沙箱、分布式任务调度、GLTF 外部资源包及完整 OBJ 纹理导入、骨骼 / morph 动画编辑、真实纹理木材、建筑施工校核或通用神经 3D 引擎。仅适用于可信本机；外部 GLTF 应仅含内嵌资源，未实现完整不可信 3D 文件解析沙箱。Windows 安装包与商店发布留待后续版本。
