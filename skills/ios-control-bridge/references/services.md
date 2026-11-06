# 设备服务调用

先运行 `iosctl capabilities`。当前已实现设备、活动、常用设置、系统闹钟、日历、提醒事项、浏览器、天气和文件适配器；网络与蓝牙设置只读，其余设置项按实际清单判断。低电量与方向锁定需要可选 ElleKit bridge 及可用的新 socket；Python 和原生 helper 应成对升级。

| 意图 | 操作 / 参数方向 | 核对点 |
| --- | --- | --- |
| 查看手机系统状态 | `device.info` | 实际设备版本、build、型号和 UID |
| 查看一条实时活动 | `activities.get` / `activity_id` | ID 来自当前目标；保留正文来源、编码和原始状态 |
| 观察活动变化 | `activities.watch` / `activity_id`, `duration_ms`, `interval_ms`, `timeout_ms` | 有界轮询，样本保留正文、生命周期与存在性；0.12.0 正文变化离线回归通过，真机变化验收待测试 App 前台 |
| 读取 / 调整音量或亮度 | `settings.get` / `settings.set`，参数 `{"setting":"volume"}` 或 `{"setting":"brightness"}`；写入另带 `"value"`（0.0-1.0） | 当前音量与亮度已实现；写后读回，测试后恢复原值 |
| 低电量模式 / 方向锁定 | `settings.get` / `settings.set`，参数 `{"setting":"low_power"}` 或 `{"setting":"orientation_lock"}`；写入 `"value"` 为 true/false | 需要可选 ElleKit SpringBoard bridge；写后读回，测试后恢复原值 |
| Wi-Fi / 飞行模式 / 蓝牙状态 | `settings.get`，参数 `{"setting":"wifi"}` / `airplane` / `bluetooth` | 只读；写入返回 `unavailable/read_only_setting` |
| 文件 | `files.list` / `files.search` / `files.read`，显式绝对路径 | 结果有界；权限失败与空结果区分；只读指定文件 |
| 安装 / 删除 App | `apps.list`, `apps.get`, `apps.store_info`, `apps.install`, `apps.download`, `apps.uninstall` | App Store / HTTPS IPA 明确来源；删除只用准确 bundle ID；独立读回安装版本或完全消失；认证在手机完成。见 [apps.md](apps.md) |
| 设置闹钟 | `alarms.create` / 明确 hour、minute、title | 系统闹钟返回真实 ID；写后读回，测试闹钟须清理 |
| 修改已有闹钟 | `alarms.update` / `alarms.set_enabled` / `alarms.delete` | 用准确 ID；删除或改时不能扩大到全部；当前实现于私有 MobileTimer helper |
| 提醒事项 | `reminders.lists` / `list` / `create` / `update` / `complete` / `delete` | 清单和条目 ID、时间与授权状态；使用私有 ReminderKit，写后读回，测试提醒须清理 |
| 日历 | `calendar.list` / `calendar.create` / `calendar.delete` / `calendar.events` / `calendar.event_create` / `calendar.event_delete` | 显式标题、来源和时间范围；events 可用 limit/offset 分页，partial 不能当完整；创建核对新 ID、时间和备注 |
| 网络查询 | `browser.search` / `browser.read` / `browser.open` | 搜索（DuckDuckGo，空结果回退 Bing）与正文读取有来源和截断标志；打开页面通过 LaunchServices，会切换前台 App |
| 天气 | `weather.current` / `weather.forecast` | 地点、单位、供应方（Open-Meteo）、时区与数据时间；超时或失败不猜天气 |

`verified` / `partial` / `unavailable` / `error` 的退出码分别为 0 / 2 / 3 / 4。`complete_for_scope` 只覆盖此次明确范围。计划操作返回不可用后，除非已有获授权且可验证的替代工具，不把临时拼接的终端命令当已完成适配。

设备写入沿用用户已授权的目标和动作；需要补齐的是缺失的关键参数，而非反复确认同一授权。新增私有接口先确认当前系统真实签名和返回值，再用专用测试对象验证；不为演示修改无关设置或个人数据。
