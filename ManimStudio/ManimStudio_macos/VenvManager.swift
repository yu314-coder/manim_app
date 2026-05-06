// VenvManager.swift — manages the virtualenv ManimStudio uses for
// renders. Mirrors the desktop app's `manim_studio_default` venv
// concept on macOS.
//
// Default location: ~/Library/Application Support/ManimStudio/venv/
// First-run wizard creates it, pip-installs `manim` + `manim-fonts`
// + `numpy` + `scipy` + `matplotlib` + `kokoro-onnx` (optional).
// RenderManager prefers this venv's `bin/python` over the host
// python3 found by PythonResolver, so the user can pin a known-good
// manim version per-app instead of fighting with their system Python.
import Foundation
import SwiftUI

/// Drops the class-level @MainActor — Swift 6's strict-isolation
/// synthesis of ObservableObject's objectWillChange publisher
/// conflicts with @MainActor when no explicit override is given.
/// All callers (SwiftUI Tasks) default to MainActor anyway, so the
/// @Published mutations land on main; the streaming onLine
/// callbacks inside setupFromScratch explicitly hop to MainActor
/// before mutating .status.
final class VenvManager: ObservableObject {

    enum Status: Equatable {
        case unknown
        case missing
        case creating(progress: Double, log: String)
        case installing(progress: Double, log: String)
        case ready
        case failed(String)
    }

    @Published var status: Status = .unknown
    @Published var pythonInVenv: URL? = nil
    @Published var manimVersion: String = ""

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

    /// Path to the venv python (if it exists and is executable).
    static var venvPython: URL? {
        let url = venvURL.appendingPathComponent("bin/python", isDirectory: false)
        return FileManager.default.isExecutableFile(atPath: url.path) ? url : nil
    }

    /// Probe the venv: does it exist? Does it have manim?
    func probe() async {
        if Self.venvPython == nil {
            status = .missing
            return
        }
        // Run `python -c "import manim; print(manim.__version__)"`.
        if let v = await runProbeManim() {
            pythonInVenv = Self.venvPython
            manimVersion = v
            status = .ready
        } else {
            status = .missing  // venv exists but manim missing — re-install
        }
    }

    /// First-run wizard target: create the venv, then pip-install manim.
    func setupFromScratch(
        host hostPython: URL,
        installKokoro: Bool = false
    ) async {
        // 1. Wipe any half-baked venv.
        try? FileManager.default.removeItem(at: Self.venvURL)
        try? FileManager.default.createDirectory(
            at: Self.venvURL.deletingLastPathComponent(),
            withIntermediateDirectories: true)

        status = .creating(progress: 0.05,
                           log: "creating virtualenv at \(Self.venvURL.path)…\n")
        let createOK = await runProcess(
            executable: hostPython,
            args: ["-m", "venv", "--clear", Self.venvURL.path],
            onLine: { [weak self] line in
                Task { @MainActor [weak self] in
                    guard let self = self else { return }
                    if case .creating(let p, let log) = self.status {
                        self.status = .creating(progress: p, log: log + line + "\n")
                    }
                }
            }
        )
        guard createOK, let venvPy = Self.venvPython else {
            status = .failed("`python -m venv` did not produce a runnable interpreter")
            return
        }

        // 2. pip install --upgrade pip
        status = .installing(progress: 0.15, log: "")
        _ = await runProcess(
            executable: venvPy,
            args: ["-m", "pip", "install", "--upgrade", "pip",
                   "--disable-pip-version-check"],
            onLine: { [weak self] line in
                Task { @MainActor [weak self] in
                    guard let self = self else { return }
                    if case .installing(let p, let log) = self.status {
                        self.status = .installing(progress: p, log: log + line + "\n")
                    }
                }
            }
        )

        // 3. The big one: manim + numpy + scipy + matplotlib + Pillow.
        var packages = ["manim", "numpy", "scipy", "matplotlib", "Pillow",
                        "manim-fonts"]
        if installKokoro {
            packages.append(contentsOf: ["kokoro-onnx", "webvtt-py"])
        }
        status = .installing(
            progress: 0.30,
            log: "installing \(packages.joined(separator: ", "))…\n")
        let pipOK = await runProcess(
            executable: venvPy,
            args: ["-m", "pip", "install",
                   "--no-warn-script-location",
                   "--disable-pip-version-check"] + packages,
            onLine: { [weak self] line in
                Task { @MainActor [weak self] in
                    guard let self = self else { return }
                    if case .installing(let p, let log) = self.status {
                        let bumped = min(0.95, p + 0.001)
                        self.status = .installing(
                            progress: bumped, log: log + line + "\n")
                    }
                }
            }
        )
        if !pipOK {
            status = .failed("pip install failed — check the log above")
            return
        }

        // 4. Verify manim is importable.
        await probe()
        if case .ready = status {
            // happy path
        } else {
            status = .failed("manim installed but failed to import — likely a binary wheel ABI mismatch")
        }
    }

    // MARK: process runner

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

    private func runProcess(
        executable: URL,
        args: [String],
        onLine: @escaping (String) -> Void
    ) async -> Bool {
        let proc = Process()
        proc.executableURL = executable
        proc.arguments = args

        let stdout = Pipe(); let stderr = Pipe()
        proc.standardOutput = stdout
        proc.standardError  = stderr

        // Buffer per-pipe so we can split on \n safely.
        nonisolated(unsafe) var bufOut = ""
        nonisolated(unsafe) var bufErr = ""
        let drain = { (pipe: Pipe, buf: inout String) in
            pipe.fileHandleForReading.readabilityHandler = { handle in
                let data = handle.availableData
                if data.isEmpty { return }
                let s = String(data: data, encoding: .utf8) ?? ""
                buf += s
                while let nl = buf.firstIndex(of: "\n") {
                    let line = String(buf[..<nl])
                    buf = String(buf[buf.index(after: nl)...])
                    onLine(line)
                }
            }
        }
        drain(stdout, &bufOut)
        drain(stderr, &bufErr)

        do {
            try proc.run()
            // Spin until it exits — Process doesn't have an async wait.
            await withCheckedContinuation { continuation in
                proc.terminationHandler = { _ in
                    continuation.resume()
                }
            }
        } catch {
            onLine("[venv] failed to launch \(executable.lastPathComponent): \(error)")
            return false
        }

        stdout.fileHandleForReading.readabilityHandler = nil
        stderr.fileHandleForReading.readabilityHandler = nil
        if !bufOut.isEmpty { onLine(bufOut) }
        if !bufErr.isEmpty { onLine(bufErr) }

        return proc.terminationStatus == 0
    }
}
