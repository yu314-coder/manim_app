// ContentView.swift — root SwiftUI view for the macOS app.
//
// Layout (high-tech glassmorphic theme):
//   ┌──────┬─────────────────────────────────────────┬────────┐
//   │      │ ┌── Top toolbar ──────────────────────┐ │        │
//   │      │ │ logo · scene-picker · render/preview │ │        │
//   │      │ └─────────────────────────────────────┘ │        │
//   │ side │ ┌──── Editor ───┐  ┌──── Preview ───┐  │ render │
//   │  bar │ │               │  │                │  │  ctrl  │
//   │      │ │   NSTextView  │  │  AVKit Player  │  │ panel  │
//   │      │ └───────────────┘  └────────────────┘  │        │
//   │      │ ┌── Terminal (read-only) ───────────┐  │        │
//   │      │ │  manim subprocess output…         │  │        │
//   │      │ └───────────────────────────────────┘  │        │
//   └──────┴─────────────────────────────────────────┴────────┘
//
// The right-side render-controls panel can collapse via the slider
// button. Workspace, Assets, Packages, History, Settings live in
// the left sidebar.
import SwiftUI
import AppKit

struct ContentView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var venv: VenvManager

    @State private var renderManager: RenderManager?
    @State private var controlsOpen = true

    var body: some View {
        NavigationSplitView {
            sidebar
                .navigationSplitViewColumnWidth(min: 200, ideal: 220, max: 260)
        } detail: {
            ZStack {
                // Window-wide blur underlay for the high-tech feel.
                VisualEffectBackground(material: .underWindowBackground)
                    .ignoresSafeArea()
                Theme.bgPrimary.opacity(0.85).ignoresSafeArea()

                detailPane
            }
        }
        .frame(minWidth: 1200, minHeight: 760)
        .preferredColorScheme(.dark)
        .onAppear {
            if renderManager == nil {
                renderManager = RenderManager(app: app)
            }
        }
        .toolbar { toolbarContent }
    }

    // MARK: sidebar (high-tech list)

    private var sidebar: some View {
        ZStack {
            VisualEffectBackground(material: .sidebar).ignoresSafeArea()
            VStack(spacing: 0) {
                logoHeader
                Divider().background(Theme.borderSubtle)
                List(selection: $app.sidebarSection) {
                    Section {
                        ForEach(SidebarSection.allCases) { section in
                            HStack(spacing: 10) {
                                Image(systemName: section.icon)
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundStyle(app.sidebarSection == section
                                                     ? Color.white
                                                     : Theme.indigo)
                                    .frame(width: 22)
                                Text(section.label)
                                    .font(.system(size: 13, weight: app.sidebarSection == section
                                                  ? .semibold : .regular))
                            }
                            .padding(.vertical, 2)
                            .tag(section)
                        }
                    } header: {
                        SectionHeader(title: "Navigate", icon: "square.grid.2x2")
                            .padding(.top, 6)
                    }
                }
                .listStyle(.sidebar)
                .scrollContentBackground(.hidden)

                Divider().background(Theme.borderSubtle)
                statusBar
            }
        }
    }

    private var logoHeader: some View {
        HStack(spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 9)
                    .fill(Theme.signatureGradient)
                    .frame(width: 34, height: 34)
                    .shadow(color: Theme.glowPrimary, radius: 8)
                Text("🎬").font(.system(size: 18))
            }
            VStack(alignment: .leading, spacing: 0) {
                Text("ManimStudio")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(Theme.textPrimary)
                Text("Native · macOS")
                    .font(.system(size: 9, weight: .medium))
                    .tracking(1)
                    .foregroundStyle(Theme.textDim)
            }
            Spacer()
        }
        .padding(.horizontal, 14).padding(.vertical, 14)
    }

    private var statusBar: some View {
        HStack(spacing: 8) {
            StatusDot(state: dotState)
            Text(statusText)
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundStyle(Theme.textSecondary)
                .lineLimit(1).truncationMode(.middle)
            Spacer()
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
    }

    private var dotState: StatusDot.DotState {
        if app.isRendering { return .active }
        switch venv.phase {
        case .ready:  return .ok
        case .failed: return .error
        default:      return .idle
        }
    }
    private var statusText: String {
        if app.isRendering { return "rendering…" }
        switch venv.phase {
        case .ready:  return "manim \(venv.manimVersion)"
        case .idle: return "venv not set up"
        case .creatingVenv, .upgradingPip, .installingPackages, .verifying: return "installing…"
        case .failed:  return "venv error"
        }
    }

    // MARK: detail

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
                    EditorView(text: $app.sourceCode,
                               fontSize: CGFloat(app.editorFontSize))
                        .frame(minWidth: 320)
                    PreviewView(url: app.lastRenderURL)
                        .frame(minWidth: 240)
                }
                .frame(minHeight: 240)

                TerminalView(text: $app.terminalText,
                             fontSize: CGFloat(app.terminalFontSize))
                    .frame(minHeight: 100)
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

    // MARK: toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .navigation) {
            scenePicker
        }
        ToolbarItemGroup(placement: .primaryAction) {
            Button {
                renderManager?.renderFinal()
            } label: {
                Label("Render", systemImage: "play.fill")
            }
            .keyboardShortcut("r", modifiers: [.command])
            .help("Render (⌘R)")
            .disabled(app.isRendering)

            Button {
                renderManager?.renderPreview()
            } label: {
                Label("Preview", systemImage: "eye")
            }
            .keyboardShortcut("r", modifiers: [.command, .shift])
            .help("Preview low-quality (⇧⌘R)")
            .disabled(app.isRendering)

            if app.isRendering {
                Button(role: .destructive) {
                    renderManager?.stop()
                } label: {
                    Label("Stop", systemImage: "stop.fill")
                }
                .keyboardShortcut(".", modifiers: [.command])
                .help("Stop (⌘.)")
            }

            Button {
                withAnimation(.spring) { controlsOpen.toggle() }
            } label: {
                Image(systemName: controlsOpen ? "sidebar.right" : "slider.horizontal.3")
            }
            .help("Toggle render controls")
        }
    }

    @ViewBuilder
    private var scenePicker: some View {
        let scenes = app.detectedScenes
        Menu {
            Button {
                app.selectedScene = ""
            } label: {
                if app.selectedScene.isEmpty {
                    Label(scenes.isEmpty ? "First detected"
                          : "First detected (\(scenes.first ?? ""))",
                          systemImage: "checkmark")
                } else {
                    Text(scenes.isEmpty ? "First detected"
                         : "First detected (\(scenes.first ?? ""))")
                }
            }
            if !scenes.isEmpty { Divider() }
            ForEach(scenes, id: \.self) { name in
                Button {
                    app.selectedScene = name
                } label: {
                    if app.selectedScene == name {
                        Label(name, systemImage: "checkmark")
                    } else {
                        Text(name)
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "rectangle.stack")
                Text(label(for: scenes))
            }
        }
        .help("Choose which Scene class to render")
    }

    private func label(for scenes: [String]) -> String {
        if !app.selectedScene.isEmpty { return app.selectedScene }
        return scenes.isEmpty ? "No Scene" : (scenes.first ?? "")
    }
}

