#if targetEnvironment(simulator)
import Foundation

/// Explicit simulator launch fixtures for visual review. Excluded from device builds.
@MainActor
enum SimulatorPreview {
    static var route: String? {
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: "--bridgechat-ui-review"),
              arguments.indices.contains(index + 1) else { return nil }
        return arguments[index + 1]
    }

    static func configure(_ store: ChatStore) -> Bool {
        guard let route = route else { return false }
        let flash = ModelChoice(["id": "deepseek-flash", "providerID": "deepseek", "name": "DeepSeek Flash"])
        let reasoner = ModelChoice(["id": "deepseek-reasoner", "providerID": "deepseek", "name": "DeepSeek Reasoner"])
        store.connected = true
        store.models = [flash, reasoner]
        store.preferred = flash
        let now = Date().timeIntervalSince1970 * 1000
        store.sessions = [
            ChatSession(["id": "ses_preview_running", "title": "整理今天的待办", "model": flash.reference, "time": ["updated": now, "busy": now, "idle": now - 1000]]),
            ChatSession(["id": "ses_preview_one", "title": "整理开发计划", "model": flash.reference, "time": ["updated": now - 3600_000]]),
            ChatSession(["id": "ses_preview_two", "title": "聊聊一个新想法", "model": reasoner.reference, "time": ["updated": now - 86400_000]]),
        ]
        switch route {
        case "chat", "models", "chat-keyboard", "chat-running":
            store.open(nil)
            store.messages = [
                ChatMessage(id: "preview_user", user: true, body: "帮我把这个想法整理成一个清晰的计划。", tools: [], error: "", created: 1),
                ChatMessage(id: "preview_assistant", user: false, body: "可以。我们先把目标拆成三个步骤：\n\n### 明确目标\n写下你希望完成的事，以及最重要的限制。\n\n### 排好顺序\n先做影响最大、今天就能推进的一步。\n\n### 留出复盘\n完成后再调整下一步。", tools: [], error: "", created: 2),
            ]
            store.draft = "先从第一步开始"
            if route == "chat-running" {
                store.selected = store.sessions.first
                store.draft = "优先处理今天要完成的事"
            }
            if route == "models" {
                Task {
                    try? await Task.sleep(nanoseconds: 400_000_000)
                    store.showingModels = true
                }
            }
        case "settings":
            store.showingSettings = true
        case "new":
            store.open(nil)
            store.draft = ""
        case "markdown-text", "markdown-code", "markdown-table":
            store.open(nil)
            store.draft = ""
            let examples: [String: String] = [
                "markdown-text": """
                # Markdown

                **粗体**、*斜体*、~~删除线~~ 与 `inline code`。

                - 支持无序列表
                  - 也支持嵌套列表
                - 保留原有段落

                3. 从指定数字开始
                4. 自动对齐编号

                - [x] 已完成的事项
                - [ ] 待办事项
                """,
                "markdown-code": """
                ## 引用与代码

                > 原生排版，保留 **强调** 与链接。

                ```swift
                let greeting = "你好，BridgeChat"

                print(greeting)
                ```

                ---

                查看 [Swift 官方文档](https://www.swift.org/documentation/)。
                """,
                "markdown-table": """
                ## 表格

                | 项目 | 状态 | 数量 |
                | :--- | :---: | ---: |
                | 原生排版（含复杂嵌套） | **完成** | 3 |
                | 兼容样式 | 支持 | 12 |
                | 留空单元格 | | 0 |

                第一行\u{20}\u{20}
                第二行

                ![示例图片](https://example.com/image.png)
                """,
            ]
            store.messages = [
                ChatMessage(id: "preview_markdown_user", user: true, body: "**我的问题**：请展示 `Markdown` 排版。", tools: [], error: "", created: 1),
                ChatMessage(id: "preview_markdown_answer", user: false, body: examples[route] ?? "", tools: [], error: "", created: 2),
            ]
        default:
            break
        }
        return true
    }
}
#endif
