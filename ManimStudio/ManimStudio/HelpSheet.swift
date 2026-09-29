// HelpSheet.swift — in-app help: the header "?" button, ⌘? and ⇧⌘K.
//
// Six sections behind a scrollable chip bar (a segmented control cannot fit
// six labels on an iPhone), and one search field that looks across every
// section at once — searching "stop" should find the shortcut, the guide
// entry and the troubleshooting note from wherever you start.
//
// Keep the content true to the code. Shortcuts are the ones MenuCommands.swift
// binds, plus Monaco defaults checked against the key codes compiled into the
// bundled Monaco: there ⌘L selects a line and ⇧⌥↑ copies one, which an earlier
// version of this sheet listed as "Go to line" and "Expand selection".
import SwiftUI
import UIKit

struct HelpSheet: View {

    enum Tab: String, CaseIterable, Identifiable {
        case whatsNew  = "What's New"
        case guide     = "Guide"
        case shortcuts = "Shortcuts"
        case snippets  = "Snippets"
        case faq       = "FAQ"
        case trouble   = "Troubleshooting"

        var id: String { rawValue }
        var icon: String {
            switch self {
            case .whatsNew:  return "sparkles"
            case .guide:     return "book"
            case .shortcuts: return "keyboard"
            case .snippets:  return "curlybraces"
            case .faq:       return "questionmark.bubble"
            case .trouble:   return "wrench.and.screwdriver"
            }
        }
    }

    /// The release the What's New notes describe. Bump it together with the
    /// notes: the header's Help button shows a dot until the user has opened
    /// notes for this version, so it reappears only when there is news.
    static let notesVersion = "1.5"

    @Environment(\.dismiss) private var dismiss
    /// Same key HeaderView reads to decide whether to show the dot.
    @AppStorage("help_whats_new_seen_version") private var seenVersion = ""
    @State private var tab: Tab
    @State private var query = ""
    @State private var toast: String?

