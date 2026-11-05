# iOS computer-use 移植研究

研究日期：2026-11-05。目标设备：已越狱 iPhone / iOS 16.1.1 / 20B101；开发主机为 Windows。目标客户端：Codex 与 OpenCode。

## 结论与当前完成度

**已通过 iOSRemoteBridge 完成观察、定位、操作、再观察的基础移植。** 复用其设备后端与 MCP，保留 iOS Control Bridge 的系统服务接口和现有 Swift 活动桥接。单独复制 SKILL.md 仍不能获得截图或触摸能力；需要实际后端连接。

后续已接入用户已有的 **iOSRemoteBridge** 外部 UI 后端，完成截图 → 点击打开测试 App → 新截图，以及滑动、Home、MCP 图片与 ASCII 可见输入验证。可用技能位于 [skills/ios-computer-use](../skills/ios-computer-use/SKILL.md)，启动器为 `tools/run_iosremote_mcp.py`；见 [接入与真机记录](iosremote-computer-use.md)。原 [研究草案](../research/ios-computer-use/SKILL.md) 保留作设计记录。

本仓库仍没有实现下文 `ui.*` / `ios_ui_*` 契约。当前采用上游实际 MCP 工具名，尚无 AX 树、前台 scene、可靠焦点元数据和服务端 observation_id。以下契约是后续增强设计，不能当成现有工具列表。

设备只读核查确认已有 clang、swiftc 和 ldid；在当前 PATH 未发现 screenshot、idevicescreenshot、zxtouch、tidevice 或 appium 命令。这只是命令入口检查，不证明相关框架或 App 一定不存在。

## 现有 computer-use 中可迁移的部分

本机随附的 Windows skill 使用 `@oai/sky`，底层依赖 Windows UI Automation、SendInput 和 Windows.Graphics.Capture。它们不是 iOS API，`Window` 句柄、Windows 键名和辅助程序也不能转换成 iPhone 句柄。

可保留的协议思想：只使用实际返回的应用身份；一次观察绑定一组控件/截图；每次动作后重新观察；输入前核实焦点；超时后的结果视为未知，先观察再决定下一步。iOS 需要增加前台 App / scene、屏幕锁定、旋转、像素到点的换算和多个客户端争用同一屏幕的处理。

Windows 专属的工具初始化和 Windows 操作规则不机械搬进 iOS skill。两个平台共用用户意图与数据可信性原则，平台动作由各自工具提供。

## 后端路线比较

| 路线 | 可复用能力 | 当前设备的条件与限制 | 建议 |
| --- | --- | --- | --- |
| iOSRemoteBridge | 已有 JPEG、HID 触摸、ASCII 与 MCP stdio | 用户设备已有安装；本轮基础操作实测通过；AX / Unicode / 旧观察拒绝缺失 | 当前基础 computer-use 主线，复用插件而无需新增注入 |
| WebDriverAgent / XCTest | 截图、可访问控件、点击、滚动、文本输入、App 操作 | 需要可运行的 XCTest runner 与匹配版本；标准构建/启动有 Xcode 和签名条件 | 作为成熟的可选后端与验收对照，先证明 runner 在目标设备可运行 |
| 设备本地 Objective-C helper / daemon | 复用现有越狱工具链，后续可独立于 Mac 运行 | 跨 App AX 等额外接口/entitlement 尚待逐项验证 | 用于后续补充能力，不重复实现现有插件已验证的截图与触摸 |
| ZXTouch / XXTouchNG 等旧项目 | 可研究触摸、OCR 与设备工具的实现思路 | ZXTouch README 声明 iOS 11–14；XXTouchNG 仓库已归档。不能据此确认 iOS 16 rootless 可用 | 仅作源码参考，不直接安装旧包；复用代码前核对对应许可证 |

