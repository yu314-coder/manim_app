import Foundation

private typealias PyObjectPointer = OpaquePointer
private typealias PyGILStateState = Int32
private typealias PySsizeT = Int

@_silgen_name("Py_IsInitialized") private func Py_IsInitialized() -> Int32
@_silgen_name("Py_Initialize") private func Py_Initialize()
@_silgen_name("PyGILState_Ensure") private func PyGILState_Ensure() -> PyGILStateState
@_silgen_name("PyGILState_Release") private func PyGILState_Release(_ state: PyGILStateState)
@_silgen_name("PyImport_AddModule") private func PyImport_AddModule(_ name: UnsafePointer<CChar>) -> PyObjectPointer?
@_silgen_name("PyModule_GetDict") private func PyModule_GetDict(_ module: PyObjectPointer?) -> PyObjectPointer?
@_silgen_name("Py_CompileString") private func Py_CompileString(_ code: UnsafePointer<CChar>, _ filename: UnsafePointer<CChar>, _ mode: Int32) -> PyObjectPointer?
@_silgen_name("PyEval_EvalCode") private func PyEval_EvalCode(_ code: PyObjectPointer?, _ globals: PyObjectPointer?, _ locals: PyObjectPointer?) -> PyObjectPointer?
@_silgen_name("Py_DecRef") private func Py_DecRef(_ object: PyObjectPointer?)
@_silgen_name("PyUnicode_FromString") private func PyUnicode_FromString(_ value: UnsafePointer<CChar>) -> PyObjectPointer?
@_silgen_name("PyDict_SetItemString") private func PyDict_SetItemString(_ dict: PyObjectPointer?, _ key: UnsafePointer<CChar>, _ item: PyObjectPointer?) -> Int32
@_silgen_name("PyDict_GetItemString") private func PyDict_GetItemString(_ dict: PyObjectPointer?, _ key: UnsafePointer<CChar>) -> PyObjectPointer?
@_silgen_name("PyUnicode_AsUTF8AndSize") private func PyUnicode_AsUTF8AndSize(_ object: PyObjectPointer?, _ size: UnsafeMutablePointer<PySsizeT>?) -> UnsafePointer<CChar>?
@_silgen_name("PyObject_Str") private func PyObject_Str(_ object: PyObjectPointer?) -> PyObjectPointer?
@_silgen_name("PyErr_Occurred") private func PyErr_Occurred() -> PyObjectPointer?
@_silgen_name("PyErr_Fetch") private func PyErr_Fetch(_ type: UnsafeMutablePointer<PyObjectPointer?>?, _ value: UnsafeMutablePointer<PyObjectPointer?>?, _ traceback: UnsafeMutablePointer<PyObjectPointer?>?)
@_silgen_name("PyErr_NormalizeException") private func PyErr_NormalizeException(_ type: UnsafeMutablePointer<PyObjectPointer?>?, _ value: UnsafeMutablePointer<PyObjectPointer?>?, _ traceback: UnsafeMutablePointer<PyObjectPointer?>?)
@_silgen_name("PyEval_SaveThread") private func PyEval_SaveThread() -> OpaquePointer?
@_silgen_name("PyRun_SimpleString") private func PyRun_SimpleString(_ code: UnsafePointer<CChar>) -> Int32
@_silgen_name("PyErr_SetInterrupt") private func PyErr_SetInterrupt()
@_silgen_name("PyGILState_Check") private func PyGILState_Check() -> Int32

final class PythonRuntime {
    static let shared = PythonRuntime()

    struct ExecutionResult {
        let output: String
        let imagePath: String?
    }

    struct LibraryProbe: Equatable {
        enum State: String {
            case installed
            case shim
            case missing
            case error
        }

        let name: String
        let state: State
        let detail: String?
    }

    private enum RuntimeError: LocalizedError {
        case message(String)

        var errorDescription: String? {
            switch self {
            case .message(let value):
                return value
            }
        }
    }

    private let queue = DispatchQueue(label: "codebench.python.runtime")
    private let queueKey = DispatchSpecificKey<Void>()
    private var pathsConfigured = false
    private var toolOutputDirectoryURL: URL?
    private var environmentConfigured = false
    private let fileInputMode: Int32 = 257 // Py_file_input
    private var gilReleasedForThreads = false
    /// Class-picker selection for the next `executeSync` run. "" = all
    /// scenes (legacy default), "*" = all scenes (explicit), otherwise
    /// the bare class name to render. Reset to "" by every executeSync
    /// invocation after it's been pushed into the wrapper's globals.
    private var targetSceneForNextRun: String = ""

    private init() {
        queue.setSpecific(key: queueKey, value: ())
    }

    /// Single-shot Python execution with no streaming and no scene
    /// targeting (renders all detected manim Scene subclasses).
    func execute(code: String) -> ExecutionResult {
        return execute(code: code, targetScene: nil, onOutput: nil)
    }

    /// Streaming Python execution. `targetScene` is the result of a
    /// class-picker dialog: pass nil or "" for the legacy "render all
    /// detected Scene subclasses" behaviour, "*" for "render all"
    /// (explicit), or the bare class name (e.g. "Lesson03_BuildPrism")
    /// to render only that class. The wrapper script reads it from
    /// `__codebench_target_scene` and filters its scene-class list
    /// accordingly.
    func execute(code: String, targetScene: String?, onOutput: ((String) -> Void)?) -> ExecutionResult {
        // Stash the picker selection in a property so executeSync (which
        // doesn't take parameters) can read it from setGlobalString just
        // before runStatements fires.
        targetSceneForNextRun = targetScene ?? ""
        return execute(code: code, onOutput: onOutput)
    }

    func execute(code: String, onOutput: ((String) -> Void)?) -> ExecutionResult {
        if let onOutput = onOutput {
            // Streaming mode: run Python on its queue, poll output file from caller thread
            let semaphore = DispatchSemaphore(value: 0)
            var result = ExecutionResult(output: "", imagePath: nil)

            // Pre-compute stream file path on calling thread
            let toolDir: String
            do {
                toolDir = try ensureToolOutputDirectory().path
            } catch {
                toolDir = NSTemporaryDirectory()
            }
            let streamFile = (toolDir as NSString).appendingPathComponent("_stream_stdout.txt")
            let stderrFile = (toolDir as NSString).appendingPathComponent("_stream_stderr.txt")

            // Delete stale stream files from previous run
            try? FileManager.default.removeItem(atPath: streamFile)
            try? FileManager.default.removeItem(atPath: stderrFile)

            queue.async {
                result = self.executeSync(code: code)
                semaphore.signal()
            }

            // Poll both stdout and stderr stream files while Python runs.
            // We MUST poll at least once per iteration regardless of
            // whether the semaphore was already signalled — otherwise
            // a fast render (manim finishes in <250ms) lets the wait()
            // return .success immediately and the loop body never runs,
            // so all output dumps only via the post-loop final-flush
            // (which the user perceives as "no streaming").
            var stdoutOffset: UInt64 = 0
            var stderrOffset: UInt64 = 0
            var pythonDone = false

            while !pythonDone {
                // Tight 50 ms poll interval so 1-second renders still
                // get ~20 ticks of live updates.
                if semaphore.wait(timeout: .now() + .milliseconds(50)) == .success {
                    pythonDone = true
                }
                let newStdout = self.readNewStreamBytes(from: streamFile, offset: &stdoutOffset)
                if !newStdout.isEmpty { onOutput(newStdout) }
                let newStderr = self.readNewStreamBytes(from: stderrFile, offset: &stderrOffset)
                if !newStderr.isEmpty { onOutput(newStderr) }
            }

            // Final flush — read any remaining content from both streams
            let remainOut = self.readNewStreamBytes(from: streamFile, offset: &stdoutOffset)
            if !remainOut.isEmpty {
                onOutput(remainOut)
            }
            let remainErr = self.readNewStreamBytes(from: stderrFile, offset: &stderrOffset)
            if !remainErr.isEmpty {
                onOutput(remainErr)
            }

            return result
        }

        // Non-streaming mode (original behavior)
        if DispatchQueue.getSpecific(key: queueKey) != nil {
            return executeSync(code: code)
        }
        return queue.sync {
            executeSync(code: code)
        }
    }

    /// Read new bytes from a stream file starting at the given offset. Fully defensive — never throws.
    private func readNewStreamBytes(from path: String, offset: inout UInt64) -> String {
        guard FileManager.default.fileExists(atPath: path),
              let data = FileManager.default.contents(atPath: path) else {
            return ""
        }
        let total = UInt64(data.count)
        guard total > offset else { return "" }
        let newData = data.subdata(in: Int(offset)..<Int(total))
        offset = total
        return String(data: newData, encoding: .utf8) ?? ""
    }

    private static var replStarted = false
    private static let replLock = NSLock()

    /// Raise KeyboardInterrupt in the Python main thread. Safe to
    /// call from any thread (Swift's Ctrl-C handler, usually); the
    /// interrupt is set asynchronously and takes effect at the next
    /// Python bytecode boundary. This is how a user interrupts a
    /// long-running computation (`while True: ...` etc.).
    ///
    /// Only meaningful once Python is initialized; before that we
    /// just swallow the request.
    func interruptPythonMainThread() {
        guard Py_IsInitialized() != 0 else { return }
        // PyErr_SetInterrupt is one of the few Python C-API calls
        // that's safe to invoke without holding the GIL.
        PyErr_SetInterrupt()
    }

    /// Eagerly boot Python (Py_Initialize + stdio redirect) and start
    /// the REPL thread. Call this from CodeEditorViewController when
    /// the terminal view appears, so the user can type commands
    /// immediately instead of having to hit Run first.
    ///
    /// Idempotent — subsequent calls are no-ops.
    func ensureRuntimeReady() {
        queue.async {
            if Py_IsInitialized() == 0 {
                do {
                    try self.configureEnvironmentBeforeInitialize()
                    PTYBridge.exportTTYEnv(cols: 80, rows: 24)
                    PTYBridge.shared.setupIfNeeded()
                    Py_Initialize()
                    guard Py_IsInitialized() != 0 else {
                        NSLog("[python] ensureRuntimeReady: Py_Initialize failed")
                        return
                    }

                    // Redirect sys.stdout / sys.stderr to the pipe at
                    // the Python level (same snippet as runTool uses).
                    let pipeFD = PTYBridge.shared.stdoutPipeWriteFD
                    let redirectSrc = """
                    import sys, os, io
                    try:
                        _fd = \(pipeFD)
                        if _fd >= 0:
                            # Build an unbuffered text writer that
                            # cannot get stuck on partial-line output
                            # (the shell prompt is "% " — no newline,
                            # so any line-buffered wrapper holds it).
                            # io.FileIO + io.TextIOWrapper(write_through=
                            # True, line_buffering=False) bypasses both
                            # the BufferedWriter buffer AND the text
                            # buffer — every write reaches the fd
                            # immediately. Tested working on iOS.
                            _raw = io.FileIO(_fd, mode='wb', closefd=False)
                            _w = io.TextIOWrapper(_raw,
                                                  encoding='utf-8',
                                                  errors='replace',
                                                  line_buffering=False,
                                                  write_through=True)
                            sys.stdout = _w
                            sys.stderr = _w
                    except Exception as _e:
                        pass
                    """
                    _ = redirectSrc.withCString { PyRun_SimpleString($0) }

                    // Install the python-ios-lib App Store import hook.
                    // After wrap-loose-dylibs.sh runs at build time,
                    // every C extension lives at
                    //   <App>.app/Frameworks/<sanitized>.framework/<X>
                    // not at its original .so path. Without this hook
                    // every `import numpy._core._multiarray_umath` etc.
                    // fails. The hook reads the wrap script's manifest
                    // and installs a MetaPathFinder that routes
                    // module-name lookups to the framework binaries.
                    let hookSrc = """
                    import sys, os
                    _stdlib = os.path.join(os.environ.get('PYTHONHOME', ''), '')
                    if _stdlib and _stdlib not in sys.path:
                        sys.path.insert(0, _stdlib)
                    try:
                        import python_ios_lib_import_hook
                        python_ios_lib_import_hook.install()
                    except Exception as _e:
                        # Hook absent (dev/TestFlight builds skip the
                        # wrap script) — every .so is still at its
                        # original path, so plain import resolution
                        # works without the hook.
                        pass
                    """
                    _ = hookSrc.withCString { PyRun_SimpleString($0) }

                    // Release the initial GIL so the REPL thread can
                    // acquire it.
                    let _ = PyEval_SaveThread()
                } catch {
                    NSLog("[python] ensureRuntimeReady: env setup failed: \(error)")
                    return
                }
            }
            PythonRuntime.startInteractiveShellIfNeeded()
        }
    }

