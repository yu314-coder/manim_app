// ManimStudioApp.swift — app entry. Only LaTeX/busytex is wired here.
// Python runtime + python-ios-lib SwiftPM products will be added back
// once we've validated which ones auto-link transitively from Manim.
import SwiftUI

@main
struct ManimStudioApp: App {
    init() {
        // Persistent crash log at Documents/Logs/manim_studio.log.
        // Visible in iOS Files app under "On My iPad / Manim Studio /
        // Logs/" so the user can read or share it after a crash. MUST
        // be installed first so signal handlers cover the rest of init.
        CrashLogger.shared.install()

        // LaTeX backend selection — match CodeBench's behaviour.
        //
        // We previously forced every MathTex call through busytex/xelatex so
        // that complex macros (\underbrace, \boxed, CJK, matrix/align
        // environments) would render correctly. The side-effect: xelatex
        // strictly enforces \frac{}{} having exactly two arguments, which
        // collides with a long-standing Manim quirk in
        // `_break_up_by_substrings`: it splits every TeX string on `{{` /
        // `}}` (substring isolation markers) and rejoins the pieces with
        // dvisvgm `\special{...}` markers + a space. When `}}` arises
        // naturally inside an expression — e.g. `\frac{p_{i|j}}{2n}`, where
        // one `}` closes `p_{i|j` and the other closes the numerator —
        // those two braces get eaten and never restored. After
        // `offlinai_latex` strips the specials, xelatex sees
        // `\frac{p_{i|j {2n}}}` (one argument, no denominator) and fails.
        //
        // CodeBench doesn't set any of these env vars, so its routing
        // condition is `(has_cjk OR has_special_macro) AND NOT disabled`.
        // CJK-bearing expressions still go to busytex; simple Latin math
        // like `\frac{p_{i|j}}{2n}` falls through to SwiftMath, which
        // tolerates the Manim mangling. Match that here.
        //
        // Force busytex back on for ALL MathTex. The previous workaround
        // (let simple Latin math fall through to SwiftMath) was needed
        // because Manim's `}}` autosplit corrupted \frac{a}{b} when xelatex
        // saw it. Upstream python-ios-lib commit fe7cfa4c
        // "undo manim's `}}` autosplit before stripping specials" plus
        // 4d081711 "route \frac through real LaTeX" have fixed both the
        // corruption and the routing — we can now use busytex for
        // everything and get crisp PNG-in-SVG output instead of
        // SwiftMath's fixed-size Latin Modern glyphs (which Manim then
        // upscales and looks blurry).
        setenv("OFFLINAI_LATEX_BACKEND", "busytex", 1)
        setenv("OFFLINAI_ENGINE",        "busytex", 1)
        setenv("OFFLINAI_LATEX_FORCE_BUSYTEX", "1", 1)
        setenv("OFFLINAI_LATEX_USE_PDFTEX",    "0", 1)

        // UTF-8 mode — make Python default to UTF-8 for stdin/stdout/stderr
        // AND for every `open(path, "w")` that doesn't pass an explicit
        // `encoding=` arg. Without this, iOS Python's `locale.getpreferredencoding()`
        // returns "ascii" (because no LANG/LC_ALL is inherited from the iOS
        // process environment), and any third-party lib that does:
        //
        //     with open(svg_path, "w") as f: f.write(svg_containing_中文)
        //
        // dies with `UnicodeEncodeError: 'ascii' codec can't encode characters`.
        // `manimpango.text2svg` and several Manim helpers fall into this trap.
        // PYTHONUTF8=1 is Python 3.7+'s official switch and the canonical
        // fix on platforms without a real locale (iOS, embedded, container).
        setenv("PYTHONUTF8", "1", 1)
        setenv("LANG",       "en_US.UTF-8", 1)
        setenv("LC_ALL",     "en_US.UTF-8", 1)

        // SSL trust roots — point OpenSSL at certifi's bundled CA file.
        //
        // Beeware's iOS Python build inherits OpenSSL's compiled-in
        // default verify paths (e.g. /etc/ssl/certs) which simply don't
        // exist on iOS. Any HTTPS call through stdlib `urllib.request`,
        // `http.client`, or anything that builds an `ssl.SSLContext`
        // without an explicit cafile dies with:
        //
        //     URLError: [SSL: CERTIFICATE_VERIFY_FAILED]
        //     certificate verify failed: unable to get local issuer
        //     certificate (_ssl.c:1081)
        //
        // `requests` and `urllib3` work around this themselves by
        // calling `certifi.where()` and passing the path as a cafile —
        // which is why high-level libs sometimes appear to work while
        // stdlib `urlopen()` doesn't. Setting these env vars fixes
        // every path in one shot: OpenSSL reads `SSL_CERT_FILE` /
        // `SSL_CERT_DIR` natively, and `requests` reads
        // `REQUESTS_CA_BUNDLE` / `CURL_CA_BUNDLE` for completeness.
        let cacert = Bundle.main.bundleURL
            .appendingPathComponent("app_packages/site-packages/certifi/cacert.pem",
                                     isDirectory: false).path
        if FileManager.default.fileExists(atPath: cacert) {
            setenv("SSL_CERT_FILE",       cacert, 1)
            setenv("REQUESTS_CA_BUNDLE",  cacert, 1)
            setenv("CURL_CA_BUNDLE",      cacert, 1)
        } else {
            NSLog("[ssl] certifi cacert.pem not found at %@ — HTTPS will fail", cacert)
        }

        DispatchQueue.main.async {
            BusytexEngine.shared.preload()
            LaTeXEngine.shared.initialize()
            // Set up the PTY pipes + write the banner immediately so
            // the terminal pane has visible content the instant it
            // mounts. Then start Python booting on its background
            // queue. By the time the user has navigated to Workspace
            // and looked at the terminal, the real
            //   mobile@iPad ~/Workspace %
            // prompt is usually already printed below the banner.
            PTYBridge.shared.setupIfNeeded()
            PythonRuntime.shared.ensureRuntimeReady()
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .commands { ManimStudioCommands() }
    }
}
