// ContentView.swift — root macOS view. Layout mirrors the iOS
// design (HeaderView at top, TabBar below, content swap based on
// selected tab) while staying purely native AppKit/SwiftUI.
//
// Workspace tab = Monaco editor + AVPlayer preview + real PTY
// terminal + collapsible right-side render controls.
import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var venv: VenvManager

    @State private var renderManager: RenderManager?
    @State private var monaco = MonacoController()
    @State private var controlsOpen = true
    @State private var openPanelShown = false
    @State private var savePanelShown = false

    var body: some View {
        VStack(spacing: 0) {
            HeaderView(
                onRender:  { renderManager?.renderFinal()  },
                onPreview: { renderManager?.renderPreview() },
                onStop:    { renderManager?.stop()         },
                onNew:     { newScene() },
                onOpen:    { openFile() },
                onSave:    { saveFile() }
            )
            TabBarView(selection: $app.sidebarSection)

            ZStack {
                VisualEffectBackground(material: .underWindowBackground)
                    .ignoresSafeArea()
                Theme.bgPrimary.opacity(0.85).ignoresSafeArea()
                detailPane
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minWidth: 1280, minHeight: 800)
        .preferredColorScheme(.dark)
        .onAppear {
            if renderManager == nil {
                renderManager = RenderManager(app: app)
            }
            // Feed Monaco any cached symbol index immediately, then
            // refresh in the background. The provider tolerates an
            // empty index so completion still works pre-install.
            if let cached = MonacoSymbolIndexer.cachedJSON() {
                monaco.setSymbolIndex(cached)
            }
            if venv.isReady {
                MonacoSymbolIndexer.refresh { json in
                    if let json = json { monaco.setSymbolIndex(json) }
                }
            }
        }
        .onChange(of: venv.phase) { _, new in
            // Re-introspect the moment the venv finishes installing —
            // gives the user manim/numpy/etc. completion as soon as
            // the wizard finishes.
            if new == .ready {
                MonacoSymbolIndexer.refresh { json in
                    if let json = json { monaco.setSymbolIndex(json) }
                }
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .renderFinal)) { _ in
            renderManager?.renderFinal()
        }
        .onReceive(NotificationCenter.default.publisher(for: .renderPreview)) { _ in
            renderManager?.renderPreview()
        }
        .onReceive(NotificationCenter.default.publisher(for: .renderStop)) { _ in
            renderManager?.stop()
        }
    }

    // MARK: detail pane

    @ViewBuilder
    private var detailPane: some View {
        switch app.sidebarSection {
        case .workspace: workspace
        case .assets:    AssetsView()
        case .packages:  PackagesView(venv: venv)
        case .history:   HistoryView()
        case .settings:  SettingsView()
        }
    }

    @ViewBuilder
    private var workspace: some View {
        HStack(spacing: 0) {
            VSplitView {
                HSplitView {
                    EditorPane(monaco: monaco)
                        .frame(minWidth: 360)
                    PreviewView(url: app.lastRenderURL)
                        .frame(minWidth: 280)
                }
                .frame(minHeight: 260)

                TerminalProcessView(venv: venv)
                    .frame(minHeight: 120)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            if controlsOpen {
                RenderControlsPanel(venv: venv, open: $controlsOpen)
                    .transition(.move(edge: .trailing).combined(with: .opacity))
            }
        }
        .overlay(alignment: .trailing) {
            if !controlsOpen {
                Button { withAnimation(.spring) { controlsOpen = true } } label: {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 36, height: 36)
                        .background(Circle().fill(Theme.signatureGradient))
                        .shadow(color: Theme.glowPrimary, radius: 10)
                }
                .buttonStyle(.plain)
                .padding(.trailing, 12)
            }
        }
    }

    // MARK: file ops

    private func newScene() {
        app.sourceCode = ""
        app.openedFileURL = nil
        app.selectedScene = ""
    }

    private func openFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.pythonScript, .plainText, .text]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            app.sourceCode = try String(contentsOf: url, encoding: .utf8)
            app.openedFileURL = url
            app.selectedScene = ""
        } catch {
            NSLog("[file] open failed: %@", error.localizedDescription)
        }
    }

    private func saveFile() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.pythonScript]
        panel.nameFieldStringValue = app.openedFileURL?.lastPathComponent ?? "scene.py"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try app.sourceCode.write(to: url, atomically: true, encoding: .utf8)
            app.openedFileURL = url
        } catch {
            NSLog("[file] save failed: %@", error.localizedDescription)
        }
    }
}

// MARK: - Editor pane (Monaco + small toolbar)

struct EditorPane: View {
    @EnvironmentObject var app: AppState
    let monaco: MonacoController

