// LibrarySymbolBuilder.swift — introspects every importable top-level
// module in the python-ios-lib bundles and emits a JSON map of
// `{ module: { name: kind } }` that Monaco's completion provider merges
// into its hardcoded LIB_SYMBOLS for richer, accurate completions.
import Foundation

@MainActor
final class LibrarySymbolBuilder {
    static let shared = LibrarySymbolBuilder()

    /// Set after the first successful build. JSON-encoded payload ready
    /// to be passed to `MonacoEditorView.setSymbolIndex(...)`.
    private(set) var payloadJSON: String?
    private var inFlight = false

    /// Introspects in the background, then calls `completion` on @MainActor
    /// with a JSON string suitable for `window.__editor.setSymbolIndex(...)`.
    /// On-disk cache path for the introspection JSON. Keyed by
    /// CFBundleVersion — bundled packages only change when the app is
    /// rebuilt, so a cache hit lets us skip the multi-second
    /// `import manim/numpy/scipy/...` cost on every launch after the
    /// first one for a given build.
    nonisolated private static func cachePath() -> String {
        let dir = (NSSearchPathForDirectoriesInDomains(
            .cachesDirectory, .userDomainMask, true).first ?? NSTemporaryDirectory())
            as NSString
        let ver = (Bundle.main.infoDictionary?["CFBundleVersion"] as? String) ?? "0"
        return dir.appendingPathComponent("manim_studio_symindex_v\(ver).json")
    }

    /// Cheap path: hand back whatever's already in memory or on disk
    /// without kicking off an introspection pass. Used at editor-ready
    /// time so the JSON is wired up the moment Monaco loads, but launch
    /// doesn't pay the import-everything cost on a cache miss.
    /// `completion` receives nil when no cache exists yet — caller
    /// should leave the editor with no extra symbol hints in that case.
    func loadIfCached(completion: @escaping (String?) -> Void) {
        if let cached = payloadJSON { completion(cached); return }
        let onDisk = (try? String(contentsOfFile: Self.cachePath(), encoding: .utf8)) ?? ""
        if !onDisk.isEmpty {
            payloadJSON = onDisk
            completion(onDisk)
        } else {
            completion(nil)
        }
    }

    func build(completion: @escaping (String) -> Void) {
        if let cached = payloadJSON {
            completion(cached)
            return
        }
        // Disk cache check — keyed by app build version. A hit means
        // bundled packages haven't changed since last successful run.
        let diskPath = Self.cachePath()
        if let onDisk = try? String(contentsOfFile: diskPath, encoding: .utf8),
           !onDisk.isEmpty {
            payloadJSON = onDisk
            completion(onDisk)
            return
        }
        guard !inFlight else { return }
        inFlight = true

        Task.detached(priority: .utility) {
            // Write to a temp file rather than stdout — the wrapper now
            // tees stdout into the PTY, so a print() of 100 KB JSON would
            // dump into the user's terminal pane.
            let outFile = (NSTemporaryDirectory() as NSString)
                .appendingPathComponent("manim_studio_symindex.json")
            try? FileManager.default.removeItem(atPath: outFile)
            setenv("MANIMSTUDIO_SYMINDEX_OUT", outFile, 1)
            _ = PythonRuntime.shared.execute(code: Self.script)
            let json = (try? String(contentsOfFile: outFile, encoding: .utf8))
                       ?? "{\"modules\":{}}"
            try? FileManager.default.removeItem(atPath: outFile)
            // Persist for next launch (only if non-empty result).
            if json.count > 32 {
                try? json.write(toFile: diskPath, atomically: true, encoding: .utf8)
            }
            await MainActor.run {
                self.payloadJSON = json
                self.inFlight = false
                completion(json)
            }
        }
    }

    nonisolated private static let script: String = """
    import io, json, os, sys, importlib, contextlib, inspect

    SKIP = {"__pycache__", "lib-dynload", "site-packages", "encodings",
            "tests", "test", "bin", "include", "share", "lib", "ffmpeg",
            "build", "Headers", "Resources",
            # Known-crashy on iOS: these abort the process at C level
            # before raising a Python exception, so a try/except is
            # useless. moderngl tries to initialize an OpenGL context;
            # moderngl_window pokes platform window APIs. Both die hard
            # on iOS where there's no X11/EGL/desktop GL.
            "moderngl", "moderngl_window", "pyglet", "watchdog",
            "screeninfo"}

    # Monaco CompletionItemKind values (from monaco.languages):
    K_FUNCTION = 1
    K_VARIABLE = 4
    K_CLASS    = 6
    K_MODULE   = 8
    K_CONSTANT = 14

    def kind_of(obj):
        if inspect.ismodule(obj):       return K_MODULE
        if inspect.isclass(obj):        return K_CLASS
        if callable(obj):               return K_FUNCTION
        # constants — uppercase names or immutable scalars
        return K_CONSTANT

    # Restrict scanning to user-installed Python packages (skip stdlib).
    # Two layouts in play:
    #   - SwiftPM resource bundles: <App>.app/python-ios-lib_*.bundle/
    #   - BeeWare consolidated: <App>.app/app_packages/site-packages/
    # install-python-stdlib.sh Step 9 deletes the bundles after merging
    # them into app_packages/site-packages — match either form.
    scan_paths = [p for p in sys.path if p and (
        ("python-ios-lib_" in p and p.endswith(".bundle")) or
        ("app_packages/site-packages" in p) or
        ("python-metadata" in p)
    )]

    modules = {}
    _stdout = io.StringIO()
    _stderr = io.StringIO()

    with contextlib.redirect_stdout(_stdout), contextlib.redirect_stderr(_stderr):
        for path in scan_paths:
            if not os.path.isdir(path): continue
            try: entries = sorted(os.listdir(path))
            except Exception: continue
            for name in entries:
                if name in SKIP or name.startswith(("_", ".")): continue
                full = os.path.join(path, name)
                modname = None
                if os.path.isdir(full):
                    if "__init__.py" in os.listdir(full) if os.access(full, os.R_OK) else False:
                        modname = name
                elif name.endswith(".py"):
                    modname = name[:-3]
                if not modname: continue
                try:
                    m = importlib.import_module(modname)
                except Exception:
                    continue
                attrs = {}
                # dir() may be expensive; cap to ~400 names per module.
                names = [n for n in dir(m) if not n.startswith("_")][:400]
                for n in names:
                    try:
                        attrs[n] = kind_of(getattr(m, n))
                    except Exception:
                        attrs[n] = K_VARIABLE
                if attrs:
                    modules[modname] = attrs

    # Write to file path passed via env var. Avoids dumping ~100 KB
    # JSON into stdout, which the wrapper tees into the PTY (terminal).
    _out_path = os.environ.get("MANIMSTUDIO_SYMINDEX_OUT", "")
    if _out_path:
        try:
            with open(_out_path, "w", encoding="utf-8") as _f:
                _f.write(json.dumps({"modules": modules}))
        except Exception:
            pass
    """

    nonisolated private static func extract(from output: String) -> String? {
        guard let s = output.range(of: "___SYMJSON___"),
              let e = output.range(of: "___ENDSYMJSON___",
                                   range: s.upperBound..<output.endIndex)
        else { return nil }
        return String(output[s.upperBound..<e.lowerBound])
    }
}
