// LaTeXFixer.swift — turns the LaTeX status chip into something
// the user can actually act on. Two pieces:
//
//   1. A real end-to-end pipeline test that compiles a one-line
//      .tex through pdflatex + dvisvgm and reports if it produced
//      a valid .svg. Catches the "exit-254 silent fail" case that
//      the binary-presence probe misses.
//
//   2. A planner that figures out the next fix step and dispatches
//      the appropriate `brew install …` command via TerminalBridge.
//      Each step is one click — install, watch the terminal, re-probe.
//
// Why everything routes through TerminalBridge instead of a hidden
// Process: brew installs print live progress, occasionally need
// password input (for casks moving system files), and can take
// minutes. Showing them in the integrated terminal lets the user
// see exactly what's happening and intervene if something asks
// for confirmation.
import Foundation
import SwiftUI
import Combine

// Class-level @MainActor dropped — Swift 6 can't synthesise
// ObservableObject conformance on an actor-isolated class.
final class LaTeXFixer: ObservableObject {
    static let shared = LaTeXFixer()
    private init() {}

    enum TestResult: Equatable {
        case unknown
        case running
        case passed(svgBytes: Int)
        case failed(stage: Stage, message: String)

        enum Stage: String { case latex, dvisvgm, kpathsea }
    }

    @Published private(set) var test: TestResult = .unknown
    @Published private(set) var brewPath: String? = nil

    /// The next concrete action the user can take to make MathTex
    /// renders work. Computed from the current state of LaTeXProbe
    /// + the end-to-end test result.
    enum NextStep: Equatable {
        case allGood
        case installLatex                // brew install --cask basictex
        case installDvisvgm              // brew install dvisvgm
        case installManimTeXPackages     // sudo tlmgr install …  (always sudo)
        case restartShellForEnvVars      // user has BasicTeX but TEXMF env
                                          // not yet exported (existing shell)
        case noFixerAvailable(String)    // brew not installed, etc.

        var label: String {
            switch self {
            case .allGood:                   return "All good"
            case .installLatex:              return "Install BasicTeX"
            case .installDvisvgm:            return "Install dvisvgm"
            case .installManimTeXPackages:   return "Install missing TeX pkgs"
            case .restartShellForEnvVars:    return "Restart workspace shell"
            case .noFixerAvailable(let why): return "Can't auto-fix: \(why)"
            }
        }
    }

