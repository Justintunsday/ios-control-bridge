# 实时活动原生适配

`native/activities` 来自已经在 iOS 16.1.1 / 20B101、iPhone12,8 上验证的独立终端读取器。本次迁移将导出符号改为 ICB 前缀、文件和可执行文件改为独立名称，并把内部目标字段改为 `target_activity_result`；实际系统调用路径保持一致。选择目标条目时只匹配 descriptor.id，Python 边界再次核对正文所属 ID，避免正文内出现其他 UUID 时关联错误。迁移后的结果单独记录，不能只用旧二进制测试证明新构建。

路径为 `ACActivityCenter` → ActivityKit 实际客户端的 `BSServiceConnection` → `com.apple.activitykit.output` → `sessionkitd` 的 `ACActivityOutputXPCServer`。查询 `activityDescriptorContentStatesWithError:`，订阅选项是包含 `includePayloads:true` 的二进制属性列表。外层响应为二进制属性列表，目标条目提供 descriptor、contentState 和 state。

本机有效权限为 `com.apple.private.sessionkit.listener=true`，原生 helper 只签入这一项。它支持独立 root 进程跨 App 查询，不需要启动前台 App 或注入 SpringBoard。连接枚举在系统客户端自己的串行队列上读取，观察句柄释放前失效。

当前只允许已核对的 16.1.1 / 20B101。JSON / 属性列表会解析为原始字段，未知二进制保留编码并报告部分可用。正文是应用自定义数据，不代表所有卡片布局、图片或业务字段都可自动解释。测试样本 Date 数字的 2001 年基准只适用于那个已知模型，不推广为所有 App 字段的解释。

## 迁移前基线

2026-11-04 的原基线中，App 内私有正文跟随 10→20→30，结束后没有旧正文，重建返回新的 ID。独立 root 读取器还读取了另一 bundle 的 37→47 更新，并验证结束、未知 ID、100ms 超时、无效参数及清理后的稳定性。原二进制 SHA-256 为 `58d7d6f51c4c58ca0c9a74676e7651228ec84403d39744573ed8819430d7a813`。

这些是迁移来源的历史结果。原始设备日志、容器 UUID、账号和调试会话不进入新仓库。当前源码重新构建后的检查见 `docs/verification.md`。
