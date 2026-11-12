import SwiftUI

@MainActor
struct SessionsView: View {
    @EnvironmentObject private var store: ChatStore

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button { store.showingSettings = true } label: {
                        ConnectionSummary(connected: store.connected, connecting: store.connecting)
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("打开连接设置")
                }

                if store.sessions.isEmpty {
                    Section {
                        ConversationListEmpty(
                            searching: !store.search.isEmpty,
                            connected: store.connected,
                            onStart: { store.open(nil) },
                            onClear: { store.search = "" }
                        )
                    }
                    .listRowBackground(Color.clear)
                } else {
                    SessionSections(
                        sessions: store.sessions, models: store.models,
                        searching: !store.search.isEmpty,
                        onOpen: { store.open($0) }
                    )
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("BridgeChat")
            .searchable(text: $store.search, placement: searchPlacement, prompt: "搜索对话")
            .accessibilityIdentifier("sessions.list")
            .task(id: store.search) {
#if targetEnvironment(simulator)
                if SimulatorPreview.route != nil { return }
#endif
                do { try await Task.sleep(nanoseconds: 250_000_000) }
                catch { return }
                if !Task.isCancelled && store.connected { await store.loadSessions() }
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
                    .accessibilityIdentifier("conversation.new")
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

    private var searchPlacement: SearchFieldPlacement {
#if BRIDGECHAT_IOS26
        if #available(iOS 26.0, *) { return .automatic }
#endif
        return .navigationBarDrawer(displayMode: .always)
    }
}

private struct ConnectionSummary: View {
    let connected: Bool
    let connecting: Bool

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "network")
                .font(.title3)
                .foregroundStyle(Color.accentColor)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text("OpenCode").font(.body.weight(.medium))
                Label(
                    connecting ? "正在连接…" : connected ? "已连接" : "点此连接服务",
                    systemImage: connected ? "checkmark.circle.fill" : "circle.dotted"
                )
                .font(.footnote)
                .foregroundStyle(connected ? Color.green : Color.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if connecting { ProgressView() }
            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
                .accessibilityHidden(true)
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

private struct SessionSections: View {
    let sessions: [ChatSession]
    let models: [ModelChoice]
    let searching: Bool
    let onOpen: (ChatSession) -> Void

    private var active: [ChatSession] { sessions.filter { $0.active } }
    private var recent: [ChatSession] { sessions.filter { !$0.active } }

    var body: some View {
        if searching {
            Section("搜索结果") { rows(sessions) }
        } else {
            if !active.isEmpty {
                Section("进行中") { rows(active) }
            }
            if !recent.isEmpty {
                Section("最近对话") { rows(recent) }
            }
        }
    }

    private func rows(_ values: [ChatSession]) -> some View {
        ForEach(values) { session in
            Button { onOpen(session) } label: {
                SessionRow(
                    session: session,
                    modelName: models.first(where: { $0.id == session.model?.id })?.name
                        ?? session.model?.name ?? "继续对话"
                )
            }
            .buttonStyle(.plain)
        }
    }
}

private struct SessionRow: View {
    let session: ChatSession
    let modelName: String
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            let layout = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
                : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 12))
            layout {
                Text(session.title)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(typeSize.isAccessibilitySize ? nil : 2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                SessionTimestamp(updated: session.updated)
            }
            HStack(spacing: 6) {
                if session.active { ProgressView().controlSize(.mini).accessibilityHidden(true) }
                Text(session.active ? "正在处理" : modelName)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .lineLimit(typeSize.isAccessibilitySize ? nil : 1)
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.tertiary)
                    .accessibilityHidden(true)
            }
        }
        .padding(.vertical, 8)
        .frame(minHeight: 44, alignment: .leading)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

private struct SessionTimestamp: View {
    let updated: Double

    var body: some View {
        Group {
            if updated > 0 {
                let date = Date(timeIntervalSince1970: updated / 1000)
                if Calendar.current.isDateInToday(date) {
                    Text(date, format: .dateTime.hour().minute())
                } else if Calendar.current.isDateInYesterday(date) {
                    Text("昨天")
                } else {
                    Text(date, format: .dateTime.month().day())
                }
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: true, vertical: false)
    }
}

private struct ConversationListEmpty: View {
    let searching: Bool
    let connected: Bool
    let onStart: () -> Void
    let onClear: () -> Void

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: searching ? "magnifyingglass" : "bubble.left.and.bubble.right")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(searching ? "没有找到对话" : "开始一段对话")
                .font(.title2.weight(.semibold))
            Text(searching ? "试试其他关键词。" : connected ? "聊个想法，或交给 OpenCode 一件事。" : "先连接 OpenCode，再开始对话。")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button(searching ? "查看最近对话" : "新对话", action: searching ? onClear : onStart)
                .buttonStyle(.bordered)
                .controlSize(.large)
                .disabled(!searching && !connected)
        }
        .padding(.vertical, 36)
        .frame(maxWidth: .infinity)
    }
}
