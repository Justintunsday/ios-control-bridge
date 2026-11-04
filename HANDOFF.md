# 开发交接：iOS Control Bridge

仓库：https://github.com/Justintunsday/ios-control-bridge

这是独立、客户端中立的 iOS 系统服务项目。用户希望让 DeepSeek 暂时接手。模型和编码客户端不是运行依赖，不需要接入原编码代理的对话服务器。

## 用户目标

读取并调整大部分日常系统服务：设置 / 控制中心开关、系统闹钟、提醒事项、浏览器与网络查询、天气。保留文件查询及 Live Activities 能力。详见 [服务范围](docs/services.md) 和 [路线图](docs/roadmap.md)。

## 已完成和未完成

- 已实现并在迁移后的独立目录验证（0.10.0）：`device.info`、`activities.get` / `activities.watch`、音量/亮度/低电量模式/方向锁定的 `settings.get` / `settings.set`、Wi-Fi/飞行模式/蓝牙只读、系统闹钟 `alarms.*`、日历与事件 `calendar.*`、`browser.search` / `read` / `open`、`weather.current` / `forecast`、`files.list` / `search` / `read`。
- 原生实时活动读取器支持当前 iOS 16.1.1 / 20B101 上的跨 App 原始正文、Attributes 和状态读取。单次查询不是常驻监听。
- 统一入口为 `bin/iosctl`，Python 3.9+；接口结果为 JSON，协议在 `schemas/`。
- 提醒事项、Wi-Fi/蓝牙/飞行模式/蜂窝/专注模式的可写控制及常驻监听仍未实现。系统闹钟已通过私有 `MobileTimer.framework` 实现；日历已通过私有 EventKit + TCC entitlement 实现。提醒事项授权可用，但设备没有提醒账户/默认清单，创建不持久。Wi-Fi/飞行模式/蓝牙已提供只读状态，写入返回 `read_only_setting`；蓝牙 `setEnabled:` 在 CLI 与 SpringBoard 均未生效，Wi-Fi/飞行模式写入存在断网风险。注册表中的 planned 操作必须返回 `unavailable/not_implemented`。低电量模式、方向锁定和只读网络状态依赖可选 ElleKit bridge（`native/ellekit`，`tools/build_ellekit_bridge.py`）；未安装 bridge 时相关设置返回 `ellekit_bridge_unavailable`。
- 浏览器 provider、天气 provider、文件边界、活动轮询和剩余阻塞项记录在 `docs/COMPLETION_REPORT.md` 与 `evidence/features-0.5.0.json`。
- 设置适配器当前支持 `volume`（`AVSystemController`，`Audio/Video` 类别）和 `brightness`（`BrightnessSystemClient`，`DisplayBrightness`），取值均为 0.0-1.0。原生 helper 位于 `native/settings/settings.m`；`browser.open` 的 helper 位于 `native/browser/open_url.m`；`tools/build_native.py` 一次构建 `build/native/icb-activities`、`icb-settings` 和 `icb-open-url`。
- 当前测试为 62 项 Python 测试（0.5.0），并在真机验证文件、浏览器、天气与活动监测；迁移期 18 项测试与 8 项手机检查的证据仍在 [migration-summary.json](evidence/migration-summary.json)。

不能将旧原生二进制的历史结果当成后续修改的验证，也不能将 planned 能力说成已完成。

## 当前代码布局

| 位置 | 当前职责 |
| --- | --- |
| `src/ios_control_bridge` | Python CLI、操作注册表、结果封装、设备信息与原生进程边界检查 |
| `native/activities/ActivityBridge.m` | 已核对 ABI 的 Objective-C runtime / BSServiceConnection 调用与原始数据解码 |
| `native/activities/main.swift` | 入口、版本检查、超时、Swift 对象反射、队列访问和 JSON 输出 |
| `native/settings/settings.m` | 媒体音量与屏幕亮度 getter / setter、参数校验、读回验证与 JSON 输出 |
| `native/browser/open_url.m` | 通过 `LSApplicationWorkspace` 打开显式 HTTP(S) URL |
| `native/ellekit/SpringBridge.m` | 可选 ElleKit SpringBoard bridge：低电量/方向锁定读写，Wi-Fi/飞行模式只读 |
| `tools/build_native.py` | 使用已有 SDK、clang、Swift 和 ldid 构建 arm64 helper |
| `skills/ios-control-bridge` | 可移植 AI 技能，不绑定某个模型或对话服务 |

## 语言选择：建议，尚未整仓迁移

