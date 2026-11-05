# iOS Unicode 直接输入

`insert_text(text)` 将文字作为 Unicode 一次提交到当前已聚焦的输入框，
避免把字符串转换成键盘按键后再次经过拼音组合、候选词选择。
skill 对普通文字优先选用该工具；旧 `type_text` 保留 US-layout ASCII
按键语义。输入框仍需获得焦点，单行框、密码框和自定义编辑器要分别验证。

原生实现位于 [iOSRemoteBridge PR #2](https://github.com/Justintunsday/iOSRemoteBridge/pull/2)。
它沿用现有证书固定、配对、控制会话和锁定检查，不使用剪贴板，不切换输入法，
不要求 `keyboard_mode`，也不将换行转换为 Return 按键。最大长度为 1024 个
UTF-16 单元；无效代理项和超长输入在提交前拒绝。

## 2026-11-05 真机回读

iPhone SE 2 / iOS 16.1.1 / 20B101 上的独立 UIKit 测试框编译并调用了实际
修改后的 `IRBInput.m`，保持 `zh-Hans` 中文输入法。混合中文、emoji、ZWJ emoji、
重音字符和换行，512 个 emoji，1024 个 ASCII 字符，组合重音及连续换行，
全部按原文回读，均无 marked text 组合态。空文本未产生输入，超长文本被拒绝。
测试没有开启远控截图或触控连接，也没有向其他 App 的输入框写入文字。

直接调用 `BKSHIDEventSendToProcess` 的独立探测未产生文字；最终采用
`IOHIDEventSystemClientDispatchEvent` 和一个 UTF-16LE Unicode 事件，
无需复制其他设备的 sender ID 或设置额外的 field-4 标记。

这证明了上述设备上原生方法在测试框中的效果，不等于任意 App、任意 iOS
版本或 secure-field 已验证。`delivery_verified:false` 保留原义，AI 应观察
目标输入框的实际结果。错误、超时或断连之后不自动重发文字，不降级成按键重打。

## 客户端检查

无依赖 stdio 入口现在提供 10 个工具；新增 Unicode、UTF-16 边界、只读拒绝和
不重放检查后，本仓库 138 项回归通过。手机 Python 3.9.9 上的 13 项 stdio
检查通过。上游 16 项自动化、TLS 和 MCP 检查，以及 macOS 上实际生产
validator 与 arm64/arm64e 原生打包 CI 均通过。

仅有工具目录不证明旧设备插件已支持新操作；先查看
`input_diagnostics.literal_text_ready`，缺失时不要把目录存在当作输入能力。

## 已安装状态

CI 产物已安装到设备，原插件和客户端配置保留备份，原配对未改变。
首次部署因桌面进程变化触发自动回退；重试时等待新插件实际发布就绪状态后再
建立稳定性基线，随后连续 30 秒以上保持同一桌面进程且没有安全模式标记。
部署及后续检查均读到 `literal_text_ready:true`。

手机 OpenCode 已切换到新的版本目录，重载后显示 `iosremote connected`；
App 使用的 OpenCode 服务也已重载。电脑与手机的 skill 均已更新。
这些是代码安装、工具目录与就绪检查，没有恢复远控截图／触控会话，也没有
把独立测试框的结果写成部署后 MCP 文字输入已完成端到端验收。
[脱敏证据](../evidence/iosremote-direct-text-2026-11-05.json) 保留具体边界。
