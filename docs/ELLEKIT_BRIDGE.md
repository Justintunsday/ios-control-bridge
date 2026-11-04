# ElleKit SpringBoard bridge（可选）

`low_power` 与 `orientation_lock` 需要 SpringBoard 进程内的私有类，CLI 进程无法直接调用。本目录的可选 tweak 通过 ElleKit 注入 `com.apple.springboard`，用固定的命令/结果文件协议提供四个设置动作和两个只读状态。

该 tweak **不属于 Debian 包**，需要手动安装；不安装时对应设置返回 `unavailable/ellekit_bridge_unavailable`，其余功能不受影响。

## 架构

- `native/ellekit/SpringBridge.m`：Objective-C 源码。constructor 只使用 C 与 Objective-C runtime C API 启动 pthread；线程等待 5 秒后轮询 `/var/jb/var/lib/icb/spring.cmd`。
- 命令被派发到 SpringBoard 主队列执行；结果写入 `/var/jb/var/lib/icb/spring.result`。
- 支持的动作固定为：
  - `get_low_power` / `set_low_power`
  - `get_orientation_lock` / `set_orientation_lock`
  - `get_wifi` / `get_airplane`（只读）
- Python 侧 `src/ios_control_bridge/ellekit_bridge.py` 负责写入带 request ID 的命令、等待匹配的结果并解析；CLI 的 `settings.get/set` 复用该客户端。
- CLI 只接受上面列出的固定动作；bridge 没有“执行任意 selector”的入口。

## 构建与安装

在设备上以 root 运行（需要已有 clang、ldid、iPhoneOS SDK）：

```sh
sudo python3 tools/build_ellekit_bridge.py --sdk /var/jb/opt/sdks/iPhoneOS16.5.sdk
```

脚本会：

1. 以 `arm64e-apple-ios16.1` 构建 `icbridge.dylib` 并用 `ldid -S` 签名；
2. 安装到 `/var/jb/usr/lib/TweakInject/icbridge.dylib`；
3. 安装二进制 plist `/var/jb/usr/lib/TweakInject/icbridge.plist`（filter：`com.apple.springboard`）；
4. 创建 `/var/jb/var/lib/icb`（0777）作为命令/结果目录。

安装后需要让 SpringBoard 重新加载 tweak：

```sh
killall -9 SpringBoard
# 或等价的 respring
```

脚本加 `--respring` 会自动执行最后一步。

> 重要：直接向正在运行的 SpringBoard 注入新 dylib 时，constructor 中调用 Foundation 可能崩溃 SpringBoard 并进入 ElleKit safe mode。本 bridge 的 constructor 只用 C/pthread，Objective-C 调用延后到主队列，已在目标设备验证。修改 constructor 时必须保持这个约束。

## 设备验证

在 iPhone SE 2 / iOS 16.1.1 / 20B101 上验证：

| 动作 | 结果 |
| --- | --- |
| `low_power` get | verified，`false` / `power_mode=0` |
| `low_power` set `true` | verified，before false，readback true |
| 再次 get | verified，`true` |
| `low_power` set `false` | verified，readback false，最终 get 为 false |
| `orientation_lock` get | verified，`false` / `isUserLocked=0` |
| `orientation_lock` set `true` | verified，readback true |
| 再次 get | verified，`true` |
| `orientation_lock` set `false` | verified，readback false，最终 get 为 false |
| `get_wifi` | ok，`enabled=1 associated=1` |
| `get_airplane` | ok，`airplaneMode=0` |

CLI 侧对应结果见 `evidence/ellekit-bridge.json`。测试只改变低电量模式与方向锁定并在同一轮恢复；没有写 Wi-Fi、飞行模式、闹钟或提醒事项。

## 安全边界

- tweak 运行在 SpringBoard 进程（mobile 用户），不获得 root；
- 命令文件目录 `/var/jb/var/lib/icb` 为 0777：**任何能访问 `/var/jb` 的本地进程都可以发送同样的固定动作**。这是本机越狱环境下的本地控制面，不是网络暴露面；
- bridge 只改变系统 UI 设置（低电量/方向锁定）或读取网络状态，不执行任意代码、不访问个人数据；
- 不安装 bridge 时 CLI 明确返回 `ellekit_bridge_unavailable`；
- Wi-Fi 与飞行模式只读：没有提供会断开 SSH/网络的写操作。

## 限制

- 需要 respring 后才加载；安装/升级 tweak 后必须重启 SpringBoard。
- 只覆盖上述固定动作；系统闹钟与提醒事项仍需要各自的目标进程/授权路径，当前未实现。
- ElleKit 版本、SpringBoard 版本或私有类变化可能导致动作返回 `class_unavailable`；不会伪造成功。
- 不是官方插件，不保证在其它 iOS 版本可用。
