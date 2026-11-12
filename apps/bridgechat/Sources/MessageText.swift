import Foundation

struct MessageTextBlock: Identifiable, Equatable {
    /// Source line anchors stay stable as a reply appends more text.
    let id: Int
    let body: String
    let code: Bool
    let heading: Bool
}

enum MessageText {
    static func blocks(_ text: String) -> [MessageTextBlock] {
        var result: [MessageTextBlock] = []
        var lines: [String] = []
        var code = false
        var start = 0

        func flush() {
            guard !lines.isEmpty else { return }
            result.append(MessageTextBlock(id: start, body: lines.joined(separator: "\n"), code: code, heading: false))
            lines.removeAll(keepingCapacity: true)
        }

        for (index, line) in text.components(separatedBy: "\n").enumerated() {
            if line.hasPrefix("```") {
                flush()
                code.toggle()
                continue
            }
            if !code && line.trimmingCharacters(in: .whitespaces).isEmpty {
                flush()
                continue
            }
            if !code, let prefix = line.range(of: "^#{1,4} ", options: .regularExpression) {
                flush()
                result.append(MessageTextBlock(id: index, body: String(line[prefix.upperBound...]), code: false, heading: true))
                continue
            }
            if lines.isEmpty { start = index }
            lines.append(line)
        }
        flush()
        return result
    }
}