    /// Start the interactive shell REPL on a background thread. Idempotent
    /// — subsequent calls are no-ops. Reads forever from sys.stdin (which
    /// is dup2'd onto the PTY slave by PTYBridge), so everything the user
    /// types into the SwiftTerm view becomes a dispatch call into
    /// offlinai_shell.
    static func startInteractiveShellIfNeeded() {
        replLock.lock()
        let alreadyStarted = replStarted
        replStarted = true
        replLock.unlock()
        guard !alreadyStarted else { return }

        DispatchQueue.global(qos: .userInitiated).async {
            let gil = PyGILState_Ensure()
            defer { PyGILState_Release(gil) }
            let ok = PyRun_SimpleString("""
            import threading, traceback, sys, faulthandler
            # Enable faulthandler at the bootstrap level so any C-level
            # crash during `import offlinai_shell` (or its transitive
            # imports — manimpango, torch, av, …) prints a Python stack
            # trace to stderr instead of surfacing as a bare  
            # EXC_BAD_ACCESS in the codebench-repl thread with no clue
            # where it came from. The shell's repl() re-enables it
            # later with all_threads=True; this earlier call covers
            # the import window.
            try:
                # Prefer the persistent log file at
                # Documents/Logs/manim_studio.log so a Python C-extension
                # segfault (manim → cairo, scipy → fortran, av → ffmpeg)
                # leaves a traceback the user can read in the Files app
                # after iOS reaps the process. If the path is unavailable
                # for any reason, fall back to stderr (the terminal pane).
                _faultlog_path = r"\(CrashLogger.shared.pythonFaultlogPath)"
                _fault_target = sys.stderr
                if _faultlog_path:
                    try:
                        _fault_target = open(_faultlog_path, "a", buffering=1)
                    except Exception:
                        _fault_target = sys.stderr
                faulthandler.enable(file=_fault_target, all_threads=True)
            except Exception:
                # iOS sandbox occasionally blocks faulthandler.enable when
                # the underlying stream lacks fileno(). Harmless — the
                # shell's repl() re-tries later with the cooked stream.
                pass
            # Suppress noisy third-party warnings that fire during bootstrap
            # imports (pydub's "couldn't find ffmpeg" — ffmpeg is bundled
            # under a different path; pydub doesn't know about it).
            try:
                import warnings as _w
                _w.filterwarnings("ignore", message=r".*ffmpeg or avconv.*")
                _w.filterwarnings("ignore", category=RuntimeWarning, module=r"pydub\\..*")
            except Exception:
                pass
            # Rebrand the bundled shell's banner from "CodeBench shell"
            # to "ManimStudio shell" without forking the package. The
            # literal lives inside an f-string at two sites in
            # offlinai_shell.py (banner emit + `python` builtin help),
            # so we wrap builtins.print with a filter that rewrites the
            # phrase wherever it appears. The filter is a no-op for any
            # other output (only one literal substitution), and it stays
            # in place for the lifetime of the interpreter — covering
            # both the initial banner and any later help-text print.
            #
            # We rebrand at the print() level rather than monkey-patching
            # offlinai_shell.repl because repl() is one giant function:
            # subclassing or replacing it would mean copying ~150 lines
            # of REPL machinery (PS1/PS2 cycling, async cancellation,
            # multi-line buffering, raw-mode key handling). Filtering
            # one phrase is a 6-line patch.
            # Set HOME + drop the user into a writable Documents/Workspace
            # directory before the shell prompt appears. Without this, the
            # interpreter starts at "/" (the read-only iOS sandbox root)
            # and EVERY filesystem builtin (ls, cd, cat, mkdir, touch, cp,
            # mv, rm, find, tree, grep, wc, …) hits PermissionError or
            # operates on a directory the app can't read. The shell has
            # an auto-chdir-to-Workspace fallback in its constructor, but
            # it only fires if the directory already exists — on a fresh
            # install it doesn't, so the fallback no-ops and cwd stays at
            # "/". Create the directory explicitly here so every shell
            # session starts in a writable place where commands work.
            try:
                import os as _os, pathlib as _pl
                _docs = _pl.Path.home() / "Documents"
                _ws   = _docs / "Workspace"
                _ws.mkdir(parents=True, exist_ok=True)
                # Mirror HOME → Documents so `~` in the prompt and
                # Path.home() in user code both resolve to a writable
                # location. iOS's default HOME points one level above
                # Documents (the container dir, which is read-only at
                # the top — Documents is the writable subdir).
                _os.environ["HOME"] = str(_docs)
                _os.chdir(str(_ws))
            except Exception:
                pass

            try:
                import builtins as _b
                _orig_print = _b.print
                def _ms_print(*args, **kwargs):
                    new_args = tuple(
                        a.replace("CodeBench shell", "ManimStudio shell")
                          .replace("CodeBench", "ManimStudio")
                        if isinstance(a, str) else a
                        for a in args
                    )
                    return _orig_print(*new_args, **kwargs)
                _b.print = _ms_print
            except Exception:
                pass
            def _codebench_start_repl():
                try:
                    import offlinai_shell  # module name kept (renaming would cascade-break dist-info + all `import` sites)
                    # Hide builtins that don't have a working backend on
                    # this build. pip in particular: the C extensions
                    # needed for compiled-wheel installs aren't shipped,
                    # and the iOS app sandbox doesn't expose a writable
                    # site-packages anyway, so the command would only
                    # ever fail. Removing from BUILTINS drops it from
                    # `help` output AND makes the dispatcher treat the
                    # word as a Python expression, which fails cleanly
                    # with NameError instead of a confusing
                    # "pip: not available: No module named 'pip'".
                    # Every pip-flavored builtin in the bundled shell.
                    # Earlier list missed the hyphenated forms — the
                    # decorator registers each as a separate dispatch
                    # key, so popping just "pip"/"pip3" left pip-list,
                    # pip-show, pip-install, pip-uninstall, pip-freeze,
                    # pip-check still visible in `help` and still
                    # routing to broken handlers.
                    try:
                        for _name in ("pip", "pip3",
                                      "pip-install", "pip-uninstall",
                                      "pip-list", "pip-show",
                                      "pip-freeze", "pip-check"):
                            offlinai_shell.BUILTINS.pop(_name, None)
                    except Exception:
                        pass

                    # Replace `top` / `htop` with implementations that
                    # don't need psutil. The bundled python-ios-lib
                    # build deletes psutil._psutil_osx (Apple private
                    # API rejection — ITMS-90338), so the shipped
                    # builtins fall through to "psutil not available".
                    # Apple's public sysctl + mach_task_basic_info
                    # + os.times() + platform are enough to show CPU,
                    # RSS memory, uptime, machine model, hostname, etc.
                    # All public APIs — no mach trap calls, no
                    # libSystem variable lookups (mach_task_self_ is a
                    # variable not a function and calling it via ctypes
                    # corrupts the stack), no private symbols. Pure
                    # stdlib + sysctlbyname for hardware stats.
                    try:
                        import ctypes, ctypes.util, struct, time as _t, os as _os
                        import platform as _plat, socket as _sock
                        import resource as _res

                        _libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.dylib")
                        _libc.sysctlbyname.argtypes = [
                            ctypes.c_char_p, ctypes.c_void_p,
                            ctypes.POINTER(ctypes.c_size_t),
                            ctypes.c_void_p, ctypes.c_size_t]
                        _libc.sysctlbyname.restype = ctypes.c_int

                        def _sysctl_str(name):
                            try:
                                sz = ctypes.c_size_t(0)
                                if _libc.sysctlbyname(name.encode(), None,
                                                       ctypes.byref(sz),
                                                       None, 0) != 0:
                                    return ""
                                if sz.value == 0:
                                    return ""
                                buf = ctypes.create_string_buffer(sz.value)
                                if _libc.sysctlbyname(name.encode(), buf,
                                                       ctypes.byref(sz),
                                                       None, 0) != 0:
                                    return ""
                                return buf.value.decode("utf-8", "replace")
                            except Exception:
                                return ""

                        def _sysctl_u64(name):
                            try:
                                v = ctypes.c_uint64(0)
                                sz = ctypes.c_size_t(8)
                                if _libc.sysctlbyname(name.encode(),
                                                       ctypes.byref(v),
                                                       ctypes.byref(sz),
                                                       None, 0) != 0:
                                    return 0
                                return v.value
                            except Exception:
                                return 0

                        def _fmt_bytes(n):
                            try:
                                n = float(n)
                            except Exception:
                                return "—"
                            for u in ("B", "KiB", "MiB", "GiB"):
                                if n < 1024: return f"{n:.1f} {u}"
                                n /= 1024
                            return f"{n:.1f} TiB"

                        def _uptime_seconds():
                            # kern.boottime returns a `struct timeval`
                            # (8-byte time_t + 8-byte suseconds_t on
                            # arm64). Wrap in try/except — sysctl is
                            # readable from app sandbox but the layout
                            # could shift in a future iOS major.
                            try:
                                sz = ctypes.c_size_t(16)
                                buf = ctypes.create_string_buffer(16)
                                if _libc.sysctlbyname(b"kern.boottime",
                                                       buf,
                                                       ctypes.byref(sz),
                                                       None, 0) != 0:
                                    return 0
                                sec, usec = struct.unpack_from("<qq", buf.raw, 0)
                                return max(0, _t.time() - sec - usec / 1e6)
                            except Exception:
                                return 0

                        def _fmt_uptime(s):
                            s = int(s); m, s = divmod(s, 60)
                            h, m = divmod(m, 60); d, h = divmod(h, 24)
                            if d: return f"{d}d {h}h {m}m"
                            if h: return f"{h}h {m}m {s}s"
                            if m: return f"{m}m {s}s"
                            return f"{s}s"

                        def _ms_top(_sh, _argv):
                            BOLD = "\\x1b[1m"; DIM  = "\\x1b[2m"
                            CYN  = "\\x1b[36m"; YLW = "\\x1b[33m"
                            GRN  = "\\x1b[32m"; RST = "\\x1b[0m"

                            ru = _os.times()
                            try:
                                rusage = _res.getrusage(_res.RUSAGE_SELF)
                                # ru_maxrss is in BYTES on Darwin (kilobytes
                                # on Linux). Display as peak RSS — that's
                                # close enough to "current memory" for a
                                # single-process iOS app where peak ≈ now
                                # most of the time.
                                rss_peak = int(rusage.ru_maxrss)
                            except Exception:
                                rss_peak = 0

                            total_ram = _sysctl_u64("hw.memsize")
                            ncpu = _sysctl_u64("hw.ncpu") or _sysctl_u64("hw.activecpu")
                            machine = _sysctl_str("hw.machine") or _plat.machine() or "—"
                            os_ver = _plat.platform()
                            try:
                                host = _sock.gethostname() or "device"
                            except Exception:
                                host = "device"
                            uptime_s = _uptime_seconds()
                            cpu_s = ru[0] + ru[1]

                            print(f"{BOLD}ManimStudio · top{RST}  {DIM}{host} ({machine}){RST}")
                            print(f"{DIM}OS{RST}         {os_ver}")
                            if uptime_s > 0:
                                print(f"{DIM}Uptime{RST}     {_fmt_uptime(uptime_s)}")
                            if ncpu:
                                print(f"{DIM}CPUs{RST}       {ncpu}")
                            if total_ram:
                                print(f"{DIM}RAM total{RST}  {_fmt_bytes(total_ram)}")
                            print("")
                            print(f"{BOLD}This process{RST}")
                            print(f"{DIM}PID{RST}        {_os.getpid()}")
                            if rss_peak:
                                print(f"{DIM}RSS peak{RST}   {GRN}{_fmt_bytes(rss_peak)}{RST}")
                            print(f"{DIM}CPU time{RST}   "
                                  f"{CYN}user {ru[0]:.2f}s · "
                                  f"sys {ru[1]:.2f}s "
                                  f"(total {cpu_s:.2f}s){RST}")

                        offlinai_shell.BUILTINS["top"]  = _ms_top
                        offlinai_shell.BUILTINS["htop"] = _ms_top
                    except Exception:
                        pass
                    offlinai_shell.repl()
                except Exception:
                    traceback.print_exc()
                    sys.stderr.flush()
            _t = threading.Thread(target=_codebench_start_repl, name='codebench-repl', daemon=True)
            _t.start()
            # (the REPL thread will print its own banner to the user;
            #  Swift-side status goes to NSLog via [shell] message below)
            """)
            if ok != 0 {
                NSLog("[shell] PyRun_SimpleString failed with code \(ok)")
            } else {
            }
        }
    }

    /// Call after first Py_Initialize to release the GIL for other threads
    private func releaseMainGILIfNeeded() {
        guard !gilReleasedForThreads else { return }
        gilReleasedForThreads = true
        // After Py_Initialize(), the calling thread holds the GIL.
        // We must release it so that PyGILState_Ensure can work from other threads.
    }

    func probeLibraries(_ libraries: [String]) -> [LibraryProbe] {
        let filtered = libraries
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        guard !filtered.isEmpty else { return [] }

        let script = """
import importlib, json
_codebench_lib_status = []
for _name in \(pythonArrayLiteral(filtered)):
    try:
        _mod = importlib.import_module(_name)
        _file = getattr(_mod, "__file__", "")
        _shim = not bool(_file)
        _codebench_lib_status.append({
            "name": _name,
            "state": "shim" if _shim else "installed",
            "detail": _file if _file else "built-in compatibility layer"
        })
    except Exception as _exc:
        _codebench_lib_status.append({
            "name": _name,
            "state": "missing",
            "detail": f"{type(_exc).__name__}: {_exc}"
        })
print("__CODEBENCH_LIB_STATUS__=" + json.dumps(_codebench_lib_status))
"""

        let result = execute(code: script)
        let output = result.output
        guard let markerRange = output.range(of: "__CODEBENCH_LIB_STATUS__=") else {
            let detail = output.trimmingCharacters(in: .whitespacesAndNewlines)
            return filtered.map {
                LibraryProbe(name: $0, state: .error, detail: detail.isEmpty ? "Probe failed." : detail)
            }
        }

        let jsonText = output[markerRange.upperBound...].trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = jsonText.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            return filtered.map {
                LibraryProbe(name: $0, state: .error, detail: "Probe response parsing failed.")
            }
        }

