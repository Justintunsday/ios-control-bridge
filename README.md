# iOS Control Bridge

让 AI 或其他客户端通过独立、可验证的接口，读取并调整 iPhone 的常用系统服务。

项目提供本机 `iosctl` JSON 命令和原生服务适配器，可在已有 SSH / 终端通道中运行。运行与构建不依赖编码代理服务器、AI SDK 或特定模型。当前设备适配以已越狱的 iOS 16.1.1 为起点，扩展到其他系统版本时逐项验证。

## 目标与当前状态

| 服务 | 目标 | 当前实现 |
| --- | --- | --- |
| 设备信息 | 系统版本、型号、UID、bootstrap 证据 | 已实现，迁移后真机验证见文档 |
| 实时活动 | 跨 App 正文、Attributes、状态和变化监测 | 按 ID 读取与有界轮询监测已实现；常驻监测待开发 |
| 设置 / 控制中心 | Wi-Fi、蓝牙、蜂窝、飞行模式、亮度、音量、低电量、方向锁定、专注模式等的读取与调整 | 媒体音量、屏幕亮度、低电量模式、方向锁定已实现并真机验证；Wi-Fi、飞行模式、蓝牙为只读；低电量/方向锁定/只读状态通过可选 ElleKit SpringBoard bridge；其他设置项待实现 |
| 闹钟 | 系统闹钟列表、创建、改时、重复、启停和删除 | 列表、创建、改时/标签、启停和删除已实现并真机验证（私有 MobileTimer 框架 + mobiletimerd entitlement） |
| 提醒事项 | 清单、查询、新建、编辑、完成和删除 | 已实现并真机验证；使用私有 ReminderKit `REMStore`（EventKit 在该设备返回 0 个清单） |
| 日历 | 日历列表、新建日历、删除指定日历；日历事件查询、新建、删除 | 日历与事件操作已实现并真机验证（私有 EventKit + TCC entitlement） |
| 浏览器 / 网络查询 | 搜索结果、网页内容提取、打开指定页面 | 搜索、正文提取与 LaunchServices 打开已实现并真机验证 |
| 天气 | 指定位置的实况、预报、来源及数据时间 | Open-Meteo 实况与预报已实现并真机验证 |
| 文件 | 明确目录内的列举、检索和有界读取 | 统一接口已实现并真机验证 |

能力清单中 `implemented` 表示已有适配代码，`validation` 表示验证状态，`runtime.ready_to_query` 表示当前执行环境具备查询条件。声明中的未来能力不会返回模拟成功。

## 使用

Python 3.9+，Python 核心无第三方运行依赖。直接从仓库运行：

```sh
python3 bin/iosctl capabilities
python3 bin/iosctl capabilities --service settings
python3 bin/iosctl call device.info
python3 bin/iosctl call activities.get --params '{"activity_id":"实际活动 UUID"}'
python3 bin/iosctl call settings.get --params '{"setting":"volume"}'
python3 bin/iosctl call settings.set --params '{"setting":"volume","value":0.4}'
python3 bin/iosctl call settings.get --params '{"setting":"brightness"}'
python3 bin/iosctl call settings.get --params '{"setting":"low_power"}'
python3 bin/iosctl call alarms.list
python3 bin/iosctl call alarms.create --params '{"hour":23,"minute":57,"title":"Alarm"}'
python3 bin/iosctl call calendar.list
python3 bin/iosctl call calendar.create --params '{"title":"My Calendar"}'
python3 bin/iosctl call settings.set --params '{"setting":"orientation_lock","value":true}'
python3 bin/iosctl call files.list --params '{"path":"/var/jb/var/root/ios-control-bridge","limit":5}'
python3 bin/iosctl call browser.search --params '{"query":"iPhone terminal","limit":3}'
python3 bin/iosctl call weather.current --params '{"latitude":52.52,"longitude":13.41}'
```

Windows 上可用 `py -3 bin/iosctl capabilities` 检查目录和接口；设备查询需要在真实 iOS 设备执行。在非 iOS 主机上返回 `unavailable/not_ios`。