    init(startTab: Tab = .guide) {
        _tab = State(initialValue: startTab)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if query.isEmpty {
                    chipBar
                    Divider()
                }
                content
            }
            .navigationTitle("Help")
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $query,
                        placement: .navigationBarDrawer(displayMode: .always),
                        prompt: "Search all of Help")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .overlay(alignment: .bottom) { toastView }
            .animation(.easeOut(duration: 0.2), value: toast)
            .onChange(of: tab, initial: true) { _, t in
                if t == .whatsNew { seenVersion = Self.notesVersion }
            }
        }
    }

    // MARK: - Navigation

    private var chipBar: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(Tab.allCases) { t in
                        Button {
                            Haptics.selection()
                            tab = t
                        } label: {
                            Label(t.rawValue, systemImage: t.icon)
                                .font(.system(size: 13, weight: tab == t ? .semibold : .regular))
                                .foregroundStyle(tab == t ? Color.white : Theme.textPrimary)
                                .padding(.horizontal, 12).padding(.vertical, 7)
                                .background(Capsule().fill(tab == t ? Theme.accentPrimary : Theme.bgTertiary))
                                .overlay(Capsule().stroke(Theme.borderSubtle,
                                                          lineWidth: tab == t ? 0 : 1))
                        }
                        .buttonStyle(.plain)
                        .id(t)
                    }
                }
                .padding(.horizontal, 12).padding(.vertical, 8)
            }
            .onAppear { proxy.scrollTo(tab, anchor: .center) }
        }
    }

    @ViewBuilder
    private var content: some View {
        if !query.isEmpty {
            searchResults
        } else {
            switch tab {
            case .whatsNew:  whatsNewTab
            case .guide:     topicsList(HelpContent.guide)
            case .shortcuts: shortcutsTab
            case .snippets:  snippetsTab
            case .faq:       faqTab
            case .trouble:   troubleTab
            }
        }
    }

    // MARK: - Sections

    private var whatsNewTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("New in \(Self.notesVersion)")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundStyle(Theme.textPrimary)
                ForEach(HelpContent.whatsNew) { item in
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: item.icon)
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundStyle(Theme.accentPrimary)
                            .frame(width: 28)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.title)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(Theme.textPrimary)
                            md(item.body)
                                .font(.system(size: 13))
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(12)
                    .background(RoundedRectangle(cornerRadius: 10).fill(Theme.bgSecondary))
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.borderSubtle, lineWidth: 1))
                }
            }
            .padding(16)
        }
    }

    private func topicsList(_ topics: [HelpTopic]) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                ForEach(topics) { topicView($0) }
            }
            .padding(16)
        }
    }

    private var shortcutsTab: some View {
        List {
            ForEach(HelpContent.shortcuts) { group in
                Section(group.name) {
                    ForEach(group.items) { shortcutRow($0) }
                }
            }
            Section {
                Text("Keyboard shortcuts need a hardware keyboard; without one, the row of keys above the on-screen keyboard covers the essentials. The editor ones are Monaco's, the code editor inside the app.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var snippetsTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("**Insert** puts a snippet at the editor's cursor and switches to Workspace.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                ForEach(HelpContent.snippets) { group in
                    Text(group.name)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                        .padding(.top, 4)
                    ForEach(group.items) { snippetCard($0) }
                }
            }
            .padding(16)
        }
    }

    private var faqTab: some View {
        List {
            ForEach(HelpContent.faq) { item in
                DisclosureGroup {
                    md(item.body)
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                        .padding(.top, 4)
                } label: {
                    Text(item.title).font(.system(size: 13, weight: .medium))
                }
            }
        }
    }

    private var troubleTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                ForEach(HelpContent.troubleshooting) { topicView($0) }
                Divider().padding(.vertical, 4)
                Text("Quick actions")
                    .font(.system(size: 13, weight: .semibold))
                if let log = CrashLogger.shared.fileURL {
                    ShareLink(item: log) {
                        actionLabel("Share log file", icon: "square.and.arrow.up")
                    }
                    .buttonStyle(.plain)
                    Button {
                        UIApplication.shared.open(folderURL(log))
                    } label: {
                        actionLabel("Show log file in Files", icon: "doc.text.magnifyingglass")
                    }
                    .buttonStyle(.plain)
                }
                Button {
                    if let u = URL(string: "https://docs.manim.community/") { UIApplication.shared.open(u) }
                } label: {
                    actionLabel("Manim documentation", icon: "book")
                }
                .buttonStyle(.plain)
                Button {
                    if let u = URL(string: "https://github.com/yu314-coder/python-ios-lib/") { UIApplication.shared.open(u) }
                } label: {
                    actionLabel("python-ios-lib (the bundled Python) on GitHub",
                                icon: "chevron.left.forwardslash.chevron.right")
                }
                .buttonStyle(.plain)
            }
            .padding(16)
        }
    }

    // MARK: - Search across every section

    @ViewBuilder
    private var searchResults: some View {
        let hits = HelpContent.search(query)
        if hits.isEmpty {
            ContentUnavailableView.search(text: query)
        } else {
            List {
                ForEach(Tab.allCases) { t in
                    let rows = hits.filter { $0.tab == t }
                    if !rows.isEmpty {
                        Section {
                            ForEach(rows) { hit in
                                Button {
                                    query = ""
                                    tab = t
                                } label: {
                                    hitRow(hit)
                                }
                                .buttonStyle(.plain)
                            }
                        } header: {
                            Label(t.rawValue, systemImage: t.icon)
                        }
                    }
                }
            }
        }
    }

    private func hitRow(_ hit: HelpHit) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(hit.title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
            if hit.mono {
                Text(hit.detail)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(Theme.accentPrimary)
            } else {
                md(hit.detail)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
    }

    // MARK: - Rows

    private func topicView(_ t: HelpTopic) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(t.title)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
            md(t.body)
                .font(.system(size: 13))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func shortcutRow(_ s: HelpShortcut) -> some View {
        HStack {
            Text(s.keys)
                .font(.system(size: 13, design: .monospaced))
                .frame(width: 110, alignment: .leading)
                .foregroundStyle(Theme.accentPrimary)
            Text(s.action).foregroundStyle(Theme.textPrimary)
        }
    }

    private func snippetCard(_ s: HelpSnippet) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(s.name).font(.system(size: 12, weight: .semibold))
                Spacer()
                Button { copy(s) } label: {
                    Label("Copy", systemImage: "doc.on.doc").font(.system(size: 11))
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .tint(Theme.accentPrimary)
                Button { insert(s) } label: {
                    Label("Insert", systemImage: "text.insert")
                        .font(.system(size: 11, weight: .semibold))
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .tint(Theme.accentPrimary)
            }
            Text(s.code)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(Theme.textPrimary)
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 6).fill(Theme.bgSecondary))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.borderSubtle, lineWidth: 1))
                .textSelection(.enabled)
        }
    }

    private func actionLabel(_ title: String, icon: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 13))
                .foregroundStyle(Theme.accentPrimary)
                .frame(width: 24)
            Text(title)
                .font(.system(size: 13))
                .foregroundStyle(Theme.textPrimary)
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 10))
                .foregroundStyle(Theme.textDim)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8).fill(Theme.bgSecondary))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.borderSubtle, lineWidth: 1))
    }

    @ViewBuilder
    private var toastView: some View {
        if let t = toast {
            Text(t)
                .font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 12).padding(.vertical, 8)
                .background(.thinMaterial, in: Capsule())
                .padding(.bottom, 16)
                .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }

    // MARK: - Actions

    private func copy(_ s: HelpSnippet) {
        UIPasteboard.general.string = s.code
        Haptics.selection()
        toast = "Copied: \(s.name)"
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
            if toast == "Copied: \(s.name)" { toast = nil }
        }
    }

    /// Same path the Apple Pencil sketch uses: EditorPane inserts at the
    /// cursor. Then bring the Workspace forward so the result is visible.
    private func insert(_ s: HelpSnippet) {
        NotificationCenter.default.post(name: .editorInsertCode, object: nil,
                                        userInfo: ["code": s.code + "\n\n"])
        NotificationCenter.default.post(name: .menuViewTab, object: nil,
                                        userInfo: ["tab": "workspace"])
        Haptics.impact(.light)
        dismiss()
    }

    /// `shareddocuments://` opens the Files app at a directory.
    private func folderURL(_ fileURL: URL) -> URL {
        URL(string: "shareddocuments://\(fileURL.deletingLastPathComponent().path)") ?? fileURL
    }

    /// Inline Markdown — `code`, **bold**, *italic* — with line breaks kept.
    private func md(_ s: String) -> Text {
        if let a = try? AttributedString(
            markdown: s,
            options: AttributedString.MarkdownParsingOptions(
                interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
            return Text(a)
        }
        return Text(s)
    }
}

