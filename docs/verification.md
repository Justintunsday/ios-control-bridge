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

## 屏幕亮度读写验证（0.4.0，2026-11-04）

在同一设备上构建 `icb-settings`（`BrightnessSystemClient` / `DisplayBrightness`）并执行亮度读写回环。原始数值保留在 [settings-brightness.json](../evidence/settings-brightness.json)。

| 检查 | 结果 |
| --- | --- |
| `settings.get {"setting":"brightness"}` | verified，读到 0.8431398868560791 |
| `settings.set {"setting":"brightness","value":0.783139887}` | verified，before 0.8431398868560791，readback 0.7831399440765381 |
| 再次 `settings.get` | verified，读到 0.7831399440765381 |
| 恢复原值 `settings.set {"setting":"brightness","value":0.843139887}` | verified，readback 0.8431398868560791 |
| 最终 `settings.get` | verified，读到 0.8431398868560791 |
| 测试后 `settings.get {"setting":"volume"}` | verified，仍为 0.0 |
| 不支持的 `wifi` | unavailable / unsupported_setting |
| 越界值 2.0 | error / invalid_value |
| 以 mobile 身份直接运行 helper | get / set / readback / restore 通过，原亮度恢复 |
| Python 测试 | 34 项通过 |

本次验证只改变屏幕亮度并在同一轮恢复；没有修改音量、网络开关、闹钟、提醒事项或其他设置。

## 文件、浏览器、天气与活动监测验证（0.5.0，2026-11-04）

在 `/var/jb/var/root/ios-control-bridge` 重新构建三个原生 helper，并在 iPhone SE 2 / iOS 16.1.1 / 20B101 上执行 0.5.0 验收。完整机器可读摘要见 [features-0.5.0.json](../evidence/features-0.5.0.json)。

| 检查 | 结果 |
| --- | --- |
| `capabilities` | verified；13 个 implemented 操作全部 ready |
| `files.list` 仓库目录 | verified，5 项，`truncated=true` |
| `files.search` 查询 `settings` | verified，5 项匹配，扫描 30 项 |
| `files.read README.md`（4000 字节上限） | partial，UTF-8，按上限截断 |
| 文件非法相对路径 | error / invalid_path |
| `activities.watch` 随机不存在活动 ID | verified，2 个样本，均 target_found=false，无状态变化 |
| `browser.search` "iPhone terminal emulator" | verified；DuckDuckGo 返回 202/0 结果，Bing 回退返回结果 |
| `browser.read https://example.com/` | verified，标题 Example Domain，最终 URL 一致 |
| `browser.open https://example.com/` | verified，LaunchServices 接受并打开；Safari 被带到前台 |
| 非 HTTP(S) URL | error / unsupported_url_scheme |
| `weather.current` 柏林坐标 | verified，Open-Meteo，Europe/Berlin，部分多云 |
| `weather.forecast` 2 天 | verified，2 条日预报 |
| 非法坐标 | error / invalid_location |
| Python 测试 | 62 项通过（设备 Python 3.9.9） |

浏览器 provider 是外部页面，DuckDuckGo 可能返回 202 或空结果；适配器在空结果时回退 Bing，并在 `attempts` 中保留每次尝试。`browser.open` 是真实前台 UI 操作，已明确记录。

系统闹钟、提醒事项、低电量模式、网络开关、专注模式和方向锁定仍未实现；阻塞原因与后续建议见 [完成报告](COMPLETION_REPORT.md)。

## ElleKit SpringBoard bridge 验证（0.6.0，2026-11-04）

`low_power` 与 `orientation_lock` 通过可选 ElleKit tweak 注入 SpringBoard 实现；bridge 源码 `native/ellekit/SpringBridge.m`，构建安装脚本 `tools/build_ellekit_bridge.py`。完整摘要见 [ellekit-bridge.json](../evidence/ellekit-bridge.json)。

| 检查 | 结果 |
| --- | --- |
| `settings.get {"setting":"low_power"}` | verified，false |
| `settings.set {"setting":"low_power","value":true}` | verified，before false，readback true |
| 再次 get | verified，true |
| 恢复 `value:false` | verified，readback false；最终 get false |
| `settings.get {"setting":"orientation_lock"}` | verified，false |
| `settings.set {"setting":"orientation_lock","value":true}` | verified，before false，readback true |
| 再次 get | verified，true |
| 恢复 `value:false` | verified，readback false；最终 get false |
| bridge `get_wifi` | ok，enabled=1 associated=1（只读） |
| bridge `get_airplane` | ok，airplaneMode=0（只读） |
| Python 测试 | 69 项通过（设备 Python 3.9.9） |

测试只切换低电量模式与方向锁定并立即恢复；Wi-Fi 与飞行模式未改变。期间曾用一个只用于探测的 tweak 验证注入，其 constructor 调用 Foundation 导致 SpringBoard 崩溃与 ElleKit safe mode；最终 bridge 将 constructor 限制为 C/pthread、把 Objective-C 调用放到主队列后稳定运行，探测 tweak 已删除。

