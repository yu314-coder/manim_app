import Foundation
import UIKit
import WebKit
import Darwin  // for open(), write(), close(), strlen, O_WRONLY/O_APPEND/O_CREAT

/// SwiftLaTeX-WASM-based pdflatex runner that compiles `.tex` → `.pdf`
/// offline, in a hidden WKWebView.
///
/// Why this exists: the C-based `lib-tex` (holzschu/lib-tex v1.40.20)
/// shipped as a framework crashes with `EXC_BAD_ACCESS @ 0x68` on
/// modern `latex.ltx` + `expl3` because those use pdftex primitives
/// added after 1.40.20 (lib-tex issue #1, unresolved since 2020).
///
/// Architecture:
///
///     Python builtin `pdflatex foo.tex`
///         ↓ writes signal file at $TMPDIR/latex_signals/compile_doc.txt
///     LaTeXEngine (swift)
///         ↓ passes to WebLaTeXEngine.compile(…)
///     WKWebView (hidden) running PdfTeXEngine.js
///         ↓ fetches support files via `offlinai-tex://` custom scheme
///     WebLaTeXEngine.URLSchemeHandler
///         ↓ reads from <App>.app/Frameworks/latex/texmf/
///     WASM pdftex runs, returns PDF bytes as base64
///         ↓ WebLaTeXEngine writes PDF to disk next to foo.tex
///     Python reads foo.pdf, returns path to user
///
/// Completely offline, reentrant (each compile is a fresh WASM run),
/// and doesn't trip iOS sandbox issues — WKWebView runs in its own
/// process with its own memory space.
@objc final class WebLaTeXEngine: NSObject {

    static let shared = WebLaTeXEngine()

    private var webView: WKWebView?
    private var isLoaded = false
    private var pendingLoadCallbacks: [() -> Void] = []
    private let queue = DispatchQueue(label: "codebench.latex.web", qos: .userInitiated)

    /// Live progress reports from the engine, forwarded to whoever's
    /// watching. LaTeXEngine hooks this up to the signal-file pipeline
    /// so Python can print "[latex] fetching article.cls" etc. while a
    /// compile is in flight instead of staring at a frozen prompt.
    var onProgress: ((_ message: String) -> Void)?

    /// When true, WebLaTeXEngine forwards JS-side log messages through
    /// onProgress. When false, they're only logged to Console (via
    /// NSLog) so the terminal stays quiet. Set true only during an
    /// active user-initiated compile so format-build chatter doesn't
    /// spam the shell on launch.
    fileprivate var verboseProgress = false

    /// Called by the URLSchemeHandler on every texmf fetch. We batch
    /// these into stats + forward notable ones so the terminal can
    /// show real progress instead of hanging silently.
    fileprivate var fetchesServed = 0
    fileprivate var fetchesMissed = 0
    fileprivate var firstFetchTime: CFAbsoluteTime = 0
    /// Name of the most recently served texmf file. When the served
    /// counter freezes, this tells us which package the compile was
    /// on right before it stuck.
    fileprivate var lastServedFile: String = "(none)"
    fileprivate var lastServedAt: CFAbsoluteTime = 0

    /// Shell progress pipe: path of a file the Python shell's poll
    /// loop tails so the user sees live "fetched 125 files", "writing
    /// PDF", etc. while a compile is in flight. nil when no shell
    /// compile is active. Set/cleared by LaTeXEngine around each
    /// signal-file-triggered compile.
    var shellProgressPath: String?
    private let progressLock = NSLock()

    /// Swift-side heartbeat: a timer that fires every 3 s while a
    /// shell compile is in flight and writes "[swift] alive (Ns)" to
    /// the progress file unconditionally. Distinguishes a "WASM truly
    /// hung" situation (Swift heartbeat lines appear, no pdftex lines)
    /// from a "Swift itself is blocked" situation (no Swift heartbeat
    /// either). Started in compile(), stopped in completion.
    private var swiftHeartbeat: DispatchSourceTimer?
    private var swiftHeartbeatStart: CFAbsoluteTime = 0

