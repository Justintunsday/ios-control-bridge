import SwiftUI

@MainActor
struct ChatView: View {
    @EnvironmentObject private var store: ChatStore
    @State private var following = true
    @State private var permission: PermissionRequest?

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 28) {
                    if store.messages.isEmpty { NewConversationView() }
                    if store.hasEarlier {
                        Button("载入更早的消息") {
                            following = false
                            Task { await store.earlier() }
                        }
                        .font(.footnote)
                        .frame(maxWidth: .infinity, minHeight: 44)
                    }
                    ForEach(store.messages) { message in
                        MessageView(message: message).equatable().id(message.id)
                    }
                    Color.clear.frame(height: 1).id("latest")
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 24)
                .frame(maxWidth: 720)
                .frame(maxWidth: .infinity)
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
                            .frame(minHeight: 32)
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
                ConversationTitle(title: store.selected?.title ?? "新对话", active: store.active)
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
                    Image(systemName: "ellipsis")
                }
                .accessibilityLabel("对话操作")
            }
        }
        .modifier(ChatComposerBar(controls:
            VStack(spacing: 0) {
                if let first = store.permissions.first {
                    Button { permission = first } label: {
                        Label("需要你的确认，查看操作", systemImage: "hand.raised")
                            .font(.footnote)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }
                    .padding(.horizontal, 20)
                }
                ComposerView(onSend: { following = true })
            }
        ))
        .sheet(isPresented: $store.showingModels) {
            ModelPickerView()
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
        .sheet(item: $permission) { PermissionView(request: $0) }
        .onAppear {
#if targetEnvironment(simulator)
            if SimulatorPreview.route != nil { return }
#endif
            store.beginPolling()
        }
        .onDisappear { store.pause() }
    }
}

private struct ConversationTitle: View {
    let title: String
    let active: Bool

    var body: some View {
        VStack(spacing: 2) {
            Text(title).font(.headline).lineLimit(1)
            Text(active ? "正在处理" : "OpenCode")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }
}

@MainActor
private struct NewConversationView: View {
    @EnvironmentObject private var store: ChatStore

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            VStack(alignment: .leading, spacing: 12) {
                Image(systemName: "bubble.left.and.bubble.right")
                    .font(.largeTitle)
                    .foregroundStyle(Color.accentColor)
                    .accessibilityHidden(true)
                Text("有什么想一起做的？")
                    .font(.title.weight(.semibold))
                Text("从一个想法开始，也可以直接交代一件事。")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
            VStack(spacing: 0) {
                ConversationSuggestion(
                    title: "整理一个想法", subtitle: "把想法变成清晰的下一步", symbol: "text.alignleft"
                ) { store.draft = "帮我把这个想法整理成一个清晰的计划。"; store.saveDraft() }
                Divider().padding(.leading, 48)
                ConversationSuggestion(
                    title: "看看当前屏幕", subtitle: "了解手机上正在显示什么", symbol: "iphone"
                ) {
                    store.draft = "请使用 ios-computer-use skill，查看手机当前屏幕并告诉我你看到了什么。只查看，不进行点击。"
                    store.saveDraft()
                }
            }
            .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 20))
        }
        .padding(.vertical, 24)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct ConversationSuggestion: View {
    let title: String
    let subtitle: String
    let symbol: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: symbol)
                    .font(.body)
                    .foregroundStyle(Color.accentColor)
                    .frame(width: 24)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 5) {
                    Text(title).font(.body.weight(.medium)).foregroundStyle(.primary)
                    Text(subtitle).font(.footnote).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(minHeight: 44, alignment: .center)
            .padding(16)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint("将提示填入输入框")
    }
}