## 只读网络/蓝牙状态验证（0.7.0，2026-11-04）

ElleKit bridge 增加 `get_bluetooth`，并把 Wi-Fi、飞行模式、蓝牙作为只读设置暴露。写操作在 CLI 边界直接返回 `read_only_setting`，不会向 bridge 发送命令。

| 检查 | 结果 |
| --- | --- |
| `settings.get {"setting":"wifi"}` | verified，true，`enabled=1 associated=1` |
| `settings.get {"setting":"airplane"}` | verified，false，`airplaneMode=0` |
| `settings.get {"setting":"bluetooth"}` | verified，false，`enabled=0` |
| `settings.set {"setting":"wifi","value":true}` | unavailable / read_only_setting，未发送 bridge 写入 |
| `settings.get {"setting":"low_power"}` | verified，false（原有能力未受影响） |
| Python 测试 | 71 项通过（设备 Python 3.9.9） |

`BluetoothManager -setEnabled:` 在 CLI helper 与 SpringBoard bridge 中均返回 `accepted=0` 且状态不变，因此未实现蓝牙写入。

## 系统闹钟验证（0.8.0，2026-11-04）

新增 `native/alarms/AlarmsBridge.m`，通过私有 `MobileTimer.framework` 的 `MTAlarmManager` 访问系统 Clock 服务；helper 使用 `com.apple.private.mobiletimerd`、`com.apple.private.ClockAngel.client` 和 MobileTimer mach-lookup entitlement 签名。完整摘要见 [alarms.json](../evidence/alarms.json)。

| 检查 | 结果 |
| --- | --- |
| `alarms.list` | verified，0 个用户闹钟 |
| `alarms.create {"hour":23,"minute":57,"title":"ICB Alarm Acceptance"}` | verified，返回真实 alarm ID |
| 创建后 `alarms.list` | verified，能找到该 ID |
| `alarms.update` 改为 minute 56、标签 2 | verified |
| `alarms.set_enabled false` | verified |
| `alarms.set_enabled true`（恢复） | verified |
| `alarms.delete` | verified |
| 删除后 `alarms.list` | verified，该 ID 不存在 |
| 清理探测产生的另一个测试闹钟 | verified，最终 0 个测试闹钟 |
| Python 测试 | 84 项通过（设备端 82 项旧同步集；新测试已加入） |

测试闹钟时间为 23:57 且立即删除，没有等待触发；没有修改用户已有闹钟。

## 日历验证（0.9.0，2026-11-04）

新增 `native/calendar/CalendarBridge.m`，使用私有 EventKit + `com.apple.private.tcc.allow`（Calendar/Reminders/AddressBook）和 `com.apple.private.calendar.calaccessd` entitlement。完整摘要见 [calendar.json](../evidence/calendar.json)。

| 检查 | 结果 |
| --- | --- |
| EventKit authorization | event/reminder 均为 3（authorized） |
| `calendar.list` | verified，9 个日历，3 个来源 |
| `calendar.create {"title":"ICB Calendar Acceptance"}` | verified，创建于 iCloud 来源，返回真实 calendar ID |
| 创建后 `calendar.list` | verified，10 个日历，包含测试日历 |
| `calendar.delete` | verified |
| 删除后 `calendar.list` | verified，9 个日历，测试日历不存在 |
| Python 测试 | 92 项通过 |

TCC/EventKit 对路径敏感：同一 helper 位于 `/var/jb/usr/local/bin/icb-calendar` 时可以访问，位于 `/var/jb/var/root/...` 时返回 `calendar_access_denied`。部署时需要复制到 `/var/jb/usr/local/bin/icb-calendar`。

提醒事项仍不可用：authorization 为 authorized，但设备没有提醒账户/默认清单；在 iCloud、Subscribed、Other 来源创建提醒清单都返回成功但不会持久化（提醒清单数量始终为 0）。

## 日历事件验证（0.10.0，2026-11-04）

在 0.9.0 日历容器基础上增加事件操作，摘要见 [calendar-events.json](../evidence/calendar-events.json)。

| 检查 | 结果 |
| --- | --- |
| `calendar.create` 测试日历 | verified |
| `calendar.event_create` 2026-11-05 10:00–11:00Z | verified |
| `calendar.events` 查询同一范围 | verified，找到事件 |
| `calendar.event_delete` | verified |
| 删除后 `calendar.events` | verified，count 0 |
| `calendar.delete` 测试日历 | verified |
| `calendar.list` 最终 | verified，9 个日历 |
| Python 测试 | 97 项通过 |

事件 ID 使用 EventKit 的 event identifier，并非 UUID；适配器按有界字符串校验并精确删除。测试日历与事件均已清理。
