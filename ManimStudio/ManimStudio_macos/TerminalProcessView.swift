// TerminalProcessView.swift — real PTY-backed terminal hosted in
// the macOS workspace. Uses SwiftTerm's `LocalProcessTerminalView`
// (an NSView subclass) which spawns `/bin/zsh -i` over a real
// `openpty()` pair and emulates xterm-256color, so everything from
// `top` to `vim` to `htop` works identically to Terminal.app.
//
// Visual: deep-navy background that matches the editor + preview,
// custom ANSI palette (indigo/violet/pink keys to fit the theme),
// header strip with Clear / font-size / Send-Render buttons that
// matches the editor and preview headers.
//
// Mouse + scroll: SwiftTerm handles drag-to-select (⌘C copies),
// right-click → Copy/Paste, and scroll-wheel scrollback by default.
// We set selectedTextBackgroundColor explicitly so the selection
// is visible against the dark background.
//
// On first prompt we `cd` to Documents/ManimStudio/ and source the
// venv's activate script, so `python -m manim render scene.py
// SceneName` works with no extra config.
import SwiftUI
import AppKit
import SwiftTerm

struct TerminalProcessView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var venv: VenvManager

    var body: some View {
        VStack(spacing: 0) {
            header
            _TerminalContainer(venv: venv,
                               fontSize: CGFloat(app.terminalFontSize))
        }
        .background(Theme.bgDeepest)
    }

    // MARK: header — matches editor + preview header style

    private var header: some View {
        HStack(spacing: 8) {
            Image(systemName: "terminal.fill")
                .font(.system(size: 11))
                .foregroundStyle(Theme.indigo)
            Text("Terminal")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
            Text("zsh · venv \(venv.phase == .ready ? "active" : "—")")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(Theme.textDim)
            Spacer()

            Menu {
                ForEach([10, 11, 12, 13, 14, 15, 16, 18, 20], id: \.self) { sz in
                    Button("\(sz)pt") { app.terminalFontSize = Double(sz) }
                }
            } label: {
                Text("\(Int(app.terminalFontSize))pt")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.textSecondary)
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(RoundedRectangle(cornerRadius: 5)
                        .fill(Theme.bgTertiary))
            }
            .menuStyle(.borderlessButton)
            .frame(width: 50)
            .help("Font size")

            iconBtn("eraser", "Clear (⌘K)") {
                TerminalBridge.shared.runInShell("clear")
            }
            iconBtn("xmark.circle", "Send Ctrl-C") {
                TerminalBridge.shared.interrupt()
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 7)
        .background(Theme.bgSecondary)
        .overlay(Rectangle().fill(Theme.borderSubtle).frame(height: 1),
                 alignment: .bottom)
    }

    @ViewBuilder
    private func iconBtn(_ icon: String, _ help: String,
                         action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary)
                .frame(width: 24, height: 24)
                .background(RoundedRectangle(cornerRadius: 6)
                    .fill(Theme.bgTertiary))
        }
        .buttonStyle(.plain)
        .help(help)
    }
}

// MARK: - NSViewRepresentable wrapping SwiftTerm's PTY view

/// The actual SwiftTerm host. Wrapped in an NSView so the SwiftUI
/// side can apply edge insets without fighting auto-layout inside
/// LocalProcessTerminalView.
private struct _TerminalContainer: NSViewRepresentable {
    @ObservedObject var venv: VenvManager
    var fontSize: CGFloat

