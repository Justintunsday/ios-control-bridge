import SwiftUI
import UIKit

@main
@MainActor
struct BridgeChatApp: App {
    @StateObject private var store = ChatStore()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            SessionsView()
                .environmentObject(store)
                .tint(.blue)
                .task {
#if targetEnvironment(simulator)
                    if SimulatorPreview.configure(store) { return }
#endif
                    await store.connect()
                }
                .onChange(of: scenePhase) { phase in
#if targetEnvironment(simulator)
                    if SimulatorPreview.route != nil { return }
#endif
                    if phase == .active {
                        if store.showingChat {
                            store.beginPolling()
                        } else {
                            Task { await store.connect() }
                        }
                    } else {
                        store.pause()
                    }
                }
        }
    }
}

@MainActor
struct SessionsView: View {
    @EnvironmentObject private var store: ChatStore

    var body: some View {
        NavigationStack {
            List {
                Button { store.showingSettings = true } label: {
                    ConnectionCard()
                }
                .buttonStyle(.plain)
                .listRowSeparator(.hidden)
                .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 16, trailing: 16))

                if store.sessions.isEmpty {
                    emptyState
                        .listRowSeparator(.hidden)
                } else {
                    Section {
                        ForEach(store.sessions) { session in
                            Button { store.open(session) } label: {
                                SessionRow(session: session)
                            }
                            .buttonStyle(.plain)
                            .listRowInsets(EdgeInsets(top: 10, leading: 16, bottom: 10, trailing: 16))
                        }
                    } header: {
                        Text(store.search.isEmpty ? "最近对话" : "搜索结果")
                            .textCase(nil)
                    }
                }
            }
            .listStyle(.plain)
            .navigationTitle("对话")
            .searchable(text: $store.search, placement: .navigationBarDrawer(displayMode: .always), prompt: "搜索对话")
            .task(id: store.search) {
#if targetEnvironment(simulator)
                if SimulatorPreview.route != nil { return }
#endif
                try? await Task.sleep(nanoseconds: 250_000_000)
                if !Task.isCancelled && store.connected {
                    await store.loadSessions()
                }
            }
            .refreshable { await store.connect() }
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button { store.showingSettings = true } label: {
                        Image(systemName: "gearshape")
                    }
                    .accessibilityLabel("连接设置")
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { store.open(nil) } label: {
                        Image(systemName: "square.and.pencil")
                    }
                    .accessibilityLabel("新对话")
                    .disabled(!store.connected)
                }
            }
            .navigationDestination(isPresented: $store.showingChat) { ChatView() }
            .sheet(isPresented: $store.showingSettings) { ConnectionSettingsView() }
            .alert("提示", isPresented: Binding(
                get: { store.notice != nil },
                set: { if !$0 { store.notice = nil } }
            )) {
                Button("好") { store.notice = nil }
            } message: {
                Text(store.notice ?? "")
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            Image(systemName: store.search.isEmpty ? "bubble.left.and.bubble.right" : "magnifyingglass")
                .font(.largeTitle)
                .foregroundStyle(Color.accentColor)
            Text(store.search.isEmpty ? "从一句话开始" : "没有找到对话")
                .font(.title2.bold())
            Text(store.search.isEmpty ? "聊个想法，或交给 OpenCode 一件事。" : "试试其他关键词，或查看最近对话。")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            if store.search.isEmpty {
                Button("开始新对话") { store.open(nil) }
                    .buttonStyle(.borderedProminent)
                    .disabled(!store.connected)
            } else {
                Button("查看最近对话") { store.search = "" }
                    .buttonStyle(.bordered)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 36)
        .frame(maxWidth: .infinity)
    }
}