    /// Append a line to the shell progress pipe OR forward to the
    /// editor's `onProgress` closure — never both. Shell compiles
    /// (triggered by Python via signal file) tail the progress file
    /// themselves, so firing onProgress in that case double-prints
    /// every line in the terminal (once from Swift's appendToTerminal,
    /// once from Python's polling loop).
    ///
    /// Thread-safe — with a concurrent scheme-handler queue, multiple
    /// emitProgress calls can race, so the full open-append-close
    /// sequence is serialized under progressLock. Uses low-level POSIX
    /// `open(O_WRONLY|O_APPEND)` instead of `FileHandle(forWritingAtPath:)`
    /// which has been observed to silently no-op when the file is also
    /// being read from another process — the POSIX path is 100% reliable.
    fileprivate func emitProgress(_ message: String) {
        progressLock.lock()
        let path = shellProgressPath
        progressLock.unlock()

        if let path {
            progressLock.lock()
            defer { progressLock.unlock() }
            let line = message + "\n"
            // O_WRONLY | O_APPEND | O_CREAT — ensures atomic appends
            // even with concurrent writers, creates the file if the
            // caller didn't.
            let fd = path.withCString { cpath in
                Darwin.open(cpath, O_WRONLY | O_APPEND | O_CREAT, 0o644)
            }
            guard fd >= 0 else {
                NSLog("[WebLaTeX] emitProgress: open(%@) failed: errno=%d",
                      path, errno)
                return
            }
            line.withCString { cstr in
                _ = Darwin.write(fd, cstr, strlen(cstr))
            }
            Darwin.close(fd)
        } else if verboseProgress {
            // Editor compile: push through onProgress (feeds the
            // editor's own terminal view).
            DispatchQueue.main.async { [weak self] in
                self?.onProgress?(message)
            }
        }
    }

    /// Start the 3s heartbeat timer that writes "[swift] alive (Ns)"
    /// to the progress file regardless of WASM engine state. Called at
    /// compile start.
    fileprivate func startSwiftHeartbeat() {
        progressLock.lock()
        swiftHeartbeatStart = CFAbsoluteTimeGetCurrent()
        progressLock.unlock()
        let timer = DispatchSource.makeTimerSource(
            queue: DispatchQueue.global(qos: .userInitiated))
        timer.schedule(deadline: .now() + 3.0, repeating: 3.0)
        timer.setEventHandler { [weak self] in
            guard let self else { return }
            let elapsed = Int(CFAbsoluteTimeGetCurrent() - self.swiftHeartbeatStart)
            let sinceServed = self.lastServedAt > 0
                ? Int(CFAbsoluteTimeGetCurrent() - self.lastServedAt)
                : 0
            // If I/O has been quiet for 10+ s, emphasize where it got
            // stuck — that's the package/file the compile is stalled on.
            if sinceServed >= 10 {
                self.emitProgress(
                    "[swift] STUCK? last served '\(self.lastServedFile)' "
                    + "\(sinceServed)s ago — elapsed \(elapsed)s, "
                    + "served \(self.fetchesServed), missed \(self.fetchesMissed)")
            } else {
                self.emitProgress(
                    "[swift] alive (elapsed \(elapsed)s, served \(self.fetchesServed), "
                    + "missed \(self.fetchesMissed), last: '\(self.lastServedFile)')")
            }
        }
        timer.resume()
        swiftHeartbeat = timer
    }

    /// Stop the Swift heartbeat timer. Called at compile completion.
    fileprivate func stopSwiftHeartbeat() {
        swiftHeartbeat?.cancel()
        swiftHeartbeat = nil
    }

    /// Persist a log line to $TMPDIR/latex_signals/engine_init.log. This
    /// file captures EVERY latexLog message, including preload-time ones
    /// that happen before any shell compile has set shellProgressPath.
    /// The shell's progress pipe only receives in-flight compile events;
    /// this separate file is how we debug "first compile fails with no
    /// output" scenarios (e.g. silent compileFormat failure).
    fileprivate func appendToEngineLog(_ message: String) {
        let dir = NSTemporaryDirectory().appending("latex_signals")
        try? FileManager.default.createDirectory(
            atPath: dir, withIntermediateDirectories: true)
        let path = dir + "/engine_init.log"
        let ts = String(format: "%.3f", CFAbsoluteTimeGetCurrent())
        let line = "[\(ts)] \(message)\n"
        let fd = path.withCString { cpath in
            Darwin.open(cpath, O_WRONLY | O_APPEND | O_CREAT, 0o644)
        }
        guard fd >= 0 else { return }
        line.withCString { cstr in
            _ = Darwin.write(fd, cstr, strlen(cstr))
        }
        Darwin.close(fd)
    }

    /// Runtime-built TeX format files keyed by basename. The
    /// SwiftLaTeX engine builds `swiftlatexpdftex.fmt` on first use
    /// via `compileFormat()` and hands the bytes back here; subsequent
    /// compileLaTeX calls XHR for this name via the `offlinai-tex://`
    /// scheme and the URLSchemeHandler serves these cached bytes.
    fileprivate var runtimeCache: [String: Data] = [:]
    fileprivate let runtimeCacheLock = NSLock()