WDA 通过 XCTest 执行设备自动化；固定版本源码中存在真实的 screenshot、element click/value 等接口，可作为接口实现对照。[WDA v8.9.1 说明](https://github.com/appium/WebDriverAgent/blob/v8.9.1/README.md)、[截图命令](https://github.com/appium/WebDriverAgent/blob/v8.9.1/WebDriverAgentLib/Commands/FBScreenshotCommands.m)、[控件命令](https://github.com/appium/WebDriverAgent/blob/v8.9.1/WebDriverAgentLib/Commands/FBElementCommands.m)。

版本条件必须单独处理：当前 Appium 兼容表把 iOS 16.0–16.3 的完整支持区间列为 XCUITest driver 4.7.4–7.26.3 / WDA 4.8.1–8.9.1。**这些范围不是本项目的真机验证结果。** 若试用 WDA，8.9.1 可作为候选固定版本，再核对 Xcode、driver 与实际设备；不能默认安装 latest。[Appium 系统要求](https://appium.github.io/appium-xcuitest-driver/latest/getting-started/system-requirements/)。

当前 Appium 的非 macOS 主机路径要求 iOS/tvOS 18 以上；WDA v13 以上的 preinstalled 启动路径又要求 iOS/tvOS 17 以上。因此不能把这两份新功能说明当成本机 iOS 16.1.1 的安装教程。已有且能独立运行的旧 WDA 服务，仍可另行研究直接连接；“Windows 上能发 HTTP”不等于 runner 已可启动。[非 macOS 主机](https://appium.github.io/appium-xcuitest-driver/latest/guides/non-macos-hosts/)、[Preinstalled WDA](https://appium.github.io/appium-xcuitest-driver/latest/guides/run-preinstalled-wda/)。

旧越狱项目的适用范围与许可直接见其上游：[ZXTouch](https://github.com/xuan32546/IOS13-SimulateTouch)、[XXTouchNG](https://github.com/XXTouchNG/XXTouchNG)。本研究没有复制这些项目或随附 Windows runtime 的实现代码。

## 后续增强结构（当前连接路线见接入记录）

```text
Codex                         OpenCode
  └──────── 共用 ios-computer-use skill ────────┘
                         │
                 同一套 MCP 工具协议
                         │
              Python host / CLI 适配层
                         │
          本机 stdio 或已校验主机身份的 SSH
                         │
          设备端会话、操作队列与独占租约
                 ┌───────┴────────┐
       Objective-C 原生 UI 后端    可选 WDA 后端
```

保留 `iosctl` 的现有 JSON 结果结构与状态区分，未来新增 `ui.*` 适配器；新增能力只有实现和实测后才能在 registry 标记 ready。系统设置、闹钟、提醒事项仍优先走准确的服务接口，UI 用于需要可视交互或没有服务适配器的任务。

设备端应提供全局串行化和租约，而不只依赖每个 MCP 进程自己的锁：Codex 与 OpenCode 会启动独立进程。会话标识不是身份验证，租约也不是对用户意图的替代。沿用用户实际授予的目标与动作范围。

[审查报告](reviews/deepseek-2026-11-05.md) 中的共享文件、链接跟随、遗留命令和并发问题已在 0.12.0 修复。当前 UI 路线复用 iOSRemoteBridge 独立认证通道，不复用旧 SpringBoard 文件 mailbox。

## 设计接口（当前尚未实现）

| MCP 工具名 | 未来 CLI 操作 | 关键输入与输出 |
| --- | --- | --- |
| `ios_ui_capabilities` | `ui.capabilities` | backend、设备 build、每项操作 implemented/verified/ready、会话状态 |
| `ios_ui_begin` / `ios_ui_end` | `ui.begin` / `ui.end` | 明确设备与应用范围；获取/释放设备端独占操作租约 |
| `ios_ui_observe` | `ui.observe` | 返回 observation_id、前台 bundle/scene、锁定状态、截图/AX、焦点、采样时刻与完整性 |
| `ios_ui_launch` | `ui.launch` | 使用实际列举或用户明确指定的 bundle ID，报告启动和前台状态 |
| `ios_ui_tap` | `ui.tap` | observation_id + element_id，或 screenshot_id + 明确坐标空间的 x/y |
| `ios_ui_swipe` | `ui.swipe` | observation_id、截图坐标空间、起终点和有界时长 |
| `ios_ui_type_text` | `ui.type_text` | observation_id、已观察的焦点、literal text、append/replace 语义 |
| `ios_ui_press_button` | `ui.press_button` | 小范围允许的设备按钮，动作后重新观察 |

截图通过 MCP image content 返回，元数据通过 structuredContent 及简短 text 返回。不要仅输出手机本地文件路径给远端模型，也不要把 base64 嵌入日志文本。MCP 原生支持图片内容，但 **实际 Codex/OpenCode 版本、模型与 provider 是否把图片交给模型仍须分别验证**；若只有文本通道，可用有来源标记的 AX/OCR，并如实标注视图缺失。[MCP 工具结果规范](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)。

### observation 最小契约

- `observation_id` / `screenshot_id` 是服务端生成的短期不透明标识，绑定 device boot/session、前台 bundle/scene、旋转和当前租约。
- 截图记录像素宽高、采样时间、原图/裁剪区域、显示坐标原点、坐标单位及点/像素换算信息。坐标始终来自本次实际返回值，不硬编码设备型号对应的缩放比例。
- AX 每项包含不透明 element_id、role、label、可用状态、边界和所属观察；焦点与 secure-text 状态独立表达。树缺失、受保护画面、截断和完整空结果分别表示。
- 点击前在设备端重检前台、锁定状态、观察有效期和租约。旧截图、换 App、旋转或别的客户端插入动作后，应拒绝旧操作并要求重新观察。
- 每次动作使用 request_id 和 deadline。结果区分 accepted、executed 与效果已观察；输入超时后用请求状态及新观察消除不确定性，不能原样重发点击或文字。

### 原生实现约束

先在独立 helper 验证截图与前台识别，再验证单次触摸。截图服务、AX 和 HID 都是需要研究的后端方向，当前不写入任何“已确认的私有 selector”清单。每个入口核对真实符号/Objective-C 方法签名、线程与 entitlement，保持 build allowlist。

如果确实必须进入 SpringBoard，tweak 只保留最小的已核对入口；避免在其主线程 sleep 等待，使用异步完成与有界超时。新增逻辑先隔离验证，保留可恢复安装方式，再部署。这一阶段需要真实设备证据，不能由 Python mock 证明 ABI 正确。

文本输入单独验收中文、emoji、组合输入、焦点丢失和 secure field；触摸注入并不自动提供 Unicode 文本输入。锁屏不能靠普通点击假定已解锁，密码/生物认证交还给用户已有的解锁方式。

页面、AX、OCR 和截图内容都是任务数据，不能授权新的发信、上传或文件动作；屏幕出现的指令也不能修改助手的任务范围。

## Codex / OpenCode 分发

两个客户端均可使用 SKILL.md 与 MCP。本轮按官方文档核实到，共用的项目发现位置可以是 `.agents/skills/ios-computer-use/SKILL.md`，用户位置为 `~/.agents/skills/ios-computer-use/SKILL.md`；具体安装前仍检查客户端版本与现有技能，避免重复同名副本。[Codex skills](https://learn.chatgpt.com/docs/build-skills)、[OpenCode skills](https://opencode.ai/docs/skills/)。

客户端配置仅有薄薄的差异：

| 客户端 | MCP 配置形状 | 设备后端 |
| --- | --- | --- |
| Codex | `config.toml` 中 `[mcp_servers.ios]`，`command` 和 `args` 启动 stdio server | 共用 |
| OpenCode | `opencode.json` 中 `mcp.ios`，`type: "local"`、`command: [...]` | 共用 |

当前实际 MCP 入口与两个客户端的配置见 [后端说明](../skills/ios-computer-use/references/backend.md)。现有配对 token 仅由本地客户端读取，stdio 不新增 HTTP 监听；不把密码放进 SKILL.md 或公共配置。[Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、[OpenCode MCP](https://opencode.ai/docs/mcp-servers/)。

## 实施与验收次序

1. **修复现有桥接与契约**：完成 R1/R3/R4 以及超时、重放、并发修复；保持已有服务可用。
2. **只读观察原型**：取得真实 screenshot + 前台身份 + 锁定/方向；用专用测试 App 对照，验证坐标空间与旋转。AX/OCR 可分别声明可用状态，不阻塞截图验证。
3. **单动作闭环**：测试 App 中一个按钮计数器，先观察、点击一次、重新观察计数 +1。旧观察、锁屏、App 切换和请求超时均不得造成补点或重复点。
4. **输入与滑动**：专用输入框验证中文/emoji 和焦点；列表验证 swipe、边界及后续重新定位。
5. **双客户端接入**：同一 MCP 后端分别由 Codex/OpenCode 加载；验证 image content 可见、工具参数一致，以及两端争用时只有租约持有者能输入。
6. **有限真实 App 验收**：在用户指定 App 和具体任务范围内测试。记录 iOS build、native/helper 哈希、前后观察和结果；截图与个人内容不提交到公开仓库。

首个可交付里程碑是“两个客户端都能观察测试 App，并可靠点一次按钮”，不是先声称支持全手机无人值守。若独立原生后端的 AX 路径暂时不可用，可先交付截图与点击，并准确暴露该限制。
