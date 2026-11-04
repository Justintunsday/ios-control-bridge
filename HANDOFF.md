# 开发交接：iOS Control Bridge

仓库：https://github.com/Justintunsday/ios-control-bridge

这是独立、客户端中立的 iOS 系统服务项目。用户希望让 DeepSeek 暂时接手。模型和编码客户端不是运行依赖，不需要接入原编码代理的对话服务器。

## 用户目标

读取并调整大部分日常系统服务：设置 / 控制中心开关、系统闹钟、提醒事项、浏览器与网络查询、天气。保留文件查询及 Live Activities 能力。详见 [服务范围](docs/services.md) 和 [路线图](docs/roadmap.md)。

## 已完成和未完成

- 已实现并在迁移后的独立目录验证：`device.info`、`activities.get`。
- 原生实时活动读取器支持当前 iOS 16.1.1 / 20B101 上的跨 App 原始正文、Attributes 和状态读取。单次查询不是常驻监听。
- 统一入口为 `bin/iosctl`，Python 3.9+；接口结果为 JSON，协议在 `schemas/`。
- 设置写入、闹钟、提醒事项、浏览器、天气、文件统一接口及持续监听仍未实现。注册表中的 planned 操作必须返回 `unavailable/not_implemented`。
- 迁移验证为 18 项 Python 测试、15 项终端探测离线测试，以及 8 项手机检查。去除个人信息的证据在 [migration-summary.json](evidence/migration-summary.json)。

不能将旧原生二进制的历史结果当成后续修改的验证，也不能将 planned 能力说成已完成。

## 当前代码布局

| 位置 | 当前职责 |
| --- | --- |
| `src/ios_control_bridge` | Python CLI、操作注册表、结果封装、设备信息与原生进程边界检查 |
| `native/activities/ActivityBridge.m` | 已核对 ABI 的 Objective-C runtime / BSServiceConnection 调用与原始数据解码 |
| `native/activities/main.swift` | 入口、版本检查、超时、Swift 对象反射、队列访问和 JSON 输出 |
| `tools/build_native.py` | 使用已有 SDK、clang、Swift 和 ldid 构建 arm64 helper |
| `skills/ios-control-bridge` | 可移植 AI 技能，不绑定某个模型或对话服务 |

## 语言选择：建议，尚未整仓迁移

用户正在评估 Python 与 Objective-C。建议让 **Objective-C 承担新增 iOS 系统服务的主要实现**，暂时保留 Python CLI、测试和构建脚本。若以后需要原生常驻服务或免 Python 的手机安装包，再逐步将分发入口迁为原生 CLI / daemon；保持现有 JSON 契约和已验证实现作为对照。

当前并非纯 Python 项目：系统私有调用已经在 Objective-C 层，实时活动还有必要的 Swift 代码。因此不要先花一轮把全部 Python 重写，再开始新增服务。

特别注意 `main.swift`：它通过 `Mirror` 沿已核对的 ActivityKit Swift 对象布局取得真实连接，并在客户端自身的串行队列上读连接枚举。已有 Objective-C 桥接只覆盖暴露给 Objective-C runtime 的部分。直接删掉 Swift 文件、把它机械翻译成 KVC，或猜 Swift 内存偏移，都不能保持当前能力。保留这段小桥接，直到有经过真机验证的替代入口。

语言迁移目前是建议，现有代码仍保持已验证的结构。Objective-C / Swift 混合项目的官方说明见 [Importing Objective-C into Swift](https://developer.apple.com/documentation/swift/importing-objective-c-into-swift)。

## 下一块工作

先在当前设备上确认一个可恢复设置项的真实 getter / setter，完成“读取 → 参数校验 → 按明确请求调整 → 读回 → 恢复测试值”。亮度、音量、低电量模式是候选，支持性仍需逐项核实。网络开关、会响铃的闹钟、个人提醒事项不作为无关的探测副作用。

新增设置适配器优先放在 `native/settings`，通过固定参数或 JSON 与 CLI 连接。遵守 [AGENTS.md](AGENTS.md)；检查实际方法签名、线程要求、权限与系统版本，不按 root 身份推断接口可用。当前目标是系统真实功能，不能用普通通知代替系统时钟里的闹钟，也不改未知私人数据库。

## 本地和设备验证

```sh
python3 -m unittest discover -s tests -v
python3 bin/iosctl capabilities
python3 bin/iosctl call device.info
python3 tools/build_native.py --sdk /path/to/installed/iPhoneOS.sdk
python3 bin/iosctl call activities.get --params '{"activity_id":"实际活动 UUID"}'
```

现有手机源码目录为 `/var/jb/var/root/ios-control-bridge`。原生 helper 位于 `build/native/icb-activities`。Windows 开发目录为 `C:\ios-control-bridge`。上一次中断发生在最终文档 / Git 元数据同步前：手机上的编译源码和 CLI 已通过验证，但不要假定它已经是完整的远端 Git 克隆；接手时核对实际文件与提交。

设备地址、SSH 凭据、完整日志、真实条目 UUID 和临时迁移脚本保留在仓库外，不向模型提供密码，也不提交到公开仓库。没有设备连接时可完成本地测试和代码工作，真机步骤应报告待验证。

## 可直接提供给接手模型的任务

> 阅读仓库的 HANDOFF.md、AGENTS.md、README.md 和 docs/roadmap.md。保持客户端中立的 JSON 接口，优先用 Objective-C 实现新增 iOS 系统服务，保留现有 Swift 实时活动桥接和 Python 测试 / CLI。先核实现有能力与设备连接，再实现一个常用设置的真实读写闭环。不要把 planned 操作冒充已实现，不提交凭据或个人数据；没有真机结果时标明未验证。
