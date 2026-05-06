// ManimStudio_macosApp.swift — @main entry for the native macOS
// build. Hosts a single ContentView (WKWebView) inside a window
// group with the standard NSWindow chrome. Keeps the menu bar
// minimal for now; a full File / Edit / Render / View / Help
// hierarchy can be wired with `.commands` once the JS↔Python
// bridge is live (Phase 2).
//
// This target shares NO Swift code with the iOS target by design —
// only the AppIcon asset is shared via the macOS Assets.xcassets
// generated from the iOS 1024 master.
import SwiftUI

@main
struct ManimStudio_macosApp: App {
    init() {
        // Boot the embedded Python on a background queue at app
        // launch so by the time the WKWebView finishes loading
        // `web/index.html` and starts firing pywebview.api.* calls,
        // PythonHost.shared.isReady is true and the IPC dispatch
        // resolves immediately. Idempotent — safe to call multiple
        // times.
        PythonHost.shared.ensureReady()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .windowResizability(.contentMinSize)
        .commands {
            // Replace the default New / Open / Save items with empty
            // placeholders for now — they'll be re-bound to JS bridge
            // calls in Phase 2 when the IPC wiring is live.
            CommandGroup(replacing: .newItem) {}
        }
    }
}