// MARK: - Settings (kept here since it's small)

struct SettingsView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var venv: VenvManager

    var body: some View {
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
            Section("Terminal") {
                HStack {
                    Text("Font size")
                    Slider(value: $app.terminalFontSize, in: 9...18, step: 1)
                    Text("\(Int(app.terminalFontSize))pt")
                        .frame(width: 44, alignment: .trailing)
                        .font(.system(.caption, design: .monospaced))
                }
                Button("Clear terminal output") { app.clearTerminal() }
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
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
                Button("Re-run setup wizard") {
                    NotificationCenter.default.post(
                        name: .reopenWelcome, object: nil)
                }
            }
        }
        .formStyle(.grouped)
        .background(Theme.bgPrimary)
    }

    private var envStatusText: String {
        switch venv.phase {
        case .ready:    return "ready · manim \(venv.manimVersion)"
        case .missing:  return "not set up"
        case .unknown:  return "checking…"
        case .creatingVenv, .upgradingPip, .installingPackages, .verifying: return "installing…"
        case .failed:   return "failed"
        }
    }
}

extension Notification.Name {
    static let reopenWelcome = Notification.Name("manimstudio.welcome.reopen")
}

#Preview {
    ContentView()
        .environmentObject(AppState())
        .environmentObject(VenvManager())
}
