# V0.2 执行清单

基线：d5ec982d18958763b5724f52e0bb531d26efe3bb。在 codex/v0.2-studio 开发；按用户最新明确授权，完成验证后提交并推送 main。

审查结论：V0.1 Y-up 交换与 Blender Z-up 转换已工作；Scene 是变换权威来源，但导出仍指向旧文件。材质高亮会污染 emissive，且多次切换 wireframe 会克隆材质。main.tsx 聚合 761 行。Provider 失败统一报错，缺乏本地地址限制、模型查询及配置。任务队列缺乏实际取消及清理策略。已有 40 后端测试与 3 浏览器测试作为回归基线。

- [x] A：Native 几何、家具、层级、资源回收、GLB 导出及测试
- [x] B：TransformControls、事务撤销、多选、快捷键、统一场景快照导出
- [x] C：Ollama 检查、设置和 Mock / 本地真实模型测试，独立对象属性与空间关系
- [x] D：四面开口、四坡屋顶、PBR 编辑和兼容参数
- [x] E：取消进程树、磁盘策略、拆分组件、CI、文档和完整回归

测试结果及仍有限制见 IMPLEMENTATION.md。已更新 CI 定义，未将尚未在 GitHub 执行的工作流标为通过。