    func makeNSView(context: Context) -> _TerminalHostView {
        let host = _TerminalHostView(frame: .zero)
        let term = host.term

        applyTheme(to: term, fontSize: fontSize)
        term.processDelegate = context.coordinator

        // Register the send-text callback so RenderManager can push
        // commands into the same shell the user types into.
        TerminalBridge.shared.sendCommand = { [weak term] text in
            term?.send(txt: text)
        }

        // Spawn /bin/zsh -l -i so ~/.zshrc is sourced. After spawn,
        // chdir to the docs working dir and source the venv's
        // activate script so the prompt shows (manimstudio).
        let cwd = TerminalProcessView.workingDirectory()
        let env = TerminalProcessView.cleanEnvironment(forVenv: venv)
        let envStrings = env.map { "\($0.key)=\($0.value)" }
        let shell = TerminalProcessView.preferredShell()

        term.startProcess(executable: shell,
                          args: ["-l", "-i"],
                          environment: envStrings,
                          execName: shell)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
            term.send(txt: "cd \(cwd.path.shellQuoted())\n")
            if let act = TerminalProcessView.activateScript(for: venv) {
                term.send(txt: "source \(act.path.shellQuoted())\n")
            }
            term.send(txt: "clear\n")
        }
        return host
    }

    func updateNSView(_ nsView: _TerminalHostView, context: Context) {
        // Re-apply font when the user changes terminalFontSize.
        if nsView.term.font.pointSize != fontSize {
            nsView.term.font = NSFont.userFixedPitchFont(ofSize: fontSize)
                ?? NSFont.monospacedSystemFont(ofSize: fontSize, weight: .regular)
        }
    }

    func makeCoordinator() -> Coord { Coord() }

    private func applyTheme(to term: LocalProcessTerminalView,
                            fontSize: CGFloat) {
        // SF Mono via userFixedPitchFont — falls back to monospaced
        // system on platforms where SF Mono isn't installed.
        term.font = NSFont.userFixedPitchFont(ofSize: fontSize)
            ?? NSFont.monospacedSystemFont(ofSize: fontSize, weight: .regular)

        // Background matches the editor (#0E0F18) so the bottom of
        // the workspace feels continuous, not a black strip.
        term.nativeBackgroundColor = NSColor(red: 0x0E/255.0,
                                             green: 0x0F/255.0,
                                             blue: 0x18/255.0,
                                             alpha: 1.0)
        term.nativeForegroundColor = NSColor(red: 0xEC/255.0,
                                             green: 0xEC/255.0,
                                             blue: 0xF1/255.0,
                                             alpha: 1.0)
        // Drag-select highlight — visible against the deep navy bg.
        term.selectedTextBackgroundColor = NSColor(red: 0x3A/255.0,
                                                   green: 0x3D/255.0,
                                                   blue: 0x75/255.0,
                                                   alpha: 1.0)
        term.caretColor = NSColor(red: 0x7B/255.0,
                                  green: 0x86/255.0,
                                  blue: 0xFF/255.0,
                                  alpha: 1.0)

        // 16-color ANSI palette — keeps stack traces / pip output
        // legible while staying in the indigo/violet visual language.
        term.installColors([
            // 0..7 — standard
            sc(0x1B, 0x1D, 0x2A),  // black  (slightly lifted from pure)
            sc(0xFF, 0x6E, 0x6E),  // red
            sc(0x8F, 0xD8, 0x6A),  // green
            sc(0xF5, 0xA0, 0x31),  // yellow
            sc(0x7B, 0x86, 0xFF),  // blue
            sc(0xC4, 0x9A, 0xFF),  // magenta (violet)
            sc(0x5B, 0xBC, 0xFF),  // cyan
            sc(0xEC, 0xEC, 0xF1),  // white
            // 8..15 — bright variants
            sc(0x4A, 0x4D, 0x60),  // bright black (mid-grey)
            sc(0xFF, 0x9E, 0x9E),  // bright red
            sc(0xB7, 0xF0, 0x96),  // bright green
            sc(0xFF, 0xC8, 0x70),  // bright yellow
            sc(0xA0, 0xAB, 0xFF),  // bright blue
            sc(0xDB, 0xBE, 0xFF),  // bright magenta
            sc(0x8A, 0xD3, 0xFF),  // bright cyan
            sc(0xFF, 0xFF, 0xFF),  // bright white
        ])
    }

    /// Shorthand for SwiftTerm.Color from 8-bit RGB bytes.
    private func sc(_ r: Int, _ g: Int, _ b: Int) -> SwiftTerm.Color {
        // SwiftTerm.Color uses 16-bit channels (0..65535). Replicate
        // each byte (e.g. 0xFF → 0xFFFF) for the full range.
        SwiftTerm.Color(red: UInt16(r) << 8 | UInt16(r),
                        green: UInt16(g) << 8 | UInt16(g),
                        blue:  UInt16(b) << 8 | UInt16(b))
    }

    final class Coord: NSObject, LocalProcessTerminalViewDelegate {
        // SwiftTerm's protocol mixes parameter types — sizeChanged
        // and setTerminalTitle take the concrete LocalProcessTerminalView,
        // while hostCurrentDirectoryUpdate and processTerminated take
        // the base TerminalView. Match exactly or the conformance
        // synthesis fails.
        func sizeChanged(source: SwiftTerm.LocalProcessTerminalView,
                         newCols: Int, newRows: Int) {}
        func setTerminalTitle(source: SwiftTerm.LocalProcessTerminalView,
                              title: String) {}
        func hostCurrentDirectoryUpdate(source: SwiftTerm.TerminalView,
                                        directory: String?) {}
        func processTerminated(source: SwiftTerm.TerminalView,
                               exitCode: Int32?) {
            // Auto-restart so the user always has a live shell. ~300ms
            // delay so we don't spin in a crash loop if zsh refuses.
            guard let local = source as? LocalProcessTerminalView else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                local.startProcess(executable: TerminalProcessView.preferredShell(),
                                   args: ["-l", "-i"],
                                   execName: TerminalProcessView.preferredShell())
            }
        }
    }
}

