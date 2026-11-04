# 开发完成报告：iOS Control Bridge 0.5.0

日期：2026-11-04
设备环境：iPhone SE 2（`iPhone12,8`）、iOS 16.1.1 / 20B101、Dopamine rootless、`/var/jb`
委托来源：仓库 `HANDOFF.md` 与用户要求“继续完成剩下的功能并写报告”。

## 1. 结论摘要

本次交付把设置之外的四个服务面和实时活动监测落地，并在真机完成验证：

| 服务面 | 状态 |
| --- | --- |
| `settings.get` / `settings.set` | 媒体音量、屏幕亮度已实现并真机验证 |
| `activities.get` / `activities.watch` | 按 ID 读取与有界轮询监测已实现，轮询在真机验证 |
| `files.list` / `files.search` / `files.read` | 统一接口已实现并真机验证（有界目录列举、检索、有界读取） |
| `browser.search` / `browser.read` / `browser.open` | 已实现并真机验证（搜索 provider、正文提取、LaunchServices 打开） |
| `weather.current` / `weather.forecast` | 已实现并真机验证（Open-Meteo，明确坐标与单位） |
| 系统闹钟、提醒事项 | 仍未实现，原因见第 5 节 |
| 其余设置项（低电量、Wi-Fi、蓝牙、蜂窝、飞行模式、专注模式等） | 仍未实现，原因见第 5 节 |

版本：`0.5.0`。设备端与本机 Python 测试均为 **62 项通过**：
`python3 -m unittest discover -s tests -v`。

## 2. 本次新增实现

### 2.1 文件服务（纯 Python，无额外 helper）

- `files.list`：显式绝对目录、`limit` 1–500、可选隐藏文件；返回名称、类型、大小、权限和时间；超过限制标记 `truncated`。
- `files.search`：显式目录、查询串、`limit` 1–200、`max_depth` 1–10；有界扫描并返回匹配项与扫描计数。
- `files.read`：显式文件、`max_bytes` 1–1,048,576；拒绝二进制文件；返回 UTF-8 内容、字节数、截断标志和编码。
- 错误区分：非法路径/参数为 `error`，缺失路径/权限/非目录/二进制为 `unavailable`。
- 源码：`src/ios_control_bridge/files.py`。

### 2.2 活动监测

- `activities.watch`：对指定活动 ID 做有界前台轮询，参数 `duration_ms`（1000–30000）、`interval_ms`（500–5000）、`timeout_ms`（500–5000）、`stop_on_change`。
- 每次采样只保留时间、目标是否存在和状态，不重复输出正文；可选在状态变化时提前停止；返回样本、变化次数与是否提前停止。
- 没有常驻守护进程、通知或断线重连；单次 CLI 调用即完整生命周期。
- 源码：`src/ios_control_bridge/activities.py`。

### 2.3 浏览器服务

- `browser.search`：先请求 DuckDuckGo HTML；若返回空结果则回退 Bing HTML，并报告实际使用的 provider 和每次尝试的结果数。
- `browser.read`：仅接受 HTTP(S)，抓取有界正文，提取标题与可读文本，返回最终 URL、状态码、内容类型、截断标志。
- `browser.open`：新增原生 helper `native/browser/open_url.m`，通过 `LSApplicationWorkspace -openURL:withOptions:error:` 打开 URL；返回 `opened` 和 LaunchServices 来源。该操作会把目标 App 带到前台，属于真实 UI 副作用。
- 源码：`src/ios_control_bridge/browser.py`、`native/browser/open_url.m`。

### 2.4 天气服务

- `weather.current` / `weather.forecast`：显式 `latitude`、`longitude`、`units`（metric/imperial）、可选 `timezone`、`days`（1–7）。
- 使用 Open-Meteo HTTP API，保留 provider、attribution、时区、UTC 偏移和请求 URL；不做历史缓存冒充当前数据。
- 无 API key 依赖；网络失败明确返回 `unavailable`。
- 源码：`src/ios_control_bridge/weather.py`。

