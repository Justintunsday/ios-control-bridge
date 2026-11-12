# BridgeChat 0.4 原生布局

## 版本与架构

最低 iOS 16.1。iOS 26 构建使用 Xcode 26.2、Swift 6.2.3，保留 Swift 5 语言模式、ObservableObject / StateObject 和现有 OpenCode API。iOS 26 API 同时由编译条件与运行时可用性检查保护。此次不引入第三方依赖。

## 设计方向

界面围绕浏览对话、阅读回复、继续输入三个动作组织。保留单一 NavigationStack 层级；会话列表使用系统分组，聊天内容保持平整，玻璃只用于导航与输入控件。模型选择靠近输入栏，任务状态与停止动作放在同一区域。

会话页：大标题 → 紧凑连接行 → 进行中的对话 → 最近对话 → 系统搜索。

聊天页：会话标题 → 可滚动消息 → 模型选择／任务状态 → 输入框与发送按钮。

设置页：App 标识 → 服务地址 → 登录信息 → 连接状态与版本。

初稿评审移除了额外的首页大卡片和仅为装饰设置的标签栏。分组只反映实际会话状态，不用统计卡片或虚构功能填充界面。

## 视觉与交互

- 配色采用 systemBackground、secondarySystemGroupedBackground、primary、secondary 与系统蓝强调色；不固定浅色／深色 RGB。
- 字体使用系统 SF、语义字号与 Dynamic Type。大标题标记页面层级，body 用于消息与表单，footnote / caption 用于模型与时间。
- 标准导航、搜索、sheet 和 Form 采用系统外观。自定义输入栏使用 safeAreaBar、GlassEffectContainer 和交互玻璃；较早系统使用 safeAreaInset 与标准材质。
- 控件至少提供 44pt 的点击区域，图标提供 VoiceOver 标签，状态同时以文字表示。辅助功能字号使用纵向布局与可换行文本。
- 模型选择使用原生 List 和选中标记；设置表单保留系统键盘、密码自动填充、取消和确认动作。
- 使用现有重绘图标，不新增光效或持续播放的装饰动画。

## 性能审查范围

拆分会话、聊天、输入、消息和设置视图，向消息单元传递值。消息单元使用完整消息值进行 Equatable 比较。草稿写入采用取消感知的延迟合并，离开会话／进入后台仍立即保存。截图解码移出随缩放反复执行的 body。

上述改动用于减少重复工作，不代表已经完成真机 Instruments 性能测量。

## 参考技能

- [SwiftUI Expert](https://github.com/AvdLee/SwiftUI-Agent-Skill/tree/62bd760f005093d1e2e4de5db156e456a5f96400/skills/swiftui-expert-skill)：状态、视图边界、布局、性能、无障碍与 API 版本。
- [SwiftUI Liquid Glass](https://github.com/Dimillian/Skills/tree/05ba982bfeb0d77d3c97d4542b0ee15034d05f84/swiftui-liquid-glass)：玻璃的层级、分组、交互与版本回退。

仅采用兼容当前部署目标的建议，不迁移至 SDK 27 API 或强制改用 Observation。

## 验证

构建脚本执行隔离模型检查。iOS 26 工作流构建设备 IPA，并在模拟器中预览正常字号、深色、辅助功能字号、键盘和任务状态；另使用较小屏幕检查布局。预览数据只存在于显式启动的模拟器夹具中。真实连接、发送、Keychain 与性能测量需分别验收。

已有 Figma 稿仍位于 https://www.figma.com/design/7ISKUCiVN5Q3eEQJW6ZSt6?node-id=5-78 ，此前受字体和调用额度限制；本次交付以实际 SwiftUI 界面与模拟器截图为准。
