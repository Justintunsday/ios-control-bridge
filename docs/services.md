# 系统服务范围

目标是覆盖日常最常用的系统读取与控制操作。下表定义开发范围和完成条件；实际可调用状态以 `iosctl capabilities` 为准。

| 服务 | 操作 | 完成条件 |
| --- | --- | --- |
| device | `info` | 当前 OS / build、型号、UID 与 bootstrap 证据来自设备 |
| settings | `get`, `set` | 每个设置项分别声明支持版本、值类型和权限；修改后读回；不支持的项目明确报告 |
| alarms | `list`, `create`, `update`, `set_enabled`, `delete` | 返回系统时钟真实闹钟的稳定 ID；时间、时区、重复和启停可读回；测试样本可清理 |
| reminders | `lists`, `list`, `create`, `update`, `complete`, `delete` | 基于明确清单和条目 ID 读取、写入并读回，保留授权状态和分页 / 范围限制 |
| browser | `search`, `read`, `open` | 搜索有真实结果及 URL；读取有最终 URL、提取时间和截断标志；打开页面报告实际执行层级 |
| weather | `current`, `forecast` | 输入明确位置与单位；输出供应方、观测 / 预报时间与时区；网络失败不回填旧数据冒充当前 |
| activities | `get`, `watch` | 正文读取来源可核实；监测另有运行器、停止条件、断连状态和通知策略 |
| files | `list`, `search`, `read` | 目录明确、结果有界，权限失败与完整空结果区分；正文只读取指定文件 |

## 设置和功能按钮

首批候选为亮度、音量、低电量模式、Wi-Fi、蓝牙、蜂窝网络、飞行模式、屏幕方向锁定与专注模式。候选不是已支持列表。按设置逐项完成 getter、值校验、setter、读回和兼容性验证；不使用一条通用任意 shell 命令替代服务接口。

## 时间与个人事项

闹钟的目标是系统时钟中的真实闹钟。当前 iOS 16 基线需要核对系统闹钟服务的实际运行时接口；Apple 的 [AlarmKit](https://developer.apple.com/videos/play/wwdc2025/230/) 面向 iOS / iPadOS 26，不能直接用作当前设备适配。

提醒事项优先使用已有系统公开能力。[EventKit](https://developer.apple.com/documentation/eventkit/accessing-the-event-store) 的授权和用途说明随系统版本变化；iOS 16 与 iOS 17+ 分别处理。若终端进程不具备需要的授权或 App 上下文，再实现明确的原生 helper 入口。当前仓库不自动修改个人事项或授权数据库。

“明早七点”等表达须转换成设备时区内的明确时间；重复规则、清单、目标条目有歧义时只补齐关键参数。相同请求重试的去重和写入后读回属于写服务适配器的验收范围。

## 网络和天气

浏览器搜索、网页正文和页面打开是三个操作，分别报告来源与结果。网页内容作为数据交给上层客户端，不作为设备控制指令。

天气以可替换的数据源适配器实现。若选 [WeatherKit REST API](https://developer.apple.com/documentation/weatherkitrestapi/request-authentication-for-weatherkit-rest-api)，需要相应开发者身份和签名令牌；没有配置时返回明确的缺口。其他供应方同样须保留来源、时间、单位与要求的署名。当前尚未选定或接入天气供应方。
