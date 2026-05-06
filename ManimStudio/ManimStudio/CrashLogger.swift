// CrashLogger.swift — best-effort persistent log so the user can recover
// crash context after iOS kills the app or after a Python segfault that
// otherwise tears down the process before stderr reaches the terminal
// pane.
//
// Output goes to:  Documents/Logs/manim_studio.log
// (Files app → On My iPad → Manim Studio → Logs/manim_studio.log)
//
// What lands in there:
//   • Every line written to the PTY pipe — i.e. every Python print(),
//     manim/numpy/scipy stack trace, render banner, etc. Plus everything
//     the shell echoes back to the user. Same content the terminal pane
//     shows, only persisted across app launches.
//   • Swift NSLog calls funneled through `CrashLogger.shared.log(...)`.
//   • An "uncaught Objective-C exception" line via
//     NSSetUncaughtExceptionHandler.
//   • A traceback for SIGSEGV / SIGBUS / SIGILL / SIGABRT / SIGFPE
//     written from the signal handler before the process dies. Note:
//     this uses async-signal-safe write(2) only — no String allocation,
//     no Swift dynamic dispatch. The traceback comes from
//     backtrace_symbols which is signal-safe on Darwin.
//   • A Python-side crash trace from faulthandler (PythonRuntime
//     enables it pointing at the same file).
//
// Cap is soft: when the file passes ~5 MB at app start, we rename it
// to manim_studio.log.1 and start fresh — keeps storage from growing
// unboundedly across long-running sessions.
import Foundation
import Darwin

final class CrashLogger {
    static let shared = CrashLogger()

    private(set) var fileURL: URL?
    private var fd: Int32 = -1
    private let queue = DispatchQueue(label: "ManimStudio.CrashLogger", qos: .utility)

    private init() {}

    // MARK: bootstrap

    /// Resolve `Documents/Logs/manim_studio.log`, rotate if oversized,
    /// install crash handlers. Idempotent — call once from app launch.
    func install() {
        let docs = FileManager.default.urls(for: .documentDirectory,
                                            in: .userDomainMask).first
        guard let logsDir = docs?.appendingPathComponent("Logs",
                                                         isDirectory: true) else {
            return
        }
        try? FileManager.default.createDirectory(at: logsDir,
                                                 withIntermediateDirectories: true)
        let url = logsDir.appendingPathComponent("manim_studio.log")
        rotateIfNeeded(at: url)
        fileURL = url

        let path = url.path
        fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0o644)
        guard fd >= 0 else { return }

        // Make the writer fd known to the C-level signal handlers.
        sharedLogFD = fd

