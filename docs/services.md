# 系统服务范围

目标是覆盖日常最常用的系统读取与控制操作。下表定义开发范围和完成条件；实际可调用状态以 `iosctl capabilities` 为准。

| 服务 | 操作 | 完成条件 |
| --- | --- | --- |
| device | `info` | 当前 OS / build、型号、UID 与 bootstrap 证据来自设备 |
| settings | `get`, `set` | 每个设置项分别声明支持版本、值类型和权限；修改后读回；不支持的项目明确报告。媒体音量（`volume`）、屏幕亮度（`brightness`）、低电量模式（`low_power`，布尔）与方向锁定（`orientation_lock`，布尔）已实现并真机验证；Wi-Fi/飞行模式/蓝牙（`wifi`/`airplane`/`bluetooth`）为只读；后五项通过可选 ElleKit SpringBoard bridge |
| alarms | `list`, `create`, `update`, `set_enabled`, `delete` | 返回系统时钟真实闹钟的稳定 ID；时间、标签、启停可读回；测试样本已清理。已实现并真机验证，使用私有 `MobileTimer.framework` 与 `com.apple.private.mobiletimerd` entitlement |
| reminders | `lists`, `list`, `create`, `update`, `complete`, `delete` | 基于明确清单和条目 ID 读取、写入并读回，保留授权状态和分页 / 范围限制。当前未实现：EventKit 授权可用，但设备无提醒账户/默认清单，创建不持久 |
| calendar | `list`, `create`, `delete` | 列出日历及来源；在显式来源创建日历并读回；按准确 ID 删除。已实现并真机验证 |
| browser | `search`, `read`, `open` | 搜索有真实结果及 URL（DuckDuckGo HTML，空结果时回退 Bing HTML）；读取有最终 URL、提取时间和截断标志；打开页面通过 LaunchServices 执行并报告实际层级 |
| weather | `current`, `forecast` | 输入明确位置与单位；输出供应方（当前为 Open-Meteo）、观测 / 预报时间与时区；网络失败不回填旧数据冒充当前 |
| activities | `get`, `watch` | 正文读取来源可核实；`watch` 当前为有界前台轮询（显式时长、间隔、超时与可选提前停止），常驻运行器和通知仍待开发 |
| files | `list`, `search`, `read` | 目录明确、结果有界，权限失败与完整空结果区分；正文只读取指定文件。已实现并真机验证 |

## 设置和功能按钮

媒体音量、屏幕亮度、低电量模式与方向锁定已实现并完成 getter、值校验、setter、读回和恢复验证。Wi-Fi、飞行模式与蓝牙提供只读状态；写入会被拒绝为 `unavailable/read_only_setting`，因为当前未找到可靠的免断网/免额外授权写入路径。蜂窝网络与专注模式仍未接入。日历列表/新建/删除已通过 EventKit 实现；提醒事项因设备没有提醒账户/默认清单而未实现。按设置逐项完成同样的读写回环和兼容性验证；不使用一条通用任意 shell 命令替代服务接口。

## 时间与个人事项

闹钟的目标是系统时钟中的真实闹钟。当前通过私有 `MobileTimer.framework` 的 `MTAlarmManager` 访问系统 Clock 服务，helper 使用 `com.apple.private.mobiletimerd` entitlement；已支持列表、创建、改时/标签、启停和删除。重复规则目前只保留原始 repeatSchedule 字段，未提供按星期几的语义化参数；时区沿用设备当前时区。Apple 的 [AlarmKit](https://developer.apple.com/videos/play/wwdc2025/230/) 面向 iOS / iPadOS 26，不能直接用于当前设备。

提醒事项优先使用已有系统公开能力。[EventKit](https://developer.apple.com/documentation/eventkit/accessing-the-event-store) 的授权和用途说明随系统版本变化；iOS 16 与 iOS 17+ 分别处理。若终端进程不具备需要的授权或 App 上下文，再实现明确的原生 helper 入口。当前仓库不自动修改个人事项或授权数据库。

“明早七点”等表达须转换成设备时区内的明确时间；重复规则、清单、目标条目有歧义时只补齐关键参数。相同请求重试的去重和写入后读回属于写服务适配器的验收范围。

## 网络和天气

浏览器搜索、网页正文和页面打开是三个操作，分别报告来源与结果。搜索先使用 DuckDuckGo HTML，空结果时回退 Bing HTML；页面打开通过 `LSApplicationWorkspace` 执行，属于真实前台 UI 操作。网页内容作为数据交给上层客户端，不作为设备控制指令。

天气以可替换的数据源适配器实现。当前接入 Open-Meteo HTTP API（无 key），输出供应方、时区、单位与 attribution；网络失败返回明确错误，不回填旧数据。未来可替换为含签名令牌的 WeatherKit 等其他供应方。

文件接口只处理显式绝对路径，所有结果有界；不提供通配符递归或任意目录遍历。
