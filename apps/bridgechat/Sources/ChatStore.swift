import Foundation
import Combine

@MainActor
final class ChatStore: ObservableObject {
    @Published var sessions: [ChatSession] = []
    @Published var models: [ModelChoice] = []
    @Published var selected: ChatSession?
    @Published var messages: [ChatMessage] = []
    @Published var permissions: [PermissionRequest] = []
    @Published var preferred: ModelChoice?
    @Published var draft = ""
    @Published var search = ""
    @Published var connected = false
    @Published var connecting = false
    @Published var sending = false
    @Published var stopping = false
    @Published var showingChat = false
    @Published var showingSettings = false
    @Published var showingModels = false
    @Published var notice: String?
    @Published var revision = 0
    @Published var uncertain = false
    let connection: ConnectionStore?
    private let api: OpenCodeAPI?
    private let drafts = DraftStore()
    private var poll: Task<Void, Never>?
    private var epoch = 0
    private var refreshing = false
    private var limit = 80
    private var outbox: (id: String, text: String, session: String)?
    var active: Bool { selected?.active ?? false }
    var currentModel: ModelChoice? {
        let ref = selected?.model ?? preferred
        return models.first(where: { $0.id == ref?.id }) ?? ref
    }
    init() {
        do {
            let connection = try ConnectionStore()
            self.connection = connection
            api = OpenCodeAPI(connection: connection)
            preferred = connection.preferred
        } catch {
            connection = nil
            api = nil
            notice = error.localizedDescription
        }
    }
    func connect() async {
        guard !connecting, let api = api, let connection = connection else { return }
        if connection.url.isEmpty { showingSettings = true; return }
        connecting = true
        defer { connecting = false }
        do {
            let info = try await api.call("GET", "/api/info")
            guard !text(info["version"]).isEmpty else { throw ClientError(message: "这个地址不是兼容的 OpenCode 2 服务。") }
            let response = try await api.call("GET", "/api/model")
            models = (response["data"] as? [JSON] ?? []).filter { ($0["enabled"] as? Bool) != false && text($0["type"]) != "embedding" }.map(ModelChoice.init)
            if !models.contains(where: { $0.id == preferred?.id }) { preferred = models.first(where: { $0.id == "deepseek/deepseek-flash" }) ?? models.first }
            connected = true
            await loadSessions()
        } catch { connected = false; show(error) }
    }
    func loadSessions() async {
        guard let api = api else { return }
        let generation = epoch
        do {
            var query = ["limit": "50", "order": "desc", "archived": "false", "parentID": "null"]
            if !search.isEmpty { query["search"] = search }
            let response = try await api.call("GET", "/api/session", query: query)
            guard generation == epoch else { return }
            sessions = (response["data"] as? [JSON] ?? []).map(ChatSession.init)
        } catch { show(error) }
    }
    func open(_ session: ChatSession?) {
        saveDraft()
        poll?.cancel()
        epoch += 1
        selected = session
        messages = []
        permissions = []
        limit = 80
        uncertain = false
        outbox = nil
        draft = drafts.read(session?.id ?? "new")
        showingChat = true
    }
    func beginPolling() {
        poll?.cancel()
        poll = Task { [weak self] in
            while !Task.isCancelled {
                guard let self = self, self.showingChat else { break }
                await self.refresh()
                try? await Task.sleep(nanoseconds: self.active ? 1_200_000_000 : 5_000_000_000)
            }
        }
    }
    func pause() { poll?.cancel(); saveDraft() }
    func saveDraft() { if showingChat { drafts.save(selected?.id ?? "new", draft) } }
    func refresh() async {
        guard !refreshing, let selected = selected, let api = api else { return }
        refreshing = true
        let generation = epoch
        defer { refreshing = false }
        do {
            let path = try OpenCodeAPI.sessionPath(selected.id)
            async let info = api.call("GET", path)
            async let history = api.call("GET", path + "/message", query: ["limit": String(limit), "order": "desc"])
            async let pending = api.call("GET", path + "/permission")
            let (a, b, c) = try await (info, history, pending)
            guard generation == epoch else { return }
            self.selected = ChatSession(object(a["data"]))
            let rows = ChatMessage.parse(b["data"] as? [JSON] ?? [])
            if rows != messages { messages = rows; revision += 1 }
            permissions = (c["data"] as? [JSON] ?? []).map(PermissionRequest.init)
            if let item = outbox, rows.contains(where: { $0.id == item.id }) {
                uncertain = false
                if draft == item.text { draft = ""; saveDraft() }
                outbox = nil
            }
            connected = true
        } catch { if generation == epoch { show(error) } }
    }
    func earlier() async { limit = min(400, limit + 80); await refresh() }
    var hasEarlier: Bool { messages.count >= limit && limit < 400 }
    func send() async {
        let value = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sending, !value.isEmpty, let api = api else { return }
        sending = true
        let generation = epoch
        defer { sending = false }
        var messageID: String?
        do {
            if selected == nil {
                var body: JSON = ["title": String(value.prefix(24)), "agent": "build", "metadata": ["client": "bridgechat", "version": "0.1.0"]]
                if let preferred = preferred { body["model"] = preferred.reference }
                let response = try await api.call("POST", "/api/session", body: body)
                guard generation == epoch else { return }
                selected = ChatSession(object(response["data"]))
            }
            guard let selected = selected else { return }
            let path = try OpenCodeAPI.sessionPath(selected.id)
            let old = outbox
            let id = old?.text == value && old?.session == selected.id ? old!.id : "msg_" + String(Int(Date().timeIntervalSince1970 * 1000), radix: 16) + String(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased().prefix(16))
            messageID = id
            outbox = (id: id, text: value, session: selected.id)
            var body: JSON = ["id": id, "text": value, "resume": true]
            if selected.active { body["delivery"] = "steer" }
            _ = try await api.call("POST", path + "/prompt", body: body)
            guard generation == epoch else { return }
            draft = ""
            drafts.save("new", "")
            saveDraft()
            uncertain = false
            await refresh()
        } catch {
            guard generation == epoch else { return }
            if let selected = selected, let id = messageID, let path = try? OpenCodeAPI.sessionPath(selected.id), let result = try? await api.call("GET", path + "/message/" + id), !object(result["data"]).isEmpty {
                draft = ""; saveDraft(); uncertain = false; await refresh()
            } else { uncertain = messageID != nil; show(error) }
        }
    }
    func stop() async {
        guard let selected = selected, let api = api else { return }
        stopping = true
        defer { stopping = false }
        do { _ = try await api.call("POST", try OpenCodeAPI.sessionPath(selected.id) + "/interrupt", query: ["resume": "false"]); await refresh() }
        catch { show(error) }
    }
    func choose(_ model: ModelChoice) async {
        guard let api = api else { return }
        do {
            if let session = selected { _ = try await api.call("POST", try OpenCodeAPI.sessionPath(session.id) + "/model", body: ["model": model.reference]); selected?.model = model }
            preferred = model
            connection?.preferred = model
            showingModels = false
        } catch { show(error) }
    }
    func saveConnection(url: String, username: String, password: String) async throws {
        guard let connection = connection else { throw ClientError(message: "Keychain 初始化失败，请重新安装 App。") }
        try connection.save(url: url, username: username, password: password)
        epoch += 1
        connected = false
        await connect()
        guard connected else { throw ClientError(message: notice ?? "连接未完成，请检查服务地址与密码。") }
        showingSettings = false
    }
    func reply(_ permission: PermissionRequest, allow: Bool) async {
        guard let selected = selected, let api = api, permission.id.range(of: "^[A-Za-z0-9_-]{1,200}$", options: .regularExpression) != nil else { return }
        do { _ = try await api.call("POST", try OpenCodeAPI.sessionPath(selected.id) + "/permission/" + permission.id + "/reply", body: ["decision": allow ? "once" : "reject"]); await refresh() }
        catch { show(error) }
    }
    private func show(_ error: Error) { if !(error is CancellationError) { notice = error.localizedDescription } }
}
