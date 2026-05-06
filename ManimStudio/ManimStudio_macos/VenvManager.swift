// VenvManager.swift — manages the per-app virtualenv ManimStudio
// uses for renders. Mirrors the Windows desktop app's
// `manim_studio_default` venv concept.
//
// Default location: ~/Library/Application Support/ManimStudio/venv/
// First-run wizard (WelcomeView) walks the user through:
//   1. picking a host Python
//   2. python -m venv  …
//   3. pip install --upgrade pip
//   4. pip install manim, manim-fonts, numpy, scipy, matplotlib,
//      Pillow [+ kokoro-onnx + webvtt-py if Kokoro toggled]
//   5. import-test manim
//
// Status updates: published once per ~100 ms via a coalescing
// timer so SwiftUI doesn't get hit with hundreds of state changes
// per second when pip is chattering. Solves
// "onChange action tried to update multiple times per frame".
import Foundation
import SwiftUI
import Combine

final class VenvManager: ObservableObject {

    // ── Phase-aware status with rich progress info.
    enum Phase: String, Equatable {
        case idle, checkingDeps, installingDeps,
             creatingVenv, upgradingPip,
             installingPackages, verifying, ready, failed
        var label: String {
            switch self {
            case .idle:               return "Idle"
            case .checkingDeps:       return "Checking system dependencies"
            case .installingDeps:     return "Installing Cairo via Homebrew"
            case .creatingVenv:       return "Creating virtualenv"
            case .upgradingPip:       return "Upgrading pip"
            case .installingPackages: return "Installing Python packages"
            case .verifying:          return "Verifying manim"
            case .ready:              return "Ready"
            case .failed:             return "Failed"
            }
        }
    }

    /// Per-package install state — the wizard renders a checklist.
    struct PackageProgress: Identifiable, Equatable {
        let name: String
        var status: PackageStatus
        var id: String { name }
    }
    enum PackageStatus: Equatable {
        case pending, installing, done, failed(String)
    }

    @Published var phase: Phase = .idle
    @Published var progress: Double = 0
    @Published var currentLine: String = ""
    @Published var log: String = ""
    @Published var packages: [PackageProgress] = []
    @Published var pythonInVenv: URL? = nil
    @Published var manimVersion: String = ""
    @Published var failureReason: String = ""

    /// Coalescing flush — pending state mutations land here, then
    /// `_flush()` fires every ~80 ms to publish them. Without this
    /// SwiftUI's onChange handlers complain about multiple updates
    /// per frame when pip emits hundreds of lines in a burst.
    private var pendingLog: String = ""
    private var pendingLine: String = ""
    private var flushTimer: Timer?

    /// `~/Library/Application Support/ManimStudio/venv/`
    static let venvURL: URL = {
        let appSup = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first!
            .appendingPathComponent("ManimStudio", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: appSup, withIntermediateDirectories: true)
        return appSup.appendingPathComponent("venv", isDirectory: true)
    }()

    static var venvPython: URL? {
        let url = venvURL.appendingPathComponent("bin/python", isDirectory: false)
        return FileManager.default.isExecutableFile(atPath: url.path) ? url : nil
    }

    // Convenience for views that previously used `.status` enum.
    var statusLabel: String { phase.label }
    var isReady: Bool { phase == .ready }

    // MARK: probe

    func probe() async {
        if Self.venvPython == nil {
            await MainActor.run { self.phase = .idle }
            return
        }
        if let v = await runProbeManim() {
            await MainActor.run {
                self.pythonInVenv = Self.venvPython
                self.manimVersion = v
                self.phase = .ready
                self.progress = 1
            }
        } else {
            await MainActor.run { self.phase = .idle }
        }
    }

    // MARK: setup

    /// Drives the entire wizard pipeline. Errors are reported via
    /// `phase = .failed` + `failureReason` rather than thrown.
    /// Brew prefix candidates (apple silicon first, then Intel).
    static let brewPrefixCandidates: [URL] = [
        URL(fileURLWithPath: "/opt/homebrew"),
        URL(fileURLWithPath: "/usr/local"),
    ]
    /// Returns a Homebrew prefix URL where `lib/pkgconfig/cairo.pc`
    /// is present, or nil if Cairo isn't installed.
    static var cairoBrewPrefix: URL? {
        for p in brewPrefixCandidates {
            let pc = p.appendingPathComponent("lib/pkgconfig/cairo.pc")
            if FileManager.default.fileExists(atPath: pc.path) {
                return p
            }
        }
        return nil
    }
    /// Brew binary URL if installed, regardless of Cairo state.
    static var brewBinary: URL? {
        for p in brewPrefixCandidates {
            let bin = p.appendingPathComponent("bin/brew")
            if FileManager.default.isExecutableFile(atPath: bin.path) {
                return bin
            }
        }
        return nil
    }