        writeHeader()
        installObjCHandler()
        installSignalHandlers()
    }

    /// Return the path Python's faulthandler.enable() should write to.
    /// Empty string if logging is disabled. PythonRuntime passes this
    /// to faulthandler so a Python C-extension segfault dumps a stack
    /// here even if our SIGSEGV handler is replaced.
    var pythonFaultlogPath: String { fileURL?.path ?? "" }

    // MARK: append

    /// Append one Swift-side line, timestamped. Called from NSLog
    /// shims and any place we want a permanent record. Goes through
    /// a serial queue so writes don't interleave with the PTY tee.
    func log(_ message: @autoclosure @escaping () -> String,
             tag: String = "app") {
        guard fd >= 0 else { return }
        let ts = Self.df.string(from: Date())
        let body = message()
        queue.async { [fd = self.fd] in
            let line = "[\(ts)] [\(tag)] \(body)\n"
            line.withCString { cs in _ = Darwin.write(fd, cs, strlen(cs)) }
        }
    }

    /// Mirror raw bytes from the PTY (Python stdout/stderr) into the
    /// log file. Called from PTYBridge after each chunk arrives.
    func appendRaw(_ data: Data) {
        guard fd >= 0, !data.isEmpty else { return }
        // Direct fd write off the main thread; no formatting because
        // the PTY stream already contains terminal escape codes from
        // tqdm progress bars etc. that we want preserved verbatim.
        queue.async { [fd = self.fd] in
            _ = data.withUnsafeBytes { buf -> Int in
                guard let p = buf.baseAddress else { return 0 }
                return Darwin.write(fd, p, buf.count)
            }
        }
    }

    // MARK: rotation

    private func rotateIfNeeded(at url: URL) {
        let attrs = try? FileManager.default.attributesOfItem(atPath: url.path)
        let size = (attrs?[.size] as? UInt64) ?? 0
        if size > 5 * 1024 * 1024 {
            let archive = url.deletingLastPathComponent()
                .appendingPathComponent("manim_studio.log.1")
            try? FileManager.default.removeItem(at: archive)
            try? FileManager.default.moveItem(at: url, to: archive)
        }
    }

    private func writeHeader() {
        let info = Bundle.main.infoDictionary ?? [:]
        let version = (info["CFBundleShortVersionString"] as? String) ?? "?"
        let build   = (info["CFBundleVersion"] as? String) ?? "?"
        let model   = ProcessInfo.processInfo.machineHardwareName
        let os      = UIDevice_systemVersionString()
        log("=== launch · v\(version) (\(build)) · iOS \(os) · \(model) ===",
            tag: "boot")
    }

    // MARK: handlers

    private func installObjCHandler() {
        NSSetUncaughtExceptionHandler { exc in
            CrashLogger.shared.log(
                "uncaught NSException: \(exc.name.rawValue) — \(exc.reason ?? "?")\n" +
                "callStack:\n" + exc.callStackSymbols.joined(separator: "\n"),
                tag: "fatal")
        }
    }

    private func installSignalHandlers() {
        for sig in [SIGSEGV, SIGBUS, SIGILL, SIGABRT, SIGFPE] {
            var sa = sigaction()
            sa.__sigaction_u.__sa_handler = signalHandlerFn
            sigemptyset(&sa.sa_mask)
            sa.sa_flags = SA_RESETHAND
            sigaction(sig, &sa, nil)
        }
    }

    private static let df: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm:ss.SSS"
        return f
    }()
}

// File descriptor visible to the C signal handler. Set once during
// install(), then read-only. Marked nonisolated to avoid the actor
// check; the handler runs on whichever thread blew up.
nonisolated(unsafe) fileprivate var sharedLogFD: Int32 = -1

/// C signal handler. MUST be async-signal-safe — only call:
///   write(2), backtrace, backtrace_symbols_fd, _exit
/// (no malloc, no Swift dispatch, no String formatting).
private func signalHandlerFn(_ sig: Int32) {
    guard sharedLogFD >= 0 else { _exit(128 &+ Int32(sig)) }
    var header = "\n[fatal] signal \(sig) — backtrace:\n"
    _ = header.withCString { Darwin.write(sharedLogFD, $0, strlen($0)) }
    var frames = [UnsafeMutableRawPointer?](repeating: nil, count: 64)
    let n = backtrace(&frames, Int32(frames.count))
    backtrace_symbols_fd(&frames, n, sharedLogFD)
    let footer = "[fatal] exiting\n\n"
    _ = footer.withCString { Darwin.write(sharedLogFD, $0, strlen($0)) }
    _exit(128 &+ sig)
}

// MARK: - small helpers (kept here so CrashLogger has zero deps)

import UIKit

private func UIDevice_systemVersionString() -> String {
    UIDevice.current.systemVersion
}

extension ProcessInfo {
    /// "iPad14,8" / "arm64" — uname machine field. Used in the log
    /// header so a crash report tells us which device class hit it.
    fileprivate var machineHardwareName: String {
        var info = utsname()
        uname(&info)
        let machine = withUnsafePointer(to: &info.machine) { ptr -> String in
            ptr.withMemoryRebound(to: CChar.self, capacity: Int(_SYS_NAMELEN)) {
                String(cString: $0)
            }
        }
        return machine
    }
}
