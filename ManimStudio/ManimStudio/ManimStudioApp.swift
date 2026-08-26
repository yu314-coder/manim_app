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

        // LaTeX backend: force every MathTex through busytex/xelatex for
        // crisp PNG-in-SVG output. Upstream python-ios-lib fe7cfa4c
        // ("undo manim's `}}` autosplit") + 4d081711 ("route \frac through
        // real LaTeX") make \frac{a}{b} compile correctly under xelatex.
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

        // Start observing external-display scene connections before any
        // external scene can connect (an already-attached display is adopted
        // in the manager's init). Drives Presentation mode's TV routing.
        _ = ExternalDisplayManager.shared
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .commands { ManimStudioCommands() }
    }
}