@MainActor
private struct ConnectionCard: View {
    @EnvironmentObject private var store: ChatStore

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "iphone")
                .font(.title2)
                .foregroundStyle(Color.accentColor)
            VStack(alignment: .leading, spacing: 3) {
                Text("OpenCode")
                    .font(.headline)
                    .foregroundStyle(.primary)
                Text(store.connecting ? "正在连接服务…" : store.connected ? "已连接，可以开始对话" : "连接服务后开始对话")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            if store.connecting {
                ProgressView()
            } else {
                Image(systemName: store.connected ? "checkmark.circle.fill" : "chevron.right")
                    .font(store.connected ? .body : .caption.weight(.semibold))
                    .foregroundStyle(store.connected ? Color.green : Color.secondary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint("打开连接设置")
    }
}

private struct SessionRow: View {
    let session: ChatSession
    @ScaledMetric(relativeTo: .body) private var iconSize: CGFloat = 36

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "text.bubble")
                .font(.body)
                .foregroundStyle(Color.accentColor)
                .frame(width: iconSize, height: iconSize)
                .background(Color.accentColor.opacity(0.10), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(session.title)
                    .font(.headline)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
                HStack(spacing: 5) {
                    if session.active {
                        ProgressView().controlSize(.mini)
                    }
                    Text(session.active ? "正在回复…" : session.model?.name ?? "继续对话")
                        .font(.footnote)
                        .foregroundStyle(session.active ? Color.accentColor : Color.secondary)
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            VStack(alignment: .trailing, spacing: 8) {
                timestamp
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Image(systemName: "chevron.right")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.tertiary)
            }
            .layoutPriority(1)
        }
        .frame(minHeight: 54)
        .contentShape(Rectangle())
        .alignmentGuide(.listRowSeparatorLeading) { $0[.leading] + iconSize + 12 }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var timestamp: some View {
        let date = Date(timeIntervalSince1970: session.updated / 1000)
        if Calendar.current.isDateInToday(date) {
            Text(date, format: .dateTime.hour().minute())
        } else if Calendar.current.isDateInYesterday(date) {
            Text("昨天")
        } else {
            Text(date, format: .dateTime.month().day())
        }
    }
}

@MainActor
struct ChatView: View {
    @EnvironmentObject private var store: ChatStore
    @State private var following = true
    @State private var permission: PermissionRequest?

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 24) {
                    if store.messages.isEmpty {
                        EmptyConversationView()
                    }
                    if store.hasEarlier {
                        Button("载入更早的消息") {
                            following = false
                            Task { await store.earlier() }
                        }
                        .font(.footnote)
                        .frame(maxWidth: .infinity)
                    }
                    ForEach(store.messages) { message in
                        MessageView(message: message).id(message.id)
                    }
                    Color.clear.frame(height: 1).id("latest")
                }
                .padding()
            }
            .scrollDismissesKeyboard(.interactively)
            .simultaneousGesture(DragGesture(minimumDistance: 16).onChanged { _ in following = false })
            .onChange(of: store.revision) { _ in
                if following { proxy.scrollTo("latest", anchor: .bottom) }
            }
            .overlay(alignment: .bottomTrailing) {
                if !following && !store.messages.isEmpty {
                    Button {
                        following = true
                        withAnimation { proxy.scrollTo("latest", anchor: .bottom) }
                    } label: {
                        Label("最新回复", systemImage: "arrow.down")
                    }
                    .font(.footnote)
                    .modifier(FloatingReplyAppearance())
                    .padding()
                }
            }
        }
        .background(Color(.systemBackground))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                Button { store.showingModels = true } label: {
                    VStack(spacing: 2) {
                        Text(store.selected?.title ?? "新对话")
                            .font(.headline)
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                        HStack(spacing: 3) {
                            Text(store.currentModel?.name ?? "选择模型")
                            Image(systemName: "chevron.down").font(.system(size: 8, weight: .semibold))
                        }
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    }
                }
                .buttonStyle(.plain)
                .disabled(store.active)
                .accessibilityLabel("选择模型，当前为" + (store.currentModel?.name ?? "未选择"))
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                Menu {
                    Button { store.showingModels = true } label: {
                        Label("选择模型", systemImage: "slider.horizontal.3")
                    }
                    .disabled(store.active)
                    Button { Task { await store.refresh() } } label: {
                        Label("刷新对话", systemImage: "arrow.clockwise")
                    }
                    if store.active {
                        Button(role: .destructive) { Task { await store.stop() } } label: {
                            Label("停止任务", systemImage: "stop.circle")
                        }
                        .disabled(store.stopping)
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
                .accessibilityLabel("对话操作")
            }
        }
        .modifier(ChatComposerBar(controls:
            VStack(spacing: 0) {
                if let first = store.permissions.first {
                    HStack(spacing: 8) {
                        Label("需要你的确认", systemImage: "hand.raised")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Button("查看操作") { permission = first }
                    }
                    .font(.footnote)
                    .padding(.horizontal)
                    .padding(.top, 10)
                }
                ComposerView(onSend: { following = true })
            }
        ))
        .sheet(isPresented: $store.showingModels) { ModelPickerView() }
        .sheet(item: $permission) { PermissionView(request: $0) }
        .onAppear { store.beginPolling() }
        .onDisappear { store.pause() }
    }
}

