import Foundation

typealias JSON = [String: Any]
func text(_ value: Any?) -> String { value as? String ?? "" }
func number(_ value: Any?) -> Double { (value as? NSNumber)?.doubleValue ?? 0 }
func object(_ value: Any?) -> JSON { value as? JSON ?? [:] }

struct ModelChoice: Identifiable, Equatable {
    let modelID: String
    let providerID: String
    let name: String
    let seesImages: Bool
    var id: String { providerID + "/" + modelID }
    var reference: JSON { ["id": modelID, "providerID": providerID] }
    init(_ raw: JSON) {
        modelID = text(raw["id"])
        providerID = text(raw["providerID"])
        name = text(raw["name"]).isEmpty ? text(raw["id"]) : text(raw["name"])
        seesImages = (object(raw["capabilities"])["input"] as? [String] ?? []).contains("image")
    }
}

struct ChatSession: Identifiable, Equatable {
    let id: String
    var title: String
    var model: ModelChoice?
    var updated: Double
    var active: Bool
    init(_ raw: JSON) {
        id = text(raw["id"])
        title = text(raw["title"]).isEmpty ? "未命名对话" : text(raw["title"])
        model = object(raw["model"]).isEmpty ? nil : ModelChoice(object(raw["model"]))
        let time = object(raw["time"])
        updated = number(time["updated"])
        active = number(time["busy"]) > number(time["idle"])
    }
}

func redact(_ value: Any) -> Any {
    if let dictionary = value as? JSON {
        var result: JSON = [:]
        for (key, item) in dictionary {
            result[key] = key.range(of: "password|token|api.?key|authorization|secret", options: [.regularExpression, .caseInsensitive]) == nil ? redact(item) : "••••"
        }
        return result
    }
    if let array = value as? [Any] { return array.map(redact) }
    return value
}

struct ToolStep: Identifiable, Equatable {
    let id: String
    let name: String
    let status: String
    let details: String
    let images: [String]
    var finished: Bool { status == "completed" }
    var failed: Bool { status == "error" || status == "failed" }
    init(_ raw: JSON) {
        id = text(raw["id"])
        let original = text(raw["name"])
        let names = ["iosremote_get_screen_frame": "查看手机屏幕", "iosremote_get_device_info": "读取设备状态", "iosremote_get_connection_status": "检查连接", "iosremote_get_orientation": "查看屏幕方向", "iosremote_tap": "点击屏幕", "iosremote_swipe": "滑动屏幕", "iosremote_type_text": "输入文字", "iosremote_press_home": "返回桌面", "iosremote_disconnect": "断开设备会话", "shell": "执行命令", "read": "读取文件", "skill": "加载技能"]
        name = names[original] ?? original
        let state = object(raw["state"])
        status = text(state["status"])
        var parts: [String] = []
        let input = object(state["input"])
        if !input.isEmpty, let data = try? JSONSerialization.data(withJSONObject: redact(input), options: [.prettyPrinted, .sortedKeys]), let string = String(data: data, encoding: .utf8) { parts.append(string) }
        var pictures: [String] = []
        for content in state["content"] as? [JSON] ?? [] {
            let uri = text(content["uri"])
            if text(content["type"]) == "file", (uri.hasPrefix("data:image/jpeg;base64,") || uri.hasPrefix("data:image/png;base64,")), uri.utf8.count < 2_200_000 { pictures.append(uri) }
            if text(content["type"]) == "text" { parts.append(String(text(content["text"]).prefix(10_000))) }
        }
        let error = text(object(state["error"])["message"]).isEmpty ? text(state["error"]) : text(object(state["error"])["message"])
        if !error.isEmpty { parts.append(error) }
        details = String(parts.joined(separator: "\n\n").prefix(14_000))
        images = pictures
    }
}

struct ChatMessage: Identifiable, Equatable {
    let id: String
    let user: Bool
    let body: String
    let tools: [ToolStep]
    let error: String
    let created: Double
    static func parse(_ records: [JSON]) -> [ChatMessage] {
        records.reversed().compactMap { raw in
            let kind = text(raw["type"])
            let id = text(raw["id"])
            let created = number(object(raw["time"])["created"])
            if kind == "user" { return ChatMessage(id: id, user: true, body: text(raw["text"]), tools: [], error: "", created: created) }
            guard kind == "assistant" || kind == "idle" else { return nil }
            var paragraphs: [String] = []
            var tools: [ToolStep] = []
            for part in raw["content"] as? [JSON] ?? [] {
                if text(part["type"]) == "text", !text(part["text"]).isEmpty { paragraphs.append(text(part["text"])) }
                if text(part["type"]) == "tool" { tools.append(ToolStep(part)) }
            }
            let error = text(object(raw["error"])["message"])
            guard !paragraphs.isEmpty || !tools.isEmpty || !error.isEmpty else { return nil }
            return ChatMessage(id: id, user: false, body: paragraphs.joined(separator: "\n\n"), tools: tools, error: error, created: created)
        }
    }
}

struct PermissionRequest: Identifiable {
    let id: String
    let title: String
    let detail: String
    init(_ raw: JSON) {
        id = text(raw["id"]).isEmpty ? text(raw["requestID"]) : text(raw["id"])
        title = text(raw["title"]).isEmpty ? text(raw["action"]) : text(raw["title"])
        let data = try? JSONSerialization.data(withJSONObject: redact(raw), options: [.prettyPrinted, .sortedKeys])
        detail = String((data.flatMap { String(data: $0, encoding: .utf8) } ?? "").prefix(8_000))
    }
}
