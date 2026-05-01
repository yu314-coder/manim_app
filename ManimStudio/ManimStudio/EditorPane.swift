// EditorPane.swift — code editor panel hosting Monaco in WKWebView.
import SwiftUI

struct EditorPane: View {
    @Binding var source: String
    @State private var fontSize: CGFloat = 14
    @State private var monaco = MonacoController()

    @State private var showStructure = false
    @State private var showShortcuts = false

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
                Text("Code Editor").font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()

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
