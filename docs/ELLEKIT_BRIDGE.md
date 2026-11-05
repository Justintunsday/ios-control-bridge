# ElleKit SpringBoard bridge（0.12.0，可选）

该 shim 提供低电量模式与方向锁定读写，以及 Wi-Fi、飞行模式和蓝牙只读状态。目标为已验证的 iOS 16.1.1 / 20B101，不是通用 selector 执行器。CLI、原生 helper 与 shim 需成对升级。

## 本地通道

- 路径：`/var/jb/var/run/ios-control-bridge/spring.sock`。
- 目录由安装器设为 mobile 所有、0700，socket 为 0600。
- 双方用内核 `getpeereid` 校验身份：服务端仅允许 root 或自己的 UID，客户端要求服务端 UID 为 mobile。root 和可访问此目录的 mobile 同属受信本地用户范围，不能据此声称隔离同 UID 恶意进程。[Apple getpeereid 文档](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man3/getpeereid.3.html)。
- 每连接一个请求及独立应答，服务端串行派发到主队列，不存在共享临时文件或公共结果文件。
- 旧目录 `/var/jb/var/lib/icb` 被收紧为 root 0700；新通道不读取其中任何命令。

## 协议与请求生命周期

协议标识为 `ios-control-bridge.spring.v2`，使用有界 ASCII 行。Python 对外仍返回结构化结果。

```text
hello:    protocol generation
request:  generation request_id deadline_unix_ms action value
response: generation request_id status value outcome_unknown detail_hex
```

`generation` 与 request ID 为 32 个十六进制字符；每次服务器启动生成新的随机代次。动作固定，value 只能为 0/1。detail 使用 UTF-8 字节的十六进制表示，空 detail 为 `-`。输入上限 1024 字节，客户端应答上限 4096 字节，服务端生成的应答更小。

服务端拒绝过期、过远的 deadline、有效期内重复 ID、旧代次与非允许动作；在主队列执行前、设置副作用前重新检查 deadline 和连接。内存记录有界，磁盘没有待执行队列，因此重载不会执行遗留文件。断连时已开始的写入可能结果未知，客户端保留 `outcome_unknown`，不自动重发。

串行化覆盖单个请求。一个 CLI 的 get/set/get 事务仍可能与另一个客户端交错；读回不一致应如实返回 partial。未来 UI 自动化还需要独占操作租约。

## 注入进程约束

constructor 仅使用 C/pthread；启动线程等待后建立 C socket 通道。当前设备工具链的 arm64e 插件在 Foundation 常量字符串/字典路径出现过 runtime trap，因此通道不用 Foundation 字面量、JSON 字典或集合。固定系统调用沿用已验证的 Objective-C runtime C 调用，并核对真实 ABI。

BluetoothManager 与 RadiosPreferences 初始化一次后持有至进程退出。蓝牙连接事件存在异步回调，一次 getter 结束后释放管理器曾导致延迟崩溃。主队列不通过 sleep 等待读回，Python 使用有界的读取重试。

## 构建和安装

```sh
sudo python3 tools/build_ellekit_bridge.py --build-only
sudo python3 tools/build_ellekit_bridge.py --respring
```

需要现有 clang、ldid、SDK。默认只安装，显式 `--respring` 才重载桌面；`--build-only` 不安装。编译与签名完成后才替换 dylib/plist，旧文件备份在仓库的忽略目录 `local/ellekit-backup-*`。没有新 socket 时相关 CLI 操作返回 unavailable。

组件为 `native/ellekit/SpringBridge.m`、`SocketServer.h`、`native/common/RuntimeABI.h` 与 Python `ellekit_bridge.py`。框架内部 getter/setter 在主队列执行；蓝牙、Wi-Fi 与飞行模式没有原生写动作。

## 验证

先运行 Python 测试，再在目标设备运行 `python3 tools/test_native.py`。原生 fixture 在独立进程验证协议与错误路径，不代替实际 shim 加载。安装观察须涵盖全部 getter 和异步回调；失败时恢复备份，不能只检查首次连接。

0.12.0 已通过 125 项 Python 测试、19 项原生隔离检查和 14 项真机检查，测试条目清理且设置恢复。两次安装失败与最终稳定性观察如实记录于 [修复报告](review-fixes-0.12.0.md)；证据包含最终 dylib 哈希，不把有界观察等同于长期稳定性证明。