    /// The directory of the .tex file being compiled. Set before each
    /// compile so the URLSchemeHandler can serve user-local assets
    /// (figures, included .tex subfiles, bib files) the way a real
    /// pdflatex finds sibling files of the input .tex.
    fileprivate var userWorkingDir: URL?

    override private init() {
        super.init()
    }

    /// Spin up the hidden WKWebView and load the PdfTeXEngine.js host.
    /// Call from the main thread (UI operations). Safe to call multiple
    /// times — subsequent calls are no-ops if the engine is already up.
    @MainActor
    func preload() {
        guard webView == nil else { return }

        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        // Register our custom scheme BEFORE creating the WKWebView; iOS
        // enforces that WKURLSchemeHandlers are set at creation time.
        config.setURLSchemeHandler(URLSchemeHandler(), forURLScheme: "offlinai-tex")

        // JS-to-Swift message handlers: the latex.html host posts the
        // runtime-built .fmt bytes here ("latexCache") and diagnostic
        // log lines ("latexLog") for surfacing in the terminal.
        let ucc = WKUserContentController()
        ucc.add(self, name: "latexCache")
        ucc.add(self, name: "latexLog")
        config.userContentController = ucc

        let wv = WKWebView(frame: .zero, configuration: config)
        wv.isHidden = true
        wv.navigationDelegate = self
        self.webView = wv

        // Load the host page via our custom `offlinai-tex://` scheme
        // rather than file:// — Web Workers (which the WASM engine
        // requires) can't be constructed from a `file://` origin on
        // macOS Catalyst / iOS. A custom scheme gets a proper
        // same-origin treatment and the Worker loads fine.
        //
        // URL namespace served by URLSchemeHandler:
        //   offlinai-tex://app/latex.html           → bundle Resources/SwiftLaTeX/latex.html
        //   offlinai-tex://app/PdfTeXEngine.js      → bundle Resources/SwiftLaTeX/PdfTeXEngine.js
        //   offlinai-tex://app/swiftlatexpdftex.js  → bundle Resources/SwiftLaTeX/swiftlatexpdftex.js
        //   offlinai-tex://app/swiftlatexpdftex.wasm→ bundle Resources/SwiftLaTeX/swiftlatexpdftex.wasm
        //   offlinai-tex://texmf/pdftex/<file>      → bundle Frameworks/latex/texmf (recursive)
        guard let url = URL(string: "offlinai-tex://app/latex.html") else {
            return
        }
        wv.load(URLRequest(url: url))

        // Pre-warm the kpathsea-lite file index off the main thread so
        // the first compile's first XHR doesn't stall while we walk 2700+
        // texmf files. Cheap (~100-500 ms) but worth doing while the
        // WASM engine is loading in parallel anyway.
        DispatchQueue.global(qos: .userInitiated).async {
            URLSchemeHandler.prewarmIndex()
        }
    }

