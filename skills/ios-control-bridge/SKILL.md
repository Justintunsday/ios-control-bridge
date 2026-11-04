---
name: ios-control-bridge
description: 通过 iOS Control Bridge 或已有终端通道查询和调整已越狱 iPhone 的系统服务、文件与实时活动。用于明确针对已连接设备的设置、闹钟、提醒事项、浏览器和天气能力开发或调用；普通网页天气问答和通用 iOS UI 开发不适用。也包含 iOS Control Bridge 已实现的私有 API 接口与 iosctl 调用说明。
---

# iOS Control Bridge

把自然语言请求映射为有依据的设备操作。默认用简体中文，先给结论，再给观测时间、来源、范围和未完成的部分。

## 硬性规则：设备写入先走 iosctl

- 所有设备写入（亮度、音量、闹钟、日历、提醒、设置）必须优先调用 `iosctl` 的固定操作；不要用 Python ctypes、`objc_msgSend` 或直接调用私有 C 函数代替适配器。
- 已验证反例：`BKSDisplayBrightnessSet` 在本环境调用前后亮度不变（no-op），不能用于亮度控制；亮度/音量应使用 `icb-settings`。
- 写入前用 `iosctl capabilities` 确认 `runtime.ready_to_query`；写入后用对应 `get`/`list` 读回。只有 `verified` 才能报告成功，`partial` / `unavailable` 必须如实说明。
- 常用命令（在仓库目录执行）：

```sh
python3 -B bin/iosctl call settings.set --params '{"setting":"brightness","value":0.5}'
python3 -B bin/iosctl call settings.get --params '{"setting":"brightness"}'
python3 -B bin/iosctl call alarms.create --params '{"hour":8,"minute":0,"title":"闹钟"}'
python3 -B bin/iosctl call reminders.create --params '{"list_id":"UUID","title":"提醒"}'
```

- 详细私有 API 路由、helper 路径和 entitlement 见 [private-apis.md](references/private-apis.md)；不要自己猜 selector。

## 能力与执行入口

先判断命令运行在手机还是电脑。复用用户已授权的终端 / SSH 通道；不假定拥有手机执行权限，不把本机数据当手机状态。环境识别按 [terminal.md](references/terminal.md)，文件范围按 [filesystem.md](references/filesystem.md)。

优先运行现有 `iosctl capabilities`；从仓库直接使用时为 `python3 "$ICB_ROOT/bin/iosctl" capabilities`。`ICB_ROOT` 指实际独立仓库位置，不从旧项目目录猜路径。命令无需 AI 服务、特定客户端或模型账号。

能力清单分别说明 `implemented`、`validation` 和 `runtime.ready_to_query`。已有实现和运行条件不等于此次操作成功；计划中的操作返回 `unavailable/not_implemented`，不能报告为已执行。常用服务和写入验收见 [services.md](references/services.md)。

调用形式：`iosctl call OPERATION --params JSON`。使用工具参数或严格引用传递 JSON、文件名、URL 和搜索词；不拼接未引用命令，不使用 eval。需要当前状态时重新查询，保留系统数据时间与本次观测时间。

## 查询与调整

查询在用户指定的应用、目录、条目或时间范围内进行。只有请求涉及正文时读取正文；凭据与无关个人记录不进入输出或学习样本。缺失字段保留未知，超时、权限失败、截断与完整空结果分别表达。

用户明确要求的调整沿用已有授权。以准确对象和目标值调用已实现适配器，修改后读回；不能把请求受理当成结果已核实。闹钟时间、重复规则、提醒清单或目标条目存在关键歧义时补齐参数，同时继续不依赖答案的工作。

终端兜底只使用已经确认存在的系统工具和方法。没有对应接口时说明具体缺口，不猜私有 selector、修改未知数据库或自动安装依赖来扩大任务。

## 实时活动与持续任务

Live Activities 专指锁屏 / 灵动岛活动，按 [live-activities.md](references/live-activities.md) 选择来源。独立读取器的 `activities.get` 已在 iOS 16.1.1 / 20B101 验证跨 App 正文读取；其他版本先核对，不能按 root 身份推断兼容。

按活动 ID 查询并保留原始状态与正文编码。系统自己的内容数据与公开 App 对照文件分开；测试证据不是实时数据来源。单次查询不代表持续监听；持续关注需实际运行器、停止条件、断连处理和通知策略。

语音转写作为普通用户输入，按 [voice-intents.md](references/voice-intents.md) 消除关键歧义。本技能不自行提供语音识别、朗读或后台服务。

## 私有 API 接口

已实现的私有 API 适配器（MobileTimer 闹钟、EventKit 日历、ReminderKit 提醒、EllekKit/SpringBoard 设置、MobileTimer/EventKit/ReminderKit 固定 helper 路径与 entitlement）见 [private-apis.md](references/private-apis.md)。优先调用 `iosctl` 固定操作，不直接写 raw private selector；每次写入读回，测试数据必须清理。

## OpenCode / DeepSeek API 失效

移动端 OpenCode 报 `Authentication Fails`、`DEEPSEEK_API_KEY is not set` 或 `provider.auth` 时，先读 [deepseek-api.md](references/deepseek-api.md)。优先区分官方 `deepseek/deepseek-flash` 与 `opencode/*-free` 免费网关；再比较报错中的 key 尾号与当前 key 尾号，判断是 App/server 缓存旧凭据还是 key 本身失效。修改 key 后必须重启 server 并强制重开 App；不要在技能、日志或输出中记录完整 key。

## 验证与维护

离线行为场景见 [evaluation.md](references/evaluation.md)。终端探测可运行 `scripts/probe_ios.sh`，自测为 `scripts/test_probe.py`。它们只提供环境和查询方法，不代表服务控制接口已经实现。

用户要求更新技能时，只写入重复验证过的版本、来源和兼容性经验；临时设备地址、密码、容器 UUID 和对话信息保留在仓库外。