        return object.map { entry in
            let name = (entry["name"] as? String) ?? "unknown"
            let rawState = (entry["state"] as? String) ?? "error"
            let state = LibraryProbe.State(rawValue: rawState) ?? .error
            let detail = entry["detail"] as? String
            return LibraryProbe(name: name, state: state, detail: detail)
        }
    }

    private func executeSync(code: String) -> ExecutionResult {
        let trimmed = code.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return ExecutionResult(output: "Python tool error: empty code.", imagePath: nil)
        }

        let execStart = Date()

        do {
            if Py_IsInitialized() == 0 {
                try configureEnvironmentBeforeInitialize()

                // Set up a pseudo-terminal and dup2 it onto stdin/stdout/
                // stderr before Python opens its own file objects. This is
                // what makes pip, rich, tqdm, click, pytest etc. produce
                // proper output: `os.isatty(1)` returns True.
                PTYBridge.exportTTYEnv(cols: 80, rows: 24)
                PTYBridge.shared.setupIfNeeded()
                Py_Initialize()
                guard Py_IsInitialized() != 0 else {
                    throw RuntimeError.message("Embedded Python failed to initialize. Check bundled runtime files.")
                }

                // Redirect Python's sys.stdout and sys.stderr at the
                // PYTHON level — NOT at the C level via dup2.
                //
                // Why: iOS shares fd 1 and fd 2 across the whole process.
                //   • fd 1 — Swift print() writes here. If we dup2'd,
                //     every "[app] Returning to foreground" print from
                //     Swift would bleed into the user's terminal.
                //   • fd 2 — iOS os_log / WebKit write diagnostic msgs.
                //     If we dup2'd, OSLOG spam floods the terminal.
                //
                // Instead PTYBridge keeps the pipe write fd in
                // `stdoutPipeWriteFD` and we wrap it with os.fdopen at
                // the Python level. Swift print() stays on Xcode console;
                // only Python's sys.stdout / sys.stderr writes go to the
                // terminal.
                let pipeFD = PTYBridge.shared.stdoutPipeWriteFD
                let redirectStdioSource = """
                import sys, os, io
                try:
                    _fd = \(pipeFD)
                    if _fd >= 0:
                        _w = os.fdopen(_fd, 'w', buffering=1,
                                       encoding='utf-8', errors='replace',
                                       closefd=False)
                        sys.stdout = _w
                        sys.stderr = _w
                except Exception as _e:
                    import sys as _sys
                    _sys.__stderr__.write(f"[stdio redirect failed: {_e}]\\n")
                """
                _ = redirectStdioSource.withCString { PyRun_SimpleString($0) }

                // After Py_Initialize the calling thread holds the GIL.
                // Release it so PyGILState_Ensure works correctly from any thread.
                let _ = PyEval_SaveThread()
            } else {
            }

            // Start the interactive shell REPL on a background thread (idempotent).
            // Reads forever from sys.stdin (= PTY slave) so the user can
            // type into SwiftTerm and have their commands dispatched.
            PythonRuntime.startInteractiveShellIfNeeded()
            let gil = PyGILState_Ensure()
            defer {
                PyGILState_Release(gil)
            }

            let globals = try mainGlobals()
            try configurePythonPathsIfNeeded(globals: globals)

            let toolDir = try ensureToolOutputDirectory()
            let encoded = Data(trimmed.utf8).base64EncodedString()
            try setGlobalString(encoded, key: "__codebench_code_b64", globals: globals)
            try setGlobalString(toolDir.path, key: "__codebench_tool_dir", globals: globals)
            // Pass the PTY write fd straight through so _StreamWriter can
            // os.write() to it directly — bypassing every Python-side
            // buffering layer (os.fdopen line buffer, io.BufferedWriter,
            // io.TextIOWrapper) that was swallowing tqdm's \\r-only chunks.
            try setGlobalString(String(PTYBridge.shared.stdoutPipeWriteFD),
                                key: "__codebench_pty_fd", globals: globals)

            // Pass manim quality settings.
            //
            // Preview-vs-Render dispatch: ContentView sets the env var
            // OFFLINAI_MANIM_QUALITY = "low_quality" | "high_quality"
            // before each call. When that env var is "low_quality" we
            // FORCE quality=0 / fps=15 regardless of what ControlsSidebar
            // wrote into UserDefaults["manim_quality"|"manim_fps"]. The
            // user explicitly tapped Preview to iterate quickly — they
            // don't want a 1080p60 render. Without this override the
            // wrapper script reads the UserDefault straight, which is
            // always the FINAL render setting, so Preview rendered at
            // 1080p60 too.
            let envQuality: String = {
                guard let p = getenv("OFFLINAI_MANIM_QUALITY") else { return "" }
                return String(cString: p)
            }()
            let isPreview = envQuality == "low_quality"
            let manimQuality: Int
            let manimFPS: Int
            if isPreview {
                manimQuality = 0
                manimFPS     = 15
            } else {
                manimQuality = UserDefaults.standard.integer(forKey: "manim_quality")  // 0=low / 1=med / 2=high
                let storedFPS = UserDefaults.standard.integer(forKey: "manim_fps")
                manimFPS     = storedFPS > 0 ? storedFPS : 24
            }
            try setGlobalString(String(manimQuality), key: "__codebench_manim_quality", globals: globals)
            try setGlobalString(String(manimFPS),    key: "__codebench_manim_fps",     globals: globals)

            // Class-picker selection (set by execute(targetScene:)). "" /
            // "*" = render all detected Scene subclasses (legacy); a
            // bare class name = render only that one. We BAKE the value
            // directly into the wrapper source as a Python literal
            // rather than going through PyDict_SetItemString — the
            // dict-set + globals().get() chain has been observed to
            // return empty on the wrapper side under conditions that
            // never reproduce in isolation (race between the Swift
            // property store on the main thread, the queue dispatch,
            // and the wrapper read). Source-substitution sidesteps that
            // entirely: the value is part of the compiled bytecode.
            let pickedTarget = targetSceneForNextRun
            targetSceneForNextRun = ""
            // Also push it into globals as a defensive backup so any
            // legacy code path that still reads the global keeps working.
            try setGlobalString(pickedTarget, key: "__codebench_target_scene", globals: globals)
            let wrapperSource = Self.executionWrapperScript.replacingOccurrences(
                of: "__CODEBENCH_TARGET_SCENE_LITERAL__",
                with: pythonQuoted(pickedTarget))
            try runStatements(wrapperSource, filename: "<offlinai-python-tool>")
            let stdoutRaw = getGlobalString("__codebench_stdout", globals: globals)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let stdout = sanitizeToolStdout(stdoutRaw)
            let stderr = getGlobalString("__codebench_stderr", globals: globals)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            var imagePath = getGlobalString("__codebench_plot_path", globals: globals)
                .trimmingCharacters(in: .whitespacesAndNewlines)

            // Fallback path discovery — three layers, each independent of
            // Python globals. The wrapper's late assignment to
            // __codebench_plot_path doesn't survive to here for reasons we
            // haven't fully isolated (it's empty even though `[manim
            // rendered] /…` lines fire right after each set). Same goes
            // for __codebench_stdout sometimes. So we go straight to the
            // sources of truth.
            //
            // Layer 1: scan the captured stdout (cheapest, in-memory).
            // Layer 2: read the on-disk stream file directly (survives
            //          when __codebench_stdout is empty too).
            // Layer 3: walk the tool output directory and pick the most
            //          recently-modified video/image file (fully decoupled
            //          from Python — works even if both Python globals
            //          and the stream file are missing).
            // Track which fallback hit so we can surface it to the user
            // terminal (NSLog goes to Xcode console only — invisible in
            // log.txt). The string ends up in the diagnostic suffix on
            // result.output so the user sees `[fallback] ...` in the
            // terminal next to "$ Execution completed".
            var fallbackHitNote = ""
            // Diagnostic trail surfaced to the terminal so we can SEE
            // what every layer of the fallback chain found. Without this
            // a silent failure of all 3 layers manifests as just
            // "[output] No image path" with no clue why.
            var diagTrail: [String] = []

            let pathLooksUsable: (String) -> Bool = { p in
                !p.isEmpty && FileManager.default.fileExists(atPath: p)
            }
            diagTrail.append("[diag] global=\(imagePath.isEmpty ? "<empty>" : URL(fileURLWithPath: imagePath).lastPathComponent) usable=\(pathLooksUsable(imagePath))")

            // Treat an `imagePath` whose file is missing as "no path" so
            // the fallback dance still runs. This matters for manim,
            // which sometimes leaves __codebench_plot_path pointing at a
            // partial-frame .mp4 that gets unlinked when combine
            // produces the final combined_scenes.mp4.
            if !imagePath.isEmpty && !pathLooksUsable(imagePath) {
                imagePath = ""
            }

            if !pathLooksUsable(imagePath) {
                let scanned = Self.scanForLatestRenderedPath(in: stdoutRaw)
                diagTrail.append("[diag] stdoutRaw len=\(stdoutRaw.count), stdout-scan=\(scanned.isEmpty ? "<none>" : URL(fileURLWithPath: scanned).lastPathComponent)")
                if !scanned.isEmpty {
                    imagePath = scanned
                    fallbackHitNote = "[fallback] stdout-scan → \(URL(fileURLWithPath: scanned).lastPathComponent)"
                }
            }
            if !pathLooksUsable(imagePath) {
                let toolDir = (try? ensureToolOutputDirectory().path) ?? NSTemporaryDirectory()
                let streamFile = (toolDir as NSString).appendingPathComponent("_stream_stdout.txt")
                let streamExists = FileManager.default.fileExists(atPath: streamFile)
                if let streamData = FileManager.default.contents(atPath: streamFile),
                   let streamText = String(data: streamData, encoding: .utf8) {
                    let scanned = Self.scanForLatestRenderedPath(in: streamText)
                    diagTrail.append("[diag] streamFile exists=\(streamExists) len=\(streamText.count) scan=\(scanned.isEmpty ? "<none>" : URL(fileURLWithPath: scanned).lastPathComponent)")
                    if !scanned.isEmpty {
                        imagePath = scanned
                        fallbackHitNote = "[fallback] stream-file → \(URL(fileURLWithPath: scanned).lastPathComponent)"
                    }
                } else {
                    diagTrail.append("[diag] streamFile exists=\(streamExists) (no readable content)")
                }
            }
            if !pathLooksUsable(imagePath) {
                let toolDir = (try? ensureToolOutputDirectory().path) ?? NSTemporaryDirectory()
                // Constrain the dir-scan to media produced DURING this run
                // — otherwise a script that doesn't render anything (e.g.
                // a pywebview / requests / data-only run) used to surface
                // the previous manim video as if it were the new output.
                if let recent = Self.mostRecentMediaFile(
                    under: toolDir, modifiedSince: execStart) {
                    imagePath = recent
                    fallbackHitNote = "[fallback] dir-scan → \(URL(fileURLWithPath: recent).lastPathComponent)"
                    diagTrail.append("[diag] dir-scan(\(toolDir)) → \(URL(fileURLWithPath: recent).lastPathComponent)")
                } else {
                    diagTrail.append("[diag] dir-scan(\(toolDir)) → <none after \(execStart))")
                }
            }

            var finalImagePath: String?
            if !imagePath.isEmpty, FileManager.default.fileExists(atPath: imagePath) {
                finalImagePath = imagePath
            } else if !imagePath.isEmpty {
                NSLog("[python] __codebench_plot_path set to %@ but FileManager.fileExists returned false", imagePath)
            }

            let plotOnlyStdout = Self.isPlotOnlyOutput(stdout, imagePath: finalImagePath)
            var sections: [String] = []
            if !stdout.isEmpty && !plotOnlyStdout {
                sections.append(stdout)
            }
            // Surface fallback-path-discovery hits to the user terminal
            // so log.txt makes it obvious which layer recovered the
            // preview path. Empty when no fallback was needed.
            if !fallbackHitNote.isEmpty {
                sections.append(fallbackHitNote)
            }
            // Surface the diagnostic trail when no preview path could be
            // recovered — gives the user a chance to figure out why
            // their render isn't surfacing in the preview panel.
            if finalImagePath == nil {
                sections.append(diagTrail.joined(separator: "\n"))
            }
            // Filter stderr: only include actual errors, not warnings
            if !stderr.isEmpty {
                let isWarningOnly = stderr.allSatisfy(\.isWhitespace)
                    || (stderr.contains("Warning") && !stderr.contains("Error") && !stderr.contains("Traceback"))
                let isActualError = stderr.contains("Traceback") || stderr.contains("Error") || stderr.contains("Exception")
                if isActualError {
                    sections.append("stderr:\n\(stderr)")
                } else if !isWarningOnly {
                    sections.append("stderr:\n\(stderr)")
                }
                // Print warnings to Xcode console but don't pollute tool output
                if !isActualError {
                    print("[python] warning (hidden from user): \(stderr.prefix(200))")
                }
            }

            if sections.isEmpty && finalImagePath == nil {
                sections.append("Python executed successfully (no output).")
            }
            return ExecutionResult(output: sections.joined(separator: "\n\n"), imagePath: finalImagePath)
        } catch {
            return ExecutionResult(output: "Python tool error: \(error.localizedDescription)", imagePath: nil)
        }
    }

    /// Scan a blob of text for the LAST `[manim rendered] /…` marker and
    /// return the path it carries (if the file exists on disk). Returns
    /// "" when no usable marker is found. Used as a Swift-side fallback
    /// when the Python wrapper's `__codebench_plot_path` global doesn't
    /// reach us through `getGlobalString`.
    private static func scanForLatestRenderedPath(in text: String) -> String {
        let marker = "[manim rendered] "
        let lines = text.components(separatedBy: "\n")
        for line in lines.reversed() {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard trimmed.hasPrefix(marker) else { continue }
            let candidate = String(trimmed.dropFirst(marker.count))
                .trimmingCharacters(in: .whitespaces)
            guard candidate.hasPrefix("/"),
                  FileManager.default.fileExists(atPath: candidate) else { continue }
            return candidate
        }
        return ""
    }

    /// Walk `dir` recursively and return the absolute path of the most
    /// recently-modified video/image file. Used as a last-resort fallback
    /// when neither the Python global nor the streamed stdout has yielded
    /// a render path. Bounded to typical render outputs (mp4 / gif / png /
    /// pdf) to avoid picking up source files or unrelated artifacts.
    private static func mostRecentMediaFile(under dir: String,
                                            modifiedSince: Date) -> String? {
        let extensions: Set<String> = ["mp4", "mov", "webm", "m4v", "gif", "png", "jpg", "jpeg", "pdf"]
        let dirURL = URL(fileURLWithPath: dir)
        guard let enumerator = FileManager.default.enumerator(
            at: dirURL,
            includingPropertiesForKeys: [.contentModificationDateKey, .isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else { return nil }
        // Reject anything older than `modifiedSince` MINUS a small grace
        // window. Without this, a Python script that produces no media
        // (e.g. a pywebview / requests / data-only run) silently surfaced
        // the LAST run's manim video because the dir-scan picked it up.
        // The grace window absorbs filesystem-mtime granularity (HFS+
        // tracks 1 s; APFS is finer but still not always sub-frame) and
        // any small clock skew between when execStart was captured and
        // when the script's first write actually completed.
        let cutoff = modifiedSince.addingTimeInterval(-1.0)
        var best: (String, Date)?
        for case let url as URL in enumerator {
            let values = try? url.resourceValues(forKeys: [.contentModificationDateKey, .isRegularFileKey])
            guard values?.isRegularFile == true,
                  extensions.contains(url.pathExtension.lowercased()),
                  let modDate = values?.contentModificationDate,
                  modDate >= cutoff else { continue }
            // Prefer combined_scenes.mp4 / non-partial files over per-frame
            // partials. Skip anything inside a `partial_movie_files/` subdir
            // — those are fragments, not the final output.
            if url.path.contains("/partial_movie_files/") { continue }
            if let (_, prev) = best, prev >= modDate { continue }
            best = (url.path, modDate)
        }
        return best?.0
    }

    private static func isPlotOnlyOutput(_ stdout: String, imagePath: String?) -> Bool {
        guard imagePath != nil else { return false }
        let lines = stdout
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        guard !lines.isEmpty else { return true }
        return lines.allSatisfy { line in
            line == "plt.show()"
                || line.hasPrefix("[plot saved]")
                || line.hasPrefix("[manim rendered]")
                || line == "None"
                || line == "Using built-in numpy compatibility layer."
                || line == "Using built-in matplotlib compatibility layer."
        }
    }

    private func sanitizeToolStdout(_ stdout: String) -> String {
        if stdout.isEmpty {
            return stdout
        }
        let lines = stdout
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { line in
                guard !line.isEmpty else { return false }
                if line == "plt.show()" { return false }
                if line.hasPrefix("[plot saved]") { return false }
                if line == "Using built-in numpy compatibility layer." { return false }
                if line == "Using built-in matplotlib compatibility layer." { return false }
                return true
            }
        return lines.joined(separator: "\n")
    }

    private func configurePythonPathsIfNeeded(globals: PyObjectPointer) throws {
        guard !pathsConfigured else { return }

        let bundleURL = Bundle.main.bundleURL
        let stdlibURL = bundleURL.appendingPathComponent("python-stdlib", isDirectory: true)
        guard FileManager.default.fileExists(atPath: stdlibURL.appendingPathComponent("os.py").path) else {
            throw RuntimeError.message("Python runtime not found (looked for python-stdlib/os.py).")
        }
        let versionPath = stdlibURL.path
        let dynloadPath = stdlibURL.appendingPathComponent("lib-dynload", isDirectory: true).path
        let toolDir = try ensureToolOutputDirectory().path

        // BeeWare-shaped or fallback per-bundle layout (matches the
        // logic in configureEnvironmentBeforeInitialize).
        // Add BOTH the consolidated site-packages AND any remaining
        // python-ios-lib_*.bundle dirs — consolidation can be partial,
        // and bundles may persist alongside an empty site-packages.
        let sitePackages = bundleURL
            .appendingPathComponent("app_packages/site-packages",
                                    isDirectory: true).path
        var libBundlePaths: [String] = []
        if FileManager.default.fileExists(atPath: sitePackages) {
            libBundlePaths.append(sitePackages)
        }
        if let entries = try? FileManager.default.contentsOfDirectory(atPath: bundleURL.path) {
            var bundleList: [String] = []
            for name in entries where name.hasPrefix("python-ios-lib_") && name.hasSuffix(".bundle") {
                bundleList.append(bundleURL.appendingPathComponent(name).path)
            }
            libBundlePaths += bundleList.sorted()
        }

        let documentsURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
        let userSitePath = documentsURL?.appendingPathComponent("site-packages", isDirectory: true).path ?? ""
        if !userSitePath.isEmpty {
            try? FileManager.default.createDirectory(atPath: userSitePath, withIntermediateDirectories: true)
        }

        let metadataPath = bundleURL.appendingPathComponent("python-metadata", isDirectory: true).path
        let metadataPaths: [String] = FileManager.default.fileExists(atPath: metadataPath) ? [metadataPath] : []
        let allPaths = ([versionPath, dynloadPath] + libBundlePaths + metadataPaths + [userSitePath])
            .filter { !$0.isEmpty }
        let script = """
import os, sys
for _p in [\(allPaths.map { pythonQuoted($0) }.joined(separator: ", "))]:
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("MPLCONFIGDIR", \(pythonQuoted(toolDir)))
"""
        _ = globals
        try runStatements(script, filename: "<offlinai-python-paths>")
        pathsConfigured = true
    }

    /// Eagerly dlopen the BLAS stub framework so its `_dcabs1_` and
    /// `_lsame_` symbols enter the process flat namespace before any
    /// scipy import. scipy.linalg.cython_blas.so was built linking
    /// Accelerate.framework, but iOS Accelerate doesn't export those
    /// two Fortran-mangled BLAS reference helpers; without this preload
    /// dyld fails the load with "symbol not found in flat namespace
    /// '_dcabs1_'" at the first `from scipy.linalg import …` and any
    /// downstream import (manim → scipy.spatial → scipy.sparse.linalg)
    /// dies with that traceback.
    ///
    /// install-python-stdlib.sh's Step 15 builds the stub framework and
    /// drops it at <App>.app/Frameworks/libscipy_blas_stubs.framework/.
    /// It's a 10-line C dylib, so the dlopen cost is negligible.
    /// dlopen a stub framework with RTLD_GLOBAL so its symbols join the
    /// process-wide flat namespace before any scipy import runs.
    private func preloadStubFramework(_ fwName: String) {
        let path = Bundle.main.bundleURL
            .appendingPathComponent("Frameworks", isDirectory: true)
            .appendingPathComponent("\(fwName).framework", isDirectory: true)
            .appendingPathComponent(fwName).path
        guard FileManager.default.fileExists(atPath: path) else { return }
        if dlopen(path, RTLD_NOW | RTLD_GLOBAL) == nil,
           let cstr = dlerror() {
            NSLog("[python] %s preload failed: %s", fwName, cstr)
        }
    }

    /// Two stub frameworks must be in the flat namespace before scipy
    /// gets imported:
    ///   • libscipy_blas_stubs   — _dcabs1_, _lsame_ for cython_blas
    ///   • libfortran_io_stubs   — __FortranA* for arpack / propack
    /// Both ship as .frameworks under <App>.app/Frameworks/. Order
    /// doesn't matter; their symbol sets are disjoint.
    private func preloadScipySupportFrameworks() {
        preloadStubFramework("libscipy_blas_stubs")
        preloadStubFramework("libfortran_io_stubs")
    }

    private func configureEnvironmentBeforeInitialize() throws {
        guard !environmentConfigured else { return }
        preloadScipySupportFrameworks()

        let fileManager = FileManager.default
        let bundleURL = Bundle.main.bundleURL

        // BeeWare stdlib (installed by scripts/install-python-stdlib.sh).
        let stdlibURL = bundleURL.appendingPathComponent("python-stdlib", isDirectory: true)
        let stdlibPath = stdlibURL.path
        let dynloadPath = stdlibURL.appendingPathComponent("lib-dynload", isDirectory: true).path
        let osModule = stdlibURL.appendingPathComponent("os.py").path
        let encodingsDir = stdlibURL.appendingPathComponent("encodings", isDirectory: true).path
        guard fileManager.fileExists(atPath: stdlibPath),
              fileManager.fileExists(atPath: osModule),
              fileManager.fileExists(atPath: encodingsDir) else {
            throw RuntimeError.message(
                "Python stdlib missing at \(stdlibPath). " +
                "Run-Script phase 'Install Python stdlib' must succeed.")
        }

        // BeeWare-shaped layout — install-python-stdlib.sh consolidates
        // every SwiftPM `python-ios-lib_*.bundle/<pkg>` into
        // `<App>/app_packages/site-packages/<pkg>` so the App Store
        // wrap-loose-dylibs.sh script can find them.
        //
        // We add BOTH paths to sys.path because consolidation may be
        // partial (e.g. archive build moved some bundles, dev/Run build
        // didn't, or vice-versa). app_packages/site-packages may exist
        // but be empty/incomplete; the python-ios-lib_*.bundle dirs may
        // also still be present. Including both means whichever has the
        // package, Python finds it.
        let sitePackages = bundleURL
            .appendingPathComponent("app_packages/site-packages",
                                    isDirectory: true).path
        var pyLibBundles: [String] = []
        if fileManager.fileExists(atPath: sitePackages) {
            pyLibBundles.append(sitePackages)
        }
        if let entries = try? fileManager.contentsOfDirectory(atPath: bundleURL.path) {
            for name in entries where name.hasPrefix("python-ios-lib_") && name.hasSuffix(".bundle") {
                pyLibBundles.append(bundleURL.appendingPathComponent(name).path)
            }
        }
        // Stable ordering: site-packages first (consolidated wins on
        // collision), then bundles alphabetical.
        if pyLibBundles.count > 1 {
            let sp = pyLibBundles.first
            let rest = Array(pyLibBundles.dropFirst()).sorted()
            pyLibBundles = (sp.map { [$0] } ?? []) + rest
        }

        let documentsURL = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first
        let userSitePath = documentsURL?.appendingPathComponent("site-packages", isDirectory: true).path ?? ""
        if !userSitePath.isEmpty {
            try? fileManager.createDirectory(atPath: userSitePath, withIntermediateDirectories: true)
        }
        // python-metadata/ holds *.dist-info dirs harvested by the build
        // script — needed for importlib.metadata.version("click") etc.
        let metadataPath = bundleURL.appendingPathComponent("python-metadata", isDirectory: true).path
        let metadataPaths: [String] = fileManager.fileExists(atPath: metadataPath) ? [metadataPath] : []

        let pythonPath = ([stdlibPath, dynloadPath] + pyLibBundles + metadataPaths + [userSitePath])
            .filter { !$0.isEmpty }
            .joined(separator: ":")
        let pythonRoot = stdlibPath
        let toolDir = try ensureToolOutputDirectory().path

        setenv("PYTHONHOME", pythonRoot, 1)
        setenv("PYTHONPATH", pythonPath, 1)
        setenv("PYTHONNOUSERSITE", "1", 1)
        setenv("PYTHONDONTWRITEBYTECODE", "1", 1)
        setenv("MPLCONFIGDIR", toolDir, 1)

        // BeeWare's per-arch _sysconfigdata; without this pydoc (used
        // transitively by scipy) crashes with AttributeError 'installed_base'.
        #if targetEnvironment(simulator)
            #if arch(arm64)
                setenv("_PYTHON_SYSCONFIGDATA_NAME", "_sysconfigdata__ios_arm64-iphonesimulator", 1)
            #else
                setenv("_PYTHON_SYSCONFIGDATA_NAME", "_sysconfigdata__ios_x86_64-iphonesimulator", 1)
            #endif
        #else
            setenv("_PYTHON_SYSCONFIGDATA_NAME", "_sysconfigdata__ios_arm64-iphoneos", 1)
        #endif

        // CRITICAL: force Python to use the system malloc for ALL
        // allocations instead of its own `pymalloc` arena allocator.
        //
        // Why: pymalloc keeps freed memory in a per-arena pool and
        // NEVER returns pages to the OS during a process's lifetime.
        // That means even after `gc.collect()` + explicit ref drops,
        // the kernel still sees our RSS as elevated, iOS jetsam
        // counts it against our budget, and a memory-heavy manim
        // scene leaves 3–7 GB of RSS "stuck" after it finishes even
        // though Python-visible objects are all dead.
        //
        // With `PYTHONMALLOC=malloc`, Python uses Darwin's system
        // malloc. Darwin DOES return freed pages on
        // `malloc_zone_pressure_relief()` (which we call from our
        // between-scene cleanup). End-to-end effect: after
        // scene.render() finishes + cleanup runs, RSS actually
        // drops back to baseline, visible to iOS, jetsam forgets.
        //
        // Cost: system malloc is slightly slower than pymalloc for
        // very small allocations — a few-percent overall. Acceptable
        // trade for not getting jetsam-killed at scene 2.
        //
        // Must be set BEFORE Py_Initialize; has no effect after.
        setenv("PYTHONMALLOC", "malloc", 1)

        // iOS's /tmp resolves to the system-owned /private/var/tmp which is
        // read-only for sandboxed apps. Point TMPDIR / TMP / TEMP at the
        // writable per-app container tmp so Python's tempfile.gettempdir(),
        // PIL's Image.save() default, pip's build cache etc. all work.
        let tmpDir = NSTemporaryDirectory()
        setenv("TMPDIR", tmpDir, 1)
        setenv("TMP",    tmpDir, 1)
        setenv("TEMP",   tmpDir, 1)

        environmentConfigured = true
    }

    private func ensureToolOutputDirectory() throws -> URL {
        if let cached = toolOutputDirectoryURL {
            return cached
        }
        guard let documentsURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
            throw RuntimeError.message("Unable to resolve documents directory for Python tool output.")
        }
        let outputURL = documentsURL.appendingPathComponent("ToolOutputs", isDirectory: true)
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
        toolOutputDirectoryURL = outputURL
        return outputURL
    }

    private func firstPythonVersionPath(in rootURL: URL) -> String? {
        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: rootURL,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else {
            return nil
        }
        let candidates = entries
            .filter { $0.lastPathComponent.hasPrefix("python") }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
        return candidates.first?.path
    }

    private func mainGlobals() throws -> PyObjectPointer {
        guard let module = "__main__".withCString({ PyImport_AddModule($0) }) else {
            throw RuntimeError.message("Unable to load Python __main__ module.")
        }
        guard let globals = PyModule_GetDict(module) else {
            throw RuntimeError.message("Unable to access Python global dictionary.")
        }
        return globals
    }

    private func runStatements(_ source: String, filename: String) throws {
        // Crash-proof GIL guard: every path to PyEval_EvalCode must hold
        // the GIL. On Mac "Designed for iPad" we've seen EXC_BAD_ACCESS
        // deep inside the evaluator; most commonly the culprit is a
        // missing GIL acquire on a background thread. Surface the bug as
        // a throwable error instead of a SIGBUS.
        if PyGILState_Check() == 0 {
            let who = Thread.current.description
            NSLog("[PythonRuntime] runStatements called without GIL on %@ " +
                  "(filename=%@, source.count=%d) — refusing to evaluate",
                  who, filename, source.count)
            throw RuntimeError.message(
                "Python evaluator called without GIL on \(who); " +
                "wrap the call in PyGILState_Ensure / Release.")
        }
        let compiled = source.withCString { sourcePointer in
            filename.withCString { filenamePointer in
                Py_CompileString(sourcePointer, filenamePointer, fileInputMode)
            }
        }
        guard let codeObject = compiled else {
            throw RuntimeError.message(currentPythonError() ?? "Failed to compile Python source.")
        }
        defer { Py_DecRef(codeObject) }

        let globals = try mainGlobals()
        // Breadcrumb: if PyEvK1al_EvalCode SIGBUSes (seen on Mac Designed-
        // for-iPad when an iOS-built C extension fails to properly load
        // its dylib and stores a stale function pointer), this NSLog is
        // the last thing in Console.app — tells us which source was the
        // trigger.
        guard let result = PyEval_EvalCode(codeObject, globals, globals) else {
            throw RuntimeError.message(currentPythonError() ?? "Failed to execute Python code.")
        }
        Py_DecRef(result)
    }

    private func setGlobalString(_ value: String, key: String, globals: PyObjectPointer) throws {
        let pyValue = value.withCString { PyUnicode_FromString($0) }
        guard let pyValue else {
            throw RuntimeError.message(currentPythonError() ?? "Unable to convert Swift string for Python.")
        }
        defer { Py_DecRef(pyValue) }

        let status = key.withCString { keyPointer in
            PyDict_SetItemString(globals, keyPointer, pyValue)
        }
        if status != 0 {
            throw RuntimeError.message(currentPythonError() ?? "Unable to store Python runtime variable.")
        }
    }

    private func getGlobalString(_ key: String, globals: PyObjectPointer) -> String {
        let object = key.withCString { keyPointer in
            PyDict_GetItemString(globals, keyPointer)
        }
        guard let object else { return "" }
        return pythonString(from: object) ?? ""
    }

    private func pythonString(from object: PyObjectPointer) -> String? {
        var size: PySsizeT = 0
        if let utf8 = PyUnicode_AsUTF8AndSize(object, &size) {
            return String(cString: utf8)
        }
        guard let rendered = PyObject_Str(object) else {
            return nil
        }
        defer { Py_DecRef(rendered) }
        var renderedSize: PySsizeT = 0
        guard let utf8 = PyUnicode_AsUTF8AndSize(rendered, &renderedSize) else {
            return nil
        }
        return String(cString: utf8)
    }

    private func currentPythonError() -> String? {
        guard PyErr_Occurred() != nil else {
            return nil
        }
        var type: PyObjectPointer?
        var value: PyObjectPointer?
        var traceback: PyObjectPointer?
        PyErr_Fetch(&type, &value, &traceback)
        PyErr_NormalizeException(&type, &value, &traceback)
        defer {
            if let type { Py_DecRef(type) }
            if let value { Py_DecRef(value) }
            if let traceback { Py_DecRef(traceback) }
        }
        if let value, let text = pythonString(from: value), !text.isEmpty {
            return text
        }
        if let type, let text = pythonString(from: type), !text.isEmpty {
            return text
        }
        return "Unknown Python error."
    }

    private func pythonQuoted(_ value: String) -> String {
        var escaped = value.replacingOccurrences(of: "\\", with: "\\\\")
        escaped = escaped.replacingOccurrences(of: "'", with: "\\'")
        return "'\(escaped)'"
    }

    private func pythonArrayLiteral(_ values: [String]) -> String {
        let encoded = values.map { pythonQuoted($0) }
        return "[\(encoded.joined(separator: ", "))]"
    }


    private static let executionWrapperScript = """
import base64, io, os, sys, time, traceback, uuid, warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
__codebench_stdout = ""
__codebench_stderr = ""
__codebench_plot_path = ""
# Picker target — baked in as a Python literal by Swift at runtime
# (see PythonRuntime.swift `wrapperSource = ...replacingOccurrences`).
# This used to be `str(globals().get("__codebench_target_scene", ""))`
# but that path was unreliable: the global was observed empty here
# even when Swift's setGlobalString had successfully stored it,
# under conditions that never reproduced in isolation (race between
# the Swift main-thread property write, the dispatch queue boundary,
# and the wrapper read). Source-baked literal removes the entire
# cross-thread / cross-language data path.
_codebench_picker_target_locked = (__CODEBENCH_TARGET_SCENE_LITERAL__ or "").strip()
try:
    sys.__stderr__.write(
        f"[picker] entry locked = "
        f"{_codebench_picker_target_locked!r}\\n")
    sys.__stderr__.flush()
except Exception:
    pass
_t0 = time.time()
# On iOS there's no real tty — sys.__stderr__ may be broken (Errno 5).
# Use a StringIO log buffer that we can read later if needed.
_log_buf = io.StringIO()
def _log(msg):
    # Internal wrapper diagnostics — go to Xcode console only, not to
    # the user-facing terminal. The terminal already shows real Python
    # stdout/stderr via the PTY redirect, so adding [py-exec] noise on
    # top would clutter every command (`ls`, `pip list`, etc.).
    line = f"[py-exec] [{time.time()-_t0:.2f}s] {msg}"
    _log_buf.write(line + "\\n")
    try:
        sys.__stderr__.write(line + "\\n")
        sys.__stderr__.flush()
    except Exception:
        pass
_log("Decoding code...")
_offlinai_code = base64.b64decode(__codebench_code_b64.encode("utf-8")).decode("utf-8", "replace")
_log(f"Code decoded ({len(_offlinai_code)} chars)")

# Pre-load the Fortran I/O runtime stubs so scipy's ARPACK (and any other
# flang-compiled extension) can resolve `_Fortran*` symbols at dlopen time.
# The stubs live in the app bundle's Frameworks/ directory. Searching for
# it: iOS Python sys.path entries include the app bundle resource paths,
# so we scan them for anything that looks like the bundle root and build
# the Frameworks/libfortran_io_stubs.dylib path from there.
try:
    import ctypes
    import os as _os_stub
    _candidates = []
    # (1) Derive from entries of sys.path that point into the app bundle.
    for _p in sys.path:
        if _p and _p.endswith(".app") or ".app/" in _p:
            # Trim everything after CodeBench.app to get bundle root.
            _root = (_p.split(".app/", 1)[0] + ".app") if ".app/" in _p else _p
            _candidates.append(_os_stub.path.join(_root, "Frameworks", "libfortran_io_stubs.dylib"))
            break
    # (2) Fallbacks
    _candidates += [
        "@rpath/libfortran_io_stubs.dylib",
        "libfortran_io_stubs.dylib",
    ]
    _loaded = False
    _errs = []
    for _candidate in _candidates:
        try:
            ctypes.CDLL(_candidate, mode=ctypes.RTLD_GLOBAL)
            _log(f"pre-loaded fortran IO stubs from {_candidate}")
            _loaded = True
            break
        except OSError as _e:
            _errs.append(f"{_candidate}: {_e}")
    if not _loaded:
        # Only surface this to the user's terminal if it actually
        # matters (scipy arpack / propack fail without the stubs).
        _log("fortran IO stubs preload failed; scipy arpack/propack will crash")
        _log(f"tried {len(_candidates)} paths:")
        for _e in _errs[:4]:
            _log(f"  {_e}")
except Exception as _fe:
    _log(f"fortran IO stubs preload skipped: {type(_fe).__name__}: {_fe}")

# Streaming stdout/stderr — writes to file immediately so Swift can poll,
# AND tees to the previously-active sys.stdout/stderr (the PTY pipe set up
# by ensureRuntimeReady) so the user sees manim/tqdm/rich output live in
# the SwiftTerm terminal pane while the render is running.
class _StreamWriter:
    # Writes to BOTH the _stream_*.txt file (for Swift polling — needed
    # because the polling loop is the canonical "Python finished" signal)
    # AND directly to the PTY pipe fd (for real-time streaming to
    # SwiftTerm). Without the PTY tee, output only appears in batches
    # whenever the OS flushes the file — on iOS device that can lag
    # several seconds, making manim/tqdm progress feel frozen.
    _pty_fd_str = globals().get('__codebench_pty_fd', '')
    _pty_fd = int(_pty_fd_str) if _pty_fd_str.isdigit() else -1

    def __init__(self, path):
        self._buf = io.StringIO()
        self._f = open(path, 'w', encoding='utf-8') if path else None
    def write(self, s):
        if s:
            try:
                self._buf.write(s)
            except (ValueError, OSError):
                pass
            if self._f:
                try:
                    self._f.write(s)
                    self._f.flush()
                except (ValueError, OSError):
                    pass
            # Tee to PTY pipe — bytes go straight to SwiftTerm with no
            # file-system buffering in the way. os.write() is unbuffered.
            if _StreamWriter._pty_fd >= 0:
                try:
                    os.write(_StreamWriter._pty_fd, s.encode('utf-8', 'replace'))
                except (ValueError, OSError, BlockingIOError):
                    pass
        return len(s) if s else 0
    def flush(self):
        if self._f:
            try:
                self._f.flush()
            except (ValueError, OSError):
                pass
    def getvalue(self):
        return self._buf.getvalue()
    def close(self):
        if self._f:
            self._f.close()
    def fileno(self):
        raise io.UnsupportedOperation("fileno")
    @property
    def encoding(self):
        return 'utf-8'
    def isatty(self):
        return True
    def readable(self):
        return False
    def writable(self):
        return True

_stream_dir = globals().get('__codebench_tool_dir', '')
_out_stream = _StreamWriter(os.path.join(_stream_dir, '_stream_stdout.txt') if _stream_dir else '')
_err_stream = _StreamWriter(os.path.join(_stream_dir, '_stream_stderr.txt') if _stream_dir else '')
_old_stdout, _old_stderr = sys.stdout, sys.stderr
sys.stdout, sys.stderr = _out_stream, _err_stream
try:
    # Import numpy and create SafeArray subclass so `if array:` never crashes
    _log("Importing numpy...")
    try:
        import numpy as np
        np.seterr(divide='ignore', invalid='ignore')

        # ndarray.__bool__ raises on multi-element arrays. We can't patch the
        # immutable builtin type, but we CAN subclass it. SafeArray.__bool__
        # falls back to .any(), and __array_finalize__ ensures ALL numpy ops
        # (ufuncs, slicing, arithmetic) propagate the subclass automatically.
        class SafeArray(np.ndarray):
            def __new__(cls, input_array):
                return np.asarray(input_array).view(cls)
            def __array_finalize__(self, obj):
                pass
            def __bool__(self):
                if self.size == 0: return False
                if self.size == 1: return bool(self.flat[0])
                return bool(self.any())
            def __and__(self, other):
                return np.bitwise_and(np.asarray(self), np.asarray(other)).view(SafeArray)
            def __or__(self, other):
                return np.bitwise_or(np.asarray(self), np.asarray(other)).view(SafeArray)

        # Patch numpy functions ONCE so they return SafeArray.
        # Guard: skip if already patched (script re-runs per execution).
        if not getattr(np, '_offlinai_patched', False):
            np._offlinai_patched = True

            _np_creators = [
                'linspace', 'arange', 'zeros', 'ones', 'array', 'asarray',
                'empty', 'full', 'zeros_like', 'ones_like', 'empty_like',
                'full_like', 'logspace', 'geomspace', 'eye', 'identity',
                'diag', 'fromfunction', 'copy',
            ]
            for _fn_name in _np_creators:
                _orig = getattr(np, _fn_name, None)
                if _orig is None:
                    continue
                def _make_safe(_orig_fn):
                    def _wrapper(*a, **k):
                        r = _orig_fn(*a, **k)
                        if isinstance(r, np.ndarray) and type(r) is np.ndarray:
                            return r.view(SafeArray)
                        return r
                    _wrapper.__name__ = _orig_fn.__name__
                    return _wrapper
                setattr(np, _fn_name, _make_safe(_orig))

            # meshgrid returns a list of arrays
            _orig_meshgrid = np.meshgrid
            def _safe_meshgrid(*a, **k):
                results = _orig_meshgrid(*a, **k)
                return [r.view(SafeArray) if isinstance(r, np.ndarray) else r for r in results]
            np.meshgrid = _safe_meshgrid

            # random functions
            for _rng_name in ['rand', 'randn', 'random', 'uniform', 'normal', 'randint']:
                _orig_rng = getattr(np.random, _rng_name, None)
                if _orig_rng:
                    def _make_safe_rng(_orig_fn):
                        def _wrapper(*a, **k):
                            r = _orig_fn(*a, **k)
                            if isinstance(r, np.ndarray) and type(r) is np.ndarray:
                                return r.view(SafeArray)
                            return r
                        return _wrapper
                    setattr(np.random, _rng_name, _make_safe_rng(_orig_rng))

            _log(f"numpy {np.__version__} OK (SafeArray patched)")
        else:
            _log(f"numpy {np.__version__} OK (already patched)")
    except Exception as _e:
        _log(f"numpy failed: {_e}")

    # Import matplotlib (our plotly-backed package in site-packages/matplotlib/)
    _log("Importing matplotlib...")
    _plt = None
    try:
        import matplotlib
        import matplotlib.pyplot as _plt
        _log(f"matplotlib {matplotlib.__version__} OK")
    except Exception as _e:
        _log(f"matplotlib failed: {_e}")

    # CSS patch injected into every generated plotly HTML to make the chart
    # fill 100% of the WKWebView viewport — no fixed 420px heights, no cropped
    # bottoms.  The `!important` wins over Plotly's inline styles, and setting
    # html/body/wrapper to 100% gives the `.js-plotly-plot` div something to
    # expand into.
    __codebench_plotly_css = (
        "<style>"
        "html, body { margin:0 !important; padding:0 !important; width:100% !important; height:100% !important; overflow:hidden !important; background:transparent !important; }"
        "body > div:first-child { width:100% !important; height:100% !important; }"
        ".plotly-graph-div, .js-plotly-plot, .svg-container, .main-svg { width:100% !important; height:100% !important; }"
        "</style>"
        "<script>"
        "window.addEventListener('load', function() {"
        "  if (!window.Plotly) return;"
        "  function _fill() {"
        "    document.querySelectorAll('.js-plotly-plot').forEach(function(p) {"
        "      try { Plotly.Plots.resize(p); } catch (e) {}"
        "    });"
        "  }"
        "  _fill();"
        "  setTimeout(_fill, 80); setTimeout(_fill, 300);"
        "  window.addEventListener('resize', _fill);"
        "  if (window.ResizeObserver) new ResizeObserver(_fill).observe(document.body);"
        "});"
        "</script>"
    )

    def __codebench_save_plotly_html(_fig, _path):
        # Serialize a plotly figure as HTML that fills 100% of the viewport.
        # Strip locked pixel dimensions and enable autosize + responsive mode.
        try:
            _fig.update_layout(
                autosize=True,
                height=None,
                width=None,
                margin=dict(l=40, r=20, t=40, b=40),
            )
        except Exception:
            pass
        _fig.write_html(
            _path,
            include_plotlyjs=True,
            full_html=True,
            default_width="100%",
            default_height="100%",
            config={"responsive": True, "displayModeBar": False},
        )
        # Splice our CSS/JS override into <head>
        try:
            with open(_path, "r", encoding="utf-8") as _f:
                _html = _f.read()
            if "<head>" in _html:
                _html = _html.replace("<head>", "<head>" + __codebench_plotly_css, 1)
            else:
                _html = __codebench_plotly_css + _html
            with open(_path, "w", encoding="utf-8") as _f:
                _f.write(_html)
        except Exception as _e:
            _log(f"css splice failed: {_e}")

    # Hook matplotlib.pyplot.show to capture chart output
    if _plt and hasattr(_plt, '_show_hook'):
        def _offlinai_mpl_show(fig_obj=None):
            global __codebench_plot_path
            os.makedirs(__codebench_tool_dir, exist_ok=True)
            if fig_obj is not None and hasattr(fig_obj, 'write_html'):
                _path = os.path.join(__codebench_tool_dir, f"chart_{uuid.uuid4().hex[:8]}.html")
                _real_fig = getattr(fig_obj, '_fig', fig_obj)
                __codebench_save_plotly_html(_real_fig, _path)
                __codebench_plot_path = _path
                _log(f"chart saved: {_path}")
                print(f"[plot saved] {_path}")
            else:
                _log("show() called but no plotly figure available")
        _plt._show_hook = _offlinai_mpl_show

    # Hook plotly.graph_objects.Figure.show directly.
    #
    # Catches AttributeError too — plotly.graph_objects uses lazy
    # __getattr__ to expose Figure/Scatter/etc. On an iOS build where
    # validators or some sub-module failed to initialize, the module
    # imports fine but accessing Figure raises AttributeError. That
    # used to bubble up and kill every script run (even ones that
    # don't touch plotly). Now we just skip the hook installation.
    try:
        import plotly.graph_objects as _pgo
        _Figure = getattr(_pgo, "Figure", None)
        if _Figure is None:
            _log("plotly loaded but Figure missing (iOS-stubbed build); skipping hook")
        else:
            _log("plotly OK")
            def _offlinai_plotly_show(self, *args, **kwargs):
                global __codebench_plot_path
                os.makedirs(__codebench_tool_dir, exist_ok=True)
                _path = os.path.join(__codebench_tool_dir, f"chart_{uuid.uuid4().hex[:8]}.html")
                # Clean numpy arrays for JSON serialization
                try:
                    import numpy as _npx
                    for trace in self.data:
                        for attr in ['x', 'y', 'z']:
                            val = getattr(trace, attr, None)
                            if val is not None and hasattr(val, 'tolist'):
                                arr = _npx.asarray(val, dtype=float).ravel()
                                trace[attr] = [None if not _npx.isfinite(v) else float(v) for v in arr]
                except Exception:
                    pass
                __codebench_save_plotly_html(self, _path)
                __codebench_plot_path = _path
                _log(f"plotly chart saved: {_path}")
                print(f"[plot saved] {_path}")
            _Figure.show = _offlinai_plotly_show
    except (ImportError, AttributeError) as _plotly_hook_err:
        _log(f"plotly hook skipped: {type(_plotly_hook_err).__name__}: {_plotly_hook_err}")
    except Exception as _plotly_hook_err:
        _log(f"plotly hook crashed ({type(_plotly_hook_err).__name__}): skipping")

    # Set up fontconfig BEFORE importing manim, so manimpango's
    # __init__.py (triggered transitively by `import manim`) sees
    # FONTCONFIG_FILE and takes the native-Pango path. Native Pango
    # has FreeType linked and handles per-character font fallback for
    # CJK text; the pycairo fallback in this iOS build has no font
    # backend and can only draw basic Latin, so Chinese text is
    # invisible unless we get onto the native path.
    #
    # The actual font registration (manimpango.register_font) happens
    # AFTER import, which is fine — fontconfig is already set up and
    # Pango re-scans its app-font list on each layout call.
    try:
        _bundle_root = None
        for _p in sys.path:
            if _p.endswith(".app") or ".app/" in _p:
                _bundle_root = (_p.split(".app/", 1)[0] + ".app") if ".app/" in _p else _p
                break
        _font_dir = None
        if _bundle_root:
            # Probe known font subdirs and the bundle root (synced-folder
            # flattening puts the .otf files straight under <App>.app/).
            for _rel in ("katex/fonts", "Frameworks/katex/fonts",
                         "KaTeX/fonts", "Frameworks/KaTeX/fonts",
                         ""):
                _cand_dir = os.path.join(_bundle_root, _rel) if _rel else _bundle_root
                if os.path.isdir(_cand_dir) and (
                    os.path.exists(os.path.join(_cand_dir, "NotoSansJP-Regular.otf"))
                    or os.path.exists(os.path.join(_cand_dir, "KaTeX_Main-Regular.ttf"))
                ):
                    _font_dir = _cand_dir
                    break
        if _font_dir:
            _fc_file_pre = os.path.join(__codebench_tool_dir, "fonts.conf")
            _prefer_pre = "<family>KaTeX_Main</family><family>Noto Sans JP</family>"
            _fc_lines_pre = [
                "<fontconfig>",
                "  <dir>" + _font_dir + "</dir>",
                "  <cachedir>" + __codebench_tool_dir + "/fontcache</cachedir>",
                "  <alias><family>serif</family><prefer>" + _prefer_pre + "</prefer></alias>",
                "  <alias><family>sans-serif</family><prefer>" + _prefer_pre + "</prefer></alias>",
                "  <alias><family>sans</family><prefer>" + _prefer_pre + "</prefer></alias>",
                "  <alias><family>monospace</family><prefer>" + _prefer_pre + "</prefer></alias>",
                "  <alias><family>Times</family><prefer>" + _prefer_pre + "</prefer></alias>",
                "</fontconfig>",
                "",
            ]
            os.makedirs(f"{__codebench_tool_dir}/fontcache", exist_ok=True)
            with open(_fc_file_pre, "w") as _fcf_pre:
                _fcf_pre.write(chr(10).join(_fc_lines_pre))
            os.environ["FONTCONFIG_FILE"] = _fc_file_pre
            os.environ["FONTCONFIG_PATH"] = __codebench_tool_dir
            _log(f"[manim-font] fontconfig pre-wired: {_fc_file_pre}")
    except Exception as _fc_pre_err:
        _log(f"[manim-font] pre-import fontconfig setup failed: {_fc_pre_err}")

    # Configure manim for iOS (if available)
    try:
        import manim
        _manim_run_id = uuid.uuid4().hex[:8]
        _manim_media = os.path.join(__codebench_tool_dir, f"manim_{_manim_run_id}")
        os.makedirs(_manim_media, exist_ok=True)
        manim.config.media_dir = _manim_media
        manim.config.renderer = "cairo"
        manim.config.format = "mp4"
        manim.config.write_to_movie = True
        manim.config.save_last_frame = False
        manim.config.preview = False
        manim.config.show_in_file_browser = False
        manim.config.disable_caching = True
        # Logger at ERROR so info-level chatter ("File ready at …",
        # caching messages, partial-movie listings) stays out of the
        # terminal. The default tqdm progress bar is left alone so the
        # user still sees per-animation progress while a long render
        # is running. Our own [manim-debug] / [diag] / [fallback]
        # prefixes are filtered to NSLog by the Swift terminal layer.
        manim.config.verbosity = "ERROR"
        # MUST use standard quality presets — custom pixel values break frame_rate!
        # Manim's quality presets set pixel_width, pixel_height, AND frame_rate together.
        _mq = int(globals().get('__codebench_manim_quality', '0') or '0')
        _quality_map = {0: 'low_quality', 1: 'medium_quality', 2: 'high_quality'}
        manim.config.quality = _quality_map.get(_mq, 'low_quality')
        _log(f"manim quality={manim.config.quality} res={manim.config.pixel_width}x{manim.config.pixel_height} fps={manim.config.frame_rate}")

        # iOS: Pango segfaults in cairo_scaled_font_glyph_extents when the
        # fallback font ("Times 9.999") can't be resolved via fontconfig.
        # iOS has no system fonts.conf, so we generate a minimal one at
        # runtime pointing at our bundled katex/fonts/ directory, set
        # FONTCONFIG_FILE before Pango/manim touch anything, and ALSO call
        # manimpango.register_font() as a belt-and-braces measure.
        try:
            _bundle_root = None
            for _p in sys.path:
                if _p.endswith(".app") or ".app/" in _p:
                    _bundle_root = (_p.split(".app/", 1)[0] + ".app") if ".app/" in _p else _p
                    break
            _log(f"[manim-font] bundle_root={_bundle_root}")
            _font_dir = None
            _font_path = None
            _cjk_font_path = None
            if _bundle_root:
                # Also probe the bundle root itself — Xcode's
                # synchronized-folder mode flattens KaTeX/fonts/*.otf
                # straight into <App>.app/, so the .otf files end up as
                # bundle-root siblings without the KaTeX/fonts/ prefix.
                for _rel in ("katex/fonts", "Frameworks/katex/fonts",
                             "KaTeX/fonts", "Frameworks/KaTeX/fonts",
                             ""):
                    _cand_dir = os.path.join(_bundle_root, _rel) if _rel else _bundle_root
                    if os.path.isdir(_cand_dir):
                        _ttf = os.path.join(_cand_dir, "KaTeX_Main-Regular.ttf")
                        _cjk = os.path.join(_cand_dir, "NotoSansJP-Regular.otf")
                        if os.path.exists(_ttf) or os.path.exists(_cjk):
                            _font_dir = _cand_dir
                            if os.path.exists(_ttf): _font_path = _ttf
                            if os.path.exists(_cjk): _cjk_font_path = _cjk
                            break
            _log(f"[manim-font] font_dir={_font_dir} latin={_font_path} cjk={_cjk_font_path}")

            if _font_dir:
                # Write a fonts.conf that maps Pango's default families to
                # KaTeX_Main (Latin coverage), with Noto Sans JP as the
                # automatic fallback for codepoints KaTeX can't render —
                # that's what gives us CJK support. Fontconfig walks the
                # <prefer> list in order and picks the first family that
                # has the glyph, so `serif` → tries KaTeX_Main first, falls
                # back to Noto Sans JP on Hanzi/Kanji/Kana.
                _fc_file = os.path.join(__codebench_tool_dir, "fonts.conf")
                _prefer = "<family>KaTeX_Main</family>"
                if _cjk_font_path:
                    _prefer += "<family>Noto Sans JP</family>"
                _lines = [
                    "<fontconfig>",
                    "  <dir>" + _font_dir + "</dir>",
                    "  <cachedir>" + __codebench_tool_dir + "/fontcache</cachedir>",
                    "  <alias><family>serif</family><prefer>" + _prefer + "</prefer></alias>",
                    "  <alias><family>sans-serif</family><prefer>" + _prefer + "</prefer></alias>",
                    "  <alias><family>sans</family><prefer>" + _prefer + "</prefer></alias>",
                    "  <alias><family>monospace</family><prefer>" + _prefer + "</prefer></alias>",
                    "  <alias><family>Times</family><prefer>" + _prefer + "</prefer></alias>",
                    "</fontconfig>",
                    "",
                ]
                _fc_content = chr(10).join(_lines)
                os.makedirs(f"{__codebench_tool_dir}/fontcache", exist_ok=True)
                with open(_fc_file, "w") as _fcf:
                    _fcf.write(_fc_content)
                os.environ["FONTCONFIG_FILE"] = _fc_file
                os.environ["FONTCONFIG_PATH"] = __codebench_tool_dir
                _log(f"[manim-font] wrote {_fc_file}")

            # Register both fonts with manimpango via direct path. The
            # Latin one keeps rendering LaTeX math and English text;
            # the CJK one lets `Text("中文")` find glyphs via fontconfig's
            # <prefer> fallback chain (or direct select_font_face in
            # the pycairo compat path, which picks it by family name).
            try:
                import manimpango as _mp
                if _font_path and hasattr(_mp, "register_font"):
                    _ok = _mp.register_font(_font_path)
                    _log(f"[manim-font] register_font latin = {_ok}")
                if _cjk_font_path and hasattr(_mp, "register_font"):
                    _ok2 = _mp.register_font(_cjk_font_path)
                    _log(f"[manim-font] register_font cjk = {_ok2}")
                manim.config.font = "KaTeX_Main"
            except BaseException as _e2:
                _log(f"[manim-font] manimpango.register_font failed: {_e2}")
        except BaseException as _fe:
            import traceback as _tb
            _log(f"[manim-font] font setup crashed: {type(_fe).__name__}: {_fe}")
            _tb.print_exc()

        # Monkey-patch to capture frames → animated GIF (since ffmpeg unavailable)
        if not getattr(manim.Scene, '_offlinai_patched', False):
            _orig_render = manim.Scene.render
            # Also patch write_frame to collect frames for GIF
            from manim.scene.scene_file_writer import SceneFileWriter
            _orig_write_frame = SceneFileWriter.write_frame
            _collected_frames = []  # shared frame buffer

            def _capture_write_frame(self_fw, frame_or_renderer, num_frames=1):
                # Intercept write_frame to collect PIL frames for GIF
                try:
                    if isinstance(frame_or_renderer, np.ndarray):
                        frame = frame_or_renderer
                    elif hasattr(frame_or_renderer, 'get_frame'):
                        frame = frame_or_renderer.get_frame()
                    else:
                        frame = None
                    if frame is not None and frame.size > 0:
                        from PIL import Image as _PILImage
                        # frame is RGBA uint8 numpy array
                        if frame.shape[-1] == 4:
                            img = _PILImage.fromarray(frame, 'RGBA').convert('RGB')
                        else:
                            img = _PILImage.fromarray(frame, 'RGB')
                        # Sample every few frames to keep GIF small
                        _collected_frames.append(img)
                except Exception:
                    pass
                # Still call original (for save_last_frame PNG)
                try:
                    _orig_write_frame(self_fw, frame_or_renderer, num_frames)
                except Exception:
                    pass

            SceneFileWriter.write_frame = _capture_write_frame

            def _offlinai_manim_render(self, *args, **kwargs):
                global __codebench_plot_path
                import manim as _m
                _m.config.renderer = "cairo"
                _m.config.format = "mp4"
                _m.config.write_to_movie = True
                _m.config.save_last_frame = False
                _m.config.preview = False
                _m.config.disable_caching = True
                # Log Pango status. `_pango_available` is set by our shim's
                # __init__.py; stock manimpango doesn't expose it, so default
                # to True (stock => always native).
                import manimpango as _mp
                _pango_ok = getattr(_mp, "_pango_available", True)
                if _pango_ok:
                    print("[manim] Pango: native rendering available")
                else:
                    print(f"[manim] Pango: pycairo compatibility mode ({getattr(_mp, '_pango_error', 'unknown')})")

                # iOS-specific: Pango falls back to 'Times 9.999' when no
                # font is available; on iOS fontconfig can't find Times,
                # so pango_layout returns NULL scaled_font and the render
                # segfaults. Register our bundled KaTeX_Main-Regular.ttf
                # and make it manim's default font to avoid the crash.
                try:
                    import os as _os_f, sys as _sys_f
                    _bundle_root = None
                    for _p in _sys_f.path:
                        if _p.endswith(".app") or ".app/" in _p:
                            _bundle_root = (_p.split(".app/", 1)[0] + ".app") if ".app/" in _p else _p
                            break
                    _font_path = None
                    _cjk_font_path = None
                    if _bundle_root:
                        # The bundled folder is "KaTeX/fonts" (capital K),
                        # not lowercase "katex/fonts" — the lowercase entries
                        # below remain only as defensive fallbacks for older
                        # bundle layouts. List capital-K paths first so the
                        # actual bundled file is picked on the first hit.
                        for _rel in ("KaTeX/fonts/KaTeX_Main-Regular.ttf",
                                     "Frameworks/KaTeX/fonts/KaTeX_Main-Regular.ttf",
                                     "Frameworks/katex/fonts/KaTeX_Main-Regular.ttf",
                                     "katex/fonts/KaTeX_Main-Regular.ttf"):
                            _cand = _os_f.path.join(_bundle_root, _rel)
                            if _os_f.path.exists(_cand):
                                _font_path = _cand
                                break
                        # Also locate the bundled NotoSansJP for the CJK
                        # fallback chain. manimpango's register_font supports
                        # multiple fonts, so registering NotoSansJP here lets
                        # native Pango pick it up automatically when a string
                        # contains CJK codepoints — this complements the
                        # PIL-based CJK Text shim further down (the shim is
                        # for plain `Text("中文")`, this is for inline mixed
                        # content like axis labels and MathTex with CJK).
                        for _rel in ("KaTeX/fonts/NotoSansJP-Regular.otf",
                                     "Frameworks/KaTeX/fonts/NotoSansJP-Regular.otf",
                                     "katex/fonts/NotoSansJP-Regular.otf"):
                            _cand = _os_f.path.join(_bundle_root, _rel)
                            if _os_f.path.exists(_cand):
                                _cjk_font_path = _cand
                                break
                    if _font_path and hasattr(_mp, "register_font"):
                        _mp.register_font(_font_path)
                        print(f"[manim] registered font {_font_path}", flush=True)
                        # Make sure Text uses it by default
                        _m.config.font = "KaTeX_Main"
                        # Register CJK font too if available — Pango's
                        # fontconfig fallback chain will pull from any
                        # registered font for codepoints the primary
                        # font can't render.
                        if _cjk_font_path:
                            try:
                                _mp.register_font(_cjk_font_path)
                                print(f"[manim] registered CJK font {_cjk_font_path}",
                                      flush=True)
                            except Exception as _cjke:
                                print(f"[manim] CJK font register failed: "
                                      f"{type(_cjke).__name__}: {_cjke}", flush=True)
                    else:
                        print(f"[manim] WARN: no bundled font found (root={_bundle_root})", flush=True)
                except Exception as _fe:
                    print(f"[manim] font registration failed: {type(_fe).__name__}: {_fe}", flush=True)
                _m.config.from_animation_number = 0
                _m.config.upto_animation_number = -1
                # Re-apply quality preset to ensure correct frame_rate
                _q = int(globals().get('__codebench_manim_quality', '0') or '0')
                _qmap = {0: 'low_quality', 1: 'medium_quality', 2: 'high_quality'}
                _m.config.quality = _qmap.get(_q, 'low_quality')
                _collected_frames.clear()
                _orig_render(self, *args, **kwargs)
                print(f"[manim-debug] frames_written={len(_collected_frames)} skip={getattr(self.renderer, 'skip_animations', '?')} sections_skip={getattr(self.renderer.file_writer.sections[-1], 'skip_animations', '?') if hasattr(self.renderer, 'file_writer') and self.renderer.file_writer.sections else '?'}")
                try:
                    fw = self.renderer.file_writer
                    _log(f"fw attrs: movie={hasattr(fw,'movie_file_path')}, image={hasattr(fw,'image_file_path')}")
                    if hasattr(fw, 'movie_file_path'):
                        _log(f"movie_file_path={fw.movie_file_path}")
                    # 1. Check for mp4 video (PyAV + ffmpeg)
                    movie_path = str(fw.movie_file_path) if hasattr(fw, 'movie_file_path') and fw.movie_file_path else None
                    if movie_path and os.path.exists(movie_path) and os.path.getsize(movie_path) > 500:
                        __codebench_plot_path = movie_path
                        _log(f"manim MP4: {movie_path} ({os.path.getsize(movie_path)} bytes)")
                        print(f"[manim rendered] {movie_path}")
                        _collected_frames.clear()
                        return
                    # 2. Fallback: assemble GIF from captured frames
                    if len(_collected_frames) >= 2:
                        from PIL import Image as _PILImage
                        gif_path = os.path.join(_m.config.media_dir, f"{type(self).__name__}.gif")
                        frames = _collected_frames
                        if len(frames) > 80:
                            step = len(frames) // 80
                            frames = frames[::step]
                        w, h = frames[0].size
                        if w > 480:
                            ratio = 480 / w
                            new_size = (480, int(h * ratio))
                            frames = [f.resize(new_size, _PILImage.LANCZOS) for f in frames]
                        fps = _m.config.frame_rate or 15
                        duration = max(int(1000 / fps), 33)
                        frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=duration, loop=0, optimize=True)
                        if os.path.exists(gif_path) and os.path.getsize(gif_path) > 100:
                            __codebench_plot_path = gif_path
                            _log(f"manim GIF: {gif_path} ({len(frames)} frames)")
                            print(f"[manim rendered] {gif_path}")
                            _collected_frames.clear()
                            return
                    # 3. Fallback: static PNG
                    img_path = str(fw.image_file_path) if hasattr(fw, 'image_file_path') and fw.image_file_path else None
                    if img_path and os.path.exists(img_path):
                        __codebench_plot_path = img_path
                        _log(f"manim PNG: {img_path}")
                        print(f"[manim rendered] {img_path}")
                    else:
                        latest = None
                        latest_t = 0
                        for root, dirs, files in os.walk(_m.config.media_dir):
                            for f in files:
                                if f.endswith(('.mp4', '.gif', '.png')):
                                    fpath = os.path.join(root, f)
                                    mt = os.path.getmtime(fpath)
                                    if mt > latest_t:
                                        latest = fpath
                                        latest_t = mt
                        if latest:
                            __codebench_plot_path = latest
                            _log(f"manim found: {latest}")
                            print(f"[manim rendered] {latest}")
                except Exception as e:
                    _log(f"manim output error: {e}")
                _collected_frames.clear()

            manim.Scene.render = _offlinai_manim_render
            manim.Scene._offlinai_patched = True

        # ── Per-animation cleanup monkey-patch ────────────────────
        # Deliberately OUTSIDE the render-patch guard above. The
        # render patch is install-once; the Python runtime is
        # long-lived, so a prior run sets `_offlinai_patched = True`
        # and the render block is skipped on subsequent runs.
        # The play patch has its OWN guard so it installs exactly
        # once, independently of the render patch. If this were
        # nested like before, re-runs never got the play patch and
        # the `[splt] play #N` lines never appeared — which is
        # exactly the symptom we debugged.
        if not getattr(manim.Scene, "_offlinai_play_patched", False):
            _orig_play = manim.Scene.play
            _play_count = [0]   # cell so closure can bump it

            def _offlinai_play_with_cleanup(self, *_a, **_kw):
                try:
                    _r = _orig_play(self, *_a, **_kw)
                finally:
                    _play_count[0] += 1
                    # PER-PLAY cleanup is intentionally MINIMAL:
                    # only safe cache drops + RSS logging. The
                    # previous attempt ran gc.collect() and
                    # malloc_pressure_relief on every play, which
                    # raced with manim's SceneFileWriter writer
                    # thread (which can still be mid-write when
                    # play() returns) and crashed with
                    # EXC_BAD_ACCESS (0x137600000-style use-
                    # after-free). Heavy cleanup belongs in the
                    # BETWEEN-SCENE hook where the writer thread
                    # has been joined.
                    try:
                        import psutil as _pp
                        import manim as _pmx
                        # Safe: clear TeX/SVG string→mob dicts.
                        # `.clear()` only drops references; nothing
                        # else is iterating over these between plays.
                        for _path, _attr in (
                                (_pmx, '_tex_string_to_mob_map'),
                                (_pmx, '_tex_cache'),
                                (getattr(_pmx, 'mobject', None),
                                 '_tex_cache'),):
                            if _path is None:
                                continue
                            _c = getattr(_path, _attr, None)
                            if _c is not None and hasattr(_c, 'clear'):
                                try: _c.clear()
                                except Exception: pass

                        _n = _play_count[0]
                        # Use phys_footprint (what Xcode/jetsam see)
                        # not psutil.rss (undercounts by ~2x on iOS
                        # because it misses compressed / IOSurface /
                        # VideoToolbox encoder buffers).
                        _phys_mb = -1
                        try:
                            import ctypes as _tc
                            _lS = _tc.CDLL("/usr/lib/libSystem.dylib")
                            _b = (_tc.c_uint64 * 64)()
                            _cnt = _tc.c_uint32(_tc.sizeof(_b) // 4)
                            _lS.mach_task_self.restype = _tc.c_uint32
                            _lS.task_info.argtypes = [
                                _tc.c_uint32, _tc.c_uint32,
                                _tc.POINTER(_tc.c_uint64),
                                _tc.POINTER(_tc.c_uint32)]
                            _lS.task_info.restype = _tc.c_int
                            if _lS.task_info(_lS.mach_task_self(),
                                             22, _b,
                                             _tc.byref(_cnt)) == 0:
                                _phys_mb = int(_b[18]) // (1024*1024)
                        except Exception:
                            pass
                        _rss = int(_pp.Process().memory_info().rss
                                   // (1024*1024))
                        if _phys_mb > 0:
                            _log(f"[splt]   play #{_n}: "
                                 f"phys={_phys_mb}MB  rss={_rss}MB")
                        else:
                            _log(f"[splt]   play #{_n}: rss={_rss}MB")
                    except Exception:
                        pass
                return _r

            manim.Scene.play = _offlinai_play_with_cleanup
            manim.Scene._offlinai_play_patched = True
            _log("[manim] Scene.play patched with per-animation cleanup")

        # CJK-aware Text factory.
        #
        # The bundled pycairo has no FreeType/Quartz backend, so manim's
        # normal `Text('中文')` pipeline produces notdef boxes for any
        # non-Latin glyph — there's no way for Cairo to load our bundled
        # NotoSansJP. Sidestep that by intercepting the Text class at
        # the manim-module level (before any user `from manim import *`)
        # and, when the input has CJK codepoints, rasterize the text via
        # Pillow's FreeType (which IS linked into Pillow on iOS) and
        # return an `ImageMobject` instead of the SVG-derived VMobject.
        # Non-CJK strings still go through the original Text class so
        # LaTeX / English / math text is unaffected.
        if not getattr(manim, "_offlinai_cjk_text_patched", False):
            _orig_Text = manim.Text
            _cjk_png_dir = os.path.join(_manim_media, "cjk_text")
            os.makedirs(_cjk_png_dir, exist_ok=True)

            def _has_cjk(s: str) -> bool:
                for _ch in s:
                    _cp = ord(_ch)
                    if (0x3000 <= _cp <= 0x30FF
                            or 0x3400 <= _cp <= 0x4DBF
                            or 0x4E00 <= _cp <= 0x9FFF
                            or 0xAC00 <= _cp <= 0xD7AF
                            or 0xF900 <= _cp <= 0xFAFF
                            or 0xFF00 <= _cp <= 0xFFEF):
                        return True
                return False

            def _cjk_factory(*args, **kwargs):
                # Accept either Text("中") or Text(text="中").
                text_arg = args[0] if args else kwargs.get("text", "")
                if not isinstance(text_arg, str) or not _has_cjk(text_arg):
                    return _orig_Text(*args, **kwargs)
                # Rasterize the whole string as one PNG and wrap in an
                # ImageMobject. Stable hash of (text, size, color) gives
                # us caching across re-renders.
                try:
                    from PIL import Image, ImageDraw, ImageFont
                    import hashlib, manim as _mm
                    _size_px = int(kwargs.get("font_size",
                                              _mm.DEFAULT_FONT_SIZE) * 2)
                    _color_str = str(kwargs.get("color", "WHITE"))
                    _color_rgba = (255, 255, 255, 255)
                    try:
                        _col = _mm.utils.color.ManimColor(_color_str)
                        _r, _g, _b = _col.to_rgb()
                        _color_rgba = (int(_r * 255), int(_g * 255),
                                       int(_b * 255), 255)
                    except Exception:
                        pass
                    _key = hashlib.sha256(
                        f"{text_arg}|{_size_px}|{_color_rgba}".encode("utf-8")
                    ).hexdigest()[:16]
                    _png = os.path.join(_cjk_png_dir, f"{_key}.png")
                    if not os.path.exists(_png):
                        # Find the bundled CJK font. Synced-folder mode
                        # flattens KaTeX/fonts/*.otf to bundle root, so
                        # also probe <App>.app/NotoSansJP-Regular.otf.
                        _font_file = None
                        for _rel in ("KaTeX/fonts/NotoSansJP-Regular.otf",
                                     "katex/fonts/NotoSansJP-Regular.otf",
                                     "NotoSansJP-Regular.otf"):
                            if _bundle_root:
                                _cand = os.path.join(_bundle_root, _rel)
                                if os.path.exists(_cand):
                                    _font_file = _cand
                                    break
                        if _font_file is None:
                            print("[manim] CJK font not found; falling back to Text()",
                                  flush=True)
                            return _orig_Text(*args, **kwargs)
                        _font = ImageFont.truetype(_font_file, _size_px)
                        # Measure + add a small padding so antialiased
                        # edges don't touch the image border.
                        _bbox = _font.getbbox(text_arg)
                        _w = (_bbox[2] - _bbox[0]) + 8
                        _h = (_bbox[3] - _bbox[1]) + 8
                        _img = Image.new("RGBA", (_w, _h), (0, 0, 0, 0))
                        _draw = ImageDraw.Draw(_img)
                        _draw.text((-_bbox[0] + 4, -_bbox[1] + 4),
                                   text_arg, font=_font, fill=_color_rgba)
                        _img.save(_png)
                    # Height in manim units — roughly match what Text()
                    # would produce for the same font_size.
                    _mob = _mm.ImageMobject(_png)
                    _font_size_units = kwargs.get("font_size",
                                                  _mm.DEFAULT_FONT_SIZE)
                    _target_h = _font_size_units / 48.0  # ~Text height rule of thumb
                    _mob.scale_to_fit_height(_target_h)
                    return _mob
                except BaseException as _ce:
                    print(f"[manim] CJK rasterize failed: {type(_ce).__name__}: {_ce} — falling back to Text()",
                          flush=True)
                    return _orig_Text(*args, **kwargs)

            manim.Text = _cjk_factory
            manim._offlinai_cjk_text_patched = True
            _log("[manim] CJK-aware Text factory installed")

            # Make VGroup accept ImageMobject children. Our CJK Text
            # factory returns ImageMobject (rasterized via Pillow, since
            # Cairo can't load CJK fonts on iOS), but user scripts do
            # `VGroup(text1, text2, …)` which raises TypeError because
            # VGroup.add() only accepts VMobject. Route non-VMobject
            # adds through the base Mobject.add instead — positioning /
            # fade / scale / shift all still work on mixed groups. The
            # one operation that doesn't is per-vertex `Transform()`
            # between a VMobject and an ImageMobject, which would need
            # vector outlines neither side has anyway.
            try:
                _VGroup = manim.VGroup
                _ImageMobject = manim.ImageMobject
                if not getattr(_VGroup, "_offlinai_accepts_image_mobject", False):
                    _orig_VGroup_add = _VGroup.add
                    def _cjk_tolerant_add(self, *mobjects):
                        vmobs = []
                        others = []
                        for m in mobjects:
                            if isinstance(m, _ImageMobject):
                                others.append(m)
                            else:
                                vmobs.append(m)
                        if vmobs:
                            _orig_VGroup_add(self, *vmobs)
                        if others:
                            # Bypass `VGroup._assert_valid_submobjects`
                            # entirely — appending to `submobjects`
                            # directly is exactly what `Mobject.add`
                            # does after its type check, so every
                            # downstream group op (shift/scale/fade/
                            # animate) still works on the mixed set.
                            for _m in others:
                                if _m is self:
                                    continue
                                if _m not in self.submobjects:
                                    self.submobjects.append(_m)
                        return self
                    _VGroup.add = _cjk_tolerant_add
                    _VGroup._offlinai_accepts_image_mobject = True
                    _log("[manim] VGroup patched to accept ImageMobject")

                # Give ImageMobject a `get_anchors` so that VGroup ops
                # that walk the family (arrange / center / get_center /
                # get_critical_point / get_points_defining_boundary)
                # see the image's four corner points as its boundary
                # contribution. Without this, mixed VGroups raise
                # `AttributeError: ImageMobject has no attribute
                # 'anchors'` as soon as you call `.arrange()`.
                if not hasattr(_ImageMobject, "_offlinai_has_get_anchors"):
                    def _image_get_anchors(self):
                        try:
                            _pts = self.points
                            if _pts is not None and len(_pts):
                                return _pts
                        except Exception:
                            pass
                        import numpy as _np_local
                        return _np_local.zeros((0, 3))
                    _ImageMobject.get_anchors = _image_get_anchors
                    _ImageMobject._offlinai_has_get_anchors = True
                    _log("[manim] ImageMobject.get_anchors shim installed")

                # VMobject-style setters that VGroup.set_fill / set_stroke
                # / set_color etc. propagate to EVERY submobject. On a
                # real ImageMobject these attributes don't exist, so
                # Mobject.__getattr__ generates a stub that takes only
                # (self, value) — then VGroup passes (color, opacity,
                # family) and we get "takes 2 positional arguments but
                # 4 were given". No-ops are safe because images don't
                # have vector fill/stroke; fade/transparency still works
                # via set_opacity (which ImageMobject provides natively).
                if not hasattr(_ImageMobject, "_offlinai_has_vmobject_setters"):
                    def _image_noop_setter(*_args, **_kwargs):
                        return _args[0] if _args else None
                    for _name in ("set_fill", "set_stroke",
                                  "set_background_stroke",
                                  "set_sheen", "set_sheen_direction",
                                  "set_shade_in_3d",
                                  "set_stroke_color", "set_fill_color",
                                  "match_style",
                                  "pointwise_become_partial",
                                  "set_anchors_and_handles"):
                        if not hasattr(_ImageMobject, _name):
                            setattr(_ImageMobject, _name, _image_noop_setter)
                    # VMobject-style scalar attrs. manim's get_X
                    # auto-getter does `getattr(self, 'X')` and raises
                    # AttributeError if absent (e.g. get_stroke_width
                    # → stroke_width). Giving ImageMobject sensible
                    # defaults makes `Write`, `DrawBorderThenFill`,
                    # `ShowCreation` etc. see a no-stroke / no-fill
                    # vector — they then skip the outline phase for
                    # this child without crashing the whole render.
                    for _name, _default in (
                            ("stroke_width", 0.0),
                            ("background_stroke_width", 0.0),
                            ("fill_opacity", 1.0),
                            ("stroke_opacity", 0.0),
                            ("background_stroke_opacity", 0.0),
                            ("sheen_factor", 0.0),
                            ("sheen_direction", None),
                            ("fill_color", None),
                            ("stroke_color", None),
                            ("background_stroke_color", None),
                            ("n_points_per_curve", 1)):
                        if not hasattr(_ImageMobject, _name):
                            setattr(_ImageMobject, _name, _default)
                    _ImageMobject._offlinai_has_vmobject_setters = True
                    _log("[manim] ImageMobject VMobject shims installed")
            except Exception as _vge:
                _log(f"[manim] VGroup patch failed: {_vge}")
        _log("manim configured for iOS (Cairo → GIF animation)")
    except ImportError:
        _log("manim not available")
    except Exception as _me:
        _log(f"manim config error: {_me}")

    # Pre-import useful math modules so user code can use them
    import math
    import cmath
    from math import factorial, gcd, comb, perm, isqrt
    from fractions import Fraction
    try:
        import decimal
        from decimal import Decimal
    except ImportError:
        pass

    # Test helper for templates (avoids nested exec + try/except indentation issues)
    _offlinai_test_pass = 0
    _offlinai_test_fail = 0
    _offlinai_test_errors = []
    def _offlinai_test(name, fn):
        global _offlinai_test_pass, _offlinai_test_fail, _offlinai_test_errors
        try:
            fn()
            _offlinai_test_pass += 1
            print("  ok " + str(name))
        except Exception as _te:
            _offlinai_test_fail += 1
            _offlinai_test_errors.append((str(name), str(_te)[:100]))
            print("  FAIL " + str(name) + ": " + str(_te)[:80])

    # Auto-inject `from manim import *` so that scripts which reference
    # Scene / VGroup / Text / etc. without their own import still run.
    # Strategy: use tokenize to find *bare identifiers* in the user's code
    # and only auto-inject `from manim import *` if at least one of a
    # known manim-name set is referenced. Plain scripts (no manim usage)
    # pay zero cost. Scripts that do their own `from manim import ...` /
    # `import manim` take the user's import as-is (we don't touch).
    _has_manim_import = (
        'from manim' in _offlinai_code or
        'import manim' in _offlinai_code
    )
    _looks_like_manim = False
    if not _has_manim_import:
        import tokenize as _tk_manim, io as _io_manim
        _manim_names = frozenset((
            # Scene types
            'Scene', 'ThreeDScene', 'MovingCameraScene', 'ZoomedScene',
            'SpecialThreeDScene', 'VectorScene', 'LinearTransformationScene',
            # Mobject hierarchy
            'Mobject', 'VMobject', 'VGroup', 'Group',
            # Text + math
            'Text', 'MarkupText', 'Paragraph', 'MathTex', 'Tex', 'Title',
            'BulletedList', 'Code',
            # Shapes
            'Circle', 'Square', 'Triangle', 'Polygon', 'Rectangle',
            'RoundedRectangle', 'Line', 'DashedLine', 'Arrow', 'Vector',
            'DoubleArrow', 'Dot', 'Star', 'RegularPolygon', 'Arc',
            # Coordinate systems / graphs
            'NumberPlane', 'Axes', 'NumberLine', 'ValueTracker',
            'ComplexPlane', 'ThreeDAxes', 'Surface', 'BarChart',
            # Animations
            'Write', 'Create', 'DrawBorderThenFill', 'Unwrite', 'Uncreate',
            'FadeIn', 'FadeOut', 'Transform', 'ReplacementTransform',
            'GrowFromCenter', 'GrowFromEdge', 'GrowArrow', 'Indicate',
            'Rotate', 'Rotating', 'MoveToTarget', 'ApplyFunction',
            'LaggedStart', 'AnimationGroup', 'Succession', 'Wait',
        ))
        try:
            _names_in_code = {
                _tok.string
                for _tok in _tk_manim.generate_tokens(_io_manim.StringIO(_offlinai_code).readline)
                if _tok.type == _tk_manim.NAME
            }
            _looks_like_manim = bool(_manim_names & _names_in_code)
        except Exception:
            # Tokenize failed (e.g. syntax error in user code) — fall back
            # to the plain substring check, which is less precise but
            # avoids blocking the user's script on our detection bug.
            _looks_like_manim = any(
                _n in _offlinai_code for _n in _manim_names
            )

    if _looks_like_manim:
        try:
            exec('from manim import *', globals(), globals())
            _log("auto-injected `from manim import *` (user code references manim names)")
        except BaseException as _mi_err:
            _log(f"manim auto-import failed: {type(_mi_err).__name__}: {_mi_err}")
            print(f"[runtime] manim auto-import failed: {type(_mi_err).__name__}: {_mi_err}", flush=True)

    # ── Snapshot global names BEFORE executing user code ────────────
    # We use this to identify which Scene classes were actually DEFINED
    # by this run (not just leftover from a previous script in the same
    # long-lived interpreter). Without this, running e.g. pip_demo.py
    # after an earlier manim script would happily re-render that
    # earlier script's Scene class.
    # Snapshot CLASS IDENTITIES, not just names. The original code only
    # recorded `set(globals().keys())` and treated anything whose name was
    # already present as "stale" — but on a re-run of the same script,
    # `class MyScene(Scene):` *re-binds* the same name to a brand-new class
    # object, so the name isn't new even though the class is. That made
    # the second-and-later runs of the same script fail with
    # "<class> not found in [] — falling back to all scenes" and then
    # finding nothing to render.
    #
    # Mapping name → id() gives us the right signal: if the name's id
    # changed, the user freshly defined that class in this run.
    _globals_before_exec = set(globals().keys())
    _class_ids_before_exec = {
        _n: id(_v) for _n, _v in globals().items() if isinstance(_v, type)
    }

    # Execute user code
    _log("Executing user code...")
    exec(_offlinai_code, globals(), globals())
    _log("User code finished")

    # Auto-detect and render manim Scene subclasses if user didn't call render() manually.
    #
    # Two guards to avoid false positives:
    #   1. The user code must look like manim (import statement or
    #      `class X(Scene):` pattern). Caught by _looks_like_manim or
    #      a quick regex scan here.
    #   2. The Scene class must have been *defined or re-bound* in this
    #      run (i.e. its name wasn't in globals before we exec'd the
    #      user code).
    _user_defined_a_scene = False
    if _looks_like_manim or 'class ' in _offlinai_code and 'Scene' in _offlinai_code:
        _user_defined_a_scene = True

    if _user_defined_a_scene and not __codebench_plot_path:
        try:
            import manim as _manim_detect
            _scene_classes = []
            for _name, _obj in list(globals().items()):
                if not isinstance(_obj, type):
                    continue
                # "Defined or re-defined in this run" check — the name is
                # either brand-new (wasn't in globals pre-exec) OR its
                # bound object's id changed (rebinding via re-running
                # `class X(Scene):`). Either way it's a fresh class from
                # the current script, not a leftover from a previous run.
                _was_new_name = _name not in _globals_before_exec
                _was_rebound = (_name in _class_ids_before_exec
                                and _class_ids_before_exec[_name] != id(_obj))
                if not (_was_new_name or _was_rebound):
                    continue
                try:
                    _is_scene = issubclass(_obj, _manim_detect.Scene) and _obj is not _manim_detect.Scene
                except TypeError:
                    _is_scene = False
                if not _is_scene:
                    continue
                # Skip manim-internal names that snuck in via
                # `from manim import *` (we handle the re-export by
                # checking __module__ below).
                if (_obj.__module__ or "").startswith("manim."):
                    continue
                if _name.startswith('_'):
                    continue
                _scene_classes.append((_name, _obj))

            # ── Class-picker filter ─────────────────────────────────
            # Use the value LOCKED at wrapper entry (top of the script,
            # before user code or any other globals fiddling). The
            # original global `__codebench_target_scene` has been
            # observed empty here even when Swift set it — root cause
            # unclear. Reading from the locked-in copy is reliable.
            try:
                _picker_target = _codebench_picker_target_locked
            except NameError:
                _picker_target = ""
            if _picker_target and _picker_target != "*":
                _matched = [(n, c) for n, c in _scene_classes if n == _picker_target]
                if _matched:
                    print(f"[manim] Class picker: rendering "
                          f"'{_picker_target}' only "
                          f"(of {len(_scene_classes)} detected)",
                          flush=True)
                    _scene_classes = _matched
                else:
                    print(f"[manim] Class picker: '{_picker_target}' not "
                          f"found in {[n for n, _ in _scene_classes]} — "
                          f"falling back to all scenes",
                          flush=True)

            if _scene_classes:
                # Render every selected Scene class in definition order,
                # then stitch the outputs into a single MP4. With one
                # class selected, no stitch happens (single mp4 IS the
                # output). With many, we still produce one combined file
                # so the preview-panel contract holds (exactly one
                # `[manim rendered]` line → one video file).
                print(f"[manim] Auto-rendering {len(_scene_classes)} scene(s): "
                      f"{', '.join(n for n, _ in _scene_classes)}",
                      flush=True)

                _rendered_mp4s: list = []
                for _scene_name, _scene_cls in _scene_classes:
                    _log(f"Auto-rendering Scene: {_scene_name}")
                    print(f"[manim] → {_scene_name}...", flush=True)
                    # manim's `print_file_ready_message` sets
                    # `config["output_file"]` globally after every render.
                    # On the next scene, `SceneFileWriter.init_output_directories`
                    # sees that leftover value and reuses it as the output
                    # path — so scene #2, #3, … all overwrite scene #1's
                    # mp4. Reset through the dict setter (NOT `.output_file`
                    # — the property's `_set_dir` coerces Path-or-None weirdly,
                    # and earlier attempts used `_m` which wasn't in scope at
                    # this outer-loop nesting, silently swallowing the reset).
                    try:
                        _manim_detect.config["output_file"] = ""
                    except Exception as _re:
                        print(f"[manim] couldn't reset output_file: {_re}",
                              flush=True)
                    try:
                        _auto_scene = _scene_cls()
                        _auto_scene.render()
                        print(f"[manim] {_scene_name}.render() returned.", flush=True)
                        try:
                            _fw = getattr(_auto_scene, 'renderer', None)
                            _fw = getattr(_fw, 'file_writer', None)
                            _mp = str(getattr(_fw, 'movie_file_path', '') or '')
                            if _mp and os.path.exists(_mp) and os.path.getsize(_mp) > 500 \
                               and _mp not in _rendered_mp4s:
                                _rendered_mp4s.append(_mp)
                                print(f"[manim]   → captured {os.path.basename(_mp)} "
                                      f"({os.path.getsize(_mp)} bytes)",
                                      flush=True)
                            elif _mp in _rendered_mp4s:
                                print(f"[manim]   ! {_scene_name} wrote to "
                                      f"{os.path.basename(_mp)} which was "
                                      f"already captured — overwrite?",
                                      flush=True)
                        except Exception as _pe:
                            _log(f"couldn't locate {_scene_name} movie file: {_pe}")
                    except BaseException as _render_err:
                        import traceback as _tb
                        print(f"[manim] {_scene_name}.render() failed: "
                              f"{type(_render_err).__name__}: {_render_err}",
                              flush=True)
                        _tb.print_exc()

                    # ── Inter-scene cleanup hook ─────────────────────
                    # Manim holds mobject/camera/renderer state on the
                    # Scene instance AND in module-level caches.
                    # Without explicit teardown, each finished scene
                    # stays resident in RAM when the next starts, so
                    # a 3D-heavy scene pushes us to iOS jetsam by
                    # scene 2. Aggressive 6-step teardown + logging.
                    def _rss_mb():
                        # PHYS_FOOTPRINT in MB — what Xcode's gauge
                        # shows AND what iOS jetsam uses for kill
                        # decisions. psutil's .rss undercounts
                        # because it excludes compressed memory,
                        # IOSurface / VideoToolbox encoder buffers,
                        # and mmap'd video files — all of which DO
                        # count against our budget on Darwin. Read
                        # TASK_VM_INFO via Mach task_info and pull
                        # phys_footprint at the known offset.
                        try:
                            import ctypes as _tc
                            _libSys = _tc.CDLL("/usr/lib/libSystem.dylib")
                            # TASK_VM_INFO struct: 40 × uint64 is
                            # enough to cover up through
                            # `phys_footprint` at offset 144 bytes
                            # (18 × 8). Allocate 512 bytes to be
                            # safe across Darwin versions.
                            _buf = (_tc.c_uint64 * 64)()
                            _count = _tc.c_uint32(
                                _tc.sizeof(_buf) // 4)
                            _libSys.mach_task_self.restype = _tc.c_uint32
                            _libSys.task_info.argtypes = [
                                _tc.c_uint32,
                                _tc.c_uint32,
                                _tc.POINTER(_tc.c_uint64),
                                _tc.POINTER(_tc.c_uint32)]
                            _libSys.task_info.restype = _tc.c_int
                            _TASK_VM_INFO = 22
                            _rc = _libSys.task_info(
                                _libSys.mach_task_self(),
                                _TASK_VM_INFO,
                                _buf,
                                _tc.byref(_count))
                            if _rc != 0:
                                raise RuntimeError(f"task_info rc={_rc}")
                            # phys_footprint is the 19th uint64
                            # (index 18, 144-byte offset).
                            _phys = int(_buf[18])
                            return _phys // (1024 * 1024)
                        except Exception:
                            # Fallback to psutil's rss (undercounts
                            # but at least something) if Mach call
                            # fails.
                            try:
                                import psutil as _pu
                                return int(_pu.Process().memory_info().rss
                                           // (1024 * 1024))
                            except Exception:
                                return -1

                    def _avail_mb():
                        try:
                            import psutil as _pu
                            return int(_pu.virtual_memory().available
                                       // (1024 * 1024))
                        except Exception:
                            return -1

                    _rss_before = _rss_mb()
                    _log(f"[splt] scene '{_scene_name}' done: "
                         f"RSS={_rss_before}MB  avail={_avail_mb()}MB  "
                         f"— cleaning up")

                    # Step 1 — break the scene's big attribute refs,
                    # including the frame buffer (camera.pixel_array)
                    # which is the single biggest RAM holder (a numpy
                    # array sized WxHx4 held as long as camera lives).
                    try:
                        _sc = locals().get('_auto_scene', None)
                        if _sc is not None:
                            # Explicitly drop the camera's pixel buffer
                            # before we null out the camera itself.
                            try:
                                _cam = getattr(_sc, 'camera', None)
                                if _cam is not None:
                                    for _a in ('pixel_array',
                                               'background',
                                               'background_image',
                                               'pixel_array_to_cairo_context'):
                                        try: setattr(_cam, _a, None)
                                        except Exception: pass
                            except Exception:
                                pass
                            # Close SceneFileWriter's movie file handle
                            # — otherwise ffmpeg process state / buffer
                            # stays held even after the file is flushed.
                            try:
                                _rdr = getattr(_sc, 'renderer', None)
                                _fw = getattr(_rdr, 'file_writer', None)
                                if _fw is not None:
                                    for _a in ('writing_process',
                                               'partial_movie_file',
                                               'video_path'):
                                        try: setattr(_fw, _a, None)
                                        except Exception: pass
                            except Exception:
                                pass
                            # Drop mobjects, animations, time data.
                            for _attr in ('mobjects', 'foreground_mobjects',
                                          'moving_mobjects', 'animations',
                                          'time_progression',
                                          'section_time_progression',
                                          'updaters'):
                                try: setattr(_sc, _attr, [])
                                except Exception: pass
                            for _attr in ('renderer', 'camera',
                                          'file_writer'):
                                try: setattr(_sc, _attr, None)
                                except Exception: pass
                        _auto_scene = None
                    except Exception:
                        pass

                    # Step 2 — clear manim's module-level caches.
                    try:
                        import manim as _mx
                        _caches_cleared = 0
                        for _name in ('_tex_string_to_mob_map',
                                      '_tex_cache',
                                      '_cached_font_faces'):
                            _cache = getattr(_mx, _name, None)
                            if _cache is not None and hasattr(_cache, 'clear'):
                                try:
                                    _cache.clear()
                                    _caches_cleared += 1
                                except Exception: pass
                        # Cairo camera surface cache.
                        try:
                            from manim.camera import cairo_camera as _cc
                            for _name in dir(_cc):
                                if _name.endswith('_cache'):
                                    _c = getattr(_cc, _name, None)
                                    if hasattr(_c, 'clear'):
                                        try:
                                            _c.clear()
                                            _caches_cleared += 1
                                        except Exception: pass
                        except Exception:
                            pass
                    except Exception:
                        pass

                    # Step 3 — Python GC. Three passes because cycles
                    # with __del__ methods need multiple collections
                    # to fully resolve.
                    try:
                        import gc as _gc, sys as _sys_c
                        _collected = 0
                        for _ in range(3):
                            _collected += _gc.collect()
                        try: _sys_c._clear_type_cache()
                        except Exception: pass
                    except Exception:
                        _collected = 0

                    # Step 4 — return pages to the kernel. Python's
                    # pymalloc keeps freed memory in a per-arena pool,
                    # so even after GC iOS still sees our RSS as
                    # elevated. Darwin's `malloc_zone_pressure_relief`
                    # tells the system allocator to release unused
                    # pages — this is what Apple's own frameworks do
                    # on `didReceiveMemoryWarning`.
                    _released_bytes = 0
                    try:
                        import ctypes as _ct
                        _libc = _ct.CDLL(None)
                        if hasattr(_libc, 'malloc_zone_pressure_relief'):
                            _libc.malloc_zone_pressure_relief.argtypes = [
                                _ct.c_void_p, _ct.c_size_t]
                            _libc.malloc_zone_pressure_relief.restype = \
                                _ct.c_size_t
                            # NULL zone = all zones. 0 = unlimited goal.
                            _released_bytes = int(
                                _libc.malloc_zone_pressure_relief(
                                    None, 0))
                        elif hasattr(_libc, 'malloc_trim'):
                            _libc.malloc_trim(0)
                    except Exception:
                        pass

                    _rss_after = _rss_mb()
                    _delta = (_rss_before - _rss_after) if (
                        _rss_before > 0 and _rss_after > 0) else 0
                    _log(f"[splt]   cleanup: RSS {_rss_before}MB "
                         f"→ {_rss_after}MB  "
                         f"(freed {_delta}MB, "
                         f"gc={_collected} objs, "
                         f"malloc_relief={_released_bytes // (1024*1024)}MB)")

                    # Step 5 — pre-flight RAM check for the NEXT scene.
                    # If we'd start the next scene with less than 500 MB
                    # free, stop rendering further scenes so we don't
                    # get jetsam-killed mid-render. Better to have a
                    # partial video than a crashed app.
                    try:
                        import psutil as _psu_c
                        _avail = _psu_c.virtual_memory().available
                        if _avail < 500 * 1024 * 1024:
                            _log(f"[splt] stopping: only "
                                 f"{_avail // (1024*1024)} MB RAM free, "
                                 f"remaining scenes would risk OOM. "
                                 f"Rendered {len(_rendered_mp4s)} of "
                                 f"{len(_scene_classes)} scenes.")
                            break
                    except Exception:
                        pass

                # Stitch multiple scene MP4s into one combined file. We
                # decode every frame and re-encode into a fresh output
                # stream — slower than stream-copy, but robust to any
                # per-clip SPS/PPS/timebase drift. Earlier stream-copy
                # attempts silently dropped all but the last clip's
                # packets when the mux rejected mismatched extradata,
                # which is the "only combines the last class" bug.
                if len(_rendered_mp4s) >= 2:
                    __codebench_plot_path = _rendered_mp4s[-1]   # default fallback
                    _combined_path = os.path.join(
                        os.path.dirname(_rendered_mp4s[0]),
                        "combined_scenes.mp4",
                    )

                    def _clip_codec_signature(path):
                        # Tuple identifying a clip's codec config.
                        # Two clips can be stream-copy concatenated
                        # iff their signatures are equal. Returns
                        # None on probe failure.
                        try:
                            import av as _av_p
                            _p = _av_p.open(path)
                            _ps = _p.streams.video[0]
                            _cc = _ps.codec_context
                            sig = (
                                str(getattr(_cc, "name", "")),
                                int(getattr(_cc, "width", 0) or 0),
                                int(getattr(_cc, "height", 0) or 0),
                                str(getattr(_cc, "pix_fmt", "") or ""),
                                str(getattr(_cc, "profile", "") or ""),
                                str(getattr(_ps, "average_rate", "")
                                    or ""),
                            )
                            _p.close()
                            return sig
                        except Exception:
                            return None

                    _stream_copy_done = False
                    try:
                        import av as _av
                        # Probe every clip up front — stream-copy is
                        # only safe if EVERY clip matches the first.
                        _sigs = [_clip_codec_signature(p)
                                 for p in _rendered_mp4s]
                        _all_match = (
                            all(s is not None for s in _sigs)
                            and len(set(_sigs)) == 1
                        )
                        if _all_match:
                            _out_ct = _av.open(_combined_path, mode="w")
                            _in0 = _av.open(_rendered_mp4s[0])
                            _in0_s = _in0.streams.video[0]
                            _out_stream = _out_ct.add_stream_from_template(
                                _in0_s)
                            _in0.close()

                            _muxed = 0
                            _dropped = 0
                            _pts_offset = 0
                            _last_duration = 1

                            for _src_i, _src in enumerate(_rendered_mp4s):
                                _in_ct = _av.open(_src)
                                _in_s = _in_ct.streams.video[0]
                                _clip_last_pts = 0
                                for _pkt in _in_ct.demux(_in_s):
                                    if _pkt.dts is None:
                                        continue
                                    try:
                                        _pkt.stream = _out_stream
                                        if _pkt.pts is not None:
                                            _pkt.pts = _pkt.pts + _pts_offset
                                            _clip_last_pts = max(
                                                _clip_last_pts, _pkt.pts)
                                        if _pkt.dts is not None:
                                            _pkt.dts = _pkt.dts + _pts_offset
                                        _last_duration = (
                                            _pkt.duration or _last_duration)
                                        _out_ct.mux(_pkt)
                                        _muxed += 1
                                    except Exception:
                                        _dropped += 1
                                _pts_offset = _clip_last_pts + _last_duration
                                _in_ct.close()

                            _out_ct.close()

                            if (_muxed > 0
                                    and os.path.exists(_combined_path)
                                    and os.path.getsize(_combined_path) > 500):
                                __codebench_plot_path = _combined_path
                                print(f"[manim rendered] {_combined_path}",
                                      flush=True)
                                print(f"[manim] combined "
                                      f"{len(_rendered_mp4s)} scenes "
                                      f"({_muxed} packets, {_dropped} "
                                      f"dropped) via stream-copy",
                                      flush=True)
                                _stream_copy_done = True
                            else:
                                print(f"[manim] stream-copy yielded no "
                                      f"packets; trying re-encode "
                                      f"fallback", flush=True)
                        else:
                            # Sigs differ: either different quality
                            # presets, dimensions, codecs — can't
                            # stream-copy, must re-encode.
                            print(f"[manim] clip codec signatures "
                                  f"differ ({len(set(_sigs))} variants) "
                                  f"— using re-encode fallback",
                                  flush=True)
                    except Exception as _sce:
                        print(f"[manim] stream-copy failed "
                              f"({type(_sce).__name__}: {_sce}) — "
                              f"trying re-encode fallback",
                              flush=True)

                    # ── Re-encode fallback ─────────────────────────
                    # Needed when (a) clips have heterogeneous codec
                    # parameters or (b) stream-copy produced no output.
                    # Our bundled PyAV 17.0.1pre has a bug on FFmpeg
                    # 8.x where `avcodec_send_frame` returns EOF
                    # unexpectedly. Workaround: drain pending packets
                    # after every EOFError and retry the frame.
                    if not _stream_copy_done:
                        try:
                            import av as _av
                            # Pick output dims/rate from the LARGEST
                            # clip so nothing gets cropped. Also pick
                            # the MAX source bitrate so our re-encode
                            # doesn't quality-starve — quality loss
                            # from re-encoding h264 → h264 at an
                            # equivalent-or-higher bitrate is typically
                            # ~1-2 dB PSNR, visually imperceptible.
                            _max_w = 0
                            _max_h = 0
                            _max_rate = 15
                            _max_bitrate = 0
                            for _p in _rendered_mp4s:
                                try:
                                    _pp = _av.open(_p)
                                    _ps = _pp.streams.video[0]
                                    _max_w = max(_max_w,
                                                 _ps.codec_context.width or 0)
                                    _max_h = max(_max_h,
                                                 _ps.codec_context.height or 0)
                                    _max_rate = max(_max_rate,
                                                    float(_ps.average_rate
                                                          or 15))
                                    _bps = (getattr(_pp, "bit_rate", 0) or 0)
                                    _max_bitrate = max(_max_bitrate, _bps)
                                    _pp.close()
                                except Exception:
                                    pass
                            if _max_w == 0 or _max_h == 0:
                                raise RuntimeError("couldn't probe any clip")

                            # ── Memory guardrail ──────────────────
                            # Before touching the encoder, make sure
                                # we have enough headroom for its
                                # internal frame buffer (~15 frames).
                                # At worst-case (1080p60) that's
                                # ~100 MB. If we're already under 200 MB
                                # free, skip re-encode and emit last
                                # scene rather than risk jetsam.
                            try:
                                import psutil as _psu
                                _avail = _psu.virtual_memory().available
                                _buffer_need = (_max_w * _max_h * 3
                                                * 15)   # 15 frames RGB
                                if _avail < max(200 * 1024 * 1024,
                                                _buffer_need * 3):
                                    print(f"[manim] skipping re-encode: "
                                          f"only {_avail // (1024*1024)} "
                                          f"MB available, need headroom "
                                          f"for {_buffer_need // (1024*1024)}"
                                          f" MB of encoder buffers",
                                          flush=True)
                                    raise MemoryError("insufficient RAM")
                            except MemoryError:
                                raise
                            except Exception:
                                pass

                            _out_ct = _av.open(_combined_path, mode="w")
                            # GPU toggle (header bolt button). When the
                            # user has it off, ContentView.triggerRender
                            # sets OFFLINAI_MANIM_GPU=0 so we drop to
                            # software libx264. Default-on (=hardware
                            # videotoolbox) because it's ~5× faster.
                            import os as _os_gpu
                            _gpu_codec = ("h264_videotoolbox"
                                          if _os_gpu.environ.get(
                                              "OFFLINAI_MANIM_GPU", "1") != "0"
                                          else "libx264")
                            _concat_stream = _out_ct.add_stream(
                                _gpu_codec, rate=int(_max_rate))
                            _concat_stream.width = _max_w
                            _concat_stream.height = _max_h
                            _concat_stream.pix_fmt = "yuv420p"
                            # Quality-preserving bitrate: match the
                            # highest source bitrate, with a floor of
                            # 3 Mbps for 480p / 6 Mbps for 720p+ /
                            # 12 Mbps for 1080p+ so upscaled content
                            # doesn't look worse than the source.
                            if _max_h >= 1080:
                                _floor = 12_000_000
                            elif _max_h >= 720:
                                _floor = 6_000_000
                            else:
                                _floor = 3_000_000
                            _concat_stream.bit_rate = max(
                                int(_max_bitrate), _floor)

                            def _drain(stream, sink):
                                # Pull every queued packet from the
                                # encoder. Tolerates the PyAV 17 /
                                # FFmpeg 8 EOFError quirk — EOFError
                                # just means "no more ready packets".
                                try:
                                    for _p in stream.encode():
                                        sink(_p)
                                except EOFError:
                                    pass
                                except Exception:
                                    pass

                            def _feed_frame(stream, frame, sink):
                                # Encode one frame, working around
                                # PyAV's over-eager EOFError by
                                # draining first and retrying once.
                                try:
                                    for _p in stream.encode(frame):
                                        sink(_p)
                                    return True
                                except EOFError:
                                    pass
                                _drain(stream, sink)
                                try:
                                    for _p in stream.encode(frame):
                                        sink(_p)
                                    return True
                                except Exception:
                                    return False

                            _encoded = 0
                            _skipped = 0
                            _pts_counter = 0
                            _mux_sink = lambda p: _out_ct.mux(p)

                            for _src_i, _src in enumerate(_rendered_mp4s):
                                try:
                                    _in_ct = _av.open(_src)
                                except Exception as _oe:
                                    print(f"[manim] couldn't open clip "
                                          f"{_src_i}: {_oe}", flush=True)
                                    continue
                                _in_s = _in_ct.streams.video[0]
                                for _frame in _in_ct.decode(_in_s):
                                    try:
                                        _arr = _frame.to_ndarray(format="rgb24")
                                        _clean = _av.VideoFrame.from_ndarray(
                                            _arr, format="rgb24")
                                        _clean.pts = _pts_counter
                                        _pts_counter += 1
                                        if _feed_frame(_concat_stream,
                                                       _clean, _mux_sink):
                                            _encoded += 1
                                        else:
                                            _skipped += 1
                                    except Exception:
                                        _skipped += 1
                                _in_ct.close()
                                # Drain between clips so encoder
                                # doesn't carry state across boundaries.
                                _drain(_concat_stream, _mux_sink)

                            # Final drain (last clip's trailing frames).
                            _drain(_concat_stream, _mux_sink)
                            _out_ct.close()

                            if (_encoded > 0
                                    and os.path.exists(_combined_path)
                                    and os.path.getsize(_combined_path) > 500):
                                __codebench_plot_path = _combined_path
                                print(f"[manim rendered] {_combined_path}",
                                      flush=True)
                                print(f"[manim] combined "
                                      f"{len(_rendered_mp4s)} scenes "
                                      f"({_encoded} frames, {_skipped} "
                                      f"skipped) via re-encode",
                                      flush=True)
                            else:
                                print(f"[manim] re-encode also yielded "
                                      f"empty video "
                                      f"({_encoded} encoded, {_skipped} "
                                      f"skipped) — emitting last scene",
                                      flush=True)
                                __codebench_plot_path = _rendered_mp4s[-1]
                                print(f"[manim rendered] "
                                      f"{_rendered_mp4s[-1]}", flush=True)
                        except Exception as _re:
                            import traceback as _rtb
                            _log(f"re-encode fallback failed: {_re}")
                            _rtb.print_exc()
                            __codebench_plot_path = _rendered_mp4s[-1]
                            print(f"[manim] concat failed both paths "
                                  f"({_re}); emitting last scene",
                                  flush=True)
                            print(f"[manim rendered] "
                                  f"{_rendered_mp4s[-1]}", flush=True)
            else:
                _log("no user-defined Scene classes in this run — skipping auto-render")
        except ImportError:
            pass
        except Exception as _ae:
            _log(f"Auto-render outer error: {_ae}")
            print(f"[manim] auto-detect outer error: {_ae}", flush=True)

    # Auto-save any unsaved matplotlib figures
    try:
        if _plt and hasattr(_plt, 'get_fignums') and _plt.get_fignums() and not __codebench_plot_path:
            _plt.show()
    except Exception:
        pass
except Exception:
    traceback.print_exc()
finally:
    sys.stdout, sys.stderr = _old_stdout, _old_stderr
__codebench_stdout = _out_stream.getvalue()
__codebench_stderr = _err_stream.getvalue()
_out_stream.close()
_err_stream.close()
# Diagnostic — log final value of __codebench_plot_path so we can tell
# from log.txt whether Swift's empty read is "Python never set it" vs
# "Swift looked at the wrong dict". Goes to NSLog (Xcode console) via
# sys.__stderr__ AND to the captured stdout, so it shows up either
# in Xcode or appended to the user's terminal output.
try:
    import sys as _diag_sys
    # Read three ways:
    #  (a) free variable      — what the auto-render assignment wrote to
    #  (b) main.__dict__[…]   — what Swift's getGlobalString reads
    #  (c) main module identity — confirms (a) and (b) point to the same dict
    _free = repr(__codebench_plot_path) if "__codebench_plot_path" in dir() or True else "<missing>"
    _md = _diag_sys.modules.get("__main__")
    _md_dict_path = repr(getattr(_md, "__codebench_plot_path", "<MISSING-FROM-MAIN>"))
    _md_id = hex(id(_md.__dict__)) if _md else "<no main>"
    _diag_msg = (
        f"[diag] free={_free}  main.dict={_md_dict_path}  "
        f"main.dict_id={_md_id}"
    )
    # __stderr__ may be the closed iOS-bundle fd (Errno 5) — keep it
    # best-effort so we don't drown the captured stdout in a red-herring
    # OSError trace at the very end of the run. We DON'T also print to
    # stdout here: stdout flows into the user-visible terminal, and
    # this diagnostic is purely for Xcode-console post-mortem when the
    # path probe came back empty. The Swift-side filter that drops
    # `[diag] …` lines didn't catch this one because it was emitted
    # outside the runTapped streaming pipeline (during runtime init),
    # so the surest way to keep it out of the terminal is just not to
    # print to stdout at all.
    try:
        _diag_sys.__stderr__.write(_diag_msg + "\\n")
        _diag_sys.__stderr__.flush()
    except OSError:
        pass
except Exception as _de:
    try:
        _diag_sys.__stderr__.write(
            f"[diag] FAILED: {type(_de).__name__}: {_de}\\n")
        _diag_sys.__stderr__.flush()
    except OSError:
        pass
"""
}