    /// Compile `texSource` to a PDF. The filename tells the engine what
    /// to call it inside its MEMFS (and therefore what the output PDF
    /// is named — `foo.tex` → `foo.pdf`).
    ///
    /// Completion runs on the main thread. `pdfData` is nil on failure;
    /// `log` always has pdftex's transcript so callers can surface
    /// errors without re-reading the engine's state.
    func compile(
        texSource: String,
        mainFileName: String = "main.tex",
        workingDir: URL? = nil,
        completion: @escaping (_ status: Int, _ log: String, _ pdfData: Data?) -> Void
    ) {
        DispatchQueue.main.async {
            // Turn on verbose progress forwarding — any JS log lines
            // from here until completion flow through onProgress to
            // the terminal. Before this, format-build chatter stays
            // in Console.app only.
            self.verboseProgress = true
            self.userWorkingDir = workingDir
            // Reset per-compile counters so "fetched N files" starts
            // at 0 for each compile (not an ever-growing global).
            URLSchemeHandler.resetStatsFor(self)
            self.emitProgress("starting compile of \(mainFileName)")
            self.startSwiftHeartbeat()
            self.preload()
            self.whenReady { [weak self] in
                guard let self, let wv = self.webView else {
                    self?.stopSwiftHeartbeat()
                    completion(-1, "engine not available", nil)
                    return
                }
                self.emitProgress("engine ready — running pdflatex")
                // Use callAsyncJavaScript so the Promise returned by
                // window.__latex.compile() actually gets awaited.
                // evaluateJavaScript returns before the Promise resolves
                // (= result is a dangling Promise, Swift reports
                // "unsupported type" Code=5).
                let js = "return await window.__latex.compile(texSource, mainFileName);"
                let args: [String: Any] = [
                    "texSource": texSource,
                    "mainFileName": mainFileName,
                ]
                wv.callAsyncJavaScript(
                    js,
                    arguments: args,
                    in: nil,
                    in: .page
                ) { result in
                    // Turn verbose progress back off once the compile
                    // settles — the terminal stays quiet if the engine
                    // logs anything after this (e.g. deferred Promise
                    // resolutions, late XHRs).
                    switch result {
                    case .failure(let error):
                        self.emitProgress("compile failed: \(error.localizedDescription)")
                        self.verboseProgress = false
                        self.stopSwiftHeartbeat()
                        completion(-2, "callAsyncJavaScript failed: \(error)", nil)
                    case .success(let value):
                        guard let obj = value as? [String: Any] else {
                            self.emitProgress("engine returned unexpected value")
                            self.verboseProgress = false
                            self.stopSwiftHeartbeat()
                            completion(-3,
                                "engine returned \(type(of: value)): \(value)",
                                nil)
                            return
                        }
                        let status = (obj["status"] as? Int) ?? -4
                        let logText = (obj["log"] as? String) ?? ""
                        let pdfB64 = (obj["pdfBase64"] as? String) ?? ""
                        let pdfData: Data? = pdfB64.isEmpty
                            ? nil
                            : Data(base64Encoded: pdfB64)
                        let elapsed = self.firstFetchTime > 0
                            ? CFAbsoluteTimeGetCurrent() - self.firstFetchTime
                            : 0
                        if status == 0, let pdf = pdfData {
                            self.emitProgress(
                                "compile OK — \(pdf.count) bytes "
                                + "in \(String(format: "%.1f", elapsed))s, "
                                + "\(self.fetchesServed) files served, "
                                + "\(self.fetchesMissed) misses")
                        } else {
                            self.emitProgress(
                                "compile failed (status \(status)) — "
                                + "\(self.fetchesServed) files served, "
                                + "\(self.fetchesMissed) misses")
                        }
                        self.verboseProgress = false
                        self.stopSwiftHeartbeat()
                        completion(status, logText, pdfData)
                    }
                }
            }
        }
    }

    /// Block the caller until the engine has finished booting, then run
    /// `action`. Called on the main thread.
    @MainActor
    private func whenReady(_ action: @escaping () -> Void) {
        if isLoaded {
            action()
            return
        }
        pendingLoadCallbacks.append(action)
    }

    // (string escaping no longer needed — callAsyncJavaScript's
    // arguments dict handles the quoting for us.)
}

// MARK: - Script message handler (JS → Swift)

extension WebLaTeXEngine: WKScriptMessageHandler {
    func userContentController(_ ucc: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        switch message.name {
        case "latexCache":
            guard let body = message.body as? [String: Any],
                  let kind = body["kind"] as? String else { return }
            if kind == "fmt", let b64 = body["data"] as? String,
               let data = Data(base64Encoded: b64) {
                runtimeCacheLock.lock()
                runtimeCache["swiftlatexpdftex.fmt"] = data
                // Also under a couple of aliases pdftex might request
                runtimeCache["pdflatex.fmt"] = data
                runtimeCacheLock.unlock()
                NSLog("[WebLaTeX] cached .fmt (\(data.count) bytes)")
                // Persist to engine_init.log so the shell can replay
                // preload-time info on next compile failure.
                appendToEngineLog("[cache] stored .fmt (\(data.count) bytes)")
            }
        case "latexLog":
            if let msg = message.body as? String {
                NSLog("[WebLaTeX/JS] \(msg)")
                // Always persist to engine_init.log so preload-time
                // messages (which happen before any shell compile sets
                // shellProgressPath) are recoverable.
                appendToEngineLog(msg)
                // Route through emitProgress so BOTH the editor's
                // onProgress AND the shell's progress file get it.
                // verboseProgress still gates the editor path inside
                // emitProgress — the shell path is unconditional (it
                // only writes if a shellProgressPath is registered).
                emitProgress(msg)
            }
        default:
            break
        }
    }
}

// MARK: - Navigation delegate

extension WebLaTeXEngine: WKNavigationDelegate {
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        isLoaded = true
        let callbacks = pendingLoadCallbacks
        pendingLoadCallbacks.removeAll()
        for cb in callbacks { cb() }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        print("[WebLaTeX] navigation failed: \(error.localizedDescription)")
    }
}

