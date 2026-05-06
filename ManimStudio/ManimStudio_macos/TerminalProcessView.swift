// TerminalProcessView.swift — real PTY-backed terminal hosted in
// the macOS workspace. Uses SwiftTerm's `LocalProcessTerminalView`
// (an NSView subclass) which spawns `/bin/zsh -i` over a real
// `openpty()` pair and emulates xterm-256color, so everything from
// `top` to `vim` to `htop` works identically to Terminal.app.
//
// We auto-activate the per-app venv on first prompt by sourcing
// its activate script and `cd`'ing to Documents/ManimStudio/. That
// makes `python -m manim render scene.py SceneName` run against
// the bundled manim install with no extra config.
import SwiftUI
import AppKit
import SwiftTerm

struct TerminalProcessView: NSViewRepresentable {
    @ObservedObject var venv: VenvManager

    func makeNSView(context: Context) -> LocalProcessTerminalView {
        let term = LocalProcessTerminalView(frame: .zero)

        // ── Visual styling — match the rest of the macOS app.
        term.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
        term.nativeBackgroundColor = NSColor.black
        term.nativeForegroundColor = NSColor(white: 0.93, alpha: 1)

        term.processDelegate = context.coordinator

        // ── Spawn /bin/zsh -i in a working dir under
        // Documents/ManimStudio/. If the venv is ready, source its
        // activate script as the shell's first action so `python`
        // and `manim` resolve to the bundled installs.
        let cwd = TerminalProcessView.workingDirectory()
        var env = TerminalProcessView.cleanEnvironment(forVenv: venv)
        // SwiftTerm passes env as ["KEY=VAL", ...].
        let envStrings = env.map { "\($0.key)=\($0.value)" }
        let shell = TerminalProcessView.preferredShell()

        // We pass `-l -i` to get a login + interactive shell so
        // ~/.zshrc is sourced. After spawn, if we have a venv,
        // immediately `feed` the activate command so the prompt
        // appears with (venv) prefix.
        term.startProcess(executable: shell,
                          args: ["-l", "-i"],
                          environment: envStrings,
                          execName: shell)
        // chdir + activate venv via a one-shot string fed into the
        // PTY a moment after launch, when zsh is ready to read.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
            term.send(txt: "cd \(cwd.path.shellQuoted())\n")
            if let act = TerminalProcessView.activateScript(for: venv) {
                term.send(txt: "source \(act.path.shellQuoted())\n")
            }
            term.send(txt: "clear\n")
        }
        return term
    }

    func updateNSView(_ nsView: LocalProcessTerminalView, context: Context) {}

    func makeCoordinator() -> Coord { Coord() }

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
        // Fully-qualify SwiftTerm.TerminalView — without the module
        // prefix Swift sometimes picks the wrong type even when the
        // signatures are identical, producing the cryptic
        // "Candidate has non-matching type" error.
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

    // MARK: - helpers

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
        // Also surface Homebrew Cairo paths so manim renders work in
        // the terminal too.
        if let prefix = VenvManager.cairoBrewPrefix {
            env["PKG_CONFIG_PATH"] = "\(prefix.path)/lib/pkgconfig:" +
                (env["PKG_CONFIG_PATH"] ?? "")
            env["PATH"] = "\(prefix.path)/bin:" + (env["PATH"] ?? "")
        }
        // Help xterm-256color-aware tools render colors.
        env["TERM"]      = "xterm-256color"
        env["LC_ALL"]    = env["LC_ALL"] ?? "en_US.UTF-8"
        env["LANG"]      = env["LANG"] ?? "en_US.UTF-8"
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
