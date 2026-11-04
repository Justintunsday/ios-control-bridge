# 独立项目迁移验证

2026-11-04，在独立目录 `/var/jb/var/root/ios-control-bridge` 从本仓库源码重新构建，构建目标为 arm64 / iOS 16.1。运行设备为 iPhone12,8、iOS 16.1.1 / 20B101。完整设备日志和目标 UUID 保留在设备及工作区的未跟踪本地目录；仓库只保存去除个人数据的 [验证摘要](../evidence/migration-summary.json)。

| 检查 | 结果 |
| --- | --- |
| Python 核心测试 | 18 项通过，包括目标 ID 一致性、空结果、超时、状态 / 退出码及未实现写操作无执行 |
| 技能结构检查 | 通过 |
| 继承的终端探测离线测试 | 15 项通过 |
| 独立设备信息查询 | 通过，取得当前 OS / build、型号、UID 和 bootstrap 证据 |
| 新原生 helper 正文读取 | 通过，从另一个 App 的实际活动读到 value 10 / revision 1 |
| 未知活动 ID | 完整空结果，未返回正文 |
| 100 ms 超时 | unavailable，未返回旧正文 |
| 无效 ID | error，未执行原生查询 |
| planned 设置写入 | not_implemented，未修改 Wi-Fi |
| 从 `/` 目录运行 CLI | 通过，路径由独立仓库解析 |
| 桌面稳定性 | 原进程保持，无安全模式或新增 SpringBoard 崩溃 |

原生 helper 只签入 `com.apple.private.sessionkit.listener=true`。迁移验证没有调用对话服务或旧项目 API，没有替换桌面注入、重载系统、切换网络、创建闹钟或提醒事项。

本次验证证明独立命名、源码构建、统一 CLI 和当前已实现读取适配器可工作。设置、闹钟、提醒事项、浏览器、天气、文件统一接口和持续监测仍处于路线图阶段，不能依据本次结果宣称它们已完成。

## 设置读写验证（0.3.0，2026-11-04）

在 `/var/jb/var/root/ios-control-bridge` 重新构建 `icb-activities` 与 `icb-settings`（同一 SDK 和签名流程），在 iPhone SE 2 / iOS 16.1.1 / 20B101 上执行媒体音量读写回环。原始数值与时间记录在 [settings-volume.json](../evidence/settings-volume.json)。

| 检查 | 结果 |
| --- | --- |
| `settings.get {"setting":"volume"}` | verified，读到 0.0 |
| `settings.set {"setting":"volume","value":0.31}` | verified，before 0.0，requested 0.31，readback 0.3100000023841858 |
| 再次 `settings.get` | verified，读到 0.3100000023841858 |
| 恢复原值 `settings.set {"setting":"volume","value":0.0}` | verified，readback 0.0 |
| 最终 `settings.get` | verified，读到 0.0 |
| 不支持的 `wifi` | unavailable / unsupported_setting，未启动 helper |
| 越界值 2.0 | error / invalid_value，未调用系统 setter |
| 以 mobile 身份直接运行 `icb-settings` | 同样的 get / set / readback / restore 流程通过 |
| Python 测试 | 31 项通过 |

本次验证只改变媒体音量并在同一轮恢复；没有修改网络开关、闹钟、提醒事项或其他设置。
