import SwiftUI
import UIKit

struct MessageView: View, Equatable {
    let message: ChatMessage

    var body: some View {
        VStack(alignment: message.user ? .trailing : .leading, spacing: 10) {
            if message.user {
                HStack {
                    Spacer(minLength: 36)
                    MarkdownMessage(text: message.body, fillsWidth: false)
                        .equatable()
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .foregroundStyle(.primary)
                        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 22))
                        .textSelection(.enabled)
                        .contextMenu {
                            Button { UIPasteboard.general.string = message.body } label: {
                                Label("复制原文", systemImage: "doc.on.doc")
                            }
                        }
                }
            } else {
                if !message.body.isEmpty {
                    HStack {
                        Label("OpenCode", systemImage: "sparkles")
                            .font(.caption.weight(.medium))
                        Spacer()
                        Button { UIPasteboard.general.string = message.body } label: {
                            Image(systemName: "doc.on.doc")
                                .font(.footnote)
                                .frame(minWidth: 44, minHeight: 44)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("复制回复")
                    }
                    .foregroundStyle(.secondary)
                    MarkdownMessage(text: message.body)
                        .equatable()
                        .textSelection(.enabled)
                        .contextMenu {
                            Button { UIPasteboard.general.string = message.body } label: {
                                Label("复制回复", systemImage: "doc.on.doc")
                            }
                        }
                }
                ForEach(message.tools) { ToolStepView(step: $0) }
                if !message.error.isEmpty {
                    Label(message.error, systemImage: "exclamationmark.circle")
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .textSelection(.enabled)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: message.user ? .trailing : .leading)
    }
}

private struct Picture: Identifiable {
    let id = UUID()
    let uri: String
}

private struct ToolStepView: View {
    let step: ToolStep
    @State private var expanded = false
    @State private var picture: Picture?

    private var status: String {
        step.failed ? "未完成" : step.finished ? "已完成" : "进行中"
    }

    private var symbol: String {
        step.failed ? "exclamationmark.circle.fill" : step.finished ? "checkmark.circle.fill" : "circle.dotted"
    }

    private var statusColor: Color {
        step.failed ? .red : step.finished ? .green : .accentColor
    }

    private var imageURIs: [String] {
        var seen = Set<String>()
        return step.images.filter { seen.insert($0).inserted }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            DisclosureGroup(isExpanded: $expanded) {
                if !step.details.isEmpty {
                    ScrollView(.horizontal) {
                        Text(step.details)
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                    }
                    .frame(maxHeight: 240)
                    .padding(.top, 6)
                } else {
                    Text("操作已返回。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: symbol).foregroundStyle(statusColor)
                    Text(step.name).foregroundStyle(.secondary)
                    Spacer(minLength: 4)
                    Text(status).foregroundStyle(.secondary)
                }
                .font(.footnote)
            }
            .tint(Color.secondary)
            ForEach(imageURIs, id: \.self) { uri in
                Button { picture = Picture(uri: uri) } label: {
                    Label("查看截图", systemImage: "photo")
                }
                .font(.footnote)
                .buttonStyle(.plain)
                .foregroundStyle(Color.accentColor)
            }
        }
        .padding(12)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .fullScreenCover(item: $picture) { ScreenshotView(uri: $0.uri) }
    }
}


private struct ScreenshotView: View {
    let uri: String
    @Environment(\.dismiss) private var dismiss
    @State private var scale: CGFloat = 1
    @State private var previous: CGFloat = 1
    @State private var image: UIImage?
    @State private var loading = true
    var body: some View {
        NavigationStack {
            GeometryReader { frame in
                ScrollView([.horizontal, .vertical]) {
                    if let image = image { Image(uiImage: image).resizable().scaledToFit().frame(width: frame.size.width * scale, height: frame.size.height * scale).accessibilityLabel("OpenCode 返回的手机截图") }
                    else if loading { ProgressView().accessibilityLabel("正在加载图片") }
                    else { Text("图片无法显示").foregroundStyle(.secondary) }
                }.gesture(MagnificationGesture().onChanged { scale = min(5, max(1, previous * $0)) }.onEnded { _ in previous = scale })
            }.background(Color.black).navigationTitle("手机截图").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } } }
        }
        .preferredColorScheme(.dark)
        .task(id: uri) {
            loading = true
            image = uri.firstIndex(of: ",")
                .flatMap { Data(base64Encoded: String(uri[uri.index(after: $0)...])) }
                .flatMap(UIImage.init(data:))
            loading = false
        }
    }
}

