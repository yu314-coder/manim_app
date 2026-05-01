import Foundation
import UIKit
import WebKit
import Darwin  // for open(), write(), close(), strlen, O_WRONLY/O_APPEND/O_CREAT

/// BusyTeX-WASM-based LaTeX runner (upstream busytex, TL 2023, pdftex
/// 1.40.25). Compiles `.tex` → `.pdf` offline inside a hidden WKWebView.
///
/// Why this exists alongside `WebLaTeXEngine`: SwiftLaTeX's pdftex
/// 1.40.21 predates a bunch of beamer/pgf/l3kernel fixes and hangs on
/// mid-size beamer docs. Rebuilding pdftex from newer TL source hit
/// an emscripten-side startup wall (see `pdflatex-ios/STATUS.md`).
/// BusyTeX is a pre-built WASM bundle from upstream
/// https://github.com/busytex/busytex that ships pdftex 1.40.25 +
/// xetex + luatex + bibtex8 + xdvipdfmx in one 30 MB WASM, with the
/// texmf tree baked into Emscripten LZ4 data packages. Completely
/// different architecture than SwiftLaTeX — no kpathsea XHRs, the FS
/// is preloaded into MEMFS before compile.
///
/// Architecture:
///
///     Python builtin `pdflatex foo.tex` (with OFFLINAI_ENGINE=busytex)
///         ↓ writes signal file at $TMPDIR/latex_signals/compile_doc.txt
///     LaTeXEngine (swift)
///         ↓ passes to BusytexEngine.compile(…)
///     WKWebView (hidden) running busytex.html + busytex_worker.js
///         ↓ fetches via `offlinai-bt://` custom scheme
///     BusytexEngine.URLSchemeHandler
///         ↓ reads from <App>.app/Resources/Busytex/
///     WASM busytex runs, returns PDF bytes as base64
///         ↓ BusytexEngine writes PDF to disk next to foo.tex
///     Python reads foo.pdf, returns path to user
///
/// Dispatch is driven by env var `OFFLINAI_ENGINE` — "busytex" routes
/// here, anything else (default) routes to `WebLaTeXEngine`.
@objc final class BusytexEngine: NSObject {

    static let shared = BusytexEngine()

    private var webView: WKWebView?
    private var isLoaded = false
    private var pendingLoadCallbacks: [() -> Void] = []

    /// Forwarded up to LaTeXEngine / CodeEditorViewController for live
    /// compile chatter in the terminal.
    var onProgress: ((_ message: String) -> Void)?
    fileprivate var verboseProgress = false

    /// See `WebLaTeXEngine.shellProgressPath` — the Python shell tails
    /// this path during a compile so the terminal streams progress.
    var shellProgressPath: String?
    private let progressLock = NSLock()

    /// Swift-side heartbeat timer that writes "[swift] alive (Ns)" to
    /// the progress file every 3 s while a shell compile is in flight.
    /// Distinguishes "WASM truly hung" (heartbeat fires, busytex quiet)
    /// from "Swift hung" (no heartbeat either).
    private var swiftHeartbeat: DispatchSourceTimer?
    private var swiftHeartbeatStart: CFAbsoluteTime = 0

    /// Directory of the .tex being compiled. Preserved so we can write
    /// out the PDF next to it.
    fileprivate var userWorkingDir: URL?

    override private init() {
        super.init()
    }

    // MARK: - Progress plumbing (identical contract to WebLaTeXEngine)

