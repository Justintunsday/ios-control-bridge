import Foundation
import ActivityKit
import Dispatch
import Darwin

let schema = "activity-private-content-v1"
let source = "sessionkitd-activitykit-private-output"
let processStarted = Date()
let outputLock = NSLock()
var outputWritten = false

func timestamp(_ date: Date = Date()) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: date)
}

func emit(_ result: [String: Any], code: Int32) -> Never {
    outputLock.lock()
    if outputWritten { outputLock.unlock(); exit(code) }
    outputWritten = true
    var output = result
    output["schema"] = schema
    output["source"] = source
    output["observed_at"] = timestamp()
    output["elapsed_ms"] = Int(Date().timeIntervalSince(processStarted) * 1000)
    guard var data = try? JSONSerialization.data(withJSONObject: output, options: [.sortedKeys]) else {
        FileHandle.standardOutput.write(Data("{\"schema\":\"activity-private-content-v1\",\"status\":\"error\",\"reason\":\"json_encoding_failed\",\"complete_for_scope\":false}\n".utf8))
        exit(4)
    }
    if data.count > 524288 {
        data = Data("{\"schema\":\"activity-private-content-v1\",\"status\":\"partial\",\"reason\":\"output_size_limit\",\"complete_for_scope\":false}".utf8)
        FileHandle.standardOutput.write(data);FileHandle.standardOutput.write(Data([10]));exit(2)
    }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([10]))
    outputLock.unlock()
    exit(code)
}

func child(_ object: Any, _ name: String) -> Any? {
    Mirror(reflecting: object).children.first { $0.label == name }?.value
}

func path(_ root: Any, _ names: [String]) -> Any? {
    var current: Any = root
    for name in names { guard let next = child(current, name) else { return nil }; current = next }
    return current
}

func runReader(activityID: String, diagnostics: Bool) -> ([String: Any], Int32) {
    let version = NSDictionary(contentsOfFile: "/System/Library/CoreServices/SystemVersion.plist") as? [String: Any] ?? [:]
    var result: [String: Any] = ["requested_activity_id": activityID, "queried_at": timestamp(processStarted),
        "caller_uid": getuid(), "caller_pid": ProcessInfo.processInfo.processIdentifier,
        "scope": ["service": "com.apple.activitykit.output", "selection": "explicit_activity_id"],
        "os_version": version["ProductVersion"] ?? "unknown", "os_build": version["ProductBuildVersion"] ?? "unknown",
        "complete_for_scope": false]
    guard version["ProductVersion"] as? String == "16.1.1", version["ProductBuildVersion"] as? String == "20B101" else {
        result["status"] = "unavailable"; result["reason"] = "unverified_os_build"; return (result, 3)
    }
    guard let center = ICBCreateActivityCenter() else {
        result["status"] = "unavailable"; result["reason"] = "private_center_abi_mismatch"; return (result, 3)
    }
    let observation = ICBObserveActivities(center) {}
    defer { if let observation { _ = ICBInvalidateObserver(observation) } }
    RunLoop.current.run(until: Date().addingTimeInterval(1))
    guard let bridge = ICBReadActivityCenterBridge(center),
          let singleton = path(bridge, ["_activityCenter", "_manager", "store", "singleton"]),
          let queue = child(singleton, "queue") as? DispatchQueue else {
        result["status"] = "unavailable"; result["reason"] = "private_client_layout_mismatch"; return (result, 3)
    }
    // Read the connection enum on the system client's own serial queue.
    let connection: AnyObject? = queue.sync {
        guard let value = path(singleton, ["_queue_target", "connection"]),
              String(reflecting: type(of: value)) == "BSServiceConnection" else { return nil }
        return value as AnyObject
    }
    guard let connection,
          let query = ICBQueryActivityOutput(connection, activityID, true) as? [String: Any] else {
        result["status"] = "unavailable"; result["reason"] = "private_output_connection_unavailable"; return (result, 3)
    }
    if diagnostics { result["diagnostics"] = query }
    guard query["status"] as? String == "returned", query["subscription_error"] == nil,
          query["complete_for_service_response"] as? Bool == true else {
        result["status"] = "unavailable"
        result["reason"] = query["status"] ?? "invalid_private_response"
        result["error"] = query["error"] ?? query["subscription_error"] ?? query["exception"] ?? NSNull()
        return (result, 3)
    }
    result["service_entry_count"] = query["service_entry_count"] ?? NSNull()
    result["target_found"] = (query["target_found"] as? NSNumber)?.boolValue ?? false
    result["complete_for_scope"] = true
    guard let activity = query["target_activity_result"] as? [String: Any] else {
        result["status"] = "verified"; result["activity"] = NSNull(); return (result, 0)
    }
    result["activity"] = activity
    if query["target_truncated"] as? Bool == true {
        result["status"] = "partial"; result["reason"] = "target_data_limit"
        result["complete_for_scope"] = false; return (result, 2)
    }
    if let state = activity["contentState"] as? [String: Any], state["encoding"] as? String == "decoded-data" {
        result["content"] = state["decoded"] ?? NSNull()
        result["content_format"] = state["format"] ?? "unknown"
    } else {
        result["status"] = "partial"; result["reason"] = "content_encoding_not_decoded"
        result["complete_for_scope"] = false; return (result, 2)
    }
    result["status"] = "verified"
    return (result, 0)
}

var activityID: String?
var timeoutMS = 5000
var diagnostics = false
var index = 1
let arguments = CommandLine.arguments
while index < arguments.count {
    switch arguments[index] {
    case "--activity-id":
        index += 1
        guard index < arguments.count, let parsed = UUID(uuidString: arguments[index]) else {
            emit(["status": "error", "reason": "invalid_activity_id", "complete_for_scope": false], code: 4)
        }
        activityID = parsed.uuidString
    case "--timeout-ms":
        index += 1
        guard index < arguments.count, let value = Int(arguments[index]), (1...15000).contains(value) else {
            emit(["status": "error", "reason": "invalid_timeout_ms", "complete_for_scope": false], code: 4)
        }
        timeoutMS = value
    case "--diagnostics": diagnostics = true
    case "--help":
        print("Usage: icb-activities --activity-id UUID [--timeout-ms 1..15000] [--diagnostics]")
        exit(0)
    default: emit(["status": "error", "reason": "unknown_argument", "complete_for_scope": false], code: 4)
    }
    index += 1
}
guard let activityID else {
    emit(["status": "error", "reason": "activity_id_required", "complete_for_scope": false], code: 4)
}
DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + .milliseconds(timeoutMS)) {
    emit(["status": "unavailable", "reason": "timeout", "requested_activity_id": activityID,
          "complete_for_scope": false, "timeout_ms": timeoutMS], code: 3)
}
let outcome = runReader(activityID: activityID, diagnostics: diagnostics)
emit(outcome.0, code: outcome.1)
