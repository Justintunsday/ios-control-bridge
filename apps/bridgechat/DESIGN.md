# BridgeChat 原生界面方案

0.3.0（build 5）采用 SwiftUI、HIG 语义色、SF Symbols 与 Dynamic Type。iOS 26 构建启用原生 Liquid Glass，iOS 16–18 使用兼容外观。

iOS 26 的聊天输入栏使用 `safeAreaBar`、`GlassEffectContainer`、`glassEffect(.regular)` 和圆形 `glassProminent` 发送按钮。导航栏、菜单与 sheet 采用新 SDK 的系统样式。工具栏的确认和取消动作使用系统符号。SDK 版本决定是否编译玻璃 API，运行时的系统版本决定是否启用。

`tools/verify_ios26.py` 使用真实 iOS 26 SDK 构建，并在 iOS 26.2 模拟器中生成浅色、深色和辅助功能字号的预览。预览消息由仅编入模拟器的显式启动夹具提供。设备安装包排除这些夹具。

Figma 可编辑稿位于 https://www.figma.com/design/7ISKUCiVN5Q3eEQJW6ZSt6?node-id=5-78 。当前 Figma 预览报告 SF Pro 缺失。按用户选择保留 SF Pro，并优先完成原生 App。App 使用 iOS 系统字体。

App 图标使用 `Assets/BridgeChatIcon.svg` 的系统蓝渐变、双对话气泡与提示符图形。导出的 120px、180px PNG 均为不透明 RGB，打包时使用 `AppIconNative60x60` 文件名。Figma 调用额度当前已耗尽，图标的可编辑源文件保留在本项目中。

- 会话入口：NavigationStack 大标题、plain List、系统搜索和工具栏新建按钮，顶部显示可打开连接设置的服务卡片。
- 会话详情：系统返回手势与导航栏；消息使用 ScrollView / LazyVStack，用户消息采用系统强调色，助手采用系统背景与正文颜色。
- 输入：原生多行 TextField，safeAreaInset 随系统键盘移动；执行中可以追问或停止。
- 设置：原生 Form、SecureField 与 sheet；密码由 Keychain 保存。
- 模型和权限：原生 sheet / List / Form；截图使用原生全屏预览和缩放。
- 字体：largeTitle、headline、body、caption 等语义样式，跟随用户文字大小；不固定页面尺寸或模拟状态栏。
- 配色：系统背景、分组背景、primary / secondary 与系统强调色，跟随系统外观；图标保留双对话气泡标识。

消息不执行 HTML，不自动加载外部图片。执行明细默认收起，截图由用户点开。系统容器提供分隔线、内边距、sheet 和导航，不手绘网页式导航组件。