    fileprivate func emitProgress(_ message: String) {
        progressLock.lock()
        let path = shellProgressPath
        progressLock.unlock()

        if let path {
            progressLock.lock()
            defer { progressLock.unlock() }
            let line = message + "\n"
            let fd = path.withCString { cpath in
                Darwin.open(cpath, O_WRONLY | O_APPEND | O_CREAT, 0o644)
            }
            guard fd >= 0 else {
                NSLog("[Busytex] emitProgress: open(%@) failed: errno=%d",
                      path, errno)
                return
            }
            line.withCString { cstr in
                _ = Darwin.write(fd, cstr, strlen(cstr))
            }
            Darwin.close(fd)
        } else if verboseProgress {
            DispatchQueue.main.async { [weak self] in
                self?.onProgress?(message)
            }
        }
    }

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
            self.emitProgress("[swift] alive (elapsed \(elapsed)s, busytex engine)")
        }
        timer.resume()
        swiftHeartbeat = timer
    }

    fileprivate func stopSwiftHeartbeat() {
        swiftHeartbeat?.cancel()
        swiftHeartbeat = nil
    }

    /// Append to engine_init.log so preload-time messages are
    /// recoverable after a failed first compile. Matches the contract
    /// of WebLaTeXEngine.appendToEngineLog.
    fileprivate func appendToEngineLog(_ message: String) {
        let dir = NSTemporaryDirectory().appending("latex_signals")
        try? FileManager.default.createDirectory(
            atPath: dir, withIntermediateDirectories: true)
        let path = dir + "/engine_init.log"
        let ts = String(format: "%.3f", CFAbsoluteTimeGetCurrent())
        let line = "[\(ts)] [busytex] \(message)\n"
        let fd = path.withCString { cpath in
            Darwin.open(cpath, O_WRONLY | O_APPEND | O_CREAT, 0o644)
        }
        guard fd >= 0 else { return }
        line.withCString { cstr in
            _ = Darwin.write(fd, cstr, strlen(cstr))
        }
        Darwin.close(fd)
    }

    // MARK: - Public API (mirrors WebLaTeXEngine exactly)

    @MainActor
    func preload() {
        guard webView == nil else { return }

        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.setURLSchemeHandler(URLSchemeHandler(), forURLScheme: "offlinai-bt")

        let ucc = WKUserContentController()
        ucc.add(self, name: "latexLog")
        config.userContentController = ucc

        let wv = WKWebView(frame: .zero, configuration: config)
        wv.isHidden = true
        wv.navigationDelegate = self
        self.webView = wv

        guard let url = URL(string: "offlinai-bt://app/busytex.html") else {
            return
        }
        wv.load(URLRequest(url: url))
    }

    func compile(
        texSource: String,
        mainFileName: String = "main.tex",
        workingDir: URL? = nil,
        driver: String = "pdftex_bibtex8",
        completion: @escaping (_ status: Int, _ log: String, _ pdfData: Data?) -> Void
    ) {
        DispatchQueue.main.async {
            self.verboseProgress = true
            self.userWorkingDir = workingDir
            // Human-readable command name for progress messages —
            // maps the pipeline driver back to what the user typed.
            let cmdName: String = {
                switch driver {
                case "xetex_bibtex8_dvipdfmx": return "xelatex"
                case "luatex_bibtex8": return "lualatex"
                case "luahbtex_bibtex8": return "luahblatex"
                default: return "pdflatex"
                }
            }()
            self.emitProgress("starting busytex \(cmdName) on \(mainFileName)")
            self.startSwiftHeartbeat()
            self.preload()
            self.whenReady { [weak self] in
                guard let self, let wv = self.webView else {
                    self?.stopSwiftHeartbeat()
                    completion(-1, "busytex engine not available", nil)
                    return
                }
                self.emitProgress("busytex engine ready — running \(cmdName)")
                // Sanitize the source for pdflatex. pdflatex + inputenc
                // only handles ASCII + Latin-1-Extended + a handful of
                // named punctuation codepoints. Anything else (CJK,
                // symbols past U+0200, math operators beyond what
                // utf8.def declares, etc.) fatal-errors with
                // "Unicode character X not set up for use with LaTeX."
                // We swap those codepoints for "[?]" so the compile
                // proceeds — the user sees where the unrenderable
                // chars were in the output PDF. Only pdflatex drivers
                // need this; xetex/luatex handle Unicode natively.
                var (sourceForEngine, replacedCount): (String, Int) =
                    driver.contains("pdftex")
                        ? Self.sanitizeForPdflatex(texSource)
                        : (texSource, 0)
                if replacedCount > 0 {
                    self.emitProgress(
                        "sanitized \(replacedCount) non-Latin char"
                        + (replacedCount == 1 ? "" : "s")
                        + " → [?] (pdflatex can't render them)")
                }
                // Auto-inject \usepackage{lmodern} when the doc uses
                // \usepackage[T1]{fontenc} without a T1-capable font.
                // Without this, pdftex tries to generate bitmap fonts
                // via mktexpk → needs fork() → unavailable in WASM →
                // "Font tcrm1095 at 600 not found" mid-compile. lmodern
                // provides native T1 Type1 fonts, so no font generation.
                if driver.contains("pdftex") {
                    let (patched, injected) = Self.injectLmodernIfNeeded(sourceForEngine)
                    if injected {
                        sourceForEngine = patched
                        self.emitProgress(
                            "injected \\usepackage{lmodern} (T1 fontenc needs it on WASM)")
                    }
                }
                // Build the files[] array the pipeline needs. Unlike
                // SwiftLaTeX (which serves sibling files on-demand via
                // URL scheme handler), busytex preloads EVERYTHING into
                // MEMFS — so we must pass real graphics/input files
                // up front. For referenced files that don't exist on
                // disk, we synthesize a 1×1 placeholder so
                // \includegraphics{missing} doesn't abort the build.
                let extraFiles = self.buildSiblingFiles(
                    texSource: sourceForEngine,
                    workingDir: workingDir)
                let js = "return await window.__busytex.compile(texSource, mainFileName, extraFiles, driver);"
                let args: [String: Any] = [
                    "texSource": sourceForEngine,
                    "mainFileName": mainFileName,
                    "extraFiles": extraFiles,
                    "driver": driver,
                ]
                wv.callAsyncJavaScript(
                    js, arguments: args, in: nil, in: .page
                ) { result in
                    switch result {
                    case .failure(let error):
                        self.emitProgress("busytex compile failed: \(error.localizedDescription)")
                        self.verboseProgress = false
                        self.stopSwiftHeartbeat()
                        completion(-2, "callAsyncJavaScript failed: \(error)", nil)
                    case .success(let value):
                        guard let obj = value as? [String: Any] else {
                            self.verboseProgress = false
                            self.stopSwiftHeartbeat()
                            completion(-3,
                                "busytex returned \(type(of: value)): \(value)",
                                nil)
                            return
                        }
                        let status = (obj["status"] as? Int) ?? -4
                        let logText = (obj["log"] as? String) ?? ""
                        let pdfB64 = (obj["pdfBase64"] as? String) ?? ""
                        // Decode base64 off the main thread — a multi-MB
                        // PDF's decode blocks the UI long enough that the
                        // watchdog can kill background WebContent
                        // processes mid-cleanup (seen as a spurious
                        // "Task NNN: signal SIGABRT" in Xcode after the
                        // compile already succeeded).
                        DispatchQueue.global(qos: .userInitiated).async {
                            let pdfData: Data? = pdfB64.isEmpty
                                ? nil
                                : Data(base64Encoded: pdfB64)
                            DispatchQueue.main.async {
                                if status == 0, let pdf = pdfData {
                                    self.emitProgress(
                                        "busytex compile OK — \(pdf.count) bytes")
                                } else {
                                    self.emitProgress(
                                        "busytex compile failed (status \(status))")
                                }
                                self.verboseProgress = false
                                self.stopSwiftHeartbeat()
                                completion(status, logText, pdfData)
                            }
                        }
                    }
                }
            }
        }
    }

    @MainActor
    private func whenReady(_ action: @escaping () -> Void) {
        if isLoaded {
            action()
            return
        }
        pendingLoadCallbacks.append(action)
    }

    // MARK: - Math expression compile (manim MathTex pipeline)
    //
    // Wraps a bare math expression in a self-contained xelatex preamble
    // (amsmath + xcolor + xeCJK), bundles a CJK-capable font alongside,
    // and runs through busytex's `xetex_bibtex8_dvipdfmx` driver →
    // returns full-quality PDF. The caller (LaTeXEngine.checkForMathCompileRequest)
    // rasterises the PDF page to a high-DPI PNG and embeds it as
    // `<image>` in an SVG that manim's patched svg_mobject loader
    // recognises (svg_mobject.image_to_mobject → ImageMobject).
    //
    // This is the path that delivers full LaTeX (\underbrace, \boxed,
    // amsmath operators) plus CJK in `\text{...}` — which SwiftMath's
    // Latin-Modern-only renderer could never do.
    func compileMath(
        expression: String,
        colorHex: String = "FFFFFF",
        completion: @escaping (_ status: Int, _ log: String, _ pdfData: Data?) -> Void
    ) {
        DispatchQueue.main.async {
            self.preload()
            self.whenReady { [weak self] in
                guard let self, let wv = self.webView else {
                    completion(-1, "busytex engine not available", nil)
                    return
                }

                let texSource = Self.mathPreamble(expression: expression,
                                                   colorHex: colorHex)
                let extraFiles = self.mathExtraFiles()

                let js = "return await window.__busytex.compile(texSource, mainFileName, extraFiles, driver);"
                let args: [String: Any] = [
                    "texSource": texSource,
                    "mainFileName": "math.tex",
                    "extraFiles": extraFiles,
                    // xelatex via xeCJK + the bundled Noto Sans JP. We
                    // briefly tried pdflatex+CJKutf8 but busytex's
                    // bundled texmf doesn't ship the gbsn TFM (the log
                    // surfacing fix made this finally visible:
                    // "Font C70/gbsn/m/n/12/5c=gbsnu5c not loadable").
                    // pdflatex can't fontspec an arbitrary OTF either,
                    // so xelatex is the only path that pairs with the
                    // font we already bundle.
                    "driver": "xetex_bibtex8_dvipdfmx",
                ]
                self.emitProgress("[math] busytex starting xelatex on '\(expression.prefix(60))…'")
                wv.callAsyncJavaScript(
                    js, arguments: args, in: nil, in: .page
                ) { result in
                    switch result {
                    case .failure(let error):
                        self.emitProgress("[math] busytex callAsyncJavaScript failed: \(error.localizedDescription)")
                        completion(-2, "callAsyncJavaScript: \(error)", nil)
                    case .success(let value):
                        guard let obj = value as? [String: Any] else {
                            completion(-3, "unexpected return shape: \(type(of: value))", nil)
                            return
                        }
                        let status = (obj["status"] as? Int) ?? -4
                        let logText = (obj["log"] as? String) ?? ""
                        let pdfB64 = (obj["pdfBase64"] as? String) ?? ""
                        DispatchQueue.global(qos: .userInitiated).async {
                            let pdfData: Data? = pdfB64.isEmpty
                                ? nil : Data(base64Encoded: pdfB64)
                            DispatchQueue.main.async {
                                if status == 0, let pdf = pdfData {
                                    self.emitProgress("[math] xelatex OK — \(pdf.count) byte PDF")
                                } else {
                                    self.emitProgress("[math] xelatex failed (status \(status))")
                                }
                                completion(status, logText, pdfData)
                            }
                        }
                    }
                }
            }
        }
    }

    /// Build the xelatex source for a math expression. `standalone`
    /// with border=2pt gives a tight bounding box; `fontspec` +
    /// `Path=./` points at NotoSansJP-Regular.otf shipped as an
    /// extraFile. We don't use xeCJK — it's not in busytex's bundled
    /// texmf. xelatex's native Unicode handling picks up CJK glyphs
    /// directly from the main font, which is enough for `\text{...}`
    /// containing Chinese/Japanese inside math.
    private static func mathPreamble(expression: String, colorHex: String) -> String {
        var expr = expression
        if expr.hasPrefix("$") && expr.hasSuffix("$") && expr.count >= 2 {
            expr = String(expr.dropFirst().dropLast())
        }
        let hex = colorHex.hasPrefix("#") ? String(colorHex.dropFirst()) : colorHex
        return """
        \\documentclass[border=2pt,12pt]{standalone}
        \\usepackage{amsmath,amssymb,amsfonts}
        \\usepackage{xcolor}
        \\usepackage{fontspec}
        \\setmainfont[Path=./]{NotoSansJP-Regular.otf}
        \\begin{document}
        \\color[HTML]{\(hex)}
        $\\displaystyle \(expr)$
        \\end{document}
        """
    }

    /// Read NotoSansJP-Regular.otf from the bundle and return it as a
    /// busytex extraFiles entry (b64-encoded). Lets xeCJK find a CJK
    /// font without relying on busytex's fontconfig knowing about one.
    private func mathExtraFiles() -> [[String: String]] {
        var out: [[String: String]] = []
        // Look for the font in any of the bundled locations.
        let candidates: [(name: String, ext: String, sub: String?)] = [
            ("NotoSansJP-Regular", "otf", "Resources/KaTeX/fonts"),
            ("NotoSansJP-Regular", "otf", "KaTeX/fonts"),
            ("NotoSansJP-Regular", "otf", nil),
        ]
        for c in candidates {
            let url: URL? = (c.sub != nil)
                ? Bundle.main.url(forResource: c.name, withExtension: c.ext, subdirectory: c.sub)
                : Bundle.main.url(forResource: c.name, withExtension: c.ext)
            if let u = url, let data = try? Data(contentsOf: u) {
                out.append([
                    "path": "NotoSansJP-Regular.otf",
                    "kind": "b64",
                    "data": data.base64EncodedString(),
                ])
                return out
            }
        }
        // Font missing — xeCJK will error on CJK input, but Latin math
        // still compiles. Caller should detect the empty result.
        emitProgress("[math] WARN: NotoSansJP-Regular.otf not found in bundle — CJK will fail")
        return out
    }

    // MARK: - Sibling file collection + missing-file placeholders
    //
    // Busytex can't fault in files on demand the way SwiftLaTeX does —
    // its MEMFS is populated entirely from preloaded data packages.
    // So: scan the user's .tex for file references (\includegraphics,
    // \input, \include, \bibliography), read real content when the
    // file exists, and synthesize a tiny placeholder for anything
    // that's missing. The pipeline then writes each entry into
    // <project_dir>/<path> in MEMFS before invoking pdflatex.
    //
    // Each entry is serialised for WKWebKit's callAsyncJavaScript
    // arguments (JSON-only): `["path": String, "kind": "text"|"b64",
    // "data": String]`. JS decodes base64 into Uint8Array for binary.

    fileprivate func buildSiblingFiles(
        texSource: String, workingDir: URL?
    ) -> [[String: String]] {
        var out: [[String: String]] = []
        var seenPaths = Set<String>()
        let sizeCap = 20 * 1024 * 1024  // 20 MB per file — images fit, no runaway

        // Image references — used by graphicx/includepdf/pdf. pdflatex
        // tries these extensions in order when no explicit ext given.
        let imageExts = ["pdf", "png", "jpg", "jpeg", "eps", "ps",
                         "bmp", "gif", "tiff", "tif"]
        let imageRefs = Self.scanRefs(
            texSource: texSource,
            commands: ["includegraphics", "includepdf"])

        for ref in imageRefs {
            let refExt = (ref as NSString).pathExtension.lowercased()
            // No extension in the ref → pdflatex probes one. Try each
            // possible sibling on disk; if none exists, synthesize a
            // .png placeholder named "<ref>.png" so graphicx resolves.
            let candidates: [String] = refExt.isEmpty
                ? imageExts.map { "\(ref).\($0)" }
                : [ref]
            var served = false
            if let workingDir {
                for cand in candidates {
                    let url = workingDir.appendingPathComponent(cand)
                    if FileManager.default.fileExists(atPath: url.path),
                       let attrs = try? FileManager.default.attributesOfItem(atPath: url.path),
                       let size = attrs[.size] as? Int, size <= sizeCap,
                       let data = try? Data(contentsOf: url) {
                        if !seenPaths.contains(cand) {
                            out.append([
                                "path": cand, "kind": "b64",
                                "data": data.base64EncodedString(),
                            ])
                            seenPaths.insert(cand)
                        }
                        served = true
                        break
                    }
                }
            }
            if !served {
                // Missing — pick a .png placeholder name. If ref has
                // a non-image extension or none, use "<ref>.png".
                let placeholderPath = refExt.isEmpty ? "\(ref).png" : ref
                if !seenPaths.contains(placeholderPath) {
                    let placeholder = Self.placeholderBytes(forExt:
                        (placeholderPath as NSString).pathExtension.lowercased())
                    out.append([
                        "path": placeholderPath, "kind": "b64",
                        "data": placeholder.base64EncodedString(),
                    ])
                    seenPaths.insert(placeholderPath)
                    self.emitProgress("placeholder for missing '\(placeholderPath)'")
                }
            }
        }

        // Sibling .tex partials — \input / \include. TeX auto-appends
        // .tex when no extension, so normalise to that first.
        let texRefs = Self.scanRefs(
            texSource: texSource, commands: ["input", "include", "subfile"])
        for ref in texRefs {
            let refExt = (ref as NSString).pathExtension.lowercased()
            let path = refExt.isEmpty ? "\(ref).tex" : ref
            if seenPaths.contains(path) { continue }
            guard let workingDir else { continue }
            let url = workingDir.appendingPathComponent(path)
            if let data = try? Data(contentsOf: url),
               data.count <= sizeCap,
               let text = String(data: data, encoding: .utf8)
                       ?? String(data: data, encoding: .isoLatin1) {
                out.append(["path": path, "kind": "text", "data": text])
                seenPaths.insert(path)
            }
            // Missing .tex partials don't get a placeholder — an
            // empty \input expansion is LaTeX's natural behaviour.
        }

        // Bibliography — \bibliography{name} looks for name.bib.
        let bibRefs = Self.scanRefs(
            texSource: texSource, commands: ["bibliography", "addbibresource"])
        for ref in bibRefs {
            let refExt = (ref as NSString).pathExtension.lowercased()
            let path = refExt.isEmpty ? "\(ref).bib" : ref
            if seenPaths.contains(path) { continue }
            guard let workingDir else { continue }
            let url = workingDir.appendingPathComponent(path)
            if let data = try? Data(contentsOf: url),
               data.count <= sizeCap,
               let text = String(data: data, encoding: .utf8)
                       ?? String(data: data, encoding: .isoLatin1) {
                out.append(["path": path, "kind": "text", "data": text])
                seenPaths.insert(path)
            }
        }

        return out
    }

    /// Extract the argument of every `\<cmd>[opts]{name}` occurrence
    /// from `texSource`. Comma-separated args like
    /// `\bibliography{a,b,c}` are split into individual names.
    static func scanRefs(texSource: String, commands: [String]) -> [String] {
        var out: [String] = []
        for cmd in commands {
            // \cmd[optional]{required}  — optional group may or may
            // not be present, required is always `{...}` (no nested
            // braces in the wild). Non-greedy inside the {}.
            let pattern = "\\\\\(cmd)(?:\\s*\\[[^\\]]*\\])?\\s*\\{([^{}]+)\\}"
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            let range = NSRange(texSource.startIndex..., in: texSource)
            regex.enumerateMatches(in: texSource, options: [], range: range) {
                match, _, _ in
                guard let match, match.numberOfRanges >= 2,
                      let r = Range(match.range(at: 1), in: texSource) else { return }
                let raw = String(texSource[r])
                for part in raw.split(separator: ",") {
                    let trimmed = part.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !trimmed.isEmpty { out.append(trimmed) }
                }
            }
        }
        return out
    }

    /// A tiny, well-formed placeholder for each common graphics type.
    /// pdflatex reads the file header for dimensions — it needs a
    /// valid format, not just arbitrary bytes.
    static func placeholderBytes(forExt ext: String) -> Data {
        switch ext {
        case "pdf":
            // Minimal single-page PDF 1.4, 1pt × 1pt, no content.
            // Produces a blank box in the output.
            return Self.placeholderPdf()
        default:
            // Everything else — PNG, JPG, unknown — we hand back the
            // 1×1 transparent PNG. graphicx identifies PNG from the
            // signature bytes; JPEG references to a PNG will be
            // silently tolerated or warned about, never fatal.
            return Self.placeholderPng()
        }
    }

    /// Inject `\usepackage{lmodern}` into the preamble if the doc asks
    /// for T1 fontenc without bringing its own T1-capable font family.
    ///
    /// Rationale: `\usepackage[T1]{fontenc}` switches LaTeX's default
    /// font encoding from OT1 to T1. The default font family (`cmr`)
    /// has no Type1 fonts for T1 — so pdftex, when asked to typeset
    /// T1-encoded CM Roman at arbitrary sizes, invokes `mktexpk` to
    /// generate bitmap PKs from Metafont sources. `mktexpk` spawns a
    /// subprocess via `fork()`, and `fork()` isn't implemented in our
    /// WASM environment, so it aborts with `Font tcrm1095 at 600 not
    /// found`. Latin Modern (lmodern) provides native T1-encoded
    /// Type1 fonts as a drop-in CM replacement — no font generation
    /// needed.
    ///
    /// We inject only when the doc:
    ///   • uses `\usepackage[T1]{fontenc}`  (or `[T2A,T1]` or similar)
    ///   • AND doesn't already declare a T1-capable family
    ///     (lmodern / newtxtext / newpxtext / kpfonts / mathpazo /
    ///      mathptmx / ...)
    ///
    /// Insertion point: right after `\documentclass{…}` so it loads
    /// before the user's own `\usepackage` lines fire `[T1]{fontenc}`.
    static func injectLmodernIfNeeded(_ source: String) -> (String, Bool) {
        // Already provides a T1-compatible family? Skip.
        let t1CapableFamilies = [
            "lmodern", "newtxtext", "newpxtext", "kpfonts",
            "mathpazo", "mathptmx", "cm-super", "times", "helvet",
            "courier", "palatino", "bookman", "charter", "libertine",
            "ccfonts", "fourier", "tgtermes", "tgpagella", "tgbonum",
            "tgschola", "tgheros", "tgcursor", "tgadventor",
        ]
        let lowered = source.lowercased()
        for fam in t1CapableFamilies {
            // Match `\usepackage{fam}` or `\usepackage[opts]{fam}`.
            if lowered.contains("\\usepackage{\(fam)}") ||
               lowered.range(of: "\\\\usepackage\\[[^\\]]*\\]\\{\(fam)\\}",
                             options: .regularExpression) != nil {
                return (source, false)
            }
        }
        // Uses T1 fontenc? If not, no injection needed.
        let usesT1 = lowered.range(
            of: "\\\\usepackage\\[[^\\]]*\\bt1\\b[^\\]]*\\]\\{fontenc\\}",
            options: .regularExpression) != nil
        guard usesT1 else { return (source, false) }

        // Insert right after the \documentclass{…} line.
        let docClassRegex = try? NSRegularExpression(
            pattern: "\\\\documentclass(?:\\[[^\\]]*\\])?\\{[^{}]+\\}[\\s]*\\n?",
            options: [])
        guard let regex = docClassRegex else { return (source, false) }
        let nsRange = NSRange(source.startIndex..., in: source)
        guard let match = regex.firstMatch(in: source, range: nsRange),
              let matchRange = Range(match.range, in: source) else {
            return (source, false)
        }
        let injection = "\\usepackage{lmodern}% auto-injected by CodeBench — T1 font compat (no mktexpk in WASM)\n"
        var out = source
        out.insert(contentsOf: injection, at: matchRange.upperBound)
        return (out, true)
    }

    /// Replace Unicode codepoints that pdflatex+inputenc can't handle
    /// with the literal string `[?]`. Returns the cleaned source and
    /// a count of replacements so the engine can tell the user.
    ///
    /// Kept (pdflatex handles these):
    /// - ASCII (U+0000..U+007F)
    /// - Latin-1 Supplement + Extended-A/B + IPA (U+0080..U+02FF) —
    ///   covered by inputenc's utf8.def declarations
    /// - A small whitelist of common punctuation used in real writing:
    ///   en/em dash, curly quotes, ellipsis, non-breaking space
    ///
    /// Replaced (fatal-errors in pdflatex by default):
    /// - Math/arrow/symbol blocks past U+2030
    /// - CJK (0x3000–0x9FFF, 0xF900+)
    /// - Any surrogate / private-use / emoji codepoint
    static func sanitizeForPdflatex(_ source: String) -> (String, Int) {
        let keepPunctuation: Set<UInt32> = [
            0x00A0,  // non-breaking space
            0x2013,  // en dash
            0x2014,  // em dash
            0x2018,  // left single quote
            0x2019,  // right single quote
            0x201C,  // left double quote
            0x201D,  // right double quote
            0x2026,  // ellipsis
            0x2022,  // bullet
        ]
        var out = String.UnicodeScalarView()
        out.reserveCapacity(source.unicodeScalars.count)
        var replaced = 0
        let qMark = Array("[?]".unicodeScalars)
        for scalar in source.unicodeScalars {
            let code = scalar.value
            if code < 0x0300 || keepPunctuation.contains(code) {
                out.append(scalar)
            } else {
                out.append(contentsOf: qMark)
                replaced += 1
            }
        }
        return (String(out), replaced)
    }

    private static func placeholderPng() -> Data {
        // 1×1 transparent RGBA PNG, 68 bytes. Generated by zlib'ing
        // [0,0,0,0,0] (filter byte + 4-byte RGBA pixel) and wrapping
        // in valid IHDR/IDAT/IEND chunks with real CRC32s. Verified
        // via python zlib — decompresses and validates cleanly. The
        // older hand-coded hex placeholder in the repo had a
        // corrupted IDAT (zlib Adler32 mismatch); pdftex's libpng
        // accepted the IHDR but rejected the IDAT with
        // "IDAT: incorrect data check" → pipeline threw Infinity.
        let hex = "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4" +
                  "890000000B4944415478DA636000020000050001E9FADCD80000000049454E" +
                  "44AE426082"
        return Self.hexToData(hex)
    }

    private static func placeholderPdf() -> Data {
        // Minimal valid one-page PDF. Produces an empty 1pt×1pt page.
        let txt = """
        %PDF-1.4
        1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
        2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
        3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 1 1]/Resources<<>>/Contents 4 0 R>>endobj
        4 0 obj<</Length 0>>stream
        endstream
        endobj
        xref
        0 5
        0000000000 65535 f
        0000000009 00000 n
        0000000054 00000 n
        0000000099 00000 n
        0000000178 00000 n
        trailer<</Size 5/Root 1 0 R>>
        startxref
        221
        %%EOF
        """
        return Data(txt.utf8)
    }

    private static func hexToData(_ hex: String) -> Data {
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
}