    func setupFromScratch(host hostPython: URL, installKokoro: Bool = false) async {
        await MainActor.run {
            self.log = ""
            self.failureReason = ""
            self.progress = 0
            self.startFlushTimer()
        }

        // ── Step 0: system dependency check.
        // pycairo + manimpango can't pip-install on a stock macOS
        // because they need Cairo + pkg-config at build time. We
        // detect Homebrew's Cairo install; if missing, run
        // `brew install cairo pkg-config py3cairo pango`.
        await MainActor.run {
            self.phase = .checkingDeps
            self.appendLog("checking for Cairo + pkg-config…")
        }
        if Self.cairoBrewPrefix == nil {
            await MainActor.run {
                self.appendLog("Cairo not found in /opt/homebrew or /usr/local")
            }
            guard let brew = Self.brewBinary else {
                await fail(
                    "Homebrew not installed. ManimStudio needs Cairo, " +
                    "pkg-config, and Pango to compile pycairo + manimpango. " +
                    "Install Homebrew from https://brew.sh, then rerun the " +
                    "wizard.")
                return
            }
            await MainActor.run {
                self.phase = .installingDeps
                self.appendLog("running: \(brew.path) install cairo pkg-config py3cairo pango")
            }
            // brew install can be slow (Cairo + Pango are big).
            let ok = await runProcess(
                executable: brew,
                args: ["install", "cairo", "pkg-config", "py3cairo", "pango"])
            if !ok {
                await fail(
                    "`brew install cairo pkg-config py3cairo pango` failed. " +
                    "Try running it yourself in Terminal — output is in the " +
                    "log above.")
                return
            }
            // Re-check.
            if Self.cairoBrewPrefix == nil {
                await fail(
                    "brew install reported success but cairo.pc still isn't " +
                    "in /opt/homebrew/lib/pkgconfig or /usr/local/lib/pkgconfig.")
                return
            }
        }
        await MainActor.run {
            if let prefix = Self.cairoBrewPrefix {
                self.appendLog("found Cairo at \(prefix.path)")
            }
        }

        // 1. Wipe any half-baked venv.
        try? FileManager.default.removeItem(at: Self.venvURL)
        try? FileManager.default.createDirectory(
            at: Self.venvURL.deletingLastPathComponent(),
            withIntermediateDirectories: true)

        // ── Step 1: create the virtualenv.
        await MainActor.run {
            self.phase = .creatingVenv
            self.progress = 0.05
            self.appendLog("creating virtualenv at \(Self.venvURL.path)")
        }
        let createOK = await runProcess(
            executable: hostPython,
            args: ["-m", "venv", "--clear", Self.venvURL.path])
        guard createOK, let venvPy = Self.venvPython else {
            await fail("`python -m venv` did not produce a runnable interpreter at \(Self.venvURL.path).")
            return
        }
        await MainActor.run { self.progress = 0.15 }

        // ── Step 2: upgrade pip.
        await MainActor.run {
            self.phase = .upgradingPip
            self.appendLog("upgrading pip in venv")
        }
        _ = await runProcess(
            executable: venvPy,
            args: ["-m", "pip", "install", "--upgrade", "pip",
                   "--disable-pip-version-check"])
        await MainActor.run { self.progress = 0.25 }

        // ── Step 3: install packages, one at a time, so the wizard
        // can show per-package progress.
        let pkgs: [String] = {
            var list = ["manim", "manim-fonts",
                        "numpy", "scipy", "matplotlib", "Pillow"]
            if installKokoro {
                list.append(contentsOf: ["kokoro-onnx", "webvtt-py"])
            }
            return list
        }()
        let pkgCount = pkgs.count
        await MainActor.run {
            self.packages = pkgs.map { .init(name: $0, status: .pending) }
            self.phase = .installingPackages
        }
        for (i, name) in pkgs.enumerated() {
            await MainActor.run {
                self.markPackage(name, status: .installing)
                self.appendLog("pip install \(name)")
            }
            let ok = await runProcess(
                executable: venvPy,
                args: ["-m", "pip", "install",
                       "--no-warn-script-location",
                       "--disable-pip-version-check", name])
            await MainActor.run {
                self.markPackage(name, status: ok ? .done
                                          : .failed("pip install failed"))
                let perPackage = 0.65 / Double(pkgCount)
                self.progress = 0.25 + perPackage * Double(i + 1)
            }
            if !ok && (name == "manim" || name == "numpy") {
                // manim and numpy are non-optional — a failure here
                // means the rest will cascade.
                await fail("pip failed to install \(name). See log for details.")
                return
            }
        }

        // ── Step 4: verify manim importable.
        await MainActor.run {
            self.phase = .verifying
            self.progress = 0.95
            self.appendLog("verifying `import manim` …")
        }
        await probe()
        await MainActor.run { self.stopFlushTimer() }
        if phase != .ready {
            await fail("manim installed but failed to import — likely a binary wheel ABI mismatch.")
        }
    }

    private func fail(_ reason: String) async {
        await MainActor.run {
            self.failureReason = reason
            self.phase = .failed
            self.appendLog("[error] \(reason)")
            self.stopFlushTimer()
        }
    }

    // MARK: package list helper

