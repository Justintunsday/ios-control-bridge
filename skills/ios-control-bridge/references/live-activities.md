# Live Activities：锁屏与灵动岛

## 判断能查什么

Live Activities 由应用的 ActivityKit 数据和 WidgetKit 展示共同提供。ActivityKit 从 iOS 16.1 开始提供；展示位置取决于设备能力。iPhone SE 2 没有原生 Dynamic Island，仍可使用兼容系统及应用提供的锁屏活动；第三方模拟灵动岛扩展需单独核实。[Apple ActivityKit 发布说明](https://developer.apple.com/news/?id=ttuz9vwq)、[iPhone 型号说明](https://support.apple.com/en-ie/108044)

公开 `Activity<Attributes>.activities` 返回**本应用、对应 Attributes 类型**的当前活动数组，无法以此列出其他应用的活动。系统 root 权限本身不会把公开接口变成跨应用查询接口。[Apple activities 文档](https://developer.apple.com/documentation/activitykit/activity/activities)

| 来源 | 可以确认 | 必须保留的限制 |
| --- | --- | --- |
| 自有应用中的 ActivityKit 查询 | 对应类型活动的 ID、状态和应用提供的内容 | 只覆盖该应用和已枚举类型；活动存在不等于此刻正在屏幕显示。 |
| 已安装并验证的越狱 helper/MCP/插件 | 工具真实返回的活动与字段 | 明确系统版本、读取方式、范围与刷新机制；不默认拥有全局视野。 |
| 当前屏幕/无障碍观察 | 可见卡片的文字、图标和展示状态 | 不可见/隐藏活动、内部 ID 和未显示字段可能未知；屏幕捕获必须来自当前设备。 |
| 系统/应用日志 | 某个时间发生的生命周期或错误事件 | 日志有延迟、裁剪和隐私隐藏；无法据空日志推断没有活动。 |
| plist、磁盘缓存、进程 | 支持配置、历史痕迹或相关服务存在 | 不能单独证明当前内容、活动数或锁屏展示状态。 |

没有来源时说明：“当前还没有可读取该活动的设备接口，因此无法核实现在的内容。”随后给出适合该任务的接入选择。学习/编写技能时仅说明方案；用户请求实现集成后再开发或安装。

## 查询过程

1. 确定设备、系统版本、目标应用/订单/计时器，以及用户要“所有已知活动”还是“屏幕正在显示的活动”。
2. 检查已有工具的文档、`--help`、可用调用与实际权限。只调用已存在且已核实的接口；不编造 `activityctl` 等命令或私有 API 方法。
3. 优先用能回答问题的现有来源查询一次。保留读取时间、来源范围和原始状态；内容更新时间未知时留空。
4. 多个来源不一致时分别陈述。例如 API 有活动但屏幕无卡片，只能确认注册状态与当前可见状态不同。
5. 回答用户关心的字段，如外卖 ETA、计时器剩余时间。保留 stale、来源延迟和未覆盖应用等实质限制。

## 已验证的独立入口

Control API 提供 `iosctl call activities.get --params '{"activity_id":"实际 UUID"}'`。它在 iOS 16.1.1 / 20B101 使用 SessionKit 监听权限与真实 `BSServiceConnection`，从 `sessionkitd` 读取跨 App 原始正文。只在能力清单显示该适配器和当前设备条件满足时调用；缺少原生 helper、系统未验证和超时分别报告。

返回的原生 payload 在统一 JSON 的 `data` 中，包含 `target_found`、`activity`、`content` 与自己的数据时间。完整范围内没有目标时，`target_found:false`、`activity:null`；查询失败不会提供旧正文。实际卡片可见性仍需屏幕来源核实。不要读取测试 App 的公开审计文件来代替私有正文。

## 其他来源的适配示例

这是其他来源的**适配示例**；独立 CLI 使用其实际 JSON schema，不要求改写成此示例：

```json
{
  "observed_at": "2026-11-04T09:30:00+08:00",
  "source": "activitykit-own-app",
  "scope": {"bundle_id": "com.example.timer", "attributes_type": "TimerAttributes"},
  "status": "verified",
  "complete_for_scope": true,
  "activities": [{
    "id": "example-activity-id",
    "state": "active",
    "content": {"remaining_seconds": 90},
    "content_updated_at": null,
    "visible_on_screen": null
  }]
}
```

示例全部为虚构数据。缺失字段用 `null` 或保留工具原始语义；区分 `verified`、`partial`、`unavailable`、`error`。`activities: []` 只有在查询成功且范围覆盖明确时才表示该范围内没有活动。`observed_at` 不是内容最后更新时间。

保留当前系统返回的状态值及版本语义；不要把 `stale`、`ended`、`dismissed` 全部映射为 active。工具不能证明完整覆盖时将 `complete_for_scope` 设为 false。未知 ID 不根据卡片文字捏造。

## 自有应用的版本差异

仅在用户要求实现或审查自有应用代码时使用这些开发规则：

- 从应用实际定义的 `ActivityAttributes` 类型查询 `Activity<MyAttributes>.activities`；多个类型分别处理。
- iOS 16.1 与 16.2 之后的 content API 不同。`ActivityContent` 和 `activity.content` 从 iOS 16.2 提供；兼容 16.1 时用该 SDK 提供的旧 contentState API，并用 `#available` 分支。[Apple ActivityContent](https://developer.apple.com/documentation/activitykit/activitycontent)、[Apple content](https://developer.apple.com/documentation/activitykit/activity/content)
- `NSSupportsLiveActivities` 只说明应用的支持声明；`ActivityAuthorizationInfo` 反映相关授权能力，两者都不证明存在某个当前活动。
- 更新/启动/结束活动属于写操作，按明确请求执行。结束活动和清除屏幕展示是不同生命周期问题，按实际 API 与 dismissal policy 核实。
- APNs token、设备 token 和推送凭据不用于朗读或训练样本。

## 越狱环境下的线索

已有扩展可能通过私有 framework、守护进程或系统 UI 获取信息。这些实现依赖版本和 entitlement，先检查已安装工具和源码/文档；公共资料无法证明它在当前手机上可用。

可以在已确认的进程列表中查找 activity/chronod/SpringBoard 等相关名称，再用精确进程或 subsystem 的有限时窗日志排查。名称只是线索，服务实现因系统版本而异；不把某个进程设为所有版本必然存在的依据。

查询内容时无需注入 SpringBoard、修改私有数据库、关闭保护或重启守护进程。用户明确要求开发跨应用 helper 时，再把版本、读取机制、权限、接口和验证场景作为独立实现任务。

## 关注活动变化

“查现在”只读取一次。“活动结束告诉我”需要已有监测运行器，明确目标和停止条件后订阅实际更新或进行有限轮询。用户要求监测时沿用其通知偏好，只在内容有意义变化、结束、失败或需要用户处理时通知。记录断线与最后成功读取时间；断线不能解释为活动结束。

复核日期：2026-11-04。未来 SDK 和私有工具行为以当前版本资料及设备实测为准。