    func detectBrew() {
        for path in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"] {
            if FileManager.default.isExecutableFile(atPath: path) {
                self.brewPath = path
                return
            }
        }
        self.brewPath = nil
    }

    /// Decide the next step based on the probe + test outcome.
    func plan(latex: LaTeXProbe.Status,
              dvisvgm: LaTeXProbe.Status) -> NextStep {
        // Both binaries present + pipeline tests passed → done.
        if latex.isReady, dvisvgm.isReady, case .passed = test {
            return .allGood
        }
        // Need brew to do auto-installs of either piece.
        let brewReady = (brewPath != nil)

        if !latex.isReady {
            return brewReady
                ? .installLatex
                : .noFixerAvailable("Homebrew not installed")
        }
        if !dvisvgm.isReady {
            return brewReady
                ? .installDvisvgm
                : .noFixerAvailable("Homebrew not installed")
        }
        // Both installed but the pipeline still fails — could be
        // TEXMF env vars (covered by app launch) or missing tlmgr
        // packages (sudo required).
        if case .failed(let stage, _) = test {
            switch stage {
            case .kpathsea:
                return .restartShellForEnvVars
            case .latex, .dvisvgm:
                return .installManimTeXPackages
            }
        }
        return .allGood
    }

    /// Compile a tiny `\(x^2\)` MathTex equivalent through
    /// pdflatex → dvisvgm and verify a non-empty SVG comes out the
    /// other side. Runs off the main thread; publishes back on it.
    func runEndToEndTest() {
        Task.detached(priority: .userInitiated) { [weak self] in
            await MainActor.run { self?.test = .running }
            let outcome = Self.compileAndConvert()
            await MainActor.run { self?.test = outcome }
        }
    }

    // MARK: - actual end-to-end compile

    /// Cooks up a temp dir, writes a small .tex, runs pdflatex, then
    /// dvisvgm. Returns a TestResult describing where (if anywhere)
    /// the pipeline broke.
    private nonisolated static func compileAndConvert() -> TestResult {
        let tmp = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("manimstudio-tex-\(UUID().uuidString.prefix(8))")
        try? FileManager.default.createDirectory(
            at: tmp, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmp) }

        let texSrc = """
        \\documentclass[preview]{standalone}
        \\usepackage{amsmath, amssymb}
        \\begin{document}
        $|AG| = \\sqrt{8^2 + 8^2 + 8^2} = 8\\sqrt{3}$
        \\end{document}
        """
        let texFile = tmp.appendingPathComponent("test.tex")
        do { try texSrc.write(to: texFile, atomically: true, encoding: .utf8) }
        catch { return .failed(stage: .latex,
                               message: "could not write .tex: \(error.localizedDescription)") }

        // 1. pdflatex test.tex (in tmp dir, output-format=dvi)
        guard let pdflatex = findOnPath("pdflatex") else {
            return .failed(stage: .latex, message: "pdflatex not found")
        }
        let latexResult = run(pdflatex.path,
                              args: ["-interaction=nonstopmode",
                                     "-output-format=dvi",
                                     "-output-directory=\(tmp.path)",
                                     texFile.path],
                              cwd: tmp,
                              timeout: .seconds(20))
        let dvi = tmp.appendingPathComponent("test.dvi")
        guard FileManager.default.fileExists(atPath: dvi.path) else {
            let snippet = (latexResult.combinedOutput
                .split(whereSeparator: \.isNewline)
                .suffix(8)
                .joined(separator: "\n"))
            return .failed(stage: .latex,
                           message: snippet.isEmpty ? "pdflatex produced no .dvi"
                                                     : snippet)
        }

        // 2. dvisvgm test.dvi -o test.svg
        guard let dvisvgm = findOnPath("dvisvgm") else {
            return .failed(stage: .dvisvgm, message: "dvisvgm not found")
        }
        let svg = tmp.appendingPathComponent("test.svg")
        let dResult = run(dvisvgm.path,
                          args: ["--page=1", "--no-fonts",
                                 "--verbosity=4",
                                 "--output=\(svg.path)",
                                 dvi.path],
                          cwd: tmp,
                          timeout: .seconds(15))
        if FileManager.default.fileExists(atPath: svg.path) {
            let size = (try? FileManager.default.attributesOfItem(
                atPath: svg.path)[.size] as? Int) ?? 0
            return size > 0
                ? .passed(svgBytes: size)
                : .failed(stage: .dvisvgm, message: "produced 0-byte .svg")
        }
        // No .svg — figure out which sub-failure mode.
        let combined = dResult.combinedOutput.lowercased()
        if combined.contains("texmf.cnf") || combined.contains("kpathsea") {
            return .failed(stage: .kpathsea,
                           message: "dvisvgm couldn't find texmf.cnf — TEXMFROOT/TEXMFCNF not set")
        }
        let snippet = dResult.combinedOutput
            .split(whereSeparator: \.isNewline)
            .suffix(6)
            .joined(separator: "\n")
        return .failed(stage: .dvisvgm,
                       message: snippet.isEmpty ? "exit \(dResult.exitCode)"
                                                 : snippet)
    }

    // MARK: - helpers

    /// Mirror of LaTeXProbe + cleanEnvironment search dirs.
    private nonisolated static var searchDirs: [String] {
        var dirs: [String] = []
        if let p = ProcessInfo.processInfo.environment["PATH"] {
            dirs.append(contentsOf: p.split(separator: ":").map(String.init))
        }
        dirs.append(contentsOf: ["/Library/TeX/texbin",
                                  "/opt/homebrew/bin", "/usr/local/bin"])
        return dirs
    }
    private nonisolated static func findOnPath(_ name: String) -> URL? {
        for dir in searchDirs {
            let url = URL(fileURLWithPath: dir).appendingPathComponent(name)
            if FileManager.default.isExecutableFile(atPath: url.path) {
                return url
            }
        }
        return nil
    }

    private struct ProcResult {
        let exitCode: Int32
        let combinedOutput: String
    }

    /// Runs an executable with the same env injection
    /// TerminalProcessView.cleanEnvironment uses, so the pipeline
    /// test actually exercises the same conditions a real render
    /// would. 5 second default timeout per stage.
    private nonisolated static func run(_ executable: String,
                                        args: [String],
                                        cwd: URL,
                                        timeout: DispatchTimeInterval = .seconds(10))
        -> ProcResult
    {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: executable)
        proc.arguments = args
        proc.currentDirectoryURL = cwd

        var env = ProcessInfo.processInfo.environment
        let extras = ["/opt/homebrew/bin", "/usr/local/bin",
                      "/Library/TeX/texbin"]
        env["PATH"] = (extras + (env["PATH"] ?? "").split(separator: ":")
                                                   .map(String.init))
            .joined(separator: ":")
        // Match the runtime env fix from cleanEnvironment so the
        // test reflects what real renders see — including TEXMFHOME
        // so kpathsea still walks the user-local tree at
        // $HOME/Library/texmf where tlmgr installs to.
        if let texRoot = detectTeXMFRoot() {
            env["TEXMFROOT"] = texRoot.path
            env["TEXMFCNF"] = texRoot
                .appendingPathComponent("texmf-dist/web2c").path
            if let home = env["HOME"] {
                env["TEXMFHOME"] = "\(home)/Library/texmf"
            }
        }
        proc.environment = env

        let out = Pipe(), err = Pipe()
        proc.standardOutput = out
        proc.standardError = err

        do { try proc.run() }
        catch { return ProcResult(exitCode: -1,
                                  combinedOutput: error.localizedDescription) }

        let group = DispatchGroup()
        group.enter()
        DispatchQueue.global().async {
            proc.waitUntilExit()
            group.leave()
        }
        if group.wait(timeout: .now() + timeout) == .timedOut {
            proc.terminate()
            return ProcResult(exitCode: -1, combinedOutput: "timed out")
        }
        let combined = (String(data: out.fileHandleForReading.readDataToEndOfFile(),
                               encoding: .utf8) ?? "")
            + (String(data: err.fileHandleForReading.readDataToEndOfFile(),
                      encoding: .utf8) ?? "")
        return ProcResult(exitCode: proc.terminationStatus,
                          combinedOutput: combined)
    }

    /// Same logic as TerminalProcessView.detectTeXMFRoot — local copy
    /// so this file doesn't depend on TerminalProcessView at compile
    /// time (avoids initialisation cycles).
    private nonisolated static func detectTeXMFRoot() -> URL? {
        let base = URL(fileURLWithPath: "/usr/local/texlive")
        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: base, includingPropertiesForKeys: nil) else { return nil }
        let sorted = entries.sorted {
            $0.lastPathComponent > $1.lastPathComponent
        }
        for url in sorted {
            let cnf = url.appendingPathComponent("texmf-dist/web2c/texmf.cnf")
            if FileManager.default.fileExists(atPath: cnf.path) {
                return url
            }
        }
        return nil
    }
}
