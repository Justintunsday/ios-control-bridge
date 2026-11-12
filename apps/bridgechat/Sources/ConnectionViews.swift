import SwiftUI
import UIKit

@MainActor
struct ConnectionSettingsView: View {
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
                    BridgeChatIdentity()
                        .listRowBackground(Color.clear)
                        .listRowInsets(EdgeInsets(top: 12, leading: 0, bottom: 12, trailing: 0))
                }

                Section {
                    TextField("http://localhost:4097", text: $url)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityLabel("服务地址")
                } header: {
                    Text("服务地址")
                } footer: {
                    Text("填写你要连接的 OpenCode 服务地址。")
                }
                .disabled(saving)

                Section {
                    TextField("用户名", text: $username)
                        .textContentType(.username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityLabel("用户名")
                    SecureField(passwordPrompt, text: $password)
                        .textContentType(.password)
                        .accessibilityLabel("服务密码")
                } header: {
                    Text("登录信息")
                } footer: {
                    Text("密码只保存在这台设备上。")
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
                        Label {
                            Text("服务已连接")
                        } icon: {
                            Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                        }
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
                    Button { Task { await save() } } label: {
                        if saving { ProgressView() }
                        else { ToolbarActionLabel("保存并连接", symbol: "checkmark") }
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
private struct BridgeChatIdentity: View {
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var iconSize: CGFloat = 56

    var body: some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 16))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 16))
        layout {
            Group {
                if let icon = BridgeChatArtwork.icon {
                    Image(uiImage: icon).resizable().scaledToFit()
                } else {
                    Image(systemName: "bubble.left.and.bubble.right.fill")
                        .font(.largeTitle)
                        .foregroundStyle(Color.accentColor)
                }
            }
            .frame(width: iconSize, height: iconSize)
            .clipShape(RoundedRectangle(cornerRadius: iconSize * 0.24))
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 5) {
                Text("BridgeChat").font(.title2.weight(.semibold))
                Text("与 OpenCode 对话").font(.subheadline).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityElement(children: .combine)
    }
}

@MainActor
private enum BridgeChatArtwork {
    // This command-line build bundles loose PNGs rather than an asset catalog.
    static let icon: UIImage? = Bundle.main.url(forResource: "AppIconNative60x60@3x", withExtension: "png")
        .flatMap { UIImage(contentsOfFile: $0.path) }
}

@MainActor
struct ModelPickerView: View {
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
                            ModelChoiceRow(model: model, selected: store.currentModel?.id == model.id)
                        }
                        .buttonStyle(.plain)
                        .disabled(choosing || store.active)
                        .accessibilityAddTraits(store.currentModel?.id == model.id ? .isSelected : [])
                    }
                } header: {
                    Text("用于当前对话")
                } footer: {
                    Text(store.active ? "当前任务结束后可切换模型。" : "选择后会用于后续消息。")
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

private struct ModelChoiceRow: View {
    let model: ModelChoice
    let selected: Bool

    var body: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text(model.name).font(.body.weight(.medium)).foregroundStyle(.primary)
                Text(model.providerID).font(.footnote).foregroundStyle(.secondary)
                if model.seesImages {
                    Label("支持图片", systemImage: "photo")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if selected {
                Image(systemName: "checkmark")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(Color.accentColor)
                    .accessibilityHidden(true)
            }
        }
        .frame(minHeight: 44)
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

@MainActor
struct PermissionView: View {
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
