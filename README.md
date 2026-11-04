# iOS Control Bridge

让 AI 或其他客户端通过独立、可验证的接口，读取并调整 iPhone 的常用系统服务。

项目提供本机 `iosctl` JSON 命令和原生服务适配器，可在已有 SSH / 终端通道中运行。运行与构建不依赖编码代理服务器、AI SDK 或特定模型。当前设备适配以已越狱的 iOS 16.1.1 为起点，扩展到其他系统版本时逐项验证。

## 目标与当前状态

| 服务 | 目标 | 当前实现 |
| --- | --- | --- |
| 设备信息 | 系统版本、型号、UID、bootstrap 证据 | 已实现，迁移后真机验证见文档 |
| 实时活动 | 跨 App 正文、Attributes、状态和变化监测 | 按 ID 读取已实现；持续监测待开发 |
| 设置 / 控制中心 | Wi-Fi、蓝牙、蜂窝、飞行模式、亮度、音量、低电量、方向锁定、专注模式等的读取与调整 | 媒体音量读写已实现并真机验证；其他设置项逐项实现中 |
| 闹钟 | 系统闹钟列表、创建、改时、重复、启停和删除 | 待实现 |
| 提醒事项 | 清单、查询、新建、编辑、完成和删除 | 待实现 |
| 浏览器 / 网络查询 | 搜索结果、网页内容提取、打开指定页面 | 待实现 |
| 天气 | 指定位置的实况、预报、来源及数据时间 | 待实现 |
| 文件 | 明确目录内的列举、检索和有界读取 | 终端技能已有；统一接口待实现 |

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

默认 helper 路径为仓库内 `build/native/icb-activities` 和 `build/native/icb-settings`。需要显式指定已有 helper 时，使用 `ICB_ACTIVITIES_HELPER`、`ICB_SETTINGS_HELPER`；SDK 可通过 `ICB_SDK` 配置。仓库不保存设备地址、密码或 SSH 私钥。

## 结果和开发

所有 `call` 返回 `ios-control-bridge.result.v1` JSON，包含请求 ID、操作、观测时间、来源和范围完整性：`verified` / `partial` / `unavailable` / `error`，退出码分别为 `0 / 2 / 3 / 4`。完整查询没有目标，与查询失败分别表示。

`settings.get` / `settings.set` 已对媒体音量实现并完成真机读写回环，包含明确值校验和读回确认；其他设置项、闹钟和提醒事项仍返回 `unavailable/not_implemented`。写操作以用户明确指定的目标和值执行，修改后读回系统状态，不把发送成功等同于效果已验证。

- [服务范围与验收](docs/services.md)
- [架构与接口契约](docs/architecture.md)
- [开发路线](docs/roadmap.md)
- [实时活动与迁移验证](docs/live-activities.md)
- [设备验证记录](docs/verification.md)
- [接手开发说明与语言建议](HANDOFF.md)

本机测试：`python3 -m unittest discover -s tests -v`。真机结果只证明记录中的设备、系统 build 和操作；不将未来服务或其他 iOS 版本列为已验证。
