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

- Control API 原有 125 项 Python 回归通过。
- 上游自动化的 16 项测试通过，含真实回环 TLS、证书固定、RPC 并发、断连不重放、MCP 图片与只读输入拒绝。这些测试不证明 iOS 私有 ABI。
- 新启动器在不同且含空格的工作目录完成实际 MCP 初始化，列出 13 工具；不存在凭据时仍可列举工具；查看模式拒绝输入，越界坐标被 schema 拒绝。
- 新启动器还通过已有配对完成真机 `get_device_info` 与 MCP 图片读取，并主动断开。
- 技能通过 `quick_validate.py`。

## 当前边界

该插件实际使用自定义 TLS / IRB1 协议，不能作为普通 RFB/VNC 服务连接。它已提供 MCP，当前不需要再开发另一套截图或 HID 注入。

这是可用的基础可视操作后端，仍缺少 AX / element_id、前台 bundle / scene、焦点与 secure-field 元数据、设备端 observation_id / 旧图拒绝和可靠业务提交语义。后续新增的 Unicode 直接插入及实际验证边界见 [直接输入记录](iosremote-direct-text.md)。旋转、长按、多点、持续运行以及两个宿主分别向其模型传递图片未在本轮完成验收。`iosctl ui.*` 及研究文档中的 `ios_ui_*` 契约没有实现。

初次桌面测试通过 Codex 的执行工具调用真实 MCP SDK，并把图片交给模型查看；它没有证明两个宿主原生 MCP 的图片链路。后续已完成下文的手机 OpenCode 模型验收，Codex 原生 MCP 链路仍待单独验证。

开发电脑已将 `iosremote` 条目分别合并到 Codex 与 OpenCode 的用户配置，其他配置保持相同；共用技能已安装到用户的 `.agents/skills/ios-computer-use`。Codex CLI 能读回新条目；桌面 OpenCode 2.0.26 经 `opencode reload` 后，`opencode mcp list` 显示 `iosremote connected`。MCP 目录连接成功不代表设备会话已经建立。

插件一次只允许一个远程会话。GUI 与两个 AI 客户端使用完应释放自己的会话；不会为另一端抢占连接。锁定会拒绝或终止会话，解锁由用户正常完成。当前系统服务继续使用 `iosctl`，可视界面通过独立 UI 后端操作。

## 手机 OpenCode 模型验收

同日 20:09:51–20:12:54（香港时间），用户要求手机 OpenCode 浏览 Instagram 三分钟。实际执行者为手机上运行的 OpenCode 2.2.5 `build` 会话与已有的 `deepseek/deepseek-flash`；开发电脑仅发送任务、读取该会话记录并抽查其返回的图片，没有代替它注入浏览动作。

手机的 Python 为 3.9.9，而上游 MCP SDK 2.3.0 要求 Python 3.10+，因此新增 `--stdlib` 入口。它使用本仓库的 `tools/iosremote_stdio.py` 提供九个基础 MCP 工具，仍复用上游 TLS 客户端和原有配对。接口在手机配置并重载后，原生 MCP 直接把 JPEG 图片交给移动端模型。

该会话先看见当前 App，返回桌面、看图定位 Instagram 图标并打开，再用新图确认首页。实际浏览 183 秒，完成 14 次滑动，包含准备阶段共取得 19 张截图。每次滑动后均重新截图；两次单击分别是打开 App 与关闭广告问卷弹窗。最后一次滑动在目标截止时间前完成，收尾记录时比 180 秒目标多三秒。随后主动断开，最后保留 Instagram 首页。

默认免费模型最初返回地区不可用的 403，尚未进行任何输入；仅本次会话改用已有 DeepSeek 配置后执行成功。没有更换全局默认模型、代理、地区或认证资料。任务期间没有点赞、关注、评论或消息操作，SpringBoard PID 前后相同，无安全模式标记。截图、账号信息、会话 ID 与原始聊天记录留在本地；公开记录仅有[脱敏结果](../evidence/iosremote-mobile-opencode-2026-11-05.json)。

新增 stdio 的九项边界测试、原有 125 项回归全部通过；这九项测试也在手机 Python 3.9.9 通过。另用官方 MCP 2.3 客户端进程验证初始化、只读拒绝、坐标约束及不同工作目录启动，图片交付经手机原生 OpenCode 链路验证。有限时长与一个真实 App 的通过不代表任意 App 或长期无人值守能力已验收。
