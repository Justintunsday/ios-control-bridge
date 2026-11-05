# 架构与接口

运行路径：客户端 → 本机 `iosctl` → 操作注册表 → 服务适配器 → iOS 系统能力 / 网络数据源。客户端可以是终端、AI 工具调用器或未来的语音入口；设备能力与模型、对话服务、SSH 账号分离。

`src/ios_control_bridge` 是 Python 3.9+ 核心。`native/<service>` 放置需要 Apple runtime 的原生适配器。`tools/build_native.py` 只调用已存在的编译器和 SDK，在本仓库 `build/native` 内生成 helper。`skills/ios-control-bridge` 提供可单独安装的指令入口。

## 请求

```json
{
  "operation": "activities.get",
  "request_id": "debd4d72-1860-4d98-a3d0-c026ddbd1744",
  "params": {"activity_id": "1DF0A9B7-6211-4FD8-A80A-03BEF357532A", "timeout_ms": 5000}
}
```

对应 CLI：`iosctl call OPERATION --params JSON --request-id UUID`。CLI 不提供任意命令执行接口。请求 schema 在 `schemas/request.schema.json`；该文件定义客户端契约，当前交付的执行入口是本机 CLI，尚未启动 HTTP 或 MCP 服务。

## 返回与实际来源

返回 schema 在 `schemas/result.schema.json`。`observed_at` 是此次适配器处理结果的时间，系统自己的数据时间保留在 `data` 中；两者不互相替代。`complete_for_scope` 只覆盖明确的操作和选择范围。`capabilities` 的来源为能力声明加执行环境探测，不代表已查询所有系统服务。

退出码 0 = verified、2 = partial、3 = unavailable、4 = error。对实时活动，完整响应中 `target_found:false`、`activity:null` 是目标在当前可读范围内不存在；超时没有正文，不能当成活动结束。

读取器的原生结果保存在 `data`，保留活动 ID、原始状态、正文编码、系统服务和采样时间。Python 边界校验 JSON schema 标识、来源、目标 ID、退出码与状态的一致性，不从历史文件补正文。

## 网络与本地数据适配器

`browser.*` 由 Python HTTP 客户端和 HTML 解析器实现；搜索 provider 为 DuckDuckGo HTML，空结果时回退 Bing HTML；`browser.open` 通过固定原生 helper `icb-open-url` 调用 `LSApplicationWorkspace`。`weather.*` 使用 Open-Meteo HTTP API，保留 provider、时区、单位与 attribution。`files.*` 是纯 Python 有界文件系统接口，只处理显式绝对路径。所有 adapters 都返回统一 result JSON 和退出码。

## 私有 MobileTimer 闹钟 helper

`alarms.*` 使用独立 helper `native/alarms/AlarmsBridge.m`，通过 dlopen 加载私有 `MobileTimer.framework` 的 `MTAlarmManager`，并以 `com.apple.private.mobiletimerd` entitlement 签名。helper 只接受固定命令（list/create/update/set_enabled/delete），返回真实闹钟 ID、时间、标签和启停状态，并在写后读回。

## EventKit 日历 helper

`calendar.*` 使用独立 helper `native/calendar/CalendarBridge.m`，以 EventKit + `com.apple.private.tcc.allow`（Calendar/Reminders/AddressBook）和 `com.apple.private.calendar.calaccessd` entitlement 签名。该 helper 必须在 `/var/jb/usr/local/bin` 路径运行；同一二进制放在 `/var/jb/var/root/...` 会被 TCC/EventKit 拒绝。支持日历列举、在显式来源创建日历、按 ID 删除、日期范围内事件查询、创建事件和按事件 ID 删除，并在写后读回。

## ReminderKit 提醒 helper

`reminders.*` 使用独立 helper `native/reminders/RemindersBridge.m`，通过 dlopen 加载私有 `ReminderKit.framework` 的 `REMStore`，并使用 `REMSaveRequest` 创建、更新、完成和删除提醒。该设备上 EventKit 即使授权为 authorized 也返回 0 个提醒清单，而 `REMStore` 能正确列出账户和用户的 `Reminders` 清单，因此提醒事项走 ReminderKit 而不是 EventKit。helper 同样需要安装到 `/var/jb/usr/local/bin`。

## 可选 ElleKit SpringBoard bridge

`low_power` 与 `orientation_lock` 依赖 SpringBoard 进程内的私有类。可选 tweak 通过受限本地 Unix socket 接受固定动作，并在主队列串行执行；内核 peer UID、启动代次、请求 ID 与有效期约束请求。通道保持 C 实现，蓝牙与 Radio 管理器在进程期持有。网络/蓝牙原生 setter 不存在；CLI 也拒绝对应写入。详见 [ELLEKIT_BRIDGE.md](ELLEKIT_BRIDGE.md)。

## 写操作的实现约束

设置写入使用固定参数、值范围和修改后的读取验证。日历与提醒创建按新 ID 确认，事件同时核对时间和备注；删除确认必须区分查询失败与完整查询后的缺失。事件分页、文件搜索失败与截断保持不完整状态。写入断连时保留结果未知，先读取状态再决定下一步。沿用用户已有授权，不要求重复确认已经明确交代的操作。

单次 CLI 查询不等于常驻监测。持续任务需要后续独立运行器管理生命周期、连接中断、停止条件和通知；目前没有部署常驻服务。