// MARK: - Content

struct HelpTopic: Identifiable {
    let title: String
    let body: String
    var id: String { title }
}

struct HelpNewItem: Identifiable {
    let icon: String
    let title: String
    let body: String
    var id: String { title }
}

struct HelpShortcut: Identifiable {
    let keys: String
    let action: String
    var id: String { keys + action }
}

struct HelpShortcutGroup: Identifiable {
    let name: String
    let items: [HelpShortcut]
    var id: String { name }
}

struct HelpSnippet: Identifiable {
    let name: String
    let code: String
    var id: String { name }
}

struct HelpSnippetGroup: Identifiable {
    let name: String
    let items: [HelpSnippet]
    var id: String { name }
}

struct HelpHit: Identifiable {
    let id = UUID()
    let tab: HelpSheet.Tab
    let title: String
    let detail: String
    let mono: Bool
}

enum HelpContent {

    static let whatsNew: [HelpNewItem] = [
        HelpNewItem(icon: "moon.zzz", title: "Renders keep going when you leave",
             body: "On iOS and iPadOS 26, a render or preview keeps running after you switch apps or lock the screen. Its progress shows in a Live Activity, where Cancel works like Stop. Earlier versions give it about 30 seconds, then it pauses until you come back."),
        HelpNewItem(icon: "arrow.up.left.and.arrow.down.right", title: "8K, 12K and 14K",
             body: "8K renders even where the hardware H.264 encoder stops at 4K: the app asks the device which encoder can take the size and uses HEVC when H.264 can't. 12K and 14K join the quality list, and **Custom** sizes have no upper limit."),
        HelpNewItem(icon: "slider.horizontal.3", title: "Encoding controls",
             body: "**Controls → Encoding** picks the encoder (Auto, H.264, HEVC or MPEG-4) and how many frames may wait for it, for Preview and Render alike. The note under Encoder says what this device's hardware can do at the size you've chosen."),
        HelpNewItem(icon: "stop.circle", title: "Stop really stops",
             body: "Stop now answers within moments — including during slow setup before the first frame, like a download or a model fit. Only a single long computation step has to finish first."),
        HelpNewItem(icon: "play.rectangle.on.rectangle", title: "Present any render",
             body: "Present opens a library of every earlier render, not just the latest, and labels each clip with its resolution, codec, frame rate, length and data rate — read from the file itself."),
        HelpNewItem(icon: "shippingbox", title: "More Python works",
             body: "`requests` makes HTTPS calls out of the box, and scikit-learn now imports — two packages it needs were missing before."),
        HelpNewItem(icon: "keyboard", title: "Keys for touch typing",
             body: "A row of extra keys sits above the on-screen keyboard. In the terminal: esc, ctrl, tab, ^C, arrows and the shell's symbols. In the editor: indent and outdent, Python's brackets and symbols, undo, completion and arrows."),
        HelpNewItem(icon: "terminal", title: "Terminal commands",
             body: "Every command in `help` works or says why it can't. `js` and `node` run JavaScript, `tex` compiles plain TeX, `pdflatex`, `md` and `nb` open what they make, and `debug`, `ps` and `test-libs` work. `curl` no longer holds a download in memory. `ai`, `pip` and the C and Fortran compilers are gone — ManimStudio has nothing behind them."),
    ]

