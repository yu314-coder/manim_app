// EditorPane.swift — code editor panel hosting Monaco in WKWebView.
import SwiftUI
import UniformTypeIdentifiers

struct EditorPane: View {
    @Binding var source: String
    @State private var fontSize: CGFloat = 14
    @State private var monaco = MonacoController()

    @State private var showStructure = false
    @State private var showShortcuts = false
    @State private var showOpenPicker = false
    @State private var showImagePicker = false
    @State private var openedFilename: String? = nil

    /// Detected Scene class names parsed from the current source code.
    /// Re-parsed each render via SceneDetector — used by the structure popover.
    private var detectedScenes: [String] {
        SceneDetector.detect(in: source)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Title bar — only the three keep-buttons + font size, all wired.
            HStack(spacing: 8) {
                Image(systemName: "chevron.left.forwardslash.chevron.right")
                    .font(.system(size: 11)).foregroundStyle(Theme.accentPrimary)
                Text(openedFilename ?? "Code Editor")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1).truncationMode(.middle)
                Spacer()

                // Open — load a .py file from Files / iCloud / another app.
                // Replaces the buffer; the title bar updates to show the
                // filename so the user knows which file is loaded.
                toolBtn("folder", "Open file") {
                    showOpenPicker = true
                }

                // Insert image — copies a picked image into Assets/
                // and inserts an `ImageMobject(...)` snippet at the
                // cursor pointing at the bundled-in path.
                toolBtn("photo.badge.plus", "Insert image as ImageMobject") {
                    showImagePicker = true
                }

                // Search — opens Monaco's built-in find widget.
                toolBtn("magnifyingglass", "Find (⌘F)") {
                    monaco.showFind()
                }

                // Structure — popover lists detected Scene classes; tapping
                // doesn't navigate yet (no line offsets emitted) but shows
                // the user the outline of their file.
                toolBtn("list.bullet.indent", "Scene Outline") {
                    showStructure.toggle()
                }
                .popover(isPresented: $showStructure, arrowEdge: .top) {
                    structurePopover
                }

                // Shortcut map — sheet with the keyboard shortcuts the
                // editor + app expose.
                toolBtn("keyboard", "Shortcut Map") {
                    showShortcuts.toggle()
                }
                .sheet(isPresented: $showShortcuts) {
                    ShortcutSheet()
                }

                Menu {
                    ForEach([10, 12, 14, 16, 18, 20, 24], id: \.self) { sz in
                        Button("\(sz)px") { fontSize = CGFloat(sz) }
                    }
                } label: {
                    Text("\(Int(fontSize))px")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.textSecondary)
                        .padding(.horizontal, 6).padding(.vertical, 3)
                        .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgTertiary))
                }
                .help("Editor font size")
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(Theme.bgSecondary)
            .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1), alignment: .bottom)

            // Editor body — Monaco in WKWebView.
            ZStack {
                MonacoEditor(text: $source, fontSize: fontSize, controller: monaco)
            }
            .background(Theme.bgPrimary)
        }
        .background(Theme.bgPrimary)
        .background(
            DocumentPicker(
                isPresented: $showOpenPicker,
                contentTypes: [.pythonScript, .plainText, .sourceCode, .text],
                allowsMultiple: false
            ) { urls in
                guard let url = urls.first else { return }
                let scope = url.startAccessingSecurityScopedResource()
                defer { if scope { url.stopAccessingSecurityScopedResource() } }
                if let text = try? String(contentsOf: url, encoding: .utf8) {
                    source = text
                    openedFilename = url.lastPathComponent
                }
            }
        )
        .background(
            DocumentPicker(
                isPresented: $showImagePicker,
                contentTypes: [.image],
                allowsMultiple: false
            ) { urls in
                guard let src = urls.first else { return }
                let scope = src.startAccessingSecurityScopedResource()
                defer { if scope { src.stopAccessingSecurityScopedResource() } }
                let assets = AssetsView.assetsRoot()
                var dst = assets.appendingPathComponent(src.lastPathComponent)
                // Avoid overwrites — append (2) / (3) etc. if needed.
                var n = 2
                while FileManager.default.fileExists(atPath: dst.path) {
                    let stem = (src.lastPathComponent as NSString).deletingPathExtension
                    let ext  = (src.lastPathComponent as NSString).pathExtension
                    dst = assets.appendingPathComponent("\(stem) (\(n)).\(ext)")
                    n += 1
                }
                _ = try? FileManager.default.copyItem(at: src, to: dst)
                let varname = (dst.deletingPathExtension().lastPathComponent
                                .components(separatedBy: CharacterSet.alphanumerics.inverted)
                                .joined(separator: "_"))
                    .lowercased()
                let escaped = dst.path.replacingOccurrences(of: "\\", with: "\\\\")
                                     .replacingOccurrences(of: "\"", with: "\\\"")
                let snippet = "\(varname.isEmpty ? "img" : varname) = ImageMobject(\"\(escaped)\").scale(2)\n"
                monaco.insertCode(snippet)
            }
        )
        // Menu-bar (Magic Keyboard) editor actions — these forward to
        // Monaco's built-in command IDs via the controller's runAction.
        .onReceive(NotificationCenter.default.publisher(for: .menuEditFind))
            { _ in monaco.runAction("actions.find") }
        .onReceive(NotificationCenter.default.publisher(for: .menuEditFindReplace))
            { _ in monaco.runAction("editor.action.startFindReplaceAction") }
        .onReceive(NotificationCenter.default.publisher(for: .menuEditComment))
            { _ in monaco.runAction("editor.action.commentLine") }
        .onReceive(NotificationCenter.default.publisher(for: .menuEditIndent))
            { _ in monaco.runAction("editor.action.indentLines") }
        .onReceive(NotificationCenter.default.publisher(for: .menuEditOutdent))
            { _ in monaco.runAction("editor.action.outdentLines") }
        .onReceive(NotificationCenter.default.publisher(for: .menuEditMoveUp))
            { _ in monaco.runAction("editor.action.moveLinesUpAction") }
        .onReceive(NotificationCenter.default.publisher(for: .menuEditMoveDown))
            { _ in monaco.runAction("editor.action.moveLinesDownAction") }
        .onReceive(NotificationCenter.default.publisher(for: .menuEditDuplicate))
            { _ in monaco.runAction("editor.action.copyLinesDownAction") }
        .onReceive(NotificationCenter.default.publisher(for: .menuEditFormat))
            { _ in
                // Pure-Swift formatter — Monaco doesn't have a Python
                // formatter provider registered (we don't bundle black
                // / ruff). PythonFormatter does whitespace + trailing
                // newline cleanup safely without touching code shape.
                source = PythonFormatter.format(source)
            }
        .onReceive(NotificationCenter.default.publisher(for: .menuEditTriggerSuggest))
            { _ in monaco.runAction("editor.action.triggerSuggest") }
        // Render-error gutter markers — populated from a parsed
        // Python traceback in ContentView.logStream_done.
        .onReceive(NotificationCenter.default.publisher(for: .editorSetMarkers)) { note in
            if let markers = note.userInfo?["markers"] as? [MonacoEditorView.EditorMarker] {
                monaco.setMarkers(markers)
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .editorClearMarkers))
            { _ in monaco.setMarkers([]) }
    }

    @ViewBuilder
    private func toolBtn(_ icon: String, _ tooltip: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 26, height: 26)
                .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgTertiary))
        }
        .buttonStyle(.plain)
        .help(tooltip)
    }

    @ViewBuilder
    private var structurePopover: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Scene Outline")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
            if detectedScenes.isEmpty {
                Text("No Scene classes detected.\nDefine `class MyScene(Scene)` to populate.")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textSecondary)
            } else {
                ForEach(detectedScenes, id: \.self) { name in
                    HStack(spacing: 6) {
                        Image(systemName: "rectangle.stack").font(.system(size: 10))
                            .foregroundStyle(Theme.accentPrimary)
                        Text(name).font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(Theme.textPrimary)
                    }
                }
            }
        }
        .padding(14)
        .frame(minWidth: 240)
    }
}

/// Modal sheet showing keyboard shortcuts for the editor + app.
private struct ShortcutSheet: View {
    @Environment(\.dismiss) private var dismiss

    private let groups: [(String, [(String, String)])] = [
        ("Editor", [
            ("⌘ F", "Find"),
            ("⌘ ⌥ F", "Find & Replace"),
            ("⌘ /", "Toggle line comment"),
            ("⌘ ]", "Indent"),
            ("⌘ [", "Outdent"),
            ("⌥ ↑ / ↓", "Move line up/down"),
            ("⌃ Space", "Trigger completion"),
        ]),
        ("App", [
            ("F5", "Render (full quality)"),
            ("F6", "Preview (low quality)"),
            ("Esc", "Stop render"),
        ]),
    ]

    var body: some View {
        NavigationStack {
            List {
                ForEach(groups, id: \.0) { group in
                    Section(group.0) {
                        ForEach(group.1, id: \.0) { row in
                            HStack {
                                Text(row.0)
                                    .font(.system(size: 13, design: .monospaced))
                                    .frame(width: 110, alignment: .leading)
                                    .foregroundStyle(Theme.accentPrimary)
                                Text(row.1)
                                    .foregroundStyle(Theme.textPrimary)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Keyboard Shortcuts")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
