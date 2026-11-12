import SwiftUI

@MainActor
struct ComposerView: View {
    @EnvironmentObject private var store: ChatStore
    @Environment(\.dynamicTypeSize) private var typeSize
    @FocusState private var composing: Bool
    let onSend: () -> Void

    private var canSend: Bool {
        store.connected && !store.sending && !store.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    @ViewBuilder
    var body: some View {
#if BRIDGECHAT_IOS26
        if #available(iOS 26.0, *) {
            GlassEffectContainer(spacing: 8) { controls }
        } else {
            controls
        }
#else
        controls
#endif
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 12) {
            if store.uncertain {
                Label("发送结果待确认，请先刷新对话。草稿已保留。", systemImage: "exclamationmark.circle")
                    .font(.footnote)
                    .foregroundStyle(.orange)
                    .padding(.bottom, 4)
            }
            let layout = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 0))
                : AnyLayout(HStackLayout(alignment: .center, spacing: 12))
            layout {
                Button { store.showingModels = true } label: {
                    HStack(spacing: 6) {
                        Text(store.currentModel?.name ?? "选择模型")
                            .font(.footnote.weight(.medium))
                            .lineLimit(typeSize.isAccessibilitySize ? nil : 1)
                        Image(systemName: "chevron.down")
                            .font(.caption2.weight(.semibold))
                            .accessibilityHidden(true)
                    }
                    .foregroundStyle(.primary)
                    .padding(.horizontal, 6)
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
                }
                .modifier(ComposerModelAppearance())
                .frame(maxWidth: .infinity, alignment: .leading)
                .disabled(store.active)
                .accessibilityLabel("选择模型")
                .accessibilityValue(store.currentModel?.name ?? "未选择")
                if store.active {
                    Button(role: .destructive) { Task { await store.stop() } } label: {
                        Label(store.stopping ? "正在停止…" : "停止任务", systemImage: "stop.fill")
                            .font(.footnote.weight(.medium))
                            .frame(minHeight: 44)
                    }
                    .modifier(ComposerModelAppearance())
                    .disabled(store.stopping)
                }
            }
            inputRow
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 12)
        .frame(maxWidth: 720)
        .frame(maxWidth: .infinity)
    }

    private var draftField: some View {
        TextField(store.active ? "补充要求，或问问进展…" : "发消息给 OpenCode…", text: $store.draft, axis: .vertical)
            .font(.body)
            .lineLimit(1...5)
            .focused($composing)
            .accessibilityIdentifier("conversation.draft")
            .task(id: store.draft) {
                do { try await Task.sleep(nanoseconds: 400_000_000) }
                catch { return }
                if !Task.isCancelled { store.saveDraft() }
            }
            .task {
#if targetEnvironment(simulator)
                if SimulatorPreview.route == "chat-keyboard" {
                    do { try await Task.sleep(nanoseconds: 600_000_000) }
                    catch { return }
                    composing = true
                }
#endif
            }
    }

    @ViewBuilder
    private var inputRow: some View {
#if BRIDGECHAT_IOS26
        if #available(iOS 26.0, *) {
            HStack(alignment: .bottom, spacing: 12) {
                draftField
                    .padding(.horizontal, 16)
                    .padding(.vertical, 14)
                    .glassEffect(.regular.interactive(), in: RoundedRectangle(cornerRadius: 28))
                Button(action: send) {
                    SendSymbol(sending: store.sending)
                        .frame(minWidth: 22, minHeight: 22)
                }
                .buttonStyle(.glassProminent)
                .buttonBorderShape(.circle)
                .controlSize(.large)
                .disabled(!canSend)
                .accessibilityLabel(store.active ? "发送追问" : "发送消息")
                .accessibilityIdentifier("conversation.send")
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
            draftField.padding(.leading, 14).padding(.vertical, 12)
            Button(action: send) {
                Group {
                    if store.sending {
                        ProgressView()
                    } else {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.title)
                            .foregroundStyle(canSend ? Color.accentColor : Color(.tertiaryLabel))
                    }
                }
                .frame(minWidth: 44, minHeight: 44)
            }
            .buttonStyle(.borderless)
            .disabled(!canSend)
            .accessibilityLabel(store.active ? "发送追问" : "发送消息")
            .accessibilityIdentifier("conversation.send")
        }
        .padding(.trailing, 2)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 24))
    }

    private func send() {
        onSend()
        Task { await store.send() }
    }
}

private struct ComposerModelAppearance: ViewModifier {
    @ViewBuilder
    func body(content: Content) -> some View {
#if BRIDGECHAT_IOS26
        if #available(iOS 26.0, *) {
            content.buttonStyle(.glass).controlSize(.small)
        } else {
            content.buttonStyle(.plain)
        }
#else
        content.buttonStyle(.plain)
#endif
    }
}

private struct SendSymbol: View {
    let sending: Bool

    var body: some View {
        Group {
            if sending { ProgressView() }
            else { Image(systemName: "arrow.up").font(.body.weight(.semibold)) }
        }
    }
}
