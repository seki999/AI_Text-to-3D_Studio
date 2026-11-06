# 第三方模型与许可证记录

核对日期：2026-11-06。项目自身的 MIT 许可证不替代外部模型、源码或权重条款。不打包第三方权重。

| 组件 | 来源 / 版本 | 许可证 / 交付状态 |
| --- | --- | --- |
| Hunyuan3D 2.1 源码 | [Tencent 官方仓库](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)，审查 commit `82920d643c0dc2f7bfd7255f45f62d386edfe60c` | [Community License 原文](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/82920d643c0dc2f7bfd7255f45f62d386edfe60c/LICENSE)。本仓库只提供适配器，不复制该模型源码或权重 |
| Hunyuan3D-Shape-v2-1 | [官方权重仓库](https://huggingface.co/tencent/Hunyuan3D-2.1/tree/0b94677654c57bb9a6b6845cd7b704ccf551d327)，revision `0b94677654c57bb9a6b6845cd7b704ccf551d327` | [权重 LICENSE](https://huggingface.co/tencent/Hunyuan3D-2.1/blob/0b94677654c57bb9a6b6845cd7b704ccf551d327/LICENSE)；未下载、未分发 |
| Hunyuan3D-Paint-v2-1 | 同一官方模型库的独立 Paint 部分 | 可选独立步骤；没有安装、下载或在本机验证 |
| Paint 的 DINO / Real-ESRGAN / 编译扩展 | 由上游 Paint 使用，需按各自官方条款准备 | 未分发；不因 Shape 许可确认而默认获授权 |
| Text-to-Image 模型 | 用户在服务端显式指定的兼容服务及模型 | 本项目未绑定第三方商业模型，不提供默认云端调用或 API Key |
| MockGenerative3DAdapter | 本项目测试代码产生的规则测试几何 | MIT；明确为测试夹具，不是 AI 推理或 Hunyuan 输出 |

## 上游条款需要注意的范围

核对的 Community License 对地域、用途、分发告知和商业规模存在条件，包括 EU / UK / 韩国的地域排除及特定规模下另行许可要求；对用其输出训练其他模型也有约束。它不是“无限制商业分发”许可证。提供涉及该模型的服务时还需核对实际服务提供者披露及无腾讯背书的说明。这里是条款定位说明，不替代完整原文。

部分源码文件头仍出现 NON-COMMERCIAL 字样，与根目录 Community License 的命名不同；不能仅凭 README 的“open-source”描述推断商业授权。正式商用 / 分发前应向上游核实具体用途、地区和版本。UI 要求用户查看许可证并确认，安装脚本也不默认接受许可证。

## 固定的 Shape 下载信息

- 文件：`hunyuan3d-dit-v2-1/model.fp16.ckpt`，**7,366,389,768 bytes**。官方固定 revision 未发布 `model.fp16.safetensors`；适配器不会请求不存在的文件。
- SHA256：`6b519fc7242f78e9b5f47ea4d55668fe3d944a2d27332f4ca68d29a6ff603f5e`。
- `config.yaml` SHA256：`a9e9b66f0163a9b827d730633ac88f47fcc8e3071dcbb9ee12d88ef7537c5c6e`。
- 来源和长度依据上述官方 revision 的文件元数据。安装脚本在用户确认后下载该 revision，并校验哈希；运行时对官方 checkpoint 再次校验。仅加载可信固定权重，不能把 `weights_only=True` 当成任意 checkpoint 的安全沙箱。
- 若用户自行提供兼容 safetensors，可走上游 safetensors 分支，但本机未验证转换模型，也不会自动转换或获取第三方权重。

资产元数据记录引擎、版本、来源、参考图、许可和内容 SHA256。项目快照保留这些信息；导出里的校验和指生成源资产，不代表用户编辑后导出文件本身的哈希。外部导入 GLB 的自报元数据不作为本系统已验证的 AI 推理证明。
