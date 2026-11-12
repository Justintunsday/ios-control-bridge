import Foundation

@main
struct ModelChecks {
    static func main() {
        var checks = 0
        func check(_ condition: @autoclosure () -> Bool) {
            precondition(condition())
            checks += 1
        }
        check(ChatSession(["id": "ses_test", "outcome": "failed", "time": ["busy": 20, "idle": 10]]).active)
        check(!ChatSession(["time": ["busy": 20, "idle": 21]]).active)
        let raw: [JSON] = [
            ["id": "a", "type": "assistant", "content": [["type": "reasoning", "text": "private reasoning"], ["type": "text", "text": "**收到**"], ["type": "tool", "id": "t", "name": "iosremote_get_screen_frame", "state": ["status": "completed", "input": ["token": "secret"], "content": [["type": "file", "uri": "data:image/jpeg;base64,YQ=="], ["type": "file", "uri": "https://unrelated.invalid/pixel.jpg"]]]]]],
            ["id": "u", "type": "user", "text": "<script>alert(1)</script>"]
        ]
        let rows = ChatMessage.parse(raw)
        check(rows.count == 2 && rows[0].id == "u")
        check(rows[0].body == "<script>alert(1)</script>")
        check(rows[1].body == "**收到**" && !rows[1].body.contains("private reasoning"))
        check(rows[1].tools[0].images.count == 1 && !rows[1].tools[0].details.contains("secret"))
        check(ChatMessage.parse([["id": "e", "type": "idle", "error": ["message": "模型不可用"]]])[0].error == "模型不可用")
        check(ModelChoice(["id": "deepseek-flash", "providerID": "deepseek", "settings": ["apiKey": "private"]]).id == "deepseek/deepseek-flash")
        let headings = MarkdownDocument.parse("# One\n\n## Two\n\n### Three\n\n#### Four\n\n##### Five\n\n###### Six\n\nSetext\n======")
        check(headings.compactMap { if case .heading(let level) = $0.kind { return level }; return nil } == [1, 2, 3, 4, 5, 6, 1])

        let inline = MarkdownDocument.parse("**粗体** *斜体* ~~删除~~ `code`")[0].content
        let styles = inline.runs.compactMap(\.inlinePresentationIntent)
        check(styles.contains { $0.contains(.stronglyEmphasized) } && styles.contains { $0.contains(.emphasized) } && styles.contains { $0.contains(.strikethrough) } && styles.contains { $0.contains(.code) })

        let nested = MarkdownDocument.parse("- first\n  - nested\n- second")
        check(nested[0].kind == .unorderedList && nested[0].children.count == 2 && nested[0].children[0].children.contains { $0.kind == .unorderedList })

        let ordered = MarkdownDocument.parse("3. third\n4. fourth")[0]
        check(ordered.kind == .orderedList && ordered.children.map(\.kind) == [.item(3, checked: nil), .item(4, checked: nil)])

        let quote = MarkdownDocument.parse("> **引用**\n>\n> second")[0]
        check(quote.kind == .quote && quote.children.count == 2 && quote.plainText == "引用\nsecond")

        let code = MarkdownDocument.parse("```swift\nlet value = 1\n\nprint(value)\n```")[0]
        check(code.kind == .code("swift") && code.plainText == "let value = 1\n\nprint(value)\n")

        let table = MarkdownDocument.parse("| Name | Middle | Count |\n| :--- | :---: | ---: |\n| One | M | **2** |")[0]
        check(table.kind == .table([.leading, .center, .trailing]) && table.children.count == 2 && table.children[0].kind == .row(header: true) && table.children[1].children[2].plainText == "2")

        let emptyCell = MarkdownDocument.parse("| A | B | C |\n| --- | --- | --- |\n| one | | three |")[0].children[1].children
        check(emptyCell.count == 3 && emptyCell[1].kind == .cell(1) && emptyCell[1].plainText.isEmpty && emptyCell[2].plainText == "three")

        let tasks = MarkdownDocument.parse("- [x] **完成**\n- [ ] 待办")[0].children
        check(tasks.map(\.kind) == [.item(1, checked: true), .item(2, checked: false)] && tasks[0].plainText == "完成" && tasks[0].children[0].content.runs.contains { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true })

        let breaks = MarkdownDocument.parse("before  \nafter\n\n---")
        check(breaks[0].plainText == "before\nafter" && breaks.last?.kind == .rule)

        let links = MarkdownDocument.parse("[safe](https://example.com) [unsafe](javascript:alert)\n\n![预览](https://example.com/photo.png)")
        let urls = links.flatMap { $0.content.runs.compactMap(\.link) }
        check(urls.count == 2 && urls.allSatisfy(MarkdownDocument.allowedURL) && links[1].plainText == "图片：预览")

        let partial = MarkdownDocument.parse("First step\n\nSecond")
        let completed = MarkdownDocument.parse("First step\n\nSecond step\n\nThird step")
        check(partial.map(\.id) == Array(completed.prefix(2)).map(\.id) && partial[0] == completed[0] && MarkdownDocument.parse("").isEmpty)

        let unclosed = MarkdownDocument.parse("~~~text\n  你好 `literal`\n")[0]
        check(unclosed.kind == .code("text") && unclosed.plainText == "  你好 `literal`\n" && !MarkdownDocument.allowedURL(URL(string: "file:///tmp/example")!))
        precondition(checks == 21)
        print("\(checks) native model checks passed")
    }
}