    static let guide: [HelpTopic] = [
        HelpTopic(title: "Getting started",
             body: "Write Python in **Workspace**: one or more `class MyScene(Scene):` classes with a `construct(self)` method. Tap **Render** or **Preview**; the video appears in the preview pane and progress streams into the terminal. The **Gallery** has six ready-made scenes to start from."),
        HelpTopic(title: "Render vs Preview",
             body: "Render uses the Final settings (default 1080p at 30 fps). Preview uses its own Quick Preview quality (default 480p at 15 fps) so you can iterate fast — raise it in the right sidebar when you need a closer look. Preview always makes an mp4."),
        HelpTopic(title: "Scene picker",
             body: "When the file has more than one Scene class, the menu next to Render picks one. **All scenes** renders every Scene subclass in source order."),
        HelpTopic(title: "Quality and size",
             body: "Final quality runs from 480p to 14K, plus **Custom** width × height with 9:16, 1:1, 4:5 and 16:9 shortcuts. Custom has no upper limit; sizes are rounded to even numbers, which video encoding requires. Everything above 4K is heavy on memory — keep an eye on the RAM meter."),
        HelpTopic(title: "Encoding",
             body: "**Controls → Encoding → Encoder**: Auto uses the hardware — H.264, or HEVC for sizes H.264 can't take — and falls back to software MPEG-4, which can't encode frames wider or taller than 8191 pixels. **Queue depth** is how many finished frames may wait for the encoder; Auto sizes it to the memory budget, and deeper queues use more memory."),
        HelpTopic(title: "Stopping a render",
             body: "Tap **Stop** (⌘.). It shows *Stopping…* right away and the render ends within moments, even during slow setup before the first frame. A single long step — one very large drawing or matrix operation — has to finish first."),
        HelpTopic(title: "GPU button (lightning)",
             body: "Turns on Metal-accelerated drawing and hardware video encoding. It mostly speeds up the encode; the per-frame Python math usually dominates, so lowering the frame rate or resolution saves more time. Off uses CPU drawing and the software encoder."),
        HelpTopic(title: "Output formats",
             body: "Final Render can make **mp4** (video), **mov** (transparent background, for compositing over other footage), **gif** (looping animation) or **html** (a self-contained player page)."),
        HelpTopic(title: "Presenting",
             body: "**Present** (⌥⌘P) plays a render full-screen on a loop. The stack button lists every earlier render, each labelled with its resolution, codec, frame rate, length and data rate. To show it on a TV or projector, use AirPlay or HDMI screen mirroring."),
        HelpTopic(title: "Sketching with Apple Pencil",
             body: "On iPad, the scribble button in the header opens a canvas. Draw circles, rectangles, polygons, lines or curves, and they come back as editable Manim code at the cursor."),
        HelpTopic(title: "Command palette",
             body: "**⇧⌘P** opens a searchable list of every command — the quickest way around with a keyboard."),
        HelpTopic(title: "LaTeX (Tex / MathTex)",
             body: "Manim's `Tex` and `MathTex` run through busytex. Single-formula math mode is reliable; full-document LaTeX is gated pending a newer pdftex build."),
        HelpTopic(title: "The terminal",
             body: "The terminal in Workspace is a shell with over 100 commands — type `help`. `js` runs JavaScript; `pdflatex` and `tex` compile LaTeX and plain TeX, and the PDF opens in a preview. To download a file use `wget <url>` or `curl -L -o <file> <url>`; plain `curl <url>` shows the start of the response."),
        HelpTopic(title: "Typing on the on-screen keyboard",
             body: "A row of extra keys sits above the keyboard. In the terminal: **esc**, **ctrl** (tap it, then a letter), tab to complete, ^C to interrupt, ^D, ^L to clear the screen, ^U to clear the line, arrows for history, and the shell's symbols. In the editor: indent and outdent, the brackets, colon and other symbols Python needs (brackets close themselves), undo, redo, completion, comment and arrows. Swipe the row sideways for more keys."),
        HelpTopic(title: "Rendering in the background",
             body: "On iOS and iPadOS 26 a render keeps going after you leave the app: a Live Activity shows the scene, the animation it's on and its progress, and **Cancel** there stops it like the Stop button. It runs slower in the background, and the system can still end it if the device is busy. Before iOS 26 the app gets about 30 seconds after you leave; the render then pauses until you return, so keep ManimStudio open for long renders."),
        HelpTopic(title: "Where outputs land",
             body: "`Documents/ToolOutputs/<run>/videos/<resolution>/<scene>.mp4` — in the Files app under **On My iPad → ManimStudio**. The History tab lists them too."),
        HelpTopic(title: "Workspace, Assets, History",
             body: "Workspace is the folder the shell starts in. Assets is for files you import (images, audio, fonts). History lists every render with a thumbnail, share and delete."),
        HelpTopic(title: "Packages tab",
             body: "Lists every bundled Python package — name, version, category, short description. Fully offline; filter by category or search."),
        HelpTopic(title: "Appearance",
             body: "The app uses a fixed dark theme. Pick an accent colour in **Settings → Accent colour** or the palette button in the header; it retints buttons, highlights and the signature gradient across the app."),
    ]

