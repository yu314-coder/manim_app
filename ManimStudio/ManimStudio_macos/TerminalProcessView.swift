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
    }
    required init?(coder: NSCoder) { fatalError() }

    /// Hover I-beam over the terminal so the user knows they can
    /// drag-select. SwiftTerm sets it during selection but not on
    /// hover, which made the UI feel non-clickable.
    override func resetCursorRects() {
        super.resetCursorRects()
        addCursorRect(bounds, cursor: .iBeam)
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
        if let py = VenvManager.venvPython {
            let bin = py.deletingLastPathComponent().path
            env["PATH"] = "\(bin):" + (env["PATH"] ?? "")
            env["VIRTUAL_ENV"] = VenvManager.venvURL.path
            env["VIRTUAL_ENV_PROMPT"] = "manimstudio"
        }
        // Surface Homebrew Cairo paths so manim renders work in the
        // terminal too.
        if let prefix = VenvManager.cairoBrewPrefix {
            env["PKG_CONFIG_PATH"] = "\(prefix.path)/lib/pkgconfig:" +
                (env["PKG_CONFIG_PATH"] ?? "")
            env["PATH"] = "\(prefix.path)/bin:" + (env["PATH"] ?? "")
        }
        env["TERM"]      = "xterm-256color"
        env["LC_ALL"]    = env["LC_ALL"] ?? "en_US.UTF-8"
        env["LANG"]      = env["LANG"] ?? "en_US.UTF-8"
        env["COLORTERM"] = "truecolor"
        return env
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