// MARK: - Custom URL scheme handler
//
// The WASM pdftex engine asks for TeX Live support files by XHR'ing
// `<texlive_endpoint>pdftex/<cacheKey>` (see swiftlatexpdftex.js).
// We point the endpoint at `offlinai-tex://texmf/` and satisfy the
// requests by reading from the app's bundled Frameworks/latex/texmf/
// tree — completely offline.
//
// The `<cacheKey>` is an opaque name like "article" or "amsmath.sty"
// or "pdflatex.fmt". We resolve it by searching the texmf tree for a
// matching filename. kpathsea-style: walk tex/, fonts/, web2c/.

extension WebLaTeXEngine {

    final class URLSchemeHandler: NSObject, WKURLSchemeHandler {

        // Concurrent — beamer + pgf trigger ~500+ XHRs on first load.
        // Serial would force every request through one worker and stall
        // the compile for minutes. Shared state (fileIndex, runtimeCache)
        // is already protected by its own locks, so concurrency is safe.
        private let queue = DispatchQueue(label: "codebench.latex.scheme",
                                          qos: .userInitiated,
                                          attributes: .concurrent)
        private var texmfRoot: URL? {
            Bundle.main.url(forResource: "texmf", withExtension: nil,
                            subdirectory: "Frameworks/latex")
        }

        func webView(_ webView: WKWebView, start urlSchemeTask: WKURLSchemeTask) {
            guard let url = urlSchemeTask.request.url else {
                urlSchemeTask.didFailWithError(Self.err("no url"))
                return
            }
            queue.async { [weak self] in
                self?.serve(urlSchemeTask, for: url)
            }
        }

        func webView(_ webView: WKWebView, stop urlSchemeTask: WKURLSchemeTask) {
            // Nothing to cancel — our handler completes synchronously.
        }

