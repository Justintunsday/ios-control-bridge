import Foundation
import Security

struct ClientError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

@MainActor
final class ConnectionStore {
    private let service = "dev.ioscontrol.bridgechat.connection"
    private let defaults = UserDefaults.standard
    var url: String { defaults.string(forKey: "serverURL") ?? "" }
    var username: String { defaults.string(forKey: "serverUsername") ?? "opencode" }
    var preferred: ModelChoice? {
        get { defaults.dictionary(forKey: "preferredModel").map(ModelChoice.init) }
        set { defaults.set(newValue?.reference, forKey: "preferredModel") }
    }
    static var support: URL {
        let url = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("BridgeChat", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.complete])
        return url
    }
    init() throws {
        let file = Self.support.appendingPathComponent("bootstrap.json")
        guard let data = try? Data(contentsOf: file) else { return }
        let raw = object(try JSONSerialization.jsonObject(with: data))
        try save(url: text(raw["url"]), username: text(raw["username"]), password: text(raw["password"]))
        guard password() == text(raw["password"]) else { throw ClientError(message: "连接密码未能写入 Keychain，请检查安装签名。") }
        if !object(raw["preferredModel"]).isEmpty { preferred = ModelChoice(object(raw["preferredModel"])) }
        try FileManager.default.removeItem(at: file)
    }
    func password() -> String? {
        guard !url.isEmpty else { return nil }
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: url, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    func save(url string: String, username: String, password: String) throws {
        guard var components = URLComponents(string: string.trimmingCharacters(in: .whitespacesAndNewlines)), ["http", "https"].contains(components.scheme?.lowercased() ?? ""), components.host != nil, components.user == nil, components.password == nil, components.query == nil, components.fragment == nil, ["", "/"].contains(components.path) else { throw ClientError(message: "请输入完整的 http 或 https 服务地址，不含用户名或路径。") }
        components.path = ""
        guard let origin = components.url?.absoluteString else { throw ClientError(message: "服务地址格式无效。") }
        if !password.isEmpty {
            let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: origin]
            let value: [String: Any] = [kSecValueData as String: Data(password.utf8)]
            var status = SecItemUpdate(query as CFDictionary, value as CFDictionary)
            if status == errSecItemNotFound {
                var item = query
                item[kSecValueData as String] = Data(password.utf8)
                item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
                status = SecItemAdd(item as CFDictionary, nil)
            }
            guard status == errSecSuccess else { throw ClientError(message: "无法保存连接密码，请检查 App 签名。") }
        }
        defaults.set(origin, forKey: "serverURL")
        defaults.set(username.isEmpty ? "opencode" : username, forKey: "serverUsername")
    }
}

@MainActor
final class OpenCodeAPI: NSObject, URLSessionTaskDelegate {
    let connection: ConnectionStore
    private lazy var network: URLSession = {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 18
        c.timeoutIntervalForResource = 25
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        c.httpShouldSetCookies = false
        c.httpCookieStorage = nil
        return URLSession(configuration: c, delegate: self, delegateQueue: nil)
    }()
    init(connection: ConnectionStore) { self.connection = connection }
    nonisolated func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
    func call(_ method: String, _ path: String, body: JSON? = nil, query: [String: String] = [:]) async throws -> JSON {
        guard !connection.url.isEmpty, var components = URLComponents(string: connection.url + path), path.hasPrefix("/api/") else { throw ClientError(message: "请先连接 OpenCode 服务。") }
        if !query.isEmpty { components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) } }
        guard let url = components.url else { throw ClientError(message: "服务地址无效。") }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let credential = connection.username + ":" + (connection.password() ?? "")
        request.setValue("Basic " + Data(credential.utf8).base64EncodedString(), forHTTPHeaderField: "Authorization")
        if let body = body {
            let data = try JSONSerialization.data(withJSONObject: body)
            guard data.count < 256 * 1024 else { throw ClientError(message: "消息过长，请分成多条发送。") }
            request.httpBody = data
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let data: Data
        let response: URLResponse
        do { (data, response) = try await network.data(for: request) }
        catch {
            if Task.isCancelled { throw CancellationError() }
            throw ClientError(message: (error as NSError).code == NSURLErrorTimedOut ? "连接超时，请刷新确认消息状态；消息不会自动重发。" : "暂时无法连接 OpenCode，请检查服务是否正在运行。")
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if status == 401 { throw ClientError(message: "服务密码无效，请在连接设置中更新。") }
        guard (200..<300).contains(status) else { throw ClientError(message: "OpenCode 未完成请求（\(status)），请刷新确认状态。") }
        guard data.count < 24 * 1024 * 1024 else { throw ClientError(message: "会话内容过大，请先查看较新的消息。") }
        if data.isEmpty { return [:] }
        guard let result = try JSONSerialization.jsonObject(with: data) as? JSON else { throw ClientError(message: "这个地址不是兼容的 OpenCode 2 服务。") }
        return result
    }
    static func sessionPath(_ id: String) throws -> String {
        guard id.range(of: "^ses[A-Za-z0-9_-]{1,180}$", options: .regularExpression) != nil else { throw ClientError(message: "对话标识无效，请刷新列表。") }
        return "/api/session/" + id
    }
}

@MainActor
final class DraftStore {
    private let file = ConnectionStore.support.appendingPathComponent("drafts.json")
    private var items: JSON = [:]
    init() { if let data = try? Data(contentsOf: file), let raw = try? JSONSerialization.jsonObject(with: data) as? JSON { items = raw } }
    func read(_ key: String) -> String { text(object(items[key])["text"]) }
    func save(_ key: String, _ string: String) {
        items[key] = ["text": String(string.prefix(40_000)), "time": Date().timeIntervalSince1970]
        if items.count > 40, let oldest = items.keys.min(by: { number(object(items[$0])["time"]) < number(object(items[$1])["time"]) }) { items.removeValue(forKey: oldest) }
        if let data = try? JSONSerialization.data(withJSONObject: items) { try? data.write(to: file, options: [.atomic, .completeFileProtection]) }
    }
}
