# 私有 API 接口与固定适配器

本文件记录 Control API 已实现、已在 iPhone SE 2 / iOS 16.1.1 / 20B101 验证的私有 API 接口。目标不是让 AI 直接调用任意私有 selector，而是使用固定适配器和 `iosctl` 操作；任何扩展都必须重新验证、固定参数、写后读回。

## 1. 总入口

```sh
python3 /var/jb/var/root/ios-control-bridge/bin/iosctl capabilities
python3 /var/jb/var/root/ios-control-bridge/bin/iosctl call OPERATION --params '<JSON>'
```

先看 `capabilities` 的 `implemented`、`validation` 和 `runtime.ready_to_query`。`unavailable` / `not_implemented` 不能报告为成功。所有写操作完成后用对应 `get/list` 读回。

App 管理新增于 0.13.0，helper 为 `build/native/icb-apps`，路由为
LaunchServices（清单、状态、系统 IPA 安装与删除）和 StoreServices
（Apple 免费报价与下载请求）。每个 selector 先核对运行时签名，写后用新进程
读回；可显式使用手机已有 TrollStore。参数和认证等待行为见 [apps.md](apps.md)。

## 2. 系统闹钟：私有 MobileTimer

- helper：`build/native/icb-alarms`
- 框架：`/System/Library/PrivateFrameworks/MobileTimer.framework`
- 类：`MTAlarmManager`、`MTAlarm`
- 签名 entitlement：
  - `com.apple.private.mobiletimerd`
  - `com.apple.private.ClockAngel.client`
  - mach lookup：`com.apple.MobileTimer.timerserver`、`com.apple.sessionservices`

调用的私有接口：

```text
MTAlarmManager -alarmsSync
MTAlarmManager -addAlarm:
MTAlarmManager -updateAlarm:
MTAlarmManager -removeAlarm:
MTAlarm -initWithHour:minute:
MTAlarm -setTitle: / -setEnabled: / -setRepeatSchedule: / -setAllowsSnooze:
MTAlarm -mutableCopy
```

注意：

- `addAlarm:` / `updateAlarm:` / `removeAlarm:` 返回的是 future（`NAFuture`），不是 `MTAlarm`；不要对返回值调用 `alarmID`。
- 用 `alarmsSync` 重新读取并匹配 alarm ID。
- id 是 `MTAlarm.alarmID` 的 UUID 字符串。
- 测试闹钟使用远离当前时间的时刻，完成后必须删除。

CLI：

```text
alarms.list
alarms.create          {"hour":0-23,"minute":0-59,"title":"..."}
alarms.update          {"alarm_id":"UUID","hour"?:0-23,"minute"?:0-59,"title"?:"..."}
alarms.set_enabled     {"alarm_id":"UUID","enabled":true|false}
alarms.delete          {"alarm_id":"UUID"}
```

## 3. 日历与事件：EventKit + 私有 TCC entitlement

- helper：`build/native/icb-calendar`
- **必须安装到：`/var/jb/usr/local/bin/icb-calendar`**；从 `/var/jb/var/root/...` 运行会被 TCC/EventKit 拒绝（`calendar_access_denied`）。
- 框架：`EventKit.framework`
- 使用的 entitlement：
  - `com.apple.private.tcc.allow`：`kTCCServiceCalendar`、`kTCCServiceReminders`、`kTCCServiceAddressBook`
  - `com.apple.private.tcc.allow.overridable`：同上
  - `com.apple.private.calendar.calaccessd`
  - `com.apple.private.calendar.syncclient`
  - mach lookup：`com.apple.calaccessd`、`com.apple.chronoservices`

使用的接口：