@MainActor
private struct EmptyConversationView: View {
    @EnvironmentObject private var store: ChatStore

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.largeTitle)
                .foregroundStyle(Color.accentColor)
                .padding(18)
                .background(Color.accentColor.opacity(0.10), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            Text("从一句话开始")
                .font(.title2.bold())
            Text("聊个想法，或交给 OpenCode 一件事。")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            VStack(spacing: 10) {
                suggestion("打个招呼", symbol: "hand.wave", draft: "你好，请确认你能收到我的消息。")
                suggestion("看看当前屏幕", symbol: "iphone", draft: "请使用 ios-computer-use skill，查看手机当前屏幕并告诉我你看到了什么。只查看，不进行点击。")
            }
            .padding(.top, 6)
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 16)
        .padding(.vertical, 36)
    }

    private func suggestion(_ title: String, symbol: String, draft: String) -> some View {
        Button {
            store.draft = draft
            store.saveDraft()
        } label: {
            Label(title, systemImage: symbol)
                .font(.body)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .padding(.horizontal, 16)
                .padding(.vertical, 2)
                .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .buttonStyle(.plain)
        .foregroundStyle(Color.accentColor)
    }
}

@MainActor
private struct ComposerView: View {
    @EnvironmentObject private var store: ChatStore
    let onSend: () -> Void

    private var canSend: Bool {
        store.connected && !store.sending && !store.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if store.uncertain {
                Text("消息结果待确认，输入已保留。请先刷新会话，再决定是否重发。")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
            if store.active {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.mini)
                    Text("正在处理，可继续补充要求")
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button(role: .destructive) { Task { await store.stop() } } label: {
                        Text(store.stopping ? "正在停止…" : "停止任务")
                    }
                    .disabled(store.stopping)
                }
                .font(.caption)
            }
            inputRow
        }
        .padding(.horizontal)
        .padding(.vertical, 12)
    }

    private var draftField: some View {
        TextField(store.active ? "补充要求，或问问进展…" : "发消息给 OpenCode…", text: $store.draft, axis: .vertical)
            .font(.body)
            .lineLimit(1...5)
            .onChange(of: store.draft) { _ in store.saveDraft() }
    }

    @ViewBuilder
    private var inputRow: some View {
#if BRIDGECHAT_IOS26
        if #available(iOS 26.0, *) {
            GlassEffectContainer(spacing: 12) {
                HStack(alignment: .bottom, spacing: 12) {
                    draftField
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 26, style: .continuous))
                    Button(action: send) {
                        Group {
                            if store.sending {
                                ProgressView()
                            } else {
                                Image(systemName: "arrow.up").font(.body.weight(.semibold))
                            }
                        }
                        .frame(minWidth: 22, minHeight: 22)
                    }
                    .buttonStyle(.glassProminent)
                    .buttonBorderShape(.circle)
                    .controlSize(.large)
                    .disabled(!canSend)
                    .accessibilityLabel(store.active ? "发送追问" : "发送消息")
                }
            }
        } else {
            legacyInputRow
        }
#else
        legacyInputRow
#endif
    }

    private var legacyInputRow: some View {
        HStack(alignment: .bottom, spacing: 4) {
            draftField.padding(.leading, 14).padding(.vertical, 11)
            Button(action: send) {
                Group {
                    if store.sending {
                        ProgressView()
                    } else {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 30))
                            .foregroundStyle(canSend ? Color.accentColor : Color(.tertiaryLabel))
                    }
                }
                .frame(minWidth: 44, minHeight: 44)
            }
            .buttonStyle(.borderless)
            .disabled(!canSend)
            .accessibilityLabel(store.active ? "发送追问" : "发送消息")
        }
        .padding(.trailing, 2)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
    }

    private func send() {
        onSend()
        Task { await store.send() }
    }
}