    static let shortcuts: [HelpShortcutGroup] = [
        HelpShortcutGroup(name: "File", items: [
            HelpShortcut(keys: "⌘ N", action: "New file"),
            HelpShortcut(keys: "⌘ O", action: "Open file…"),
            HelpShortcut(keys: "⌘ S", action: "Save…"),
        ]),
        HelpShortcutGroup(name: "Render", items: [
            HelpShortcut(keys: "⌘ R", action: "Render (Final quality)"),
            HelpShortcut(keys: "⇧ ⌘ R", action: "Preview (Quick Preview quality)"),
            HelpShortcut(keys: "⌘ .", action: "Stop"),
            HelpShortcut(keys: "⌥ ⌘ P", action: "Present"),
            HelpShortcut(keys: "⌥ ⌘ G", action: "Toggle GPU acceleration"),
        ]),
        HelpShortcutGroup(name: "View", items: [
            HelpShortcut(keys: "⇧ ⌘ P", action: "Command palette"),
            HelpShortcut(keys: "⌘ 1", action: "Gallery"),
            HelpShortcut(keys: "⌘ 2", action: "Workspace"),
            HelpShortcut(keys: "⌘ 3", action: "Assets"),
            HelpShortcut(keys: "⌘ 4", action: "Packages"),
            HelpShortcut(keys: "⌘ 5", action: "History"),
            HelpShortcut(keys: "⌘ 6", action: "System"),
            HelpShortcut(keys: "⌘ \\", action: "Toggle right sidebar"),
        ]),
        HelpShortcutGroup(name: "Editor", items: [
            HelpShortcut(keys: "⌘ F", action: "Find"),
            HelpShortcut(keys: "⌥ ⌘ F", action: "Find and replace"),
            HelpShortcut(keys: "⌘ G", action: "Find next"),
            HelpShortcut(keys: "⇧ ⌘ G", action: "Find previous"),
            HelpShortcut(keys: "⌘ /", action: "Toggle line comment"),
            HelpShortcut(keys: "⌘ ]", action: "Indent"),
            HelpShortcut(keys: "⌘ [", action: "Outdent"),
            HelpShortcut(keys: "⌥ ↑", action: "Move line up"),
            HelpShortcut(keys: "⌥ ↓", action: "Move line down"),
            HelpShortcut(keys: "⇧ ⌥ ↑", action: "Copy line up"),
            HelpShortcut(keys: "⇧ ⌥ ↓", action: "Copy line down"),
            HelpShortcut(keys: "⇧ ⌘ D", action: "Duplicate selection"),
            HelpShortcut(keys: "⌥ ⌘ I", action: "Format document"),
            HelpShortcut(keys: "⌃ Space", action: "Show completions"),
        ]),
        HelpShortcutGroup(name: "Selection", items: [
            HelpShortcut(keys: "⌘ A", action: "Select all"),
            HelpShortcut(keys: "⌘ L", action: "Select line"),
            HelpShortcut(keys: "⌘ D", action: "Add next match to selection"),
        ]),
        HelpShortcutGroup(name: "Help", items: [
            HelpShortcut(keys: "⌘ ?", action: "Open Help"),
            HelpShortcut(keys: "⇧ ⌘ K", action: "Keyboard shortcuts"),
        ]),
        HelpShortcutGroup(name: "Terminal", items: [
            HelpShortcut(keys: "help", action: "List every command"),
            HelpShortcut(keys: "ls / cd", action: "Browse files"),
            HelpShortcut(keys: "clear", action: "Clear the terminal"),
            HelpShortcut(keys: "top / htop", action: "CPU and memory snapshot"),
            HelpShortcut(keys: "wget <url>", action: "Download a file"),
            HelpShortcut(keys: "⌃ C", action: "Interrupt the running command"),
        ]),
    ]

