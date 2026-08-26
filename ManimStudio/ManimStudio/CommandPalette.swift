// CommandPalette.swift — ⇧⌘P quick-action palette (VS Code style).
//
// A keyboard-first overlay for iPad: type to filter, ↑/↓ to move, Return
// to run, Esc to dismiss (tap a row or the dimmed backdrop also work). It
// reuses the exact same NSNotifications the menu bar posts, so every
// action already has a handler in ContentView / EditorPane — the palette
// adds zero new dispatch logic. Opened via ⇧⌘P (declared in MenuCommands)
// which posts `.menuOpenCommandPalette`, shown by ContentView as an overlay.
import SwiftUI

struct PaletteCommand: Identifiable {
    let id = UUID()
    let title: String
    let group: String
    let icon: String
    let shortcut: String?
    let run: () -> Void
}

struct CommandPaletteView: View {
    @Binding var isPresented: Bool
    @ObservedObject private var theme = ThemeManager.shared

    @State private var query = ""
    @State private var selection = 0
    @FocusState private var searchFocused: Bool

    private static func post(_ n: Notification.Name, _ info: [AnyHashable: Any]? = nil) {
        NotificationCenter.default.post(name: n, object: nil, userInfo: info)
    }

    /// All commands. Tab navigation is generated from AppTab so it stays in
    /// sync; everything posts the same notification the menu bar uses.
    private var commands: [PaletteCommand] {
        var c: [PaletteCommand] = [
            .init(title: "Render (Final quality)", group: "Render", icon: "play.fill", shortcut: "⌘R") { Self.post(.menuRenderRender) },
            .init(title: "Preview (Quick)",        group: "Render", icon: "eye",       shortcut: "⇧⌘R") { Self.post(.menuRenderPreview) },
            .init(title: "Stop render",            group: "Render", icon: "stop.fill", shortcut: "⌘.") { Self.post(.menuRenderStop) },
            .init(title: "Toggle GPU acceleration", group: "Render", icon: "bolt.fill", shortcut: "⌥⌘G") { Self.post(.menuRenderGPU) },
            .init(title: "Delete all renders",      group: "Render", icon: "trash",     shortcut: nil) { Self.post(.menuRenderClearOutputs) },
            .init(title: "Present (full-screen / external display)", group: "Render", icon: "play.rectangle.on.rectangle", shortcut: "⌥⌘P") { Self.post(.menuRenderPresent) },

            .init(title: "New file",  group: "File", icon: "doc.badge.plus",        shortcut: "⌘N") { Self.post(.menuFileNew) },
            .init(title: "Open file…", group: "File", icon: "folder",               shortcut: "⌘O") { Self.post(.menuFileOpen) },
            .init(title: "Save…",     group: "File", icon: "square.and.arrow.down", shortcut: "⌘S") { Self.post(.menuFileSave) },

            .init(title: "Find",            group: "Code", icon: "magnifyingglass", shortcut: "⌘F") { Self.post(.menuEditFind) },
            .init(title: "Find & Replace",  group: "Code", icon: "text.magnifyingglass", shortcut: "⌥⌘F") { Self.post(.menuEditFindReplace) },
            .init(title: "Format document", group: "Code", icon: "wand.and.stars",  shortcut: "⌥⌘I") { Self.post(.menuEditFormat) },
            .init(title: "Toggle line comment", group: "Code", icon: "text.line.first.and.arrowtriangle.forward", shortcut: "⌘/") { Self.post(.menuEditComment) },

            .init(title: "Toggle right sidebar", group: "View", icon: "sidebar.right", shortcut: "⌘\\") { Self.post(.menuViewToggleSidebar) },
            .init(title: "Sketch with Apple Pencil → Manim", group: "Tools", icon: "scribble.variable", shortcut: nil) { Self.post(.menuOpenSketch) },
        ]
        for (i, tab) in AppTab.allCases.enumerated() {
            c.append(.init(title: "Go to \(tab.title)", group: "Navigate",
                           icon: tab.icon, shortcut: "⌘\(i + 1)") {
                Self.post(.menuViewTab, ["tab": tab.rawValue])
            })
        }
        c += [
            .init(title: "Settings",          group: "App", icon: "gearshape",            shortcut: nil) { Self.post(.menuHelpOpenSettings) },
            .init(title: "Help",              group: "App", icon: "questionmark.circle",  shortcut: "⌘?") { Self.post(.menuHelpOpenHelp) },
            .init(title: "Keyboard shortcuts", group: "App", icon: "keyboard",            shortcut: "⇧⌘K") { Self.post(.menuHelpShortcuts) },
            .init(title: "Open log file",     group: "App", icon: "doc.text.magnifyingglass", shortcut: nil) { Self.post(.menuHelpOpenLog) },
        ]
        return c
    }

