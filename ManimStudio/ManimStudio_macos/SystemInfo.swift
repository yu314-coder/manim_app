// SystemInfo.swift — collects the diagnostic info the Settings >
// "System info" tab shows: app/OS/CPU details (synchronous), plus
// Python / manim / pdflatex / dvisvgm versions (each shelled out
// in the background so the UI doesn't block).
//
// Why per-tool probes instead of a single dump-everything script:
// each subprocess takes 50–300 ms, and we'd rather show partial
// info immediately than make the user wait for all of them.
import Foundation
import SwiftUI
import Combine

final class SystemInfo: ObservableObject {

    /// Result of one tool probe.
    struct ToolInfo: Equatable {
        var path: String?
        var version: String?
        var error: String?
    }

    // ── synchronous (filled in init)
    let appName: String
    let appVersion: String
    let appBuild: String
    let osVersion: String
    let osName: String
    let architecture: String
    let locale: String

    // ── async tool probes (filled by `refresh()`)
    @Published var python   = ToolInfo()
    @Published var pip      = ToolInfo()
    @Published var manim    = ToolInfo()
    @Published var pdflatex = ToolInfo()
    @Published var dvisvgm  = ToolInfo()
    @Published var pipList: [(name: String, version: String)] = []

    @Published var refreshing = false

    init() {
        let info = Bundle.main.infoDictionary ?? [:]
        self.appName    = (info["CFBundleName"] as? String) ?? "ManimStudio"
        self.appVersion = (info["CFBundleShortVersionString"] as? String) ?? "?"
        self.appBuild   = (info["CFBundleVersion"] as? String) ?? "?"

        let v = ProcessInfo.processInfo.operatingSystemVersion
        self.osVersion = "\(v.majorVersion).\(v.minorVersion).\(v.patchVersion)"
        self.osName = "macOS"

        var size = 0
        sysctlbyname("hw.machine", nil, &size, nil, 0)
        var machine = [CChar](repeating: 0, count: size)
        sysctlbyname("hw.machine", &machine, &size, nil, 0)
        self.architecture = String(cString: machine)

        self.locale = Locale.current.identifier
    }

    /// Re-runs every async probe. Cheap to call; each probe will
    /// publish into its own ToolInfo when done.
    func refresh() {
        refreshing = true
        Task.detached(priority: .userInitiated) { [weak self] in
            await self?.runAllProbes()
            await MainActor.run { self?.refreshing = false }
        }
    }

    private func runAllProbes() async {
        let venvPython = await MainActor.run { VenvManager.venvPython }

        // Python interpreter
        if let py = venvPython {
            let info = Self.probe(executable: py.path,
                                  args: ["--version"])
            await MainActor.run {
                self.python = ToolInfo(path: py.path,
                                       version: info.version,
                                       error: info.error)
            }
            // pip
            let pipInfo = Self.probe(executable: py.path,
                                     args: ["-m", "pip", "--version"])
            await MainActor.run {
                self.pip = ToolInfo(path: nil, // bundled in venv
                                    version: pipInfo.version,
                                    error: pipInfo.error)
            }
            // manim
            let manimInfo = Self.probe(executable: py.path,
                                       args: ["-m", "manim", "--version"])
            await MainActor.run {
                self.manim = ToolInfo(path: nil,
                                      version: manimInfo.version,
                                      error: manimInfo.error)
            }
            // pip list — best-effort, skip if it errors out
            if let listed = Self.probePipList(python: py.path) {
                await MainActor.run { self.pipList = listed }
            }
        } else {
            await MainActor.run {
                let missing = ToolInfo(error: "venv not initialised")
                self.python = missing; self.pip = missing; self.manim = missing
            }
        }

        // pdflatex
        if let url = Self.findOnPath("pdflatex") {
            let info = Self.probe(executable: url.path, args: ["--version"])
            await MainActor.run {
                self.pdflatex = ToolInfo(path: url.path,
                                         version: info.version,
                                         error: info.error)
            }
        } else {
            await MainActor.run {
                self.pdflatex = ToolInfo(error: "not found")
            }
        }

        // dvisvgm
        if let url = Self.findOnPath("dvisvgm") {
            let info = Self.probe(executable: url.path, args: ["--version"])
            await MainActor.run {
                self.dvisvgm = ToolInfo(path: url.path,
                                        version: info.version,
                                        error: info.error)
            }
        } else {
            await MainActor.run {
                self.dvisvgm = ToolInfo(error: "not found")
            }
        }
    }