        private func serve(_ task: WKURLSchemeTask, for url: URL) {
            // Two namespaces served under the `offlinai-tex://` scheme:
            //
            // 1. `offlinai-tex://app/<filename>` — engine files (HTML,
            //    JS, WASM) from the app bundle's Resources/SwiftLaTeX/
            //    dir. We serve the host page via the custom scheme so
            //    Web Workers can be created (file:// origin blocks them).
            //
            // 2. `offlinai-tex://texmf/pdftex/<cacheKey>` — TeX Live
            //    support files from Frameworks/latex/texmf/. The WASM
            //    engine's kpse_find_file_js XHRs these during compile.
            let host = url.host ?? ""
            if host == "app" {
                serveAppResource(task, for: url)
                return
            }
            if host != "texmf" {
                NSLog("[WebLaTeX] unknown host '\(host)' in \(url)")
                task.didFailWithError(Self.err("unknown host"))
                return
            }

            let path = url.path
            let key = (path as NSString).lastPathComponent
            guard !key.isEmpty else {
                task.didFailWithError(Self.err("empty key"))
                return
            }
            // Runtime cache first — serves `swiftlatexpdftex.fmt` that
            // was built earlier via compileFormat(). Checked before the
            // static texmf bundle so runtime-built formats take priority.
            let engine = WebLaTeXEngine.shared
            engine.runtimeCacheLock.lock()
            let cached = engine.runtimeCache[key]
            engine.runtimeCacheLock.unlock()
            if let data = cached {
                // The engine's kpse_find_file_impl was patched at build
                // time to save each response under /tex/<reqname> (the
                // requested filename), so we don't need to supply a
                // `fileid` header — WKURLSchemeHandler would've stripped
                // custom headers anyway, which was the original bug
                // (all files landing at /tex/null).
                let response = HTTPURLResponse(
                    url: url, statusCode: 200,
                    httpVersion: "HTTP/1.1",
                    headerFields: [
                        "Content-Type": "application/octet-stream",
                        "Content-Length": "\(data.count)",
                        "Access-Control-Allow-Origin": "*",
                    ]
                )!
                task.didReceive(response)
                task.didReceive(data)
                task.didFinish()
                NSLog("[WebLaTeX] served runtime-cached \(key) (\(data.count) bytes)")
                return
            }
            guard let root = texmfRoot else {
                NSLog("[WebLaTeX] texmf root not found — bundle missing?")
                task.didFailWithError(Self.err("texmf bundle missing"))
                return
            }
            // Track progress so the terminal can print "fetched N files"
            if engine.firstFetchTime == 0 {
                engine.firstFetchTime = CFAbsoluteTimeGetCurrent()
                engine.emitProgress("compiling (WASM engine serving texmf)")
            }
            // User working-dir assets — images, \input-ed subfiles,
            // .bib files next to the .tex the user invoked pdflatex
            // on. Check BEFORE the texmf tree so a user-provided
            // `article.cls` overrides the bundled one.
            // Drop the checkResourceIsReachable() pre-check — Data(contentsOf:)
            // itself fails fast on missing files. Saves one syscall per fetch
            // × 500+ fetches on first beamer/pgf load.
            if let workDir = engine.userWorkingDir,
               let data = try? Data(contentsOf: workDir.appendingPathComponent(key)) {
                engine.fetchesServed += 1
                let response = HTTPURLResponse(
                    url: url, statusCode: 200,
                    httpVersion: "HTTP/1.1",
                    headerFields: [
                        "Content-Type": Self.mimeType(
                            for: workDir.appendingPathComponent(key)),
                        "Content-Length": "\(data.count)",
                        "Access-Control-Allow-Origin": "*",
                    ]
                )!
                task.didReceive(response)
                task.didReceive(data)
                task.didFinish()
                NSLog("[WebLaTeX] served user-asset \(key) (\(data.count) bytes)")
                return
            }
            if let fileURL = locate(key: key, root: root) {
                do {
                    let data = try Data(contentsOf: fileURL)
                    engine.fetchesServed += 1
                    engine.lastServedFile = key
                    engine.lastServedAt = CFAbsoluteTimeGetCurrent()
                    let mime = Self.mimeType(for: fileURL)
                    let response = HTTPURLResponse(
                        url: url,
                        statusCode: 200,
                        httpVersion: "HTTP/1.1",
                        headerFields: [
                            "Content-Type": mime,
                            "Content-Length": "\(data.count)",
                            "Access-Control-Allow-Origin": "*",
                        ]
                    )!
                    task.didReceive(response)
                    task.didReceive(data)
                    task.didFinish()
                    if engine.fetchesServed <= 5 ||
                       engine.fetchesServed % 25 == 0 {
                        NSLog("[WebLaTeX] served \(engine.fetchesServed) files (last: \(key))")
                        // Heartbeat for the shell: every 25 files, tell
                        // the user how far along we are.
                        engine.emitProgress(
                            "fetched \(engine.fetchesServed) texmf files (last: \(key))")
                    }
                } catch {
                    NSLog("[WebLaTeX] read error for \(key): \(error)")
                    task.didFailWithError(error)
                }
            } else {
                engine.fetchesMissed += 1
                // Missing image? Serve a 1x1 transparent PNG placeholder
                // so `\includegraphics{not_here.png}` doesn't abort the
                // compile — matches real pdflatex's default behavior of
                // warning-not-erroring on missing image files (well,
                // pdflatex actually errors by default; we choose the
                // friendlier behavior because on-device users frequently
                // reference external images they don't realize aren't
                // in the sandbox).
                let ext = (key as NSString).pathExtension.lowercased()
                let imageExts: Set<String> = [
                    "png", "jpg", "jpeg", "pdf", "eps", "ps",
                    "bmp", "gif", "tiff", "tif"
                ]
                if imageExts.contains(ext) {
                    let placeholder = Self.placeholderImage(for: ext)
                    let response = HTTPURLResponse(
                        url: url,
                        statusCode: 200,
                        httpVersion: "HTTP/1.1",
                        headerFields: [
                            "Content-Type": Self.mimeType(
                                for: URL(fileURLWithPath: key)),
                            "Content-Length": "\(placeholder.count)",
                            "Access-Control-Allow-Origin": "*",
                        ]
                    )!
                    task.didReceive(response)
                    task.didReceive(placeholder)
                    task.didFinish()
                    NSLog("[WebLaTeX] placeholder for missing image \(key)")
                    return
                }
                // Engine's kpse_find_file_impl only caches misses when
                // the status is 301 — with 404 it re-XHRs every time
                // pdftex asks for the same missing file. Return 301 so
                // the miss goes into texlive404_cache and subsequent
                // asks short-circuit instead of roundtripping.
                if engine.fetchesMissed <= 5 ||
                   engine.fetchesMissed % 25 == 0 {
                    NSLog("[WebLaTeX] miss (\(engine.fetchesMissed)): \(key)")
                }
                let response = HTTPURLResponse(
                    url: url,
                    statusCode: 301,
                    httpVersion: "HTTP/1.1",
                    headerFields: ["Access-Control-Allow-Origin": "*"]
                )!
                task.didReceive(response)
                task.didFinish()
            }
        }

