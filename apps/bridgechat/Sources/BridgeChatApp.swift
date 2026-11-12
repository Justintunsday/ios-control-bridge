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