    private var filtered: [PaletteCommand] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return commands }
        return commands.filter {
            $0.title.lowercased().contains(q) || $0.group.lowercased().contains(q)
        }
    }

    var body: some View {
        ZStack(alignment: .top) {
            Color.black.opacity(0.4).ignoresSafeArea()
                .onTapGesture { isPresented = false }

            VStack(spacing: 0) {
                searchField
                Divider().overlay(Theme.borderSubtle)
                list
            }
            .frame(maxWidth: 560)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Theme.bgSecondary)
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(Theme.borderSubtle, lineWidth: 1))
            )
            .shadow(color: .black.opacity(0.45), radius: 24, y: 10)
            .padding(.top, 72)
            .padding(.horizontal, 24)
        }
        .onAppear { selection = 0; searchFocused = true }
        .onChange(of: query) { _, _ in selection = 0 }
        // Arrow / Esc handling — Return is handled by the field's onSubmit.
        .onKeyPress(.downArrow) { move(1);  return .handled }
        .onKeyPress(.upArrow)   { move(-1); return .handled }
        .onKeyPress(.escape)    { isPresented = false; return .handled }
    }

    private var searchField: some View {
        HStack(spacing: 10) {
            Image(systemName: "command")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Theme.accentSecondary)
            TextField("Run a command…", text: $query)
                .textFieldStyle(.plain)
                .font(.system(size: 16))
                .foregroundStyle(Theme.textPrimary)
                .focused($searchFocused)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .onSubmit(runSelected)
            Text("esc")
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundStyle(Theme.textDim)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(Capsule().fill(Theme.bgTertiary))
        }
        .padding(.horizontal, 16).padding(.vertical, 14)
    }

    private var list: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(Array(filtered.enumerated()), id: \.element.id) { idx, cmd in
                        row(cmd, active: idx == selection)
                            .id(idx)
                            .onTapGesture { run(cmd) }
                    }
                    if filtered.isEmpty {
                        Text("No matching command")
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.textDim)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 20)
                    }
                }
                .padding(8)
            }
            .frame(maxHeight: 360)
            .onChange(of: selection) { _, s in
                withAnimation(.easeOut(duration: 0.1)) { proxy.scrollTo(s, anchor: .center) }
            }
        }
    }

    private func row(_ cmd: PaletteCommand, active: Bool) -> some View {
        HStack(spacing: 12) {
            Image(systemName: cmd.icon)
                .font(.system(size: 14))
                .foregroundStyle(active ? .white : Theme.accentSecondary)
                .frame(width: 22)
            VStack(alignment: .leading, spacing: 1) {
                Text(cmd.title)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(active ? .white : Theme.textPrimary)
                Text(cmd.group)
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .tracking(0.5)
                    .foregroundStyle(active ? .white.opacity(0.8) : Theme.textDim)
            }
            Spacer()
            if let s = cmd.shortcut {
                Text(s)
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(active ? .white.opacity(0.9) : Theme.textDim)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 9)
        .background(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(active ? AnyShapeStyle(Theme.signatureGradient) : AnyShapeStyle(Color.clear))
        )
        .contentShape(Rectangle())
        .hoverEffect(.highlight)
    }

    private func move(_ d: Int) {
        guard !filtered.isEmpty else { return }
        selection = (selection + d + filtered.count) % filtered.count
    }

    private func runSelected() {
        guard filtered.indices.contains(selection) else { return }
        run(filtered[selection])
    }

    /// Dismiss first, then fire — so the overlay is gone before an action
    /// that itself presents UI (tab switch, Settings sheet) runs.
    private func run(_ cmd: PaletteCommand) {
        isPresented = false
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.06) { cmd.run() }
    }
}
