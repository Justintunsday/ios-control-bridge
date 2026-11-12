import Foundation

struct MarkdownBlock: Identifiable, Equatable {
    enum Kind: Equatable {
        case paragraph
        case heading(Int)
        case code(String?)
        case quote
        case unorderedList
        case orderedList
        case item(Int, checked: Bool?)
        case table([ColumnAlignment])
        case row(header: Bool)
        case cell(Int)
        case rule
    }

    enum ColumnAlignment: Equatable { case leading, center, trailing }

    let id: Int
    let kind: Kind
    let content: AttributedString
    let children: [MarkdownBlock]

    var attributedText: AttributedString {
        if children.isEmpty { return content }
        var value = content
        for child in children {
            if !value.characters.isEmpty { value.append(AttributedString("\n")) }
            value.append(child.attributedText)
        }
        return value
    }

    var plainText: String { String(attributedText.characters) }
}

enum MarkdownDocument {
    /// Foundation supplies CommonMark/GFM block semantics; SwiftUI lays them out.
    static func parse(_ source: String) -> [MarkdownBlock] {
        guard !source.isEmpty else { return [] }
        let options = AttributedString.MarkdownParsingOptions(
            allowsExtendedAttributes: false, interpretedSyntax: .full, failurePolicy: .returnPartiallyParsedIfPossible
        )
        guard let parsed = try? AttributedString(markdown: source, options: options) else {
            return [plain(source)]
        }
        var roots: [Builder] = []
        var nodes: [Int: Builder] = [:]

        for run in parsed.runs {
            var parent: Builder?
            for component in (run.presentationIntent?.components ?? []).reversed() {
                let node: Builder
                if let existing = nodes[component.identity] {
                    node = existing
                } else {
                    node = Builder(id: component.identity, kind: kind(component.kind))
                    nodes[component.identity] = node
                    if let parent = parent { parent.children.append(node) }
                    else { roots.append(node) }
                }
                parent = node
            }
            if parent == nil {
                let node = Builder(id: -roots.count - 1, kind: .paragraph)
                roots.append(node)
                parent = node
            }
            var text = AttributedString(parsed[run.range])
            text.presentationIntent = nil
            if let url = run.link, !allowedURL(url) { text.link = nil }
            if let image = run.imageURL {
                let label = String(text.characters)
                text = AttributedString(label.isEmpty ? "图片" : "图片：" + label)
                if allowedURL(image) { text.link = image }
            }
            parent?.content.append(text)
        }
        if roots.isEmpty { return source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? [] : [plain(source)] }
        return roots.map { $0.freeze(depth: 0) }
    }

    static func allowedURL(_ url: URL) -> Bool {
        ["http", "https"].contains(url.scheme?.lowercased() ?? "") && url.host != nil
    }

    private static func plain(_ text: String) -> MarkdownBlock {
        MarkdownBlock(id: 0, kind: .paragraph, content: AttributedString(text), children: [])
    }

    private static func kind(_ intent: PresentationIntent.Kind) -> MarkdownBlock.Kind {
        switch intent {
        case .paragraph: return .paragraph
        case .header(let level): return .heading(level)
        case .codeBlock(let language): return .code(language)
        case .blockQuote: return .quote
        case .unorderedList: return .unorderedList
        case .orderedList: return .orderedList
        case .listItem(let ordinal): return .item(ordinal, checked: nil)
        case .table(let columns):
            return .table(columns.map { column in
                switch column.alignment {
                case .center: return .center
                case .right: return .trailing
                case .left: return .leading
                @unknown default: return .leading
                }
            })
        case .tableHeaderRow: return .row(header: true)
        case .tableRow: return .row(header: false)
        case .tableCell(let column): return .cell(column)
        case .thematicBreak: return .rule
        @unknown default: return .paragraph
        }
    }

    private final class Builder {
        let id: Int
        let kind: MarkdownBlock.Kind
        var content = AttributedString()
        var children: [Builder] = []

        init(id: Int, kind: MarkdownBlock.Kind) { self.id = id; self.kind = kind }

        func freeze(depth: Int) -> MarkdownBlock {
            if depth >= 24 {
                var text = content
                var pending = Array(children.reversed())
                while let child = pending.popLast() {
                    text.append(AttributedString("\n"))
                    text.append(child.content)
                    pending.append(contentsOf: child.children.reversed())
                }
                return MarkdownBlock(id: id, kind: .paragraph, content: text, children: [])
            }
            var values = children.map { $0.freeze(depth: depth + 1) }
            var finalKind = kind
            if case .table(let columns) = kind {
                values = values.map { row in
                    var cells: [Int: MarkdownBlock] = [:]
                    for cell in row.children {
                        if case .cell(let column) = cell.kind { cells[column] = cell }
                    }
                    let complete = columns.indices.map { column in
                        cells[column] ?? MarkdownBlock(id: -column - 1, kind: .cell(column), content: AttributedString(), children: [])
                    }
                    return MarkdownBlock(id: row.id, kind: row.kind, content: row.content, children: complete)
                }
            }
            if case .item(let ordinal, _) = kind, let first = values.first, first.kind == .paragraph {
                let prefix = String(first.content.characters.prefix(4)).lowercased()
                if prefix == "[x] " || prefix == "[ ] " {
                    var text = first.content
                    let end = text.characters.index(text.startIndex, offsetBy: 4)
                    text.removeSubrange(text.startIndex..<end)
                    values[0] = MarkdownBlock(id: first.id, kind: first.kind, content: text, children: first.children)
                    finalKind = .item(ordinal, checked: prefix == "[x] ")
                }
            }
            return MarkdownBlock(id: id, kind: finalKind, content: content, children: values)
        }
    }
}