// MARK: - host NSView with edge-insets around SwiftTerm

/// Thin NSView that hugs the LocalProcessTerminalView with a small
/// inset so terminal text doesn't crash into the splitview edges.
/// Also stamps the deep-navy background underneath in case the
/// terminal is briefly transparent during init.
private final class _TerminalHostView: NSView {
    let term = LocalProcessTerminalView(frame: .zero)
    private static let inset: CGFloat = 6

    // Autoscroll-during-drag plumbing — see comment block before the
    // monitor closure for the full rationale.
    private var dragMonitor: Any?
    private var dragScrollTimer: Timer?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor(red: 0x0E/255.0,
                                         green: 0x0F/255.0,
                                         blue: 0x18/255.0,
                                         alpha: 1.0).cgColor
        term.translatesAutoresizingMaskIntoConstraints = false
        addSubview(term)
        let i = Self.inset
        NSLayoutConstraint.activate([
            term.leadingAnchor.constraint(equalTo: leadingAnchor, constant: i),
            term.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -i),
            term.topAnchor.constraint(equalTo: topAnchor, constant: i),
            term.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -i),
        ])

        installDragAutoscrollMonitor()
    }
    required init?(coder: NSCoder) { fatalError() }

    deinit {
        if let m = dragMonitor { NSEvent.removeMonitor(m) }
        dragScrollTimer?.invalidate()
    }

    /// Hover I-beam over the terminal so the user knows they can
    /// drag-select. SwiftTerm sets it during selection but not on
    /// hover, which made the UI feel non-clickable.
    override func resetCursorRects() {
        super.resetCursorRects()
        addCursorRect(bounds, cursor: .iBeam)
    }

    // MARK: drag-select autoscroll
    //
    // SwiftTerm's mouseDragged correctly computes an autoscroll delta
    // when the cursor leaves the visible area, but the timer that
    // consumes it is never scheduled (verified — scrollingTimerElapsed
    // has no callers in MacTerminalView.swift). The class's mouse
    // methods are `public`, not `open`, so we can't subclass to fix.
    //
    // Instead we install a local NSEvent monitor that observes
    // leftMouse{Down,Dragged,Up} events without consuming them, and
    // run our own 50 ms timer that scrolls the buffer while a drag
    // is active and the cursor is past the top/bottom of the view.
    private func installDragAutoscrollMonitor() {
        dragMonitor = NSEvent.addLocalMonitorForEvents(
            matching: [.leftMouseDown, .leftMouseDragged, .leftMouseUp]
        ) { [weak self] event in
            self?.handleMouseEvent(event)
            return event  // never consume — let SwiftTerm see it
        }
    }

    private func handleMouseEvent(_ event: NSEvent) {
        // Only act on events targeting our terminal subview.
        guard let win = window, event.window === win else { return }
        let pInWindow = event.locationInWindow
        let pInTerm = term.convert(pInWindow, from: nil)
        let initiallyInside = term.bounds.contains(pInTerm)

        switch event.type {
        case .leftMouseDown:
            // Only start on a click that lands inside the terminal.
            if initiallyInside { startDragScrollTimer() }
        case .leftMouseDragged:
            if dragScrollTimer == nil && initiallyInside {
                // Some drags begin without a leftMouseDown coming
                // through the monitor (e.g. focus changes). Start lazy.
                startDragScrollTimer()
            }
        case .leftMouseUp:
            stopDragScrollTimer()
        default:
            break
        }
    }

    private func startDragScrollTimer() {
        guard dragScrollTimer == nil else { return }
        let t = Timer(timeInterval: 0.05, repeats: true) { [weak self] _ in
            self?.dragTick()
        }
        // .eventTracking so the timer fires WHILE a mouse drag is
        // happening (the default mode is suspended during tracking).
        RunLoop.main.add(t, forMode: .eventTracking)
        RunLoop.main.add(t, forMode: .common)
        dragScrollTimer = t
    }
    private func stopDragScrollTimer() {
        dragScrollTimer?.invalidate()
        dragScrollTimer = nil
    }

    private func dragTick() {
        guard let win = window else { stopDragScrollTimer(); return }
        let pInWindow = win.mouseLocationOutsideOfEventStream
        let p = term.convert(pInWindow, from: nil)
        let h = term.bounds.height

        // SwiftTerm's view uses non-flipped coordinates: y > h means
        // the cursor went above the top edge → user wants to extend
        // selection upward → reveal older lines via scrollUp.
        if p.y > h {
            let over = max(1, Int((p.y - h) / 16))
            term.scrollUp(lines: min(over, 6))
        } else if p.y < 0 {
            let over = max(1, Int(-p.y / 16))
            term.scrollDown(lines: min(over, 6))
        }
    }
}