### 2.5 构建与注册表

- `tools/build_native.py` 一次构建并签名三个 helper：
  - `icb-activities`（实时活动）
  - `icb-settings`（音量、亮度）
  - `icb-open-url`（LaunchServices 打开 URL）
- 能力注册表将新增操作标记为 implemented / device_verified；`capabilities` 输出 supported settings、verified builds 与运行时 ready 状态。
- 版本：`0.5.0`。

## 3. 真机验证

工件与证据：`evidence/features-0.5.0.json`、`evidence/settings-volume.json`、`evidence/settings-brightness.json`。

| 检查 | 结果 |
| --- | --- |
| `capabilities` | verified；13 个 implemented 操作全部 `ready_to_query` |
| `files.list /var/jb/var/root/ios-control-bridge` | verified，5 项，`truncated=true` |
| `files.search` 查询 `settings` | verified，5 项匹配，扫描 30 项 |
| `files.read README.md` | partial（按 4000 字节截断），UTF-8 |
| `activities.watch` 随机不存在的活动 ID | verified，2 个样本，均 `target_found=false`，无状态变化 |
| `browser.search` "iPhone terminal emulator" | verified；DuckDuckGo 返回 202/0 结果，Bing 回退返回结果 |
| `browser.read https://example.com/` | verified，标题 `Example Domain`，最终 URL 一致 |
| `browser.open https://example.com/` | verified，`opened=true`；设备上 Safari 被带到前台 |
| `weather.current` 柏林坐标 | verified；Open-Meteo，`Europe/Berlin`，部分多云 |
| `weather.forecast` 2 天 | verified，2 条日预报 |
| 文件非法路径 / 天气非法坐标 / 非 HTTP URL | error，原因分别为 `invalid_path` / `invalid_location` / `unsupported_url_scheme` |
| 本机与设备 Python 测试 | 62 项通过（设备 Python 3.9.9） |

## 4. 已知限制与风险

- 浏览器搜索依赖第三方 HTML 页面（DuckDuckGo/Bing），页面结构或反爬策略变化会导致空结果；适配器会返回 `partial/no_search_results` 或回退，不会伪造结果。
- `browser.open` 会实际切换前台 App；测试时已打开一次 `https://example.com/`，Safari 可能仍在前台。
- 天气依赖 Open-Meteo 公网服务；断网、限流或 provider 字段变化会明确失败，不使用缓存旧数据。
- 文件读取只覆盖显式路径，不提供通配符或递归读取任意目录；符号链接按显式路径处理。
- 活动监测是有界轮询，不是常驻服务；没有通知、断线重连或后台生命周期管理。
- 网络开关、闹钟、提醒事项等高风险服务没有为了“补齐列表”而做未经验证的写入。

## 5. 未完成项及阻塞原因

### 5.1 系统闹钟（`alarms.*`）

iOS 16.1.1 没有公开的“系统时钟闹钟”API（Apple `AlarmKit` 面向 iOS/iPadOS 26）。当前未找到可安全固定调用的私有服务入口，也没有在未核实签名的情况下修改时钟数据库。因此 `alarms.*` 保持 `not_implemented`；需要在当前设备上确认系统闹钟服务的真实 XPC/私有接口后再实现。

### 5.2 提醒事项（`reminders.*`）

EventKit 需要 App 上下文、用户授权和明确的清单/条目范围；命令行进程无法可靠呈现授权流程。仓库不自动修改个人提醒事项或授权数据库，因此保持 `not_implemented`；若要继续，需要先确定授权获取方式和明确的目标清单。

### 5.3 其余设置项

- 低电量模式：`NSProcessInfo` 只暴露 `isLowPowerModeEnabled`，未找到运行时 setter；`_setLowPowerModeEnabled:` 在当前系统不存在。
- Wi-Fi / 蓝牙 / 蜂窝 / 飞行模式 / 专注模式 / 方向锁定：涉及私有系统服务、权限或网络断开副作用；未做未经验证的写入。
- 上述项目继续作为候选，按“真实 getter/setter → 参数校验 → 读回 → 恢复”的流程逐项确认后再接入。