private struct MessageView: View {
    let message: ChatMessage

    var body: some View {
        VStack(alignment: message.user ? .trailing : .leading, spacing: 10) {
            if message.user {
                HStack {
                    Spacer(minLength: 36)
                    Text(message.body)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .foregroundStyle(.white)
                        .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                        .textSelection(.enabled)
                }
            } else {
                if !message.body.isEmpty {
                    Label("OpenCode", systemImage: "sparkles")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    MarkdownMessage(text: message.body)
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

private struct MarkdownMessage: View {
    let text: String
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                if block.code { ScrollView(.horizontal) { Text(block.body).font(.system(.footnote, design: .monospaced)).padding(12) }.background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 10)) }
                else if block.heading { Text(inline(block.body)).font(.headline) }
                else { Text(inline(block.body)).font(.body).lineSpacing(4).fixedSize(horizontal: false, vertical: true) }
            }
        }.environment(\.openURL, OpenURLAction { url in ["http", "https"].contains(url.scheme?.lowercased() ?? "") ? .systemAction : .discarded })
    }
    private struct Block { var body: String; let code: Bool; let heading: Bool }
    private var blocks: [Block] {
        var result: [Block] = []; var code = false; var lines: [String] = []
        func append() { if !lines.isEmpty { result.append(Block(body: lines.joined(separator: "\n"), code: code, heading: false)); lines = [] } }
        for line in text.components(separatedBy: "\n") {
            if line.hasPrefix("```") { append(); code.toggle(); continue }
            if !code && line.trimmingCharacters(in: .whitespaces).isEmpty { append(); continue }
            if !code && line.range(of: "^#{1,4} ", options: .regularExpression) != nil { append(); result.append(Block(body: line.replacingOccurrences(of: "^#{1,4} ", with: "", options: .regularExpression), code: false, heading: true)); continue }
            lines.append(line)
        }
        append(); return result
    }
    private func inline(_ string: String) -> AttributedString { (try? AttributedString(markdown: string, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(string) }
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
            ForEach(Array(step.images.enumerated()), id: \.offset) { _, uri in
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
    private var image: UIImage? { uri.firstIndex(of: ",").flatMap { Data(base64Encoded: String(uri[uri.index(after: $0)...])) }.flatMap(UIImage.init(data:)) }
    var body: some View {
        NavigationStack {
            GeometryReader { frame in
                ScrollView([.horizontal, .vertical]) {
                    if let image = image { Image(uiImage: image).resizable().scaledToFit().frame(width: frame.size.width * scale, height: frame.size.height * scale).accessibilityLabel("OpenCode 返回的手机截图") }
                    else { Text("图片无法显示").foregroundStyle(.secondary) }
                }.gesture(MagnificationGesture().onChanged { scale = min(5, max(1, previous * $0)) }.onEnded { _ in previous = scale })
            }.background(Color.black).navigationTitle("手机截图").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } } }
        }.preferredColorScheme(.dark)
    }
}

@MainActor
private struct ConnectionSettingsView: View {
    @EnvironmentObject private var store: ChatStore
    @Environment(\.dismiss) private var dismiss
    @State private var url = ""
    @State private var username = "opencode"
    @State private var password = ""
    @State private var saving = false
    @State private var error = ""

