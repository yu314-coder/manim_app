// PythonHost.swift — embeds Python.framework, imports the desktop
// app's `app` module, exposes the `app.api` instance to the JS
// bridge. Owns the GIL serialization so multiple WKWebView IPC
// calls can be in flight without stomping each other.
//
// Why this shape:
// PyWebView on Windows constructs a single API instance once at
// startup (e.g. `App()` in app.py) and gives JS a proxy object.
// We replicate that exactly: at boot, import `bootstrap_macos`
// which imports `app`, instantiates `App()`, and stores it as a
// module-level `api`. Every IPC call from JS becomes
// `getattr(api, method)(*args)` with JSON serialization on both
// sides.
//
// macOS makes this dramatically simpler than the iOS version
// (PythonRuntime.swift in the iOS target):
//   • no wrap-loose-dylibs / .fwork normalization needed
//   • no SwiftPM bundle consolidation
//   • no BLAS / Fortran I/O stub frameworks
//   • no flat-namespace dlopen preload
//   • Python.framework links cleanly via Mach-O @rpath
// All those exist purely to satisfy iOS App Store + dyld quirks.
import Foundation

// Minimal Python C API surface — pulled in via Python.framework
// linkage. Same _silgen_name pattern the iOS target uses.
@_silgen_name("Py_Initialize")            private func Py_Initialize()
@_silgen_name("Py_IsInitialized")         private func Py_IsInitialized() -> Int32
@_silgen_name("PyRun_SimpleString")       private func PyRun_SimpleString(_ s: UnsafePointer<CChar>) -> Int32
@_silgen_name("PyGILState_Ensure")        private func PyGILState_Ensure() -> Int32
@_silgen_name("PyGILState_Release")       private func PyGILState_Release(_ s: Int32)
@_silgen_name("PyEval_SaveThread")        private func PyEval_SaveThread() -> OpaquePointer?

@MainActor
final class PythonHost {
    static let shared = PythonHost()

    private(set) var isReady = false
    private let queue = DispatchQueue(label: "macos.python", qos: .userInitiated)
    private var initOnce = false

    private init() {}

    // MARK: bootstrap

    /// Eagerly boot Python. Idempotent. Call once from
    /// ManimStudio_macosApp.init.
    func ensureReady() {
        queue.async { [weak self] in
            guard let self = self, !self.initOnce else { return }
            self.initOnce = true
            self.bootPythonOnce()
        }
    }

    private func bootPythonOnce() {
        guard let bundle = Bundle.main.resourcePath else { return }
        // Resources/python-stdlib/ — copied by install-python-macos.sh
        // Resources/site-packages/ — pip-installed by install-python-macos.sh
        // PythonApp/ — app.py + bootstrap_macos.py + ai_edit.py + …
        let stdlib       = "\(bundle)/python-stdlib"
        let sitePackages = "\(bundle)/site-packages"
        let pythonApp    = "\(bundle)/PythonApp"

        setenv("PYTHONHOME",         stdlib, 1)
        setenv("PYTHONPATH",         "\(stdlib):\(sitePackages):\(pythonApp)", 1)
        setenv("PYTHONNOUSERSITE",   "1", 1)
        setenv("PYTHONDONTWRITEBYTECODE", "1", 1)

        if Py_IsInitialized() == 0 {
            Py_Initialize()
            guard Py_IsInitialized() != 0 else {
                NSLog("[macos.python] Py_Initialize failed")
                return
            }
        }

        // Import bootstrap_macos which imports app, instantiates the
        // API class, and exposes it as `bootstrap_macos.api`. All
        // platform-specific shims (winpty→pty, cmd.exe→/bin/zsh,
        // path separators) live in bootstrap_macos.py — app.py stays
        // unmodified.
        let boot = """
        try:
            import sys, traceback
            sys.path.insert(0, r"\(pythonApp)")
            import bootstrap_macos
            bootstrap_macos.boot()
        except Exception as e:
            import traceback
            traceback.print_exc()
        """
        _ = boot.withCString { PyRun_SimpleString($0) }

        // Release the initial GIL so PyGILState_Ensure works from
        // dispatch threads.
        _ = PyEval_SaveThread()
        isReady = true
        NSLog("[macos.python] runtime ready")
    }