    static let snippets: [HelpSnippetGroup] = [
        HelpSnippetGroup(name: "Manim", items: [
            HelpSnippet(name: "Hello scene", code: """
                from manim import *

                class Hello(Scene):
                    def construct(self):
                        t = Text("Hello, ManimStudio!")
                        self.play(Write(t))
                        self.wait(1)
                """),
            HelpSnippet(name: "Fade between two formulas", code: """
                from manim import *

                class FadeMath(Scene):
                    def construct(self):
                        a = MathTex(r"e^{i\\pi} + 1 = 0")
                        b = MathTex(r"\\int_0^1 x^2\\,dx = \\tfrac{1}{3}")
                        self.play(Write(a))
                        self.wait(0.5)
                        self.play(ReplacementTransform(a, b))
                        self.wait(1)
                """),
            HelpSnippet(name: "Move and recolor", code: """
                from manim import *

                class Move(Scene):
                    def construct(self):
                        dot = Dot(LEFT * 3, color=YELLOW)
                        self.add(dot)
                        self.play(dot.animate.shift(RIGHT * 6).set_color(BLUE), run_time=2)
                """),
            HelpSnippet(name: "Plot a function", code: """
                from manim import *

                class PlotSine(Scene):
                    def construct(self):
                        axes = Axes(x_range=[-PI, PI, PI / 2], y_range=[-1.5, 1.5, 0.5])
                        graph = axes.plot(lambda x: np.sin(x), color=BLUE)
                        self.play(Create(axes))
                        self.play(Create(graph), run_time=2)
                        self.wait(1)
                """),
            HelpSnippet(name: "Animate a changing value", code: """
                from manim import *

                class Tracker(Scene):
                    def construct(self):
                        t = ValueTracker(0)
                        dot = always_redraw(lambda: Dot(RIGHT * t.get_value(), color=YELLOW))
                        label = always_redraw(lambda: DecimalNumber(t.get_value()).next_to(dot, UP))
                        self.add(dot, label)
                        self.play(t.animate.set_value(3), run_time=2)
                        self.wait(1)
                """),
        ]),
        HelpSnippetGroup(name: "Python", items: [
            HelpSnippet(name: "NumPy and matplotlib", code: """
                import numpy as np, matplotlib.pyplot as plt
                x = np.linspace(0, 2 * np.pi, 200)
                plt.plot(x, np.sin(x))
                plt.savefig("sin.png")  # current folder; /tmp is not writable on iOS
                """),
            HelpSnippet(name: "HTTPS request", code: """
                import requests
                r = requests.get("https://example.com", timeout=15)
                print(r.status_code, len(r.content), "bytes")
                """),
        ]),
    ]

