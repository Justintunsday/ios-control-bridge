# BridgeChat

与手机上的 OpenCode 交流的原生 SwiftUI iPhone 客户端。采用现有 `figma-swiftui` skill 的原生组件和语义样式规则，使用系统导航、List、Form、sheet、键盘、Dynamic Type 和系统浅色 / 深色外观。

支持最近对话、查找、新建、模型选择、发送和追问、任务状态、停止任务、截图预览、回复复制和本次权限确认。连接已有服务，不启动另一套代理；后台任务由 OpenCode 继续执行，App 回到前台刷新结果。当前使用前台有界轮询，非 SSE 逐字流式传输。

密码保存在本机 Keychain；模型凭据由 OpenCode 管理。安装包不含用户地址、密码、会话或聊天记录。发送失败后先按消息 ID 检查读回，不自动重发结果未知的任务。草稿保存在 App 私有目录并使用完整文件保护。

## 构建与使用

在已有 Swift compiler、clang、ldid 与 iPhoneOS SDK 的越狱开发设备上运行 `python3 build.py`。可用 `ICB_SDK` 指定现有 SDK，不下载或分发 Apple SDK。产物位于 `build/`，通过已有 TrollStore 安装。最低 iOS 16.1，arm64；适配 OpenCode 2 的 `/api/*`，当前验证目标为 2.2.5。

Liquid Glass 构建在安装了 Xcode 26 的 Mac 上运行 `python3 build.py --require-liquid-glass`。构建器校验 SDK 与 Swift 版本，并记录是否编译玻璃 API。`python3 tools/verify_ios26.py` 会执行构建与 iOS 26.2 模拟器预览检查。GitHub Actions 的 `Build BridgeChat for iOS 26` 工作流导出设备 IPA 和预览截图。常规 iOS 26 设备需使用自己的有效签名安装 IPA。

首次运行在连接设置填写服务地址、用户名和服务密码。受控部署可在 App 私有 Application Support/BridgeChat 中提供一次性 `bootstrap.json`；成功写入并读回 Keychain 后删除。

## 验证

构建时执行八项隔离模型检查，覆盖实际活跃状态、消息排序、图片边界、正文与推理区分、凭据字段排除和错误保留。手机构建在本机执行，Mac 设备构建在 macOS 执行，模拟器构建在 iOS 模拟器执行；构建记录标明具体环境。真实连接、键盘、发送、回复、模型选择、Keychain 和停止任务另需真机验收，不能由测试数据推断成功。
