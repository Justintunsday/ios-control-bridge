import Foundation

@main
struct ModelChecks {
    static func main() {
        precondition(ChatSession(["id": "ses_test", "outcome": "failed", "time": ["busy": 20, "idle": 10]]).active)
        precondition(!ChatSession(["time": ["busy": 20, "idle": 21]]).active)
        let raw: [JSON] = [
            ["id": "a", "type": "assistant", "content": [["type": "reasoning", "text": "private reasoning"], ["type": "text", "text": "**收到**"], ["type": "tool", "id": "t", "name": "iosremote_get_screen_frame", "state": ["status": "completed", "input": ["token": "secret"], "content": [["type": "file", "uri": "data:image/jpeg;base64,YQ=="], ["type": "file", "uri": "https://unrelated.invalid/pixel.jpg"]]]]]],
            ["id": "u", "type": "user", "text": "<script>alert(1)</script>"]
        ]
        let rows = ChatMessage.parse(raw)
        precondition(rows.count == 2 && rows[0].id == "u")
        precondition(rows[0].body == "<script>alert(1)</script>")
        precondition(rows[1].body == "**收到**" && !rows[1].body.contains("private reasoning"))
        precondition(rows[1].tools[0].images.count == 1 && !rows[1].tools[0].details.contains("secret"))
        precondition(ChatMessage.parse([["id": "e", "type": "idle", "error": ["message": "模型不可用"]]])[0].error == "模型不可用")
        precondition(ModelChoice(["id": "deepseek-flash", "providerID": "deepseek", "settings": ["apiKey": "private"]]).id == "deepseek/deepseek-flash")
        print("8 native model checks passed")
    }
}