// MARK: - Script message handler (JS → Swift)

extension BusytexEngine: WKScriptMessageHandler {
    func userContentController(_ ucc: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard message.name == "latexLog",
              let msg = message.body as? String else { return }
        NSLog("[Busytex/JS] \(msg)")
        appendToEngineLog(msg)
        emitProgress(msg)
    }
}

// MARK: - Navigation delegate

extension BusytexEngine: WKNavigationDelegate {
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        isLoaded = true
        let callbacks = pendingLoadCallbacks
        pendingLoadCallbacks.removeAll()
        for cb in callbacks { cb() }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        print("[Busytex] navigation failed: \(error.localizedDescription)")
    }
}

// MARK: - Custom URL scheme handler
//
// Unlike WebLaTeXEngine's handler (which serves a flat texmf tree by
// basename for the WASM engine's kpathsea XHRs), this handler only
// serves files from Resources/Busytex/ — the Emscripten glue JS,
// busytex.wasm, the host HTML/worker, and the data packages. All
// texmf files live inside those data packages as LZ4 blobs preloaded
// into MEMFS, so no per-file fetching happens during compile.
//
// URL namespace:
//   offlinai-bt://app/<filename>  →  Resources/Busytex/<filename>
//
// Serving the host from this scheme (not file://) ensures the Worker
// spawned by busytex.html has a proper same-origin parent.