    private func markPackage(_ name: String, status: PackageStatus) {
        guard let i = packages.firstIndex(where: { $0.name == name }) else { return }
        packages[i].status = status
    }

    // MARK: log batching

    @MainActor
    private func startFlushTimer() {
        stopFlushTimer()
        flushTimer = Timer.scheduledTimer(withTimeInterval: 0.08,
                                          repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in self?.flush() }
        }
        if let t = flushTimer { RunLoop.main.add(t, forMode: .common) }
    }
    @MainActor
    private func stopFlushTimer() {
        flushTimer?.invalidate()
        flushTimer = nil
        flush()  // one last drain
    }
    @MainActor
    private func flush() {
        if !pendingLog.isEmpty {
            log += pendingLog
            pendingLog = ""
        }
        if !pendingLine.isEmpty {
            currentLine = pendingLine
            pendingLine = ""
        }
        // Cap log to last ~80 KB so SwiftUI's text view doesn't
        // re-layout megabytes per pip burst.
        if log.count > 80_000 {
            log = String(log.suffix(60_000))
        }
    }
    private func appendLog(_ s: String) {
        pendingLog += s
        if !s.hasSuffix("\n") { pendingLog += "\n" }
    }

    // MARK: subprocess

    private func runProbeManim() async -> String? {
        guard let py = Self.venvPython else { return nil }
        let proc = Process()
        proc.executableURL = py
        proc.arguments = ["-c", "import manim; print(manim.__version__)"]
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = Pipe()
        do {
            try proc.run()
            proc.waitUntilExit()
            if proc.terminationStatus == 0,
               let data = try? pipe.fileHandleForReading.readToEnd(),
               let s = String(data: data, encoding: .utf8) {
                return s.trimmingCharacters(in: .whitespacesAndNewlines)
            }
        } catch { /* fall through */ }
        return nil
    }

    /// Runs a subprocess, streaming stdout/stderr line-by-line into
    /// the pendingLog/pendingLine buffers. Returns true on exit 0.
    private func runProcess(executable: URL, args: [String]) async -> Bool {
        let proc = Process()
        proc.executableURL = executable
        proc.arguments = args

        // Wire Homebrew's pkg-config + headers + libs into the
        // child env so pip install pycairo / manimpango can find
        // Cairo and Pango at build time. Harmless when Cairo isn't
        // installed (the paths just won't exist).
        var env = ProcessInfo.processInfo.environment
        if let prefix = Self.cairoBrewPrefix {
            let pkgConfig = "\(prefix.path)/lib/pkgconfig"
            env["PKG_CONFIG_PATH"] = pkgConfig + ":" + (env["PKG_CONFIG_PATH"] ?? "")
            // Some setup.py scripts honor these directly.
            env["CFLAGS"]  = "-I\(prefix.path)/include " + (env["CFLAGS"] ?? "")
            env["LDFLAGS"] = "-L\(prefix.path)/lib "    + (env["LDFLAGS"] ?? "")
            // Ensure pkg-config itself is on PATH (Apple Silicon brew
            // doesn't add /opt/homebrew/bin to non-shell processes).
            env["PATH"] = "\(prefix.path)/bin:" + (env["PATH"] ?? "")
        }
        proc.environment = env

        let stdout = Pipe(); let stderr = Pipe()
        proc.standardOutput = stdout
        proc.standardError  = stderr

        // Reference-typed line buffers so the escaping
        // readabilityHandler can mutate them across calls.
        final class LineBuf { var s = "" }
        let bufOut = LineBuf()
        let bufErr = LineBuf()

        let drain: (Pipe, LineBuf) -> Void = { [weak self] pipe, buf in
            pipe.fileHandleForReading.readabilityHandler = { handle in
                let data = handle.availableData
                if data.isEmpty { return }
                let chunk = String(data: data, encoding: .utf8) ?? ""
                buf.s += chunk
                while let nl = buf.s.firstIndex(of: "\n") {
                    let line = String(buf.s[..<nl])
                    buf.s = String(buf.s[buf.s.index(after: nl)...])
                    Task { @MainActor [weak self] in
                        self?.pendingLog += line + "\n"
                        self?.pendingLine = line
                    }
                }
            }
        }
        drain(stdout, bufOut)
        drain(stderr, bufErr)

        do {
            try proc.run()
        } catch {
            await MainActor.run {
                self.appendLog("[venv] failed to launch \(executable.lastPathComponent): \(error)")
            }
            return false
        }

        await withCheckedContinuation { continuation in
            proc.terminationHandler = { _ in continuation.resume() }
        }

        stdout.fileHandleForReading.readabilityHandler = nil
        stderr.fileHandleForReading.readabilityHandler = nil
        if !bufOut.s.isEmpty {
            await MainActor.run { self.pendingLog += bufOut.s + "\n" }
        }
        if !bufErr.s.isEmpty {
            await MainActor.run { self.pendingLog += bufErr.s + "\n" }
        }

        return proc.terminationStatus == 0
    }
}
