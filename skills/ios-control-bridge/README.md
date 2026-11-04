# iOS Control Bridge Skill

这是 iOS Control Bridge 的 OpenCode skill/插件说明。

## 名称

- 插件/skill 名：`ios-control-bridge`
- 显示名：`iOS Control Bridge`
- 设备端安装目录：`/var/jb/var/root/.config/opencode/skills/ios-control-bridge`
- 仓库源目录：`skills/ios-control-bridge`

## 作用

让 OpenCode 通过固定的 `iosctl` JSON 操作查询和调整 iPhone 系统服务，不直接猜私有 selector：

- 设备信息、实时活动
- 音量、亮度、低电量模式、方向锁定
- Wi-Fi、飞行模式、蓝牙只读状态
- 系统闹钟
- 日历与日历事件
- 提醒事项
- 文件、浏览器、天气

私有 API 的具体路由、helper、entitlement 和验证方式见：

- [private-apis.md](references/private-apis.md)
- [services.md](references/services.md)
- [DeepSeek API 失效处理](references/deepseek-api.md)

## 入口

```sh
cd /var/jb/var/root/ios-control-bridge
python3 -B bin/iosctl capabilities
python3 -B bin/iosctl call settings.get --params '{"setting":"brightness"}'
python3 -B bin/iosctl call settings.set --params '{"setting":"brightness","value":0.5}'
python3 -B bin/iosctl call alarms.list
python3 -B bin/iosctl call reminders.lists
```

设备写入必须走 `iosctl` 固定操作；不要用 ctypes/`objc_msgSend` 直接调用私有框架。写入后读回，只有 `verified` 才能报告成功。

## 仓库

- GitHub：<https://github.com/Justintunsday/ios-control-bridge>
- 分支：`main`
- 根 README：https://github.com/Justintunsday/ios-control-bridge/blob/main/README.md
- 维护：iOS Control Bridge contributors；本机验证设备：iPhone12,8 / iOS 16.1.1 / 20B101 / Dopamine rootless

## 版本与兼容性

- 项目版本：0.11.0
- 已验证系统：iOS 16.1.1（20B101）
- 私有 API、TCC entitlement 和 helper 路径只对已验证 build 负责；其他系统版本必须重新验证。