// MARK: - helpers (used by both wrapper + container)

extension TerminalProcessView {
    /// Where the shell starts each session.
    static func workingDirectory() -> URL {
        let docs = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask).first!
        let dir = docs.appendingPathComponent("ManimStudio", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// Build env for the child shell. Prepend the venv's bin/ to
    /// PATH if it exists — even if we don't `source activate`,
    /// `which python` then resolves to the venv binary.
    static func cleanEnvironment(forVenv venv: VenvManager) -> [String: String] {
        var env = ProcessInfo.processInfo.environment

        // Inject the dirs where common LaTeX / dvisvgm / Homebrew
        // tools live. macOS GUI apps (launchd-spawned) get a tiny
        // $PATH (/usr/bin:/bin:…), missing /opt/homebrew/bin and
        // /Library/TeX/texbin even though the user's interactive
        // shell has them. Without this, `manim` finds latex but then
        // `dvisvgm` fails — which is exactly the .dvi → .svg error
        // the user hit. Order: venv bin > brew > tex > system.
        var pathDirs: [String] = []
        if let py = VenvManager.venvPython {
            pathDirs.append(py.deletingLastPathComponent().path)
            env["VIRTUAL_ENV"] = VenvManager.venvURL.path
            env["VIRTUAL_ENV_PROMPT"] = "manimstudio"
        }
        for dir in ["/opt/homebrew/bin", "/opt/homebrew/sbin",
                    "/usr/local/bin", "/usr/local/sbin",
                    "/Library/TeX/texbin"] {
            if FileManager.default.fileExists(atPath: dir) {
                pathDirs.append(dir)
            }
        }
        let existing = env["PATH"] ?? ""
        env["PATH"] = (pathDirs + existing.split(separator: ":").map(String.init))
            .reduce(into: [String]()) { acc, d in
                if !acc.contains(d) { acc.append(d) }  // de-dup, preserve order
            }
            .joined(separator: ":")

        if let prefix = VenvManager.cairoBrewPrefix {
            env["PKG_CONFIG_PATH"] = "\(prefix.path)/lib/pkgconfig:" +
                (env["PKG_CONFIG_PATH"] ?? "")
        }

        // Surface the user's TeX Live root so Homebrew's dvisvgm
        // can find texmf.cnf + fontmaps. Without TEXMFROOT/TEXMFCNF,
        // brew dvisvgm exits silently with code 254 because its
        // bundled libkpathsea only searches under /opt/homebrew/Cellar
        // — completely missing /usr/local/texlive/<year>basic. Manim
        // then reports "Your installation does not support converting
        // .dvi files to SVG" with no clue why.
        //
        // CRITICAL: also export TEXMFHOME explicitly. Setting
        // TEXMFROOT/TEXMFCNF without TEXMFHOME makes kpathsea ignore
        // the user-local tree at $HOME/Library/texmf, where TeX Live
        // installs *.cls files for unprivileged tlmgr installs.
        // Without it, even an installed `standalone.cls` is invisible
        // to pdflatex spawned from this shell.
        if let texRoot = detectTeXMFRoot() {
            env["TEXMFROOT"] = texRoot.path
            env["TEXMFCNF"] = texRoot
                .appendingPathComponent("texmf-dist/web2c").path
            if let home = env["HOME"] {
                env["TEXMFHOME"] = "\(home)/Library/texmf"
            }
        }

        env["TERM"]      = "xterm-256color"
        env["LC_ALL"]    = env["LC_ALL"] ?? "en_US.UTF-8"
        env["LANG"]      = env["LANG"] ?? "en_US.UTF-8"
        env["COLORTERM"] = "truecolor"
        return env
    }

    /// Finds the user's TeX Live root by scanning /usr/local/texlive
    /// for the newest year-stamped directory that contains
    /// texmf-dist/web2c/texmf.cnf. Works for both BasicTeX
    /// ("2025basic") and full MacTeX ("2025"). Returns nil if no
    /// install is present.
    static func detectTeXMFRoot() -> URL? {
        let base = URL(fileURLWithPath: "/usr/local/texlive")
        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: base, includingPropertiesForKeys: nil)
        else { return nil }
        // Newest first — directory names sort lexicographically by year.
        let sorted = entries.sorted {
            $0.lastPathComponent > $1.lastPathComponent
        }
        for url in sorted {
            let cnf = url.appendingPathComponent(
                "texmf-dist/web2c/texmf.cnf")
            if FileManager.default.fileExists(atPath: cnf.path) {
                return url
            }
        }
        return nil
    }

    /// `bin/activate` for the per-app venv if it exists.
    static func activateScript(for venv: VenvManager) -> URL? {
        guard VenvManager.venvPython != nil else { return nil }
        let url = VenvManager.venvURL
            .appendingPathComponent("bin/activate", isDirectory: false)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    /// Picks the user's default shell (from $SHELL) if it's a known
    /// safe binary, otherwise /bin/zsh.
    static func preferredShell() -> String {
        if let shell = ProcessInfo.processInfo.environment["SHELL"],
           FileManager.default.isExecutableFile(atPath: shell) {
            return shell
        }
        return "/bin/zsh"
    }
}

// MARK: - String shell-quoting

private extension String {
    /// Wrap a path in single quotes safely, escaping any embedded
    /// single quotes via `'\''` so the shell sees one argument.
    func shellQuoted() -> String {
        "'" + self.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}