```text
+[EKEventStore authorizationStatusForEntityType:]
-[EKEventStore calendarsForEntityType:]
-[EKEventStore saveCalendar:commit:error:]
-[EKEventStore removeCalendar:commit:error:]
-[EKEventStore calendarWithIdentifier:]
-[EKEventStore predicateForEventsWithStartDate:endDate:calendars:]
-[EKEventStore eventsMatchingPredicate:]
+[EKCalendar calendarForEntityType:eventStore:]
+[EKEvent eventWithEventStore:]
-[EKEventStore saveEvent:span:commit:error:]
-[EKEventStore removeEvent:span:commit:error:]
-[EKEventStore eventWithIdentifier:]
```

CLI：

```text
calendar.list
calendar.create        {"title":"...","source_id"?:"..."}
calendar.delete        {"calendar_id":"UUID"}
calendar.events        {"calendar_id":"UUID","start":"ISO8601","end":"ISO8601"}
calendar.event_create  {"calendar_id":"UUID","title":"...","start":"ISO8601","end":"ISO8601","notes"?:"..."}
calendar.event_delete  {"event_id":"EventKit identifier"}
```

事件 ID 是 EventKit 的 event identifier，不一定是 UUID；按返回字符串精确传递。时间必须是带时区的 ISO-8601，helper 统一转 UTC。测试日历/事件必须清理。

## 4. 提醒事项：私有 ReminderKit

- helper：`build/native/icb-reminders`
- **必须安装到：`/var/jb/usr/local/bin/icb-reminders`**
- 框架：`/System/Library/PrivateFrameworks/ReminderKit.framework`
- 签名 entitlement：
  - `com.apple.private.tcc.allow`：`kTCCServiceReminders`、`kTCCServiceCalendar`
  - `com.apple.private.remindd`
  - `com.apple.private.calendar.syncclient`
  - mach lookup：`com.apple.remindd`

使用的私有接口：

```text
! 若 EventKit 返回 0 个提醒清单，不要继续只调 EventKit；该设备已验证改用 ReminderKit。
-[REMStore fetchListsForEventKitBridgingWithError:]
-[REMList fetchRemindersWithError:]
-[REMSaveRequest initWithStore:]
-[REMSaveRequest updateList:]
-[REMSaveRequest addReminderWithTitle:toListChangeItem:]
-[REMSaveRequest updateReminder:]
-[REMReminderChangeItem setTitleAsString:]
-[REMReminderChangeItem setCompleted:]
-[REMReminderChangeItem removeFromList]
-[REMSaveRequest saveSynchronouslyWithError:]
```

注意：

- 列表/提醒 ID 通过真实 `objectID.uuid` 的 NSUUID 获取；change item 的 objectID 会转发到 storage，先核对 forwardingTarget/objectID/uuid 的真实方法签名。不能解析 description 或按标题猜 ID。
- 创建必须按新 change item 的稳定 ID 读回，核对 `created_id`、返回 ID 和 list/source；不能用同名旧条目确认成功。
- 删除只有在完整查询成功且目标缺失时才能 verified；读取失败返回 partial/unavailable，不能把 nil 当成已删除。
- 创建/更新/完成/删除必须用 `REMSaveRequest` 并 `saveSynchronouslyWithError:` 落盘，然后重新 `fetchRemindersWithError:` 验证。
- 用户自己的提醒只读；测试提醒创建后必须删除并恢复原数量。
- 如果设备没有提醒账户/清单，不能伪造成功；先确认 EventKit 与 ReminderKit 的实际清单状态。

CLI：

```text
reminders.lists
reminders.list       {"list_id":"UUID"}
reminders.create     {"list_id":"UUID","title":"..."}
reminders.update     {"reminder_id":"UUID","title":"..."}
reminders.complete   {"reminder_id":"UUID"}
reminders.delete     {"reminder_id":"UUID"}
```

## 5. 设置与控制中心

### 音量 / 亮度（helper `icb-settings`）

```text
AVSystemController -sharedAVSystemController
-[AVSystemController getVolume:forCategory:]       category: "Audio/Video"
-[AVSystemController setVolumeTo:forCategory:]
BrightnessSystemClient -copyPropertyForKey:@"DisplayBrightness"
BrightnessSystemClient -setProperty:forKey:@"DisplayBrightness"
```