    static let faq: [HelpTopic] = [
        HelpTopic(title: "Why does Preview look lower-res than Render?",
             body: "Preview has its own Quick Preview quality (default 480p at 15 fps), separate from Final Render, so you can iterate fast and still render at full quality. Raise Quick Preview in the right sidebar, or press ⌘R for a Final render."),
        HelpTopic(title: "Where can I find my renders?",
             body: "Files → **On My iPad** (or On My iPhone) → **ManimStudio** → `ToolOutputs`, or the History tab."),
        HelpTopic(title: "The app freezes on launch.",
             body: "Close it once and reopen. The first launch after an update warms up Python and imports manim, NumPy, SciPy and matplotlib (about 10 s); later launches are much faster."),
        HelpTopic(title: "`pip install …` doesn't work.",
             body: "Right — pip is turned off. iOS apps have no writable site-packages, and most wheels need a compiler iOS doesn't allow. The Packages tab lists everything bundled."),
        HelpTopic(title: "Can I use my own fonts?",
             body: "Yes. Add the `.ttf` or `.otf` in Assets, register it, then use its *family name* — `font=` takes a name, not a file path:\n`with register_font('path/to/MyFont.ttf'):`\n`    title = Text('Hello', font='My Font')`"),
        HelpTopic(title: "Why is there no 16K option?",
             body: "16K couldn't complete a render on device, so it was removed; 14K is the top preset. If you had 16K selected, it is now 14K."),
        HelpTopic(title: "Can ManimStudio run AI models?",
             body: "No. ManimStudio makes animations and has no engine for running AI models. The terminal's old `ai` command came from another app and has been removed."),
        HelpTopic(title: "Why does `top` show only this app?",
             body: "iOS sandboxing hides other processes. `top` shows this app's memory and CPU time plus the device-wide numbers iOS exposes (RAM, CPU count, uptime)."),
        HelpTopic(title: "What's in the log file?",
             body: "Python tracebacks, render output and crash backtraces. Share it from **Settings → Diagnostics → Share log file**, or from Troubleshooting here, when reporting a problem."),
    ]

    static let troubleshooting: [HelpTopic] = [
        HelpTopic(title: "Render hangs at \"loading manim…\"",
             body: "The first render of a session imports manim and friends, which can take 10–30 s. Later renders take seconds. If it's still stuck after a minute, force-quit and reopen."),
        HelpTopic(title: "Render produces no video",
             body: "Look for a Python traceback in the terminal; the failing lines are also marked red in the editor. Common causes: a Scene that raises in `construct()`, a missing font file, low storage, or a size the chosen encoder can't take — the note under **Controls → Encoding → Encoder** says which encoder this device can use at your size."),
        HelpTopic(title: "The app closed during a render",
             body: "Usually memory. Lower the Final quality or frame rate, keep **Queue depth** on Auto, and watch the RAM meter. If it keeps happening, share the log file."),
        HelpTopic(title: "Stop takes a moment",
             body: "Stop waits for the step that's running to finish — usually a fraction of a second, longer for one very large frame. Everything after that stops at once."),
        HelpTopic(title: "Editor completion is empty",
             body: "manim, Python builtins and the bundled libraries (NumPy, SciPy, SymPy, matplotlib…) complete from an index that loads with the editor — no setup needed. If it looks incomplete, fully quit and reopen the app."),
        HelpTopic(title: "\"symbol not found in flat namespace\" on import",
             body: "A compiled extension needs a symbol the app doesn't bundle. Share the log file — these are usually small fixes."),
        HelpTopic(title: "Files doesn't show my renders",
             body: "Open Files → **On My iPad** (or On My iPhone) → **ManimStudio** → `ToolOutputs`. Files can take a few seconds to catch up after a render; pull down to refresh."),
    ]

    /// Every entry whose text contains `query`, across all sections.
    static func search(_ query: String) -> [HelpHit] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return [] }
        func matches(_ parts: String...) -> Bool {
            parts.contains { $0.lowercased().contains(needle) }
        }
        var hits: [HelpHit] = []
        for n in whatsNew where matches(n.title, n.body) {
            hits.append(HelpHit(tab: .whatsNew, title: n.title, detail: n.body, mono: false))
        }
        for t in guide where matches(t.title, t.body) {
            hits.append(HelpHit(tab: .guide, title: t.title, detail: t.body, mono: false))
        }
        for g in shortcuts {
            for s in g.items where matches(g.name, s.keys, s.action) {
                hits.append(HelpHit(tab: .shortcuts, title: s.action, detail: s.keys, mono: true))
            }
        }
        for g in snippets {
            for s in g.items where matches(g.name, s.name, s.code) {
                hits.append(HelpHit(tab: .snippets, title: s.name, detail: g.name, mono: false))
            }
        }
        for t in faq where matches(t.title, t.body) {
            hits.append(HelpHit(tab: .faq, title: t.title, detail: t.body, mono: false))
        }
        for t in troubleshooting where matches(t.title, t.body) {
            hits.append(HelpHit(tab: .trouble, title: t.title, detail: t.body, mono: false))
        }
        return hits
    }
}