extension BusytexEngine {

    final class URLSchemeHandler: NSObject, WKURLSchemeHandler {

        private let queue = DispatchQueue(label: "codebench.busytex.scheme",
                                          qos: .userInitiated,
                                          attributes: .concurrent)

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
            // Synchronous — nothing to cancel.
        }

        private func serve(_ task: WKURLSchemeTask, for url: URL) {
            guard (url.host ?? "") == "app" else {
                task.didFailWithError(Self.err("unknown host '\(url.host ?? "")'"))
                return
            }
            let filename = (url.path as NSString).lastPathComponent
            guard !filename.isEmpty else {
                task.didFailWithError(Self.err("empty filename"))
                return
            }
            let ext = (filename as NSString).pathExtension
            let base = (filename as NSString).deletingPathExtension
            // Xcode's synchronized-group processing flattens
            // Resources/Busytex/* into the bundle root — all 21 files
            // (busytex.wasm, *.data, *.js, etc.) land at
            // <Bundle>/<filename>. Look there directly.
            guard let fileURL = Bundle.main.url(
                forResource: base, withExtension: ext
            ) else {
                NSLog("[Busytex] resource not found: \(filename)")
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
                let response = HTTPURLResponse(
                    url: url, statusCode: 200,
                    httpVersion: "HTTP/1.1",
                    headerFields: [
                        "Content-Type": Self.mimeType(ext: ext),
                        "Content-Length": "\(data.count)",
                        "Access-Control-Allow-Origin": "*",
                    ]
                )!
                task.didReceive(response)
                task.didReceive(data)
                task.didFinish()
                // Only log small assets and the occasional data package.
                // Full data-package load is 6 × 10-100 MB, noisy per-log.
                if data.count < 2_000_000 || filename.hasSuffix(".js") {
                    NSLog("[Busytex] served \(filename) (\(data.count) bytes)")
                }
            } catch {
                NSLog("[Busytex] read error for \(filename): \(error)")
                task.didFailWithError(error)
            }
        }

        private static func mimeType(ext: String) -> String {
            switch ext.lowercased() {
            case "html": return "text/html; charset=utf-8"
            case "js":   return "application/javascript; charset=utf-8"
            case "wasm": return "application/wasm"
            case "css":  return "text/css; charset=utf-8"
            case "data": return "application/octet-stream"
            case "cfg":  return "text/plain; charset=utf-8"
            case "cnf":  return "text/plain; charset=utf-8"
            default:     return "application/octet-stream"
            }
        }

        private static func err(_ msg: String) -> NSError {
            NSError(domain: "codebench.busytex", code: -1,
                    userInfo: [NSLocalizedDescriptionKey: msg])
        }
    }
}