用户正在评估 Python 与 Objective-C。建议让 **Objective-C 承担新增 iOS 系统服务的主要实现**，暂时保留 Python CLI、测试和构建脚本。若以后需要原生常驻服务或免 Python 的手机安装包，再逐步将分发入口迁为原生 CLI / daemon；保持现有 JSON 契约和已验证实现作为对照。

当前并非纯 Python 项目：系统私有调用已经在 Objective-C 层，实时活动还有必要的 Swift 代码。因此不要先花一轮把全部 Python 重写，再开始新增服务。设置 adapter 已按此方式实现：Objective-C helper + Python 参数/结果边界。

特别注意 `main.swift`：它通过 `Mirror` 沿已核对的 ActivityKit Swift 对象布局取得真实连接，并在客户端自身的串行队列上读连接枚举。已有 Objective-C 桥接只覆盖暴露给 Objective-C runtime 的部分。直接删掉 Swift 文件、把它机械翻译成 KVC，或猜 Swift 内存偏移，都不能保持当前能力。保留这段小桥接，直到有经过真机验证的替代入口。

语言迁移目前是建议，现有代码仍保持已验证的结构。Objective-C / Swift 混合项目的官方说明见 [Importing Objective-C into Swift](https://developer.apple.com/documentation/swift/importing-objective-c-into-swift)。

## 下一块工作

媒体音量与屏幕亮度已完成读写闭环；文件、浏览器、天气和有界活动监测已完成 0.5.0 真机验收。下一步优先研究系统闹钟与提醒事项的真实接口和授权路径，并在不产生网络断开或可听副作用的前提下继续设置项；网络开关、会响铃的闹钟、个人提醒事项不作为无关的探测副作用。

新增设置适配器优先放在 `native/settings`，通过固定参数或 JSON 与 CLI 连接。遵守 [AGENTS.md](AGENTS.md)；检查实际方法签名、线程要求、权限与系统版本，不按 root 身份推断接口可用。当前目标是系统真实功能，不能用普通通知代替系统时钟里的闹钟，也不改未知私人数据库。

## 本地和设备验证

```sh
python3 -m unittest discover -s tests -v
python3 bin/iosctl capabilities
python3 bin/iosctl call device.info
python3 tools/build_native.py --sdk /path/to/installed/iPhoneOS.sdk
python3 bin/iosctl call activities.get --params '{"activity_id":"实际活动 UUID"}'
python3 bin/iosctl call settings.get --params '{"setting":"volume"}'
python3 bin/iosctl call settings.set --params '{"setting":"volume","value":0.3}'
python3 bin/iosctl call settings.get --params '{"setting":"brightness"}'
python3 bin/iosctl call settings.get --params '{"setting":"low_power"}'
python3 bin/iosctl call settings.set --params '{"setting":"orientation_lock","value":true}'
python3 bin/iosctl call settings.get --params '{"setting":"wifi"}'
python3 bin/iosctl call settings.get --params '{"setting":"bluetooth"}'
python3 bin/iosctl call files.list --params '{"path":"/var/jb/var/root/ios-control-bridge","limit":5}'
python3 bin/iosctl call browser.search --params '{"query":"iPhone terminal","limit":3}'
python3 bin/iosctl call weather.current --params '{"latitude":52.52,"longitude":13.41}'
```

现有手机源码目录为 `/var/jb/var/root/ios-control-bridge`。原生 helper 位于 `build/native/icb-activities`、`icb-settings`、`icb-open-url`、`icb-alarms`、`icb-calendar`；日历 helper 还需安装到 `/var/jb/usr/local/bin/icb-calendar`。可选 ElleKit bridge 位于 `/var/jb/usr/lib/TweakInject/icbridge.dylib`。Windows 开发目录为 `C:\ios-control-bridge`。上一次中断发生在最终文档 / Git 元数据同步前：手机上的编译源码和 CLI 已通过验证，但不要假定它已经是完整的远端 Git 克隆；接手时核对实际文件与提交。

设备地址、SSH 凭据、完整日志、真实条目 UUID 和临时迁移脚本保留在仓库外，不向模型提供密码，也不提交到公开仓库。没有设备连接时可完成本地测试和代码工作，真机步骤应报告待验证。

## 可直接提供给接手模型的任务

> 阅读仓库的 HANDOFF.md、AGENTS.md、README.md 和 docs/roadmap.md。保持客户端中立的 JSON 接口，优先用 Objective-C 实现新增 iOS 系统服务，保留现有 Swift 实时活动桥接和 Python 测试 / CLI。先核实现有能力与设备连接，再实现一个常用设置的真实读写闭环。不要把 planned 操作冒充已实现，不提交凭据或个人数据；没有真机结果时标明未验证。
