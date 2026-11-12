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
        store.sessions = [
            ChatSession(["id": "ses_preview_one", "title": "整理开发计划", "model": flash.reference, "time": ["updated": Date().timeIntervalSince1970 * 1000]]),
            ChatSession(["id": "ses_preview_two", "title": "聊聊一个新想法", "model": flash.reference]),
        ]
        switch route {
        case "chat", "models":
            store.open(nil)
            store.messages = [
                ChatMessage(id: "preview_user", user: true, body: "帮我把这个想法整理成一个清晰的计划。", tools: [], error: "", created: 1),
                ChatMessage(id: "preview_assistant", user: false, body: "可以。先明确目标，再把它拆成今天能推进的小步骤。\n\n接下来，你可以补充时间安排或其他要求。", tools: [], error: "", created: 2),
            ]
            store.draft = "先从第一步开始"
            if route == "models" {
                Task {
                    try? await Task.sleep(nanoseconds: 400_000_000)
                    store.showingModels = true
                }
            }
        case "settings":
            store.showingSettings = true
        default:
            break
        }
        return true
    }
}
#endif
