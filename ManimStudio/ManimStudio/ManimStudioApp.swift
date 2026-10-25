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

        // The 16K rung was removed; move any device still holding it
        // down to 14K before a picker or a render reads the setting.
        RenderResolution.migrateRetiredSelection()

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
            // The LaTeX engine (busytex) loads on demand — see
            // BusytexEngine.warmUp — not here.
            LaTeXEngine.shared.initialize()
            LaTeXEngine.shared.onPreviewRequest = { target in
                NotificationCenter.default.post(name: .terminalPreviewRequest, object: nil,
                                                userInfo: ["target": target])
            }
            // Set up the PTY pipes + write the banner immediately so
            // the terminal pane has visible content the instant it
            // mounts. Then start Python booting on its background
            // queue. By the time the user has navigated to Workspace
            // and looked at the terminal, the real
            //   mobile@iPad ~/Workspace %
            // prompt is usually already printed below the banner.
            PTYBridge.shared.setupIfNeeded()
            // A render that was running when the app last stopped — closed by
            // iOS in the background, most likely — says so in the terminal.
            UnfinishedRender.reportIfAny()
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
                .modifier(NarrowWindowLayout())
                .modifier(DuoLaptopLayout())
        }
        .commands { ManimStudioCommands() }
    }
}

/// Uses the phone layout in a window narrower than 700 points even when
/// the system calls it regular width. The iPhone Duo held half-open like a
/// laptop gives the app the top half of its inner screen, ~669 points wide
/// but "regular", and the iPad layout (editor + preview + controls side by
/// side) ran off both edges. Every iPad keeps its layout: the narrowest,
/// the iPad mini in portrait, is 744 points.
private struct NarrowWindowLayout: ViewModifier {
    @Environment(\.horizontalSizeClass) private var systemSizeClass

    func body(content: Content) -> some View {
        // The window's width, not the content's: the iPad layout is wider
        // than such a window, so measuring the content never saw it narrow.
        GeometryReader { geo in
            content
                .environment(\.horizontalSizeClass,
                             geo.size.width > 0 && geo.size.width < 700 ? .compact : systemSizeClass)

        }
    }
}

extension EnvironmentValues {
    /// Height of the iPhone Duo's lower screen while it's held like a
    /// laptop, nil otherwise. ContentView keeps the app off it.
    @Entry var duoLowerScreen: CGFloat? = nil
}

/// The iPhone Duo held half-open, the keyboard has one screen to itself.
enum DuoPosture: Equatable {
    /// Hinge across the window: the lower screen is Apple's keyboard and
    /// nothing else (ContentView leaves it empty); its height.
    case laptop(lowerScreen: CGFloat)
    /// Hinge top to bottom as iOS sees it, though the Duo is held like a
    /// laptop then too: the app turns its picture a quarter so the far
    /// screen is the app and the near (right) one ManimStudio's keyboard
    /// (DuoBookKeyboard) — iOS won't turn its own keyboard, nor let the app
    /// keep to portrait in this windowing mode. Where the hinge is.
    case book(hinge: CGFloat, insets: UIEdgeInsets)
}

/// Lays the app out for DuoPosture. Here at the root SwiftUI is told to
/// ignore the keyboard while the Duo is half-open: the keyboard has its
/// own screen, and making room for it as well pushed the whole app up off
/// the top.
private struct DuoLaptopLayout: ViewModifier {
    @State private var posture: DuoPosture?

    private var lowerScreen: CGFloat? {
        if case .laptop(let height) = posture { height } else { nil }
    }
    private var hinge: CGFloat? {
        if case .book(let x, _) = posture { x } else { nil }
    }
    /// The window's safe area turned with the picture: the screen's left
    /// edge is the canvas's top, its right edge (the clock and Wi-Fi) the
    /// canvas's bottom, its bottom the canvas's leading edge.
    private var turnedInsets: EdgeInsets {
        guard case .book(_, let i) = posture else { return EdgeInsets() }
        return EdgeInsets(top: i.left, leading: i.bottom, bottom: i.right, trailing: i.top)
    }

    func body(content: Content) -> some View {
        GeometryReader { geo in
            let size = geo.size
            // Held like a book the picture turns a quarter to the left:
            // laid out upright on a portrait canvas — the app on the far
            // half, the keyboard on the near one — then rotated so the
            // keyboard has the right screen.
            let canvas = hinge != nil ? CGSize(width: size.height, height: size.width) : size
            let pad = turnedInsets
            VStack(spacing: 0) {
                // Always the first child, so the app isn't rebuilt when the
                // Duo turns from one posture to another.
                content
                    .frame(height: hinge.map { _ in canvas.height / 2 - pad.top } ?? canvas.height)
                    .environment(\.duoLowerScreen, lowerScreen)
                if hinge != nil {
                    DuoBookKeyboard()
                        .frame(height: canvas.height / 2 - pad.bottom)
                }
            }
            .padding(pad)
            // The safe area's strips in the halves' own colours.
            .background {
                if hinge != nil {
                    VStack(spacing: 0) {
                        Theme.bgPrimary
                        Color(uiColor: DuoBookKeyboardView.background)
                    }
                }
            }
            .frame(width: canvas.width, height: canvas.height)
            .rotationEffect(.degrees(hinge != nil ? -90 : 0))
            .position(x: size.width / 2, y: size.height / 2)
        }
        .ignoresSafeArea(hinge != nil ? .all : posture != nil ? .keyboard : [], edges: hinge != nil ? .all : .bottom)
        .background(DuoPostureReader(posture: $posture))
    }
}

/// Reports DuoPosture: hinge partly open (iOS 27.1), and which way it
/// runs across the window. For the laptop, the lower screen is measured
/// from where the key bar sits on the keys down to the bottom safe area.
private struct DuoPostureReader: UIViewRepresentable {
    @Binding var posture: DuoPosture?

    func makeUIView(context: Context) -> ReaderView {
        let view = ReaderView()
        let binding = $posture
        view.onChange = { posture in
            // Not during SwiftUI's own update, where a state change is
            // dropped (the first hinge report comes then).
            DispatchQueue.main.async {
                if binding.wrappedValue != posture { binding.wrappedValue = posture }
            }
        }
        return view
    }

    func updateUIView(_ uiView: ReaderView, context: Context) {}

    final class ReaderView: UIView {
        var onChange: ((DuoPosture?) -> Void)?
        private var partlyOpen = false
        private var reported: DuoPosture??

        override init(frame: CGRect) {
            super.init(frame: frame)
            isUserInteractionEnabled = false
            if #available(iOS 27.1, *) {
                addInteraction(UIHingeInteraction { [weak self] _, update in
                    self?.partlyOpen = update.hinge?.status == .partiallyOpen
                    self?.report()
                })
            }
        }

        required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

        override func layoutSubviews() {
            super.layoutSubviews()
            report()   // rotation turns book posture into laptop
        }

        override func didMoveToWindow() {
            super.didMoveToWindow()
            report()
        }

        private func report() {
            guard let window else { return }
            let size = window.bounds.size
            var posture: DuoPosture?
            if partlyOpen && size.height > size.width {
                let barTop = FloatingKeyBarPresenter.laptopKeysTop(in: window)
                    - KeyBar.height(forWidth: size.width)
                posture = .laptop(lowerScreen: max(0, window.bounds.maxY - window.safeAreaInsets.bottom - barTop))
            } else if partlyOpen && size.width > size.height {
                posture = .book(hinge: window.bounds.midX, insets: window.safeAreaInsets)
            }
            guard reported != .some(posture) else { return }
            reported = .some(posture)
            onChange?(posture)
        }
    }
}