    // MARK: dispatch

    /// Call `bootstrap_macos.api.<method>(*args)` and return a
    /// JSON-serializable payload (or NSNull on error). Args are
    /// already deserialized into Foundation types by IPCHandler;
    /// we re-encode them as JSON so the Python side can decode
    /// without us touching the C API for every primitive.
    func dispatch(method: String, args: [Any]) -> Any? {
        guard isReady else { return NSNull() }

        // Encode args as a JSON string so the Python side decodes
        // them back to native types. Avoids hand-coded conversions
        // for every dict/array/number combination JS might send.
        let argsJSON: String = {
            guard JSONSerialization.isValidJSONObject(args) ||
                  args is [Any]
            else { return "[]" }
            do {
                let data = try JSONSerialization.data(
                    withJSONObject: args,
                    options: [.fragmentsAllowed])
                return String(data: data, encoding: .utf8) ?? "[]"
            } catch {
                return "[]"
            }
        }()

        // Execute on the Python queue, blocking the caller's thread
        // until the result lands. IPCHandler invokes us from a
        // detached Task so the WebView main thread isn't blocked.
        let semaphore = DispatchSemaphore(value: 0)
        nonisolated(unsafe) var resultJSON: String = "null"

        queue.async {
            let gil = PyGILState_Ensure()
            defer { PyGILState_Release(gil) }

            // Build a tiny Python wrapper that calls the API method
            // with the JSON-decoded args, captures the return value,
            // and writes it to a sys-attached holder we read back.
            let q = method.replacingOccurrences(of: "\\", with: "\\\\")
                          .replacingOccurrences(of: "'",  with: "\\'")
            let argsEsc = argsJSON
                .replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "'",  with: "\\'")
            let prog = """
            import json, sys, traceback
            try:
                import bootstrap_macos as _bm
                _api = getattr(_bm, 'api', None)
                _fn  = getattr(_api, '\(q)', None) if _api is not None else None
                _args = json.loads('\(argsEsc)')
                if _fn is None:
                    sys.__manimstudio_macos_result__ = json.dumps({
                        '__error__': 'method not found: \(q)'
                    })
                else:
                    _ret = _fn(*_args)
                    try:
                        sys.__manimstudio_macos_result__ = json.dumps(_ret)
                    except (TypeError, ValueError):
                        sys.__manimstudio_macos_result__ = json.dumps(str(_ret))
            except Exception as _e:
                sys.__manimstudio_macos_result__ = json.dumps({
                    '__error__': f'{type(_e).__name__}: {_e}',
                    '__traceback__': traceback.format_exc(),
                })
            """
            _ = prog.withCString { PyRun_SimpleString($0) }

            // Read the result back via another tiny PyRun that
            // writes it to a temp file. PyRun_SimpleString doesn't
            // expose return values directly; the temp-file dance
            // is the simplest way to avoid wading into PyObject*.
            let tmpPath = (NSTemporaryDirectory() as NSString)
                .appendingPathComponent("manimstudio_macos_ipc.json")
            let read = """
            try:
                with open(r'\(tmpPath)', 'w', encoding='utf-8') as _f:
                    _f.write(sys.__manimstudio_macos_result__)
            except Exception:
                pass
            """
            _ = read.withCString { PyRun_SimpleString($0) }

            if let txt = try? String(contentsOfFile: tmpPath, encoding: .utf8),
               !txt.isEmpty {
                resultJSON = txt
            }
            try? FileManager.default.removeItem(atPath: tmpPath)
            semaphore.signal()
        }

        semaphore.wait()

        // Decode the JSON string back to Foundation types for IPCHandler
        // to re-encode when it replies to JS.
        if let data = resultJSON.data(using: .utf8),
           let obj = try? JSONSerialization.jsonObject(
            with: data, options: [.fragmentsAllowed]) {
            return obj
        }
        return NSNull()
    }
}