也可安装命令入口：`python3 -m pip install --no-deps -e .`，之后调用 `iosctl`。任何能执行本机命令并解析 JSON 的客户端都可使用该接口；提供给 AI 的可移植技能位于 `skills/ios-control-bridge`。

原生 helper 需要现有 clang、Swift、ldid 和 iPhoneOS SDK，在手机仓库根目录构建；一次构建会生成实时活动读取器和设置适配器：

```sh
python3 tools/build_native.py --sdk /var/jb/opt/sdks/iPhoneOS16.5.sdk
python3 bin/iosctl call activities.get \
  --params '{"activity_id":"实际活动 UUID","timeout_ms":5000}'
python3 bin/iosctl call settings.get --params '{"setting":"volume"}'
```

默认 helper 路径为仓库内 `build/native/icb-activities`、`build/native/icb-settings`、`build/native/icb-open-url`、`build/native/icb-alarms`、`build/native/icb-calendar`、`build/native/icb-reminders`。需要显式指定已有 helper 时，使用 `ICB_ACTIVITIES_HELPER`、`ICB_SETTINGS_HELPER`、`ICB_OPEN_URL_HELPER`、`ICB_ALARMS_HELPER`、`ICB_CALENDAR_HELPER`、`ICB_REMINDERS_HELPER`；SDK 可通过 `ICB_SDK` 配置。日历与提醒 helper 还需安装到 `/var/jb/usr/local/bin/`（`icb-calendar`、`icb-reminders`，TCC/私有框架对路径敏感），见 [完成报告](docs/COMPLETION_REPORT.md) 与 [设备验证记录](docs/verification.md)。低电量模式与方向锁定需要额外安装可选 ElleKit SpringBoard bridge：`sudo python3 tools/build_ellekit_bridge.py --respring`；详见 [ElleKit bridge](docs/ELLEKIT_BRIDGE.md)。仓库不保存设备地址、密码或 SSH 私钥。

## 结果和开发

所有 `call` 返回 `ios-control-bridge.result.v1` JSON，包含请求 ID、操作、观测时间、来源和范围完整性：`verified` / `partial` / `unavailable` / `error`，退出码分别为 `0 / 2 / 3 / 4`。完整查询没有目标，与查询失败分别表示。

`settings.get` / `settings.set` 已对媒体音量和屏幕亮度实现并完成真机读写回环；`files.*`、`browser.*`、`weather.*` 与有界 `activities.watch` 也已实现。系统闹钟、提醒事项以及低电量、网络开关等其他设置项仍返回 `unavailable/not_implemented`，阻塞原因记录在完成报告中。写操作以用户明确指定的目标和值执行，修改后读回系统状态，不把发送成功等同于效果已验证。

- [服务范围与验收](docs/services.md)
- [架构与接口契约](docs/architecture.md)
- [开发路线](docs/roadmap.md)
- [实时活动与迁移验证](docs/live-activities.md)
- [设备验证记录](docs/verification.md)
- [0.5.0 开发完成报告](docs/COMPLETION_REPORT.md)
- [ElleKit SpringBoard bridge](docs/ELLEKIT_BRIDGE.md)
- [接手开发说明与语言建议](HANDOFF.md)

本机测试：`python3 -m unittest discover -s tests -v`。真机结果只证明记录中的设备、系统 build 和操作；不将未来服务或其他 iOS 版本列为已验证。

## 团队与维护

- 项目名称：iOS Control Bridge
- 仓库：https://github.com/Justintunsday/ios-control-bridge
- 分支：main
- 维护：iOS Control Bridge contributors
- OpenCode skill/插件名：`ios-control-bridge`
- Skill 说明：`skills/ios-control-bridge/README.md`
- 已验证设备：iPhone12,8 / iOS 16.1.1 / 20B101 / Dopamine rootless
- Sileo 私有 API 包：`com.opencode.sbsnapshot` → `iOS Control Bridge - Private API Snapshot` 0.5
- 私有 API 插件说明：[docs/PRIVATE_API_PLUGIN.md](docs/PRIVATE_API_PLUGIN.md)
