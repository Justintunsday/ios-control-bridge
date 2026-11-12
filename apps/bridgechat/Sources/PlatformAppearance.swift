import SwiftUI

/// Keeps platform-owned scroll-edge treatment around the floating chat controls.
struct ChatComposerBar<Controls: View>: ViewModifier {
    let controls: Controls

    @ViewBuilder
    func body(content: Content) -> some View {
#if BRIDGECHAT_IOS26
        if #available(iOS 26.0, *) {
            content.safeAreaBar(edge: .bottom, spacing: 0) {
                controls
            }
        } else {
            legacy(content)
        }
#else
        legacy(content)
#endif
    }

    private func legacy(_ content: Content) -> some View {
        content.safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                Divider()
                controls
            }
            .background(.bar)
        }
    }
}

struct FloatingReplyAppearance: ViewModifier {
    @ViewBuilder
    func body(content: Content) -> some View {
#if BRIDGECHAT_IOS26
        if #available(iOS 26.0, *) {
            content.buttonStyle(.glass)
        } else {
            legacy(content)
        }
#else
        legacy(content)
#endif
    }

    private func legacy(_ content: Content) -> some View {
        content.buttonStyle(.bordered)
            .background(.regularMaterial, in: Capsule())
    }
}

struct ToolbarActionLabel: View {
    let title: String
    let symbol: String

    init(_ title: String, symbol: String) {
        self.title = title
        self.symbol = symbol
    }

    @ViewBuilder
    var body: some View {
#if BRIDGECHAT_IOS26
        if #available(iOS 26.0, *) {
            Image(systemName: symbol).accessibilityLabel(title)
        } else {
            Text(title)
        }
#else
        Text(title)
#endif
    }
}
