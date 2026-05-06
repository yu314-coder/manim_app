// ManimStudio_macosApp.swift — @main entry. Boots VenvManager, gates
// the main UI behind the welcome wizard until the per-app venv is
// ready (or the user explicitly dismissed it).
import SwiftUI
import UniformTypeIdentifiers

@main
struct ManimStudio_macosApp: App {
    @StateObject private var appState = AppState()
    @StateObject private var venv     = VenvManager()
    @State private var welcomeDismissed = false

    var body: some Scene {
        WindowGroup {
            RootGate(welcomeDismissed: $welcomeDismissed)
                .environmentObject(appState)
                .environmentObject(venv)
                .task {
                    await venv.probe()
                }
                .onReceive(NotificationCenter.default.publisher(for: .welcomeDone)) { _ in
                    welcomeDismissed = true
                }
                .onReceive(NotificationCenter.default.publisher(for: .reopenWelcome)) { _ in
                    welcomeDismissed = false
                    Task { await venv.probe() }
                }
        }
        .windowResizability(.contentMinSize)
        .commands {
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

            CommandMenu("Render") {
                Button("Render (Final)") {
                    NotificationCenter.default.post(name: .renderFinal, object: nil)
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Quick Preview") {
                    NotificationCenter.default.post(name: .renderPreview, object: nil)
                }
                .keyboardShortcut("r", modifiers: [.command, .shift])
            }

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

            CommandGroup(replacing: .help) {
                Button("Set Up Environment…") {
                    NotificationCenter.default.post(
                        name: .reopenWelcome, object: nil)
                }
            }
        }
    }

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

// MARK: - root gate

/// Routes between the welcome wizard and the main ContentView.
struct RootGate: View {
    @EnvironmentObject var venv: VenvManager
    @Binding var welcomeDismissed: Bool

    var body: some View {
        // Show the wizard until the venv is ready — unless the user
        // explicitly dismissed it (Skip / Open ManimStudio).
        if shouldShowWelcome {
            WelcomeView(venv: venv)
        } else {
            ContentView()
        }
    }

    private var shouldShowWelcome: Bool {
        if welcomeDismissed { return false }
        switch venv.phase {
        case .ready:                       return false
        case .missing, .failed,
             .creating, .installing,
             .unknown:
            return true
        }
    }
}

extension Notification.Name {
    static let renderFinal   = Notification.Name("manimstudio.render.final")
    static let renderPreview = Notification.Name("manimstudio.render.preview")
}

extension UTType {
    /// Either the system-registered Python script type, or plain
    /// text as a fallback. Used by NSOpenPanel.allowedContentTypes.
    static var pythonScript: UTType {
        UTType("public.python-script") ?? .plainText
    }
}