## 6. 复验命令

```sh
python3 -m unittest discover -s tests -v
python3 tools/build_native.py --sdk /var/jb/opt/sdks/iPhoneOS16.5.sdk
python3 bin/iosctl capabilities
python3 bin/iosctl call files.list --params '{"path":"/var/jb/var/root/ios-control-bridge","limit":5}'
python3 bin/iosctl call files.search --params '{"path":"/var/jb/var/root/ios-control-bridge","query":"settings"}'
python3 bin/iosctl call files.read --params '{"path":"/var/jb/var/root/ios-control-bridge/README.md","max_bytes":4000}'
python3 bin/iosctl call activities.watch --params '{"activity_id":"UUID","duration_ms":1500,"interval_ms":500,"timeout_ms":3000}'
python3 bin/iosctl call browser.search --params '{"query":"iPhone terminal emulator","limit":3}'
python3 bin/iosctl call browser.read --params '{"url":"https://example.com/","max_chars":800}'
python3 bin/iosctl call weather.current --params '{"latitude":52.52,"longitude":13.41}'
python3 bin/iosctl call weather.forecast --params '{"latitude":52.52,"longitude":13.41,"days":2}'
```

## 7. 结论

`0.5.0` 在原有设备信息、实时活动读取、音量与亮度设置之上，完成了文件、浏览器、天气和活动监测四类能力，并在 iPhone SE 2 / iOS 16.1.1 上完成真机验收。除闹钟、提醒事项和其余高风险/无可用接口的设置项外，当前路线图中的常规服务均已具备可执行的固定接口；未完成项已明确记录阻塞原因，没有以模拟成功或未验证写入替代。

## 8. 0.6.0 补充：ElleKit SpringBoard bridge

对于 CLI 无法直接控制的 `low_power` 与 `orientation_lock`，新增可选 ElleKit tweak `native/ellekit/SpringBridge.m`：

- 注入 `com.apple.springboard`，以固定命令/结果文件协议接收动作；
- 低电量通过 `_PMLowPowerMode` 的 `getPowerMode` / `setPowerMode:fromSource:`；
- 方向锁定通过 `SBOrientationLockManager` 的 `isUserLocked` / `lock` / `unlock`；
- 额外提供 Wi-Fi / 飞行模式只读状态（未暴露为可写设置，避免断开网络）；
- CLI `settings.get/set` 已把这两项纳入 `supported_settings` 与 `available_settings`。

设备结果：低电量 false → true → true → false；方向锁定 false → true → true → false；均在同一轮恢复。测试 69 项通过。安装与安全边界见 `docs/ELLEKIT_BRIDGE.md`，证据见 `evidence/ellekit-bridge.json`。

仍未完成：系统闹钟、提醒事项、Wi-Fi/蓝牙/蜂窝/飞行模式/专注模式的可写控制。前两者需要各自的目标进程与授权路径；网络开关的写入需要用户明确的断网测试窗口，当前只保留只读能力。

## 9. 0.7.0 补充：只读网络与蓝牙状态

- 新增只读设置 `wifi`、`airplane`、`bluetooth`；通过 ElleKit bridge 读取 SpringBoard 内状态。
- 写操作在 CLI 边界返回 `unavailable/read_only_setting`，不会向 bridge 发送写入命令。
- 设备结果：Wi-Fi true（enabled=1 associated=1）、飞行模式 false、蓝牙 false；低电量读取仍正常；测试 71 项通过。
- 蓝牙写入未实现：`BluetoothManager -setEnabled:` 在 CLI 和 SpringBoard 上下文都返回未生效；Wi-Fi/飞行模式写入会断开当前 SSH 网络，未做未经验证的写操作。
- 证据：`evidence/readonly-network-settings.json`；相关说明已同步到 README、服务范围、架构、验证、技能与 HANDOFF。