        /// kpathsea-lite: recursively walk texmf looking for a file
        /// whose basename matches `key`. Cached in memory so repeated
        /// lookups (the engine asks for the same font 30+ times per
        /// doc) don't re-walk the tree.
        private static var fileIndex: [String: URL] = [:]
        private static let indexLock = NSLock()

        /// Zero out the per-compile fetch counters on the shared engine.
        /// Called at the start of each compile() so progress messages
        /// like "fetched 50 files" reflect THIS compile, not cumulative
        /// stats across the app's lifetime.
        static func resetStatsFor(_ engine: WebLaTeXEngine) {
            engine.fetchesServed = 0
            engine.fetchesMissed = 0
            engine.firstFetchTime = 0
            engine.lastServedFile = "(none)"
            engine.lastServedAt = 0
        }

        /// Build the file index off the main thread so the first compile's
        /// first XHR doesn't pay the ~100-500 ms walk cost. Idempotent.
        static func prewarmIndex() {
            indexLock.lock()
            defer { indexLock.unlock() }
            if !fileIndex.isEmpty { return }
            guard let root = Bundle.main.url(
                forResource: "texmf", withExtension: nil,
                subdirectory: "Frameworks/latex") else { return }
            let tmp = URLSchemeHandler()
            tmp.buildIndex(root: root)
        }

        private func locate(key: String, root: URL) -> URL? {
            Self.indexLock.lock()
            defer { Self.indexLock.unlock() }
            if Self.fileIndex.isEmpty {
                buildIndex(root: root)
            }
            // Try the exact key first, then common TeX aliases.
            // Engine sometimes asks for "article" (no ext), sometimes
            // "article.cls". Try both.
            if let u = Self.fileIndex[key] { return u }
            for suffix in [".cls", ".sty", ".tex", ".ltx", ".def",
                           ".fd", ".tfm", ".pfb", ".map", ".enc", ".cfg"] {
                if let u = Self.fileIndex[key + suffix] { return u }
            }

            // Rollback fallback: modern LaTeX's \usepackage{xcolor}[=2022-06-12]
            // asks for `xcolor-2022-06-12.sty` (a dated snapshot) and errors
            // out if it's not found. We only ship undated current versions,
            // so strip the `-YYYY-MM-DD` or `-YYYY/MM/DD` suffix and try again.
            // This lets user docs pin specific dates without us needing to
            // bundle every historic snapshot of every package.
            if let stripped = Self.stripRollbackDate(from: key) {
                if let u = Self.fileIndex[stripped] { return u }
                for suffix in [".cls", ".sty", ".tex", ".ltx", ".def",
                               ".fd", ".tfm", ".pfb", ".map", ".enc", ".cfg"] {
                    if let u = Self.fileIndex[stripped + suffix] { return u }
                }
            }
            return nil
        }

        /// If `key` ends in `-YYYY-MM-DD.ext` or `/YYYY-MM-DD.ext`, return
        /// the key with the date part removed. Otherwise nil.
        /// Examples:
        ///   "xcolor-2022-06-12.sty" → "xcolor.sty"
        ///   "graphicx-2020/10/01.sty" → "graphicx.sty"
        ///   "article.cls" → nil
        static func stripRollbackDate(from key: String) -> String? {
            // Extract extension, base name
            let nsKey = key as NSString
            let ext = nsKey.pathExtension
            let base = ext.isEmpty ? key : nsKey.deletingPathExtension
            // Look for the trailing `-YYYY-MM-DD` or `-YYYY/MM/DD`
            let pattern = "[-/]([0-9]{4})[-/]([0-9]{2})[-/]([0-9]{2})$"
            guard let regex = try? NSRegularExpression(pattern: pattern),
                  let match = regex.firstMatch(
                    in: base, range: NSRange(base.startIndex..., in: base))
            else { return nil }
            let newBase = (base as NSString).replacingCharacters(
                in: match.range, with: "")
            return ext.isEmpty ? newBase : (newBase + "." + ext)
        }

        private func buildIndex(root: URL) {
            let fm = FileManager.default
            guard let enumerator = fm.enumerator(
                at: root, includingPropertiesForKeys: [.isRegularFileKey]
            ) else { return }
            var count = 0
            for case let u as URL in enumerator {
                let values = try? u.resourceValues(forKeys: [.isRegularFileKey])
                if values?.isRegularFile == true {
                    // Earliest match wins — the bundled tree is flat
                    // enough that collisions are rare; if they do
                    // occur, the first hit is usually the canonical
                    // one because texmf/tex/latex/base/ is walked
                    // before texmf/tex/generic/ etc.
                    let name = u.lastPathComponent
                    if Self.fileIndex[name] == nil {
                        Self.fileIndex[name] = u
                    }
                    count += 1
                }
            }
            print("[WebLaTeX] indexed \(count) texmf files for kpathsea lookup")
        }