CLI：`settings.get/set {"setting":"volume"|"brightness","value":0.0-1.0}`。

### ElleKit SpringBoard bridge

- dylib：`/var/jb/usr/lib/TweakInject/icbridge.dylib`
- filter：`com.apple.springboard`
- IPC：`/var/jb/var/run/ios-control-bridge/spring.sock`，目录 mobile 所有且 0700，socket 0600；新协议不读取旧文件 mailbox。
- 固定动作：
  - `get_low_power` / `set_low_power`
  - `get_orientation_lock` / `set_orientation_lock`
  - `get_wifi` / `get_airplane` / `get_bluetooth`（只读）
- 私有类/方法：
  - `_PMLowPowerMode`：`+sharedInstance`、`getPowerMode`、`setPowerMode:fromSource:`
  - `SBOrientationLockManager`：`+sharedInstance`、`isUserLocked`、`lock`、`unlock`
  - `HSWiFiManager`：`+sharedWiFiManager`、`isWiFiEnabled`、`isWiFiAssociated`
  - `RadiosPreferences`：`alloc/init`、`airplaneMode`
  - `BluetoothManager`：`alloc/init`、`enabled`；`setEnabled:` 在该设备未生效
- CLI：
  - `settings.get`：`low_power`、`orientation_lock`、`wifi`、`airplane`、`bluetooth`
  - `settings.set`：仅 `volume`、`brightness`、`low_power`、`orientation_lock`；网络/蓝牙为 `read_only_setting`
- 安全约束：
  - bridge constructor 只能使用 C/pthread；当前设备工具链的 arm64e 注入通道保持 C 字符串和 C 帧解析，避免 Foundation 常量字符串/字典路径。固定系统操作在主队列执行，不能 sleep 等待。
  - BluetoothManager / RadiosPreferences 只初始化一次并持有至进程退出；蓝牙存在异步回调，不能在一次 getter 后释放管理器。
  - 动作固定，内核校验连接者 UID；每连接独立应答，携带启动代次、request ID 与有效期，过期/断连检查后才执行。写入结果未知时先重新读取，不盲目重发。
  - Wi-Fi/飞行模式写入会断开 SSH/网络，未实现为可写；不要偷偷尝试。

## 6. 构建、部署与验证

```sh
cd /var/jb/var/root/ios-control-bridge
sudo python3 tools/build_native.py
sudo cp build/native/icb-calendar /var/jb/usr/local/bin/icb-calendar
sudo cp build/native/icb-reminders /var/jb/usr/local/bin/icb-reminders
sudo chown root:wheel /var/jb/usr/local/bin/icb-calendar /var/jb/usr/local/bin/icb-reminders
sudo chmod 755 /var/jb/usr/local/bin/icb-calendar /var/jb/usr/local/bin/icb-reminders
python3 -B -m unittest discover -s tests -v
```

验证顺序：

1. `iosctl capabilities`：确认操作 `implemented`、`runtime.ready_to_query`。
2. 读操作先跑通，再跑写操作。
3. 写操作使用明确对象和参数，读回一致后才算 verified。
4. 记录 helper SHA-256、iOS build、entitlement 和路径；不同 build 重新验证。
5. 测试结束后清理测试闹钟、日历、事件、提醒，恢复设置原值。

## 7. 给 AI 的调用规则

- 优先调用 `iosctl` 固定操作，不直接写 raw private framework 调用。
- 读能力清单；不把 `unavailable`、`partial` 或助手文本当成已执行。
- 使用准确 ID；不要按标题模糊删除用户数据。
- 用户明确要求个人数据写入时才执行，遵守“最小范围 + 读回 + 可清理”。
- 私有 API 与 entitlement 仅适用于已验证 build；不要声称跨 iOS 版本稳定。
- 输出中不出现完整 key、密码、个人提醒正文或无关日历内容。
