# iOSRemoteBridge computer-use 接入

2026-11-05，基础 UI 操作已在用户现有的 iPhone SE 2 / iOS 16.1.1 / 20B101 上完成实际验证。UI 后端复用 [iOSRemoteBridge](https://github.com/Justintunsday/iOSRemoteBridge)，未重新安装插件、重载桌面或改动手机锁定策略。

可执行技能是 [ios-computer-use](../skills/ios-computer-use/SKILL.md)，薄启动器为 [run_iosremote_mcp.py](../tools/run_iosremote_mcp.py)。它从指定的上游目录启动实际 MCP 服务，支持不同工作目录，不把可选 MCP 依赖加入 `iosctl` 核心。两个客户端的配置示例见 [backend.md](../skills/ios-computer-use/references/backend.md)。

## 本轮实际结果

测试约为 19:40–19:50 香港时间。截图保留在未跟踪的本地目录，公开记录不包含截图、个人界面文字、设备地址或配对 token。

| 检查 | 结果与证明范围 |
| --- | --- |
| 现有设备服务 | `io.github.justintunsday.iosremotebridge` 0.1.0~dev 正在运行；先复用已验证的 SSH 通道读取现有配对与公钥证书指纹，再通过证书固定的 TLS 连接 |
| 实时截图 | Python API 与 MCP 均返回实际 750×1334 JPEG，模型查看过真实图片；不是示例图或旧缓存文件 |
| 点击 | 根据桌面截图选择测试 App 图标；一次 tap 后，新截图显示“实时活动测试”App 已打开 |
| 滑动 | 在测试 App 内上滑；新截图显示原先屏幕下方的活动列表与底部说明 |
| Home | Python 与 MCP 的 Home 请求后，新截图均确认回到桌面 |
| MCP 通道 | 标准 stdio 初始化列出 13 个工具，`get_screen_frame` 返回 `image/jpeg` image content；经 MCP 的点击、滑动与文字请求实际作用于设备 |
| ASCII | 在设置的可见搜索框获得焦点后输入 `irbtest42`，截图显示相同文字。当前输入法带组合态下划线；没有把“显示文字”当成输入法提交或业务查询成功。随后点击 Cancel，截图确认输入框清空、键盘收起 |
| App 启动 | `launch_app(com.apple.Preferences)` 返回错误，但后续截图显示设置已打开。记录为结果语义不可靠，不能据报错自动重试 |
| 结束状态 | 清理测试文字、返回原桌面并断开会话。前后 SpringBoard PID 相同，安全模式标记未出现；这只证明本轮有限时长，不是长期稳定性验收 |

客户端源码固定于 `24e7a212eb3f4cd8602e884bdba02a54fa16a092`，设备既有二进制的来源提交未知，哈希记录于 [脱敏证据](../evidence/iosremote-computer-use-2026-11-05.json)。服务返回 `runtime_verified:false` / `delivery_verified:false` 的字段保留原义；上述成功来自后续图像观测。

## 自动检查

- iOS Control Bridge 原有 125 项 Python 回归通过。
- 上游自动化的 16 项测试通过，含真实回环 TLS、证书固定、RPC 并发、断连不重放、MCP 图片与只读输入拒绝。这些测试不证明 iOS 私有 ABI。
- 新启动器在不同且含空格的工作目录完成实际 MCP 初始化，列出 13 工具；不存在凭据时仍可列举工具；查看模式拒绝输入，越界坐标被 schema 拒绝。
- 新启动器还通过已有配对完成真机 `get_device_info` 与 MCP 图片读取，并主动断开。
- 技能通过 `quick_validate.py`。

## 当前边界

该插件实际使用自定义 TLS / IRB1 协议，不能作为普通 RFB/VNC 服务连接。它已提供 MCP，当前不需要再开发另一套截图或 HID 注入。

这是可用的基础可视操作后端，仍缺少 AX / element_id、前台 bundle / scene、焦点与 secure-field 元数据、设备端 observation_id / 旧图拒绝、任意 Unicode 和可靠输入语义。旋转、长按、多点、持续运行以及两个宿主分别向其模型传递图片未在本轮完成验收。`iosctl ui.*` 及研究文档中的 `ios_ui_*` 契约没有实现。

Codex 和 OpenCode 可以配置同一个 stdio 启动入口；本轮通过 Codex 的执行工具调用真实 MCP SDK，并把图片交给模型查看。此结果不等于两个客户端重载后各自的原生 MCP 工具已由模型验收。要补这项，只需在各宿主重载后分别调用一次截图、描述图片，并执行一次可恢复操作；不需要重复安装手机插件。

本机已将 `iosremote` 条目分别合并到 Codex 与 OpenCode 的用户配置，其他配置保持相同；共用技能已安装到用户的 `.agents/skills/ios-computer-use`。Codex CLI 能读回新条目；OpenCode 2.0.26 经 `opencode reload` 后，`opencode mcp list` 显示 `iosremote connected`。两个入口使用同一已验证的启动命令。MCP 目录连接成功仍不代表设备会话已经建立；模型图片验收保持待补。

插件一次只允许一个远程会话。GUI 与两个 AI 客户端使用完应释放自己的会话；不会为另一端抢占连接。锁定会拒绝或终止会话，解锁由用户正常完成。当前系统服务继续使用 `iosctl`，可视界面通过独立 UI 后端操作。