        /// Serve a file from the app bundle's Resources/SwiftLaTeX dir
        /// — the host HTML, PdfTeXEngine.js, the Emscripten glue JS,
        /// and the .wasm binary.
        private func serveAppResource(_ task: WKURLSchemeTask, for url: URL) {
            let filename = (url.path as NSString).lastPathComponent
            guard !filename.isEmpty else {
                task.didFailWithError(Self.err("empty app filename"))
                return
            }
            let ext = (filename as NSString).pathExtension
            let base = (filename as NSString).deletingPathExtension
            guard let fileURL = Bundle.main.url(
                forResource: base, withExtension: ext,
                subdirectory: "Resources/SwiftLaTeX"
            ) ?? Bundle.main.url(
                forResource: base, withExtension: ext
            ) else {
                NSLog("[WebLaTeX] app resource not found: \(filename)")
                let response = HTTPURLResponse(
                    url: url, statusCode: 404,
                    httpVersion: "HTTP/1.1", headerFields: nil
                )!
                task.didReceive(response)
                task.didFinish()
                return
            }
            do {
                let data = try Data(contentsOf: fileURL)
                let mime: String
                switch ext.lowercased() {
                case "html": mime = "text/html; charset=utf-8"
                case "js":   mime = "application/javascript; charset=utf-8"
                case "wasm": mime = "application/wasm"
                case "css":  mime = "text/css; charset=utf-8"
                default:     mime = "application/octet-stream"
                }
                // Note: we deliberately DO NOT set
                // Cross-Origin-Embedder-Policy=require-corp here.
                // That would force every sub-resource (every texmf XHR)
                // to also carry `Cross-Origin-Resource-Policy`, and
                // missing that header would silently fail the fetch —
                // the symptom was pdftex receiving truncated file data
                // and erroring with "\immediion {VMS (???)}". We don't
                // use SharedArrayBuffer so the policy isn't needed.
                let response = HTTPURLResponse(
                    url: url, statusCode: 200,
                    httpVersion: "HTTP/1.1",
                    headerFields: [
                        "Content-Type": mime,
                        "Content-Length": "\(data.count)",
                        "Access-Control-Allow-Origin": "*",
                    ]
                )!
                task.didReceive(response)
                task.didReceive(data)
                task.didFinish()
                NSLog("[WebLaTeX] served app/\(filename) (\(data.count) bytes)")
            } catch {
                NSLog("[WebLaTeX] read error for app/\(filename): \(error)")
                task.didFailWithError(error)
            }
        }

        private static func mimeType(for url: URL) -> String {
            switch url.pathExtension.lowercased() {
            case "pdf":  return "application/pdf"
            case "png":  return "image/png"
            case "jpg", "jpeg": return "image/jpeg"
            case "gif":  return "image/gif"
            case "bmp":  return "image/bmp"
            case "tiff", "tif": return "image/tiff"
            case "eps", "ps":   return "application/postscript"
            case "pfb":  return "application/x-font-type1"
            case "tfm":  return "application/octet-stream"
            case "fmt":  return "application/octet-stream"
            default:     return "text/plain; charset=utf-8"
            }
        }

        /// Minimal 1x1 placeholder so a missing `\includegraphics{foo}`
        /// doesn't abort the compile. For PNG this is a static 67-byte
        /// transparent-pixel blob (spec-valid). For anything else we
        /// return the same PNG bytes — pdflatex will warn but keep
        /// going.
        private static func placeholderImage(for ext: String) -> Data {
            // A 1×1 transparent PNG, hand-rolled as a hex blob.
            // This is a valid, complete PNG file (IHDR + IDAT + IEND).
            let hex = "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4" +
                      "890000000D49444154789C6300010000000500010D0A2DB40000000049454E" +
                      "44AE426082"
            var data = Data(capacity: hex.count / 2)
            var idx = hex.startIndex
            while idx < hex.endIndex {
                let next = hex.index(idx, offsetBy: 2)
                if let byte = UInt8(hex[idx..<next], radix: 16) {
                    data.append(byte)
                }
                idx = next
            }
            return data
        }

        private static func err(_ msg: String) -> NSError {
            NSError(domain: "codebench.latex", code: -1,
                    userInfo: [NSLocalizedDescriptionKey: msg])
        }
    }
}
