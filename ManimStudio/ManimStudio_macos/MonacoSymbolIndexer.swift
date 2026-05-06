// MonacoSymbolIndexer.swift — runs the venv's Python once after
// install to produce a symbol index for the Monaco editor's
// completion provider. Result shape:
//
//   {
//     "modules":  [ "manim", "numpy", "scipy", … ],
//     "members":  { "manim": ["Scene","Text","Write",…], … },
//     "submodules": { "manim": ["mobject","animation",…], … }
//   }
//
// The index is cached to ~/Library/Application Support/ManimStudio/
// monaco-symbols.json so we don't re-run Python on every launch.
// Re-runs only when the venv's site-packages directory mtime is
// newer than the cache (i.e. user installed/upgraded a package).
//
// On the JS side, editor.html receives the JSON via
// `window.__editor.setSymbolIndex(json)` and registers a
// CompletionItemProvider that surfaces module names + their public
// members + their submodules.
import Foundation

@MainActor
enum MonacoSymbolIndexer {

    /// Cache file — contains the JSON shape described above.
    static var cacheURL: URL {
        let dir = FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask)
            .first!.appendingPathComponent("ManimStudio", isDirectory: true)
        try? FileManager.default.createDirectory(
            at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("monaco-symbols.json")
    }

    /// site-packages dir under the venv, used for staleness check.
    static var sitePackagesURL: URL? {
        guard let py = VenvManager.venvPython else { return nil }
        // …/venv/bin/python  →  …/venv/lib/python3.X/site-packages/
        let venv = py.deletingLastPathComponent().deletingLastPathComponent()
        let lib = venv.appendingPathComponent("lib", isDirectory: true)
        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: lib, includingPropertiesForKeys: nil) else { return nil }
        // Pick the first python3.* dir — there's only ever one.
        guard let pyDir = entries.first(where: {
            $0.lastPathComponent.hasPrefix("python")
        }) else { return nil }
        return pyDir.appendingPathComponent("site-packages", isDirectory: true)
    }

    /// True if the cache is fresh (cache mtime ≥ site-packages mtime).
    static var cacheIsFresh: Bool {
        guard let sp = sitePackagesURL,
              FileManager.default.fileExists(atPath: cacheURL.path) else {
            return false
        }
        let cacheMTime = (try? cacheURL.resourceValues(
            forKeys: [.contentModificationDateKey]))?.contentModificationDate
            ?? .distantPast
        let spMTime = (try? sp.resourceValues(
            forKeys: [.contentModificationDateKey]))?.contentModificationDate
            ?? .distantPast
        return cacheMTime >= spMTime
    }

    /// Returns the cached JSON synchronously if available. JS side
    /// can render completion as soon as it loads.
    static func cachedJSON() -> String? {
        guard FileManager.default.fileExists(atPath: cacheURL.path) else {
            return nil
        }
        return try? String(contentsOf: cacheURL, encoding: .utf8)
    }

    /// Re-introspect the venv off the main thread, write to cache,
    /// and call `completion` with the JSON when done. No-op if the
    /// venv isn't ready.
    static func refresh(completion: @escaping (String?) -> Void) {
        guard let py = VenvManager.venvPython else {
            completion(nil); return
        }
        if cacheIsFresh, let json = cachedJSON() {
            completion(json); return
        }
        DispatchQueue.global(qos: .utility).async {
            let json = runIntrospect(python: py.path) ?? "{}"
            try? json.write(to: cacheURL, atomically: true, encoding: .utf8)
            DispatchQueue.main.async { completion(json) }
        }
    }

    // MARK: - subprocess

    /// Spawns `python -c <introspectScript>` and returns its stdout.
    /// Runs with a 30-second timeout — rip out long-running or hanging
    /// imports (e.g. matplotlib's font cache rebuild) without
    /// blocking the editor forever.
    private static func runIntrospect(python: String) -> String? {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        proc.arguments = ["-I", "-c", introspectScript]
        // Inherit PATH so /opt/homebrew tools (cairo) are findable
        // but nuke PYTHONPATH to keep introspection isolated.
        var env = ProcessInfo.processInfo.environment
        env.removeValue(forKey: "PYTHONPATH")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc.environment = env

        let outPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = Pipe()  // discard

        do { try proc.run() }
        catch {
            NSLog("[indexer] python failed to launch: %@",
                  error.localizedDescription)
            return nil
        }
        // 30-second guard.
        let deadline = DispatchTime.now() + .seconds(30)
        let group = DispatchGroup()
        group.enter()
        DispatchQueue.global().async {
            proc.waitUntilExit()
            group.leave()
        }
        if group.wait(timeout: deadline) == .timedOut {
            proc.terminate()
            NSLog("[indexer] python introspection timed out")
            return nil
        }
        let data = outPipe.fileHandleForReading.readDataToEndOfFile()
        return String(data: data, encoding: .utf8)
    }

    /// Inline Python that walks site-packages, picks the relevant
    /// modules, and emits the JSON shape Monaco expects.
    ///
    /// We deliberately limit to a curated allowlist + every top-level
    /// pkg that doesn't start with "_" — the result is small enough
    /// to ship to the WKWebView in one postMessage.
    private static let introspectScript = #"""
    import json, importlib, pkgutil, sys, traceback

    PRIORITY = [
        "manim", "numpy", "np", "scipy", "sympy", "matplotlib",
        "PIL", "cv2", "networkx", "pandas",
    ]
    EXTRA_DEPTH = {"manim": True, "numpy": True}

    def safe_dir(obj):
        try:
            return [n for n in dir(obj) if not n.startswith("_")]
        except Exception:
            return []

    def submodules_of(name):
        try:
            mod = importlib.import_module(name)
        except Exception:
            return []
        path = getattr(mod, "__path__", None)
        if not path:
            return []
        names = []
        try:
            for _, sub, _ in pkgutil.iter_modules(path):
                if not sub.startswith("_"):
                    names.append(sub)
        except Exception:
            pass
        return names

    members = {}
    submods = {}

    seen = set()
    queue = list(PRIORITY)

    # Discover top-level packages that are siblings of the priority
    # ones too — gives the user completion for whatever else they
    # pip-installed.
    try:
        import sysconfig
        sp = sysconfig.get_paths().get("purelib")
        if sp:
            for _, sub, _ in pkgutil.iter_modules([sp]):
                if not sub.startswith("_") and sub not in queue:
                    queue.append(sub)
    except Exception:
        pass

    for name in queue:
        if name in seen:
            continue
        seen.add(name)
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue
        members[name] = safe_dir(mod)[:1500]
        subs = submodules_of(name)[:200]
        if subs:
            submods[name] = subs

        if EXTRA_DEPTH.get(name):
            # One level deeper for the keystone packages so users get
            # `manim.mobject.*` and `numpy.linalg.*` completion too.
            for sub in subs[:60]:
                full = name + "." + sub
                if full in seen: continue
                seen.add(full)
                try:
                    sm = importlib.import_module(full)
                except Exception:
                    continue
                members[full] = safe_dir(sm)[:600]

    out = {
        "modules":   sorted(members.keys()),
        "members":   members,
        "submodules": submods,
    }
    print(json.dumps(out))
    """#
}
