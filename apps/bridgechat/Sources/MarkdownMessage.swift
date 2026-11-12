import SwiftUI
import UIKit

struct MarkdownMessage: View, Equatable {
    let text: String
    var fillsWidth = true

    var body: some View {
        MarkdownBlocks(blocks: MarkdownDocument.parse(text), fillsWidth: fillsWidth)
            .textSelection(.enabled)
            .environment(\.openURL, OpenURLAction { url in
                MarkdownDocument.allowedURL(url) ? .systemAction : .discarded
            })
    }
}

private struct MarkdownBlocks: View {
    let blocks: [MarkdownBlock]
    var fillsWidth = true

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(blocks) { MarkdownBlockView(block: $0) }
        }
        .frame(maxWidth: fillsWidth ? .infinity : nil, alignment: .leading)
    }
}

private struct MarkdownBlockView: View {
    let block: MarkdownBlock

    @ViewBuilder
    var body: some View {
        switch block.kind {
        case .heading(let level):
            Text(block.attributedText)
                .font(headingFont(level))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
        case .code(let language):
            MarkdownCodeBlock(code: block.plainText, language: language)
        case .quote:
            MarkdownBlocks(blocks: block.children)
                .foregroundStyle(.secondary)
                .padding(.leading, 16)
                .overlay(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2).fill(.tertiary).frame(width: 3)
                }
        case .orderedList:
            MarkdownList(items: block.children, ordered: true)
        case .unorderedList:
            MarkdownList(items: block.children, ordered: false)
        case .table(let columns):
            MarkdownTable(rows: block.children, alignments: columns)
        case .rule:
            Divider().padding(.vertical, 4)
        case .paragraph, .item, .row, .cell:
            if block.children.isEmpty {
                Text(block.content).font(.body).lineSpacing(4).fixedSize(horizontal: false, vertical: true)
            } else {
                MarkdownBlocks(blocks: block.children)
            }
        }
    }

    private func headingFont(_ level: Int) -> Font {
        switch level {
        case 1: return .title2.weight(.semibold)
        case 2: return .title3.weight(.semibold)
        case 3: return .headline
        default: return .subheadline.weight(.semibold)
        }
    }
}

private struct MarkdownList: View {
    let items: [MarkdownBlock]
    let ordered: Bool
    @ScaledMetric(relativeTo: .body) private var markerWidth: CGFloat = 20

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(items) { item in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    marker(item)
                        .frame(minWidth: markerWidth, alignment: .leading)
                        .accessibilityHidden(true)
                    MarkdownBlocks(blocks: item.children)
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(itemLabel(item))
            }
        }
    }

    private func ordinal(_ item: MarkdownBlock) -> Int {
        if case .item(let value, _) = item.kind { return value }
        return 1
    }

    @ViewBuilder
    private func marker(_ item: MarkdownBlock) -> some View {
        HStack(spacing: 6) {
            if ordered { Text("\(ordinal(item)).") }
            if case .item(_, let checked?) = item.kind {
                Image(systemName: checked ? "checkmark.square.fill" : "square")
                    .foregroundStyle(checked ? Color.accentColor : Color.secondary)
            } else if !ordered {
                Text("•")
            }
        }
        .font(.body)
    }

    private func itemLabel(_ item: MarkdownBlock) -> String {
        if case .item(_, let checked?) = item.kind { return checked ? "已完成项" : "待办项" }
        return ordered ? "第 \(ordinal(item)) 项" : "列表项"
    }
}

private struct MarkdownCodeBlock: View {
    let code: String
    let language: String?
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(language.flatMap { $0.isEmpty ? nil : $0 } ?? "代码")
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
                Spacer()
                Button {
                    UIPasteboard.general.string = code
                    copied = true
                } label: {
                    Label(copied ? "已复制" : "复制", systemImage: copied ? "checkmark" : "doc.on.doc")
                        .font(.caption)
                        .frame(minHeight: 44)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(copied ? "代码已复制" : "复制代码")
            }
            .padding(.horizontal, 14)
            Divider()
            ScrollView(.horizontal) {
                Text(verbatim: code)
                    .font(.system(.footnote, design: .monospaced))
                    .textSelection(.enabled)
                    .padding(14)
            }
        }
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
        .task(id: copied) {
            guard copied else { return }
            do { try await Task.sleep(nanoseconds: 1_500_000_000) }
            catch { return }
            copied = false
        }
    }
}

private struct MarkdownTable: View {
    let rows: [MarkdownBlock]
    let alignments: [MarkdownBlock.ColumnAlignment]
    @ScaledMetric(relativeTo: .body) private var columnWidth: CGFloat = 140

    var body: some View {
        ScrollView(.horizontal) {
            Grid(alignment: .topLeading, horizontalSpacing: 0, verticalSpacing: 0) {
                ForEach(rows) { row in
                    GridRow(alignment: .top) {
                        ForEach(row.children) { cell in
                            Text(cell.attributedText)
                                .font(header(row) ? .headline : .body)
                                .multilineTextAlignment(textAlignment(cell))
                                .frame(width: columnWidth, alignment: alignment(cell))
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(12)
                                .accessibilityAddTraits(header(row) ? .isHeader : [])
                        }
                    }
                    .background(header(row) ? Color(.secondarySystemBackground) : Color.clear)
                    .overlay(alignment: .bottom) { Divider() }
                }
            }
        }
        .accessibilityLabel("表格")
    }

    private func header(_ row: MarkdownBlock) -> Bool {
        if case .row(let value) = row.kind { return value }
        return false
    }

    private func column(_ cell: MarkdownBlock) -> MarkdownBlock.ColumnAlignment {
        if case .cell(let index) = cell.kind, alignments.indices.contains(index) { return alignments[index] }
        return .leading
    }

    private func alignment(_ cell: MarkdownBlock) -> Alignment {
        switch column(cell) {
        case .leading: return .leading
        case .center: return .center
        case .trailing: return .trailing
        }
    }

    private func textAlignment(_ cell: MarkdownBlock) -> TextAlignment {
        switch column(cell) {
        case .leading: return .leading
        case .center: return .center
        case .trailing: return .trailing
        }
    }
}
