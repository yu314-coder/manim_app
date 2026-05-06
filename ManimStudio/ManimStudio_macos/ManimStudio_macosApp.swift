// ManimStudio_macosApp.swift — @main entry for the native macOS
// rewrite. Pure SwiftUI; no embedded Python interpreter, no
// WKWebView shell. The render pipeline shells out to a host
// python3.* via RenderManager (Process), reading bundled
// site-packages from <App>.app/Contents/Resources/site-packages/.
//
// Shares ZERO code with the iOS target — only the AppIcon asset
// is regenerated from the iOS 1024×1024 master.
import SwiftUI

@main
struct ManimStudio_macosApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
        }
        .windowResizability(.contentMinSize)
        .commands {
            // ── File menu — replace the default New / Open / Save
            // with handlers wired to AppState.
            CommandGroup(replacing: .newItem) {
                Button("New Scene") {
                    appState.sourceCode = ""
                    appState.openedFileURL = nil
                    appState.selectedScene = ""
                }
                .keyboardShortcut("n", modifiers: [.command])

                Button("Open Python File…") { openFile() }
                    .keyboardShortcut("o", modifiers: [.command])

                Divider()

                Button("Save Scene…") { saveFile() }
                    .keyboardShortcut("s", modifiers: [.command])
            }

            // ── View menu shortcuts for sidebar navigation.
            CommandMenu("View") {
                Button("Workspace") { appState.sidebarSection = .workspace }
                    .keyboardShortcut("1", modifiers: [.command])
                Button("Assets")    { appState.sidebarSection = .assets }
                    .keyboardShortcut("2", modifiers: [.command])
                Button("Packages")  { appState.sidebarSection = .packages }
                    .keyboardShortcut("3", modifiers: [.command])
                Button("History")   { appState.sidebarSection = .history }
                    .keyboardShortcut("4", modifiers: [.command])
                Button("Settings")  { appState.sidebarSection = .settings }
                    .keyboardShortcut(",", modifiers: [.command])
            }
        }
    }

    // MARK: file IO

    private func openFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.pythonScript, .plainText, .text]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            appState.sourceCode = try String(contentsOf: url, encoding: .utf8)
            appState.openedFileURL = url
            appState.selectedScene = ""
        } catch {
            NSLog("[file] open failed: %@", error.localizedDescription)
        }
    }

    private func saveFile() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.pythonScript]
        panel.nameFieldStringValue = appState.openedFileURL?.lastPathComponent ?? "scene.py"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try appState.sourceCode.write(to: url, atomically: true, encoding: .utf8)
            appState.openedFileURL = url
        } catch {
            NSLog("[file] save failed: %@", error.localizedDescription)
        }
    }
}

// MARK: - small UTType helper

import UniformTypeIdentifiers

extension UTType {
    /// Either the system-registered Python script type, or plain
    /// text as a fallback. Used by NSOpenPanel.allowedContentTypes.
    static var pythonScript: UTType {
        UTType("public.python-script") ?? .plainText
    }
}
