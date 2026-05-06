// ContentView.swift — root SwiftUI view. NavigationSplitView with
// a sidebar (Workspace / Assets / Packages / History / Settings)
// and a detail pane that swaps based on the selected section.
//
// Workspace is the main editor experience: top split = editor +
// preview, bottom = terminal. Terminal text comes from RenderManager
// streaming the manim subprocess's stdout/stderr.
import SwiftUI

struct ContentView: View {
    @EnvironmentObject var app: AppState
    @StateObject private var render: RenderHolder

    init() {
        // RenderManager has to be created with the AppState that's
        // injected via @EnvironmentObject, but @StateObject can't
        // capture @EnvironmentObject in init. Workaround: defer
        // construction to onAppear via a Holder that owns the
        // optional manager.
        _render = StateObject(wrappedValue: RenderHolder())
    }

    var body: some View {
        NavigationSplitView {
            sidebar
                .navigationSplitViewColumnWidth(min: 180, ideal: 200, max: 240)
        } detail: {
            detailPane
        }
        .frame(minWidth: 1100, minHeight: 700)
        .background(Theme.bgPrimary)
        .preferredColorScheme(.dark)
        .onAppear {
            if render.manager == nil {
                render.manager = RenderManager(app: app)
            }
        }
        .toolbar { toolbarContent }
    }

    // MARK: sidebar

    private var sidebar: some View {
        List(selection: $app.sidebarSection) {
            ForEach(SidebarSection.allCases) { section in
                Label(section.label, systemImage: section.icon)
                    .tag(section)
            }
        }
        .listStyle(.sidebar)
    }

    // MARK: detail

    @ViewBuilder
    private var detailPane: some View {
        switch app.sidebarSection {
        case .workspace: workspace
        case .assets:    AssetsView()
        case .packages:  PackagesView()
        case .history:   HistoryView()
        case .settings:  SettingsView()
        }
    }

    @ViewBuilder
    private var workspace: some View {
        VSplitView {
            HSplitView {
                EditorView(text: $app.sourceCode,
                           fontSize: CGFloat(app.editorFontSize))
                    .frame(minWidth: 320)
                PreviewView(url: app.lastRenderURL)
                    .frame(minWidth: 240)
            }
            .frame(minHeight: 220)

            TerminalView(text: $app.terminalText,
                         fontSize: CGFloat(app.terminalFontSize))
                .frame(minHeight: 100)
        }
        .background(Theme.bgPrimary)
    }

    // MARK: toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .navigation) {
            scenePicker
        }
        ToolbarItemGroup(placement: .primaryAction) {
            // Render — primary gradient action.
            Button {
                render.manager?.renderFinal()
            } label: {
                Label("Render", systemImage: "play.fill")
            }
            .keyboardShortcut("r", modifiers: [.command])
            .help("Render (⌘R)")
            .disabled(app.isRendering)

            Button {
                render.manager?.renderPreview()
            } label: {
                Label("Preview", systemImage: "eye")
            }
            .keyboardShortcut("r", modifiers: [.command, .shift])
            .help("Preview low-quality (⇧⌘R)")
            .disabled(app.isRendering)

            if app.isRendering {
                Button(role: .destructive) {
                    render.manager?.stop()
                } label: {
                    Label("Stop", systemImage: "stop.fill")
                }
                .keyboardShortcut(".", modifiers: [.command])
                .help("Stop (⌘.)")
            }
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
                    Label(scenes.isEmpty ? "First detected" : "First detected (\(scenes.first ?? ""))",
                          systemImage: "checkmark")
                } else {
                    Text(scenes.isEmpty ? "First detected" : "First detected (\(scenes.first ?? ""))")
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

// MARK: - holder wrapper for the render manager

@MainActor
final class RenderHolder: ObservableObject {
    var manager: RenderManager?
}

// MARK: - placeholders for non-workspace sections

struct AssetsView: View {
    var body: some View {
        VStack {
            Image(systemName: "folder").font(.largeTitle)
            Text("Assets").font(.title2.weight(.semibold))
            Text("File browser for Documents/Assets — coming soon")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.bgPrimary)
    }
}
struct PackagesView: View {
    var body: some View {
        VStack {
            Image(systemName: "shippingbox").font(.largeTitle)
            Text("Packages").font(.title2.weight(.semibold))
            Text("Browse the embedded Python's installed packages")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.bgPrimary)
    }
}
struct HistoryView: View {
    var body: some View {
        VStack {
            Image(systemName: "clock.arrow.circlepath").font(.largeTitle)
            Text("Render History").font(.title2.weight(.semibold))
            Text("Past renders with thumbnails and share/delete")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.bgPrimary)
    }
}
struct SettingsView: View {
    @EnvironmentObject var app: AppState
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
        }
        .formStyle(.grouped)
        .background(Theme.bgPrimary)
    }
}

#Preview {
    ContentView().environmentObject(AppState())
}