    private var passwordPrompt: String {
        store.connection?.url == url && store.connection?.password() != nil ? "已保存，留空保留" : "服务密码"
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    LabeledContent("服务地址") {
                        TextField("http://localhost:4097", text: $url)
                            .keyboardType(.URL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .multilineTextAlignment(.trailing)
                            .accessibilityLabel("服务地址")
                    }
                    LabeledContent("用户名") {
                        TextField("opencode", text: $username)
                            .textContentType(.username)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .multilineTextAlignment(.trailing)
                            .accessibilityLabel("用户名")
                    }
                    LabeledContent("服务密码") {
                        SecureField(passwordPrompt, text: $password)
                            .textContentType(.password)
                            .multilineTextAlignment(.trailing)
                            .accessibilityLabel("服务密码")
                    }
                } header: {
                    Text("OpenCode 服务")
                } footer: {
                    Text("密码安全保存在本机 Keychain。连接成功后即可查看对话。")
                }
                .disabled(saving)

                if !error.isEmpty {
                    Section {
                        Label(error, systemImage: "exclamationmark.circle")
                            .foregroundStyle(.red)
                            .accessibilityLabel("连接失败。" + error)
                    }
                } else if store.connected && store.connection?.url == url {
                    Section {
                        Label("服务已连接", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                    }
                }

                Section("关于") {
                    LabeledContent("版本", value: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "")
                    LabeledContent("兼容服务", value: "OpenCode 2")
                }
            }
            .navigationTitle("连接设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { dismiss() } label: {
                        ToolbarActionLabel("取消", symbol: "xmark")
                    }
                        .disabled(saving)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        Task { await save() }
                    } label: {
                        if saving {
                            ProgressView()
                        } else {
                            ToolbarActionLabel("连接", symbol: "checkmark")
                        }
                    }
                    .accessibilityLabel("保存并连接")
                    .disabled(saving || url.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .interactiveDismissDisabled(saving)
            .onAppear {
                url = store.connection?.url ?? ""
                username = store.connection?.username ?? "opencode"
            }
            .onDisappear { password = "" }
        }
    }

    private func save() async {
        saving = true
        error = ""
        defer { saving = false }
        do {
            try await store.saveConnection(url: url, username: username, password: password)
            password = ""
        } catch {
            self.error = error.localizedDescription
        }
    }
}

@MainActor
private struct ModelPickerView: View {
    @EnvironmentObject private var store: ChatStore
    @Environment(\.dismiss) private var dismiss
    @State private var choosing = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    if store.models.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("暂无可用模型").font(.headline)
                            Text("请检查已连接服务的模型配置。")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 8)
                    }
                    ForEach(store.models) { model in
                        Button {
                            choosing = true
                            Task {
                                await store.choose(model)
                                choosing = false
                            }
                        } label: {
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(model.name)
                                        .font(.body)
                                        .foregroundStyle(.primary)
                                    Text(model.providerID + (model.seesImages ? " · 支持图片" : ""))
                                        .font(.footnote)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                if store.currentModel?.id == model.id {
                                    Image(systemName: "checkmark")
                                        .font(.body.weight(.semibold))
                                        .foregroundStyle(Color.accentColor)
                                }
                            }
                            .padding(.vertical, 4)
                            .contentShape(Rectangle())
                        }
                        .disabled(choosing || store.active)
                    }
                } header: {
                    Text("选择用于这次对话的模型")
                } footer: {
                    Text(store.active ? "当前任务结束后可切换模型。" : "模型列表由已连接的 OpenCode 服务提供。")
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("选择模型")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button { dismiss() } label: {
                        ToolbarActionLabel("完成", symbol: "checkmark")
                    }
                }
            }
        }
    }
}

@MainActor
private struct PermissionView: View {
    let request: PermissionRequest
    @EnvironmentObject private var store: ChatStore
    @Environment(\.dismiss) private var dismiss
    @State private var sending = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Label("请确认这次操作", systemImage: "hand.raised")
                        .font(.headline)
                    Text(request.title.isEmpty ? "OpenCode 需要你的确认后继续。" : request.title)
                }
                Section("操作详情") {
                    Text(request.detail)
                        .font(.system(.footnote, design: .monospaced))
                        .textSelection(.enabled)
                }
                Section {
                    Button("本次允许") { reply(true) }
                    Button("拒绝", role: .destructive) { reply(false) }
                }
                .disabled(sending)
            }
            .navigationTitle("确认操作")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { dismiss() } label: {
                        ToolbarActionLabel("关闭", symbol: "xmark")
                    }
                    .disabled(sending)
                }
            }
            .interactiveDismissDisabled(sending)
        }
    }

    private func reply(_ allow: Bool) {
        sending = true
        Task {
            await store.reply(request, allow: allow)
            sending = false
            dismiss()
        }
    }
}