    var body: some View {
        VStack(spacing: 0) {
            // Editor mini toolbar — Find / Format / Comment + filename
            HStack(spacing: 8) {
                Image(systemName: "chevron.left.forwardslash.chevron.right")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.indigo)
                Text(app.openedFileURL?.lastPathComponent ?? "Code Editor")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1).truncationMode(.middle)
                Spacer()

                editorToolBtn("magnifyingglass", "Find (⌘F)") {
                    monaco.showFind()
                }
                editorToolBtn("text.alignleft",  "Format (⌥⌘L)") {
                    monaco.format()
                }
                editorToolBtn("text.bubble",     "Toggle comment (⌘/)") {
                    monaco.toggleComment()
                }
                Menu {
                    ForEach([10, 12, 13, 14, 16, 18, 20, 24], id: \.self) { sz in
                        Button("\(sz)px") { app.editorFontSize = Double(sz) }
                    }
                } label: {
                    Text("\(Int(app.editorFontSize))px")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.textSecondary)
                        .padding(.horizontal, 6).padding(.vertical, 3)
                        .background(RoundedRectangle(cornerRadius: 5)
                            .fill(Theme.bgTertiary))
                }
                .menuStyle(.borderlessButton)
                .frame(width: 50)
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(Theme.bgSecondary)
            .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1),
                     alignment: .bottom)

            MonacoEditorView(text: $app.sourceCode,
                             fontSize: CGFloat(app.editorFontSize),
                             controller: monaco)
                .background(Color(red: 0.055, green: 0.060, blue: 0.095))
        }
    }

    @ViewBuilder
    private func editorToolBtn(_ icon: String, _ tip: String,
                               action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 26, height: 26)
                .background(RoundedRectangle(cornerRadius: 6)
                    .fill(Theme.bgTertiary))
        }
        .buttonStyle(.plain)
        .help(tip)
    }
}

// MARK: - Settings (modal sheet)

struct SettingsView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var venv: VenvManager
    @Environment(\.dismiss) private var dismiss
    @State private var tab: Tab = .general

    enum Tab: Hashable { case general, system }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Text("Settings").font(.system(size: 18, weight: .bold))
                Picker("", selection: $tab) {
                    Text("General").tag(Tab.general)
                    Text("System info").tag(Tab.system)
                }
                .pickerStyle(.segmented)
                .frame(width: 240)
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.escape, modifiers: [])
            }
            .padding(16)
            Divider()

            switch tab {
            case .general: generalForm
            case .system:  SystemInfoView()
                .environmentObject(venv)
            }
        }
    }

    private var generalForm: some View {
        Form {
            Section("Editor") {
                HStack {
                    Text("Font size")
                    Slider(value: $app.editorFontSize, in: 9...22, step: 1)
                    Text("\(Int(app.editorFontSize))pt")
                        .frame(width: 44, alignment: .trailing)
                        .font(.system(.caption, design: .monospaced))
                }
            }
            Section("Terminal") {
                HStack {
                    Text("Font size")
                    Slider(value: $app.terminalFontSize, in: 9...22, step: 1)
                    Text("\(Int(app.terminalFontSize))pt")
                        .frame(width: 44, alignment: .trailing)
                        .font(.system(.caption, design: .monospaced))
                }
            }
            Section("Render") {
                Picker("Quality", selection: $app.renderQuality) {
                    ForEach(RenderQuality.allCases) { q in
                        Text(q.label).tag(q)
                    }
                }
                Picker("Format", selection: $app.renderFormat) {
                    ForEach(RenderFormat.allCases) { f in
                        Text(f.label).tag(f)
                    }
                }
                Stepper(value: $app.renderFPS, in: 12...120, step: 6) {
                    Text("FPS: \(app.renderFPS)")
                }
            }
            Section("Environment") {
                LabeledContent("Status") {
                    HStack {
                        StatusDot(state: venv.phase == .ready ? .ok : .idle)
                        Text(envStatusText)
                            .font(.system(.caption, design: .monospaced))
                    }
                }
                if let py = venv.pythonInVenv {
                    LabeledContent("Python") {
                        Text(py.path)
                            .font(.system(.caption, design: .monospaced))
                            .lineLimit(1).truncationMode(.middle)
                    }
                }
                Button("Re-run setup wizard") {
                    NotificationCenter.default.post(
                        name: .reopenWelcome, object: nil)
                }
            }
        }
        .formStyle(.grouped)
    }

    private var envStatusText: String {
        switch venv.phase {
        case .ready:           return "ready · manim \(venv.manimVersion)"
        case .idle:            return "not set up"
        case .checkingDeps:    return "checking system deps…"
        case .installingDeps:  return "installing Cairo via brew…"
        case .creatingVenv, .upgradingPip,
             .installingPackages, .verifying: return "installing…"
        case .failed:          return "failed"
        }
    }
}

extension Notification.Name {
    static let renderStop      = Notification.Name("manimstudio.render.stop")
    static let reopenWelcome   = Notification.Name("manimstudio.welcome.reopen")
}

#Preview {
    ContentView()
        .environmentObject(AppState())
        .environmentObject(VenvManager())
}