    // MARK: - subprocess helpers

    /// Mirrors LaTeXProbe's PATH logic — checks $PATH plus the
    /// standard MacTeX/Homebrew dirs that GUI apps don't inherit.
    private nonisolated static func findOnPath(_ name: String) -> URL? {
        var dirs: [String] = []
        if let p = ProcessInfo.processInfo.environment["PATH"] {
            dirs.append(contentsOf: p.split(separator: ":").map(String.init))
        }
        dirs.append(contentsOf: ["/Library/TeX/texbin",
                                  "/opt/homebrew/bin", "/usr/local/bin"])
        for dir in dirs {
            let url = URL(fileURLWithPath: dir).appendingPathComponent(name)
            if FileManager.default.isExecutableFile(atPath: url.path) {
                return url
            }
        }
        return nil
    }

    /// Spawns the executable, captures stdout + stderr, and uses the
    /// first non-empty line as the version string. 5-second timeout
    /// so a hung tool can't lock the UI refresh.
    private nonisolated static func probe(executable: String,
                                          args: [String]) -> ToolInfo {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: executable)
        proc.arguments = args
        var env = ProcessInfo.processInfo.environment
        // Prepend brew + texbin so the subprocess can find latex/dvisvgm
        // dependencies even when launchd's PATH was minimal.
        let extras = ["/opt/homebrew/bin", "/usr/local/bin",
                      "/Library/TeX/texbin"]
        env["PATH"] = (extras + (env["PATH"] ?? "").split(separator: ":")
                                                   .map(String.init))
            .joined(separator: ":")
        proc.environment = env
        let out = Pipe(), err = Pipe()
        proc.standardOutput = out
        proc.standardError = err

        do { try proc.run() }
        catch {
            return ToolInfo(error: error.localizedDescription)
        }
        // 5s budget.
        let group = DispatchGroup()
        group.enter()
        DispatchQueue.global().async {
            proc.waitUntilExit()
            group.leave()
        }
        if group.wait(timeout: .now() + .seconds(5)) == .timedOut {
            proc.terminate()
            return ToolInfo(error: "timed out")
        }
        let outData = out.fileHandleForReading.readDataToEndOfFile()
        let errData = err.fileHandleForReading.readDataToEndOfFile()
        let combined = (String(data: outData, encoding: .utf8) ?? "")
            + (String(data: errData, encoding: .utf8) ?? "")
        let firstLine = combined
            .split(whereSeparator: \.isNewline)
            .first.map(String.init) ?? ""
        return ToolInfo(version: firstLine.isEmpty ? nil : firstLine)
    }

    /// Returns up to ~40 packages, sorted by name. Best-effort —
    /// returns nil if pip can't be invoked.
    private nonisolated static func probePipList(python: String)
        -> [(name: String, version: String)]?
    {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        proc.arguments = ["-m", "pip", "list", "--format=json",
                          "--disable-pip-version-check"]
        let out = Pipe()
        proc.standardOutput = out
        proc.standardError = Pipe()
        do { try proc.run() }
        catch { return nil }
        let group = DispatchGroup()
        group.enter()
        DispatchQueue.global().async {
            proc.waitUntilExit()
            group.leave()
        }
        if group.wait(timeout: .now() + .seconds(8)) == .timedOut {
            proc.terminate()
            return nil
        }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        guard let arr = try? JSONSerialization.jsonObject(
            with: data, options: []) as? [[String: Any]] else { return nil }
        return arr.compactMap { item -> (String, String)? in
            guard let n = item["name"] as? String,
                  let v = item["version"] as? String else { return nil }
            return (n, v)
        }
        .sorted { $0.0.lowercased() < $1.0.lowercased() }
    }
}
