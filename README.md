# ManimStudio — iOS / iPadOS

> **Branch:** `ios` &nbsp;·&nbsp; **App:** [`euleryu.ManimStudio`](https://apps.apple.com/app/id6764472686) (App Store ID `6764472686`) &nbsp;·&nbsp;
> **Version:** 1.5 &nbsp;·&nbsp; **Min iOS:** 17.0 &nbsp;·&nbsp; **Architectures:** `arm64-iphoneos` &nbsp;·&nbsp; **Python:** 3.14
>
> The `main` branch contains the original Windows / Electron desktop app and is **unrelated** — this branch is a from-scratch native port that does not merge back.

A complete offline Python animation studio for iPad and iPhone, built on the
Manim engine. Edit Python in a Monaco editor, render to MP4 via Apple
VideoToolbox hardware encode, drop in LaTeX with busytex — everything happens
on-device without an internet connection.

---

## Quick links

| | |
|---|---|
| 🐍 **Embedded Python stack** | [yu314-coder/python-ios-lib](https://github.com/yu314-coder/python-ios-lib) — manim · numpy · scipy · matplotlib · plotly · PyAV · pycairo · pangocairo · busytex, all `arm64-iphoneos` |
| 📦 **Reference iOS app** | [yu314-coder/CodeBench](https://github.com/yu314-coder/CodeBench) (ships on the App Store as **BenchCode**) — sister iOS Python IDE that pioneered the App Store-compliant layout, the wrap-loose-dylibs pipeline, and the `offlinai_shell` builtin set this app reuses |
| 🐚 **Embedded shell** | `offlinai_shell` from [BenchCode / CodeBench](https://github.com/yu314-coder/CodeBench) (rebranded `ManimStudio shell` at install time) — full POSIX-style builtins (`ls`, `cd`, `cat`, `top`, `find`, `grep`, …) bundled inside python-ios-lib |
| 🔤 **Editor** | [microsoft/monaco-editor](https://github.com/microsoft/monaco-editor) in WKWebView |
| 🖥 **Terminal** | [migueldeicaza/SwiftTerm](https://github.com/migueldeicaza/SwiftTerm) bridged to Python via PTY |
| 🎬 **Manim** | [3b1b/manim](https://github.com/ManimCommunity/manim) (Community edition, patched for iOS Cairo + VideoToolbox encode) |
| 🧮 **LaTeX** | [busytex](https://github.com/jamesgao/busytex) WASM build for Tex / MathTex rendering |

---

## Features

### Editor

- **Monaco** in a WKWebView with full Python autocomplete, find/replace,
  comment toggle, indent/outdent, multi-cursor, snippets — every standard
  shortcut works.
- **Keys over the on-screen keyboard** (`KeyBar.swift`) — on an iPhone,
  or an iPad without a hardware keyboard, a row above the keyboard holds
  indent / outdent, the symbols Python needs (typed through Monaco, so
  brackets close themselves), undo / redo, completion, comment toggling
  and arrows that step through the suggestion list when it's open. A
  WKWebView can't take an input accessory (its first responder is
  WebKit's), so the bar floats in the window, placed from the keyboard
  notifications.
- **Symbol completion** ships pre-built. `scripts/gen-library-symbols.py`
  introspects the bundled packages at *build* time and writes
  `Resources/LibrarySymbols.json`, which Monaco loads directly — no Python
  runs to populate it, so there is no first-launch penalty.
  `LibrarySymbolBuilder` remains only as the on-device fallback.
- **Render error gutter** — when a render fails, `parseTracebackMarkers`
  regexes `File "<string>", line N` out of the captured stderr and pushes
  red markers into Monaco at the offending lines.
- **Pure-Swift formatter** (⌥⌘I) — whitespace cleanup, leading-tab → 4-space
  conversion, blank-line collapse, single-newline EOF. Round-trips on its
  own output.
- **Drag-drop image as `ImageMobject`** — toolbar button copies an image
  into `Documents/Assets/`, inserts a working `ImageMobject(...).scale(2)`
  snippet at the cursor.

### Creating &amp; presenting

- **Gallery** is the cold-launch tab — six ready-made Manim scenes you can
  load onto the workbench, so the app reads as an animation studio rather
  than an editor with a terminal attached.
- **Apple Pencil → Manim** (`PencilKitView.swift`) — sketch on iPad and get
  editable Manim source. A PencilKit drawing is resampled, simplified with
  Ramer–Douglas–Peucker, then classified: least-squares (Kåsa) circle fit,
  edge-based rectangle/square fit, regular-polygon fit, straight line, or a
  smooth `VMobject` through the points. Emits `Circle`, `Square`,
  `Rectangle`, `RegularPolygon`, `Polygon`, `Line` or
  `set_points_smoothly(...)` in ManimStudio's coordinate frame. Entirely
  on-device — no network, no model.
- **Presentation mode** (`PresentationMode.swift`) — full-screen looping
  playback with tap-to-reveal transport, the status bar and home indicator
  hidden. It opens on the latest render, and a **library strip** lists every
  earlier render in `Documents/ToolOutputs/`, so Present works on a cold
  launch too. Each clip is labelled from the file itself — resolution, codec,
  frame rate, duration and data rate, plus a quality badge — because the
  render settings are not stored with the mp4, and the two can disagree.
  Thumbnails decode one at a time (a 14K frame is ~388 MB) into a cache
  capped at 40 (`RenderLibrary.swift`). Reaching a TV is plain **AirPlay /
  HDMI mirroring**: `ExternalDisplayManager` is deliberately **inert** and
  never claims the external scene, because an app that attaches its own
  window to that scene *replaces* the mirror with its own UI.
- **Command palette** (⇧⌘P) — one list over the existing menu
  notifications: render, preview, stop, file ops, sketch, present, tabs.

### Terminal

- **SwiftTerm** xterm-256color emulator backed by a real PTY pair.
- The bundled **`offlinai_shell`** (originally written for
  [CodeBench / BenchCode](https://github.com/yu314-coder/CodeBench),
  rebranded to `ManimStudio shell` at install time via `sed`) provides
  over 100 builtins — `ls`, `cd`, `cat`, `grep`, `python`, `pdflatex`,
  `curl`, `zip`, `tree`, … — and
  [`PythonSupport/manimstudio_shell.py`](ManimStudio/PythonSupport/manimstudio_shell.py)
  fits it to this app before the REPL starts:
  - commands with no backend here — `pip` (no writable site-packages, no
    toolchain for wheels), `ai` (CodeBench's local-LLM runner), the
    C/C++/Fortran compilers, `swift`, `debug-gui` — are removed and answer
    with a one-line reason;
  - `exit` / `quit` no longer end the app; `top`, `htop` and `ps` read
    `sysctl` and Mach task info instead of psutil's private-API module;
  - `curl` streams instead of holding a download in memory, `git` is
    clone-only (the rest needs dulwich), `debug` works with Python 3.14's
    pdb, `md` / `nb` render without linkify, `test-libs` skips what isn't
    shipped, and `$VAR` expands on shell command lines.
- **`js` / `node`** run on JavaScriptCore (`JSEngine.swift`), which answers
  the shell's `js_eval` signal files; **`tex` / `pdftex`** compile plain TeX
  through busytex's `pdftex.fmt`. PDFs from `pdflatex` and HTML from `md` /
  `nb` open in Quick Look.
- **Extra keys** above the on-screen keyboard — esc, sticky ctrl, tab,
  ^C ^D ^L ^U, auto-repeating arrows and shell symbols (`KeyBar.swift`, in
  place of SwiftTerm's generic accessory).
- [`scripts/terminal-selftest.py`](scripts/terminal-selftest.py) runs every
  command once inside the app and writes a JSON report.
- **Magic Keyboard support** — every shortcut you'd want (⌘C / ⌘V / Ctrl-C
  / arrow keys / Tab) is wired through `LineBuffer` to the PTY.
- **Live render output** is teed to both the visible terminal AND
  `Documents/Logs/manim_studio.log`. The `[manim-debug]` filter strips
  internal pipeline traces from the visible terminal but keeps the
  log file unfiltered for diagnosis.

### Render pipeline

- **Hardware encode by default** — VideoToolbox H.264, or HEVC where H.264
  cannot take the size (see
  [High-resolution rendering](#high-resolution-rendering-4k-and-up)). The
  software fallback is `mpeg4`: the bundled ffmpeg has **no libx264, libx265
  or OpenH264**. The Settings sheet's "GPU acceleration" toggle can turn
  hardware encoding off.
- **Encoding controls** (Controls → Encoding, applied to both Preview and
  Render) — Encoder `auto` / `h264` / `hevc` / `mpeg4`, frame-queue depth
  `auto` or 2–32, and the queue's memory budget in MB while depth is `auto`.
  They reach the render as interpreter globals, not environment variables:
  `os.environ` is a snapshot Python takes when it imports `os`, so a
  `setenv` from Swift after boot never arrives.
- **Renders continue in the background** (`BackgroundTaskGuard.swift`). On
  iOS / iPadOS 26 every Render and Preview submits a
  `BGContinuedProcessingTask` (Info.plist permits
  `euleryu.ManimStudio.render.*`; each render registers its own suffix), so
  the process keeps running after the user leaves the app. The system shows
  it as a Live Activity; its Cancel goes through the Stop path. Progress
  comes from `ToolOutputs/_render_progress.json`, which the wrapper rewrites
  as frames are written — scene, animation, frames against the animation's
  length, and a "finishing" phase while the final file is combined — because
  iOS ends a task whose progress stops moving. Frames are rasterized on the
  CPU, so no background-GPU entitlement is involved; whether the hardware
  video encoder keeps running in the background has to be confirmed on a
  device. An encoder that fails now ends the render with its error instead
  of leaving the renderer blocked on the frame queue. Earlier iOS, and the
  Simulator (where `BGTaskScheduler` is unavailable), fall back to the ~30 s
  `beginBackgroundTask` window.
- **Stop stops.** The tap shows "Stopping…" at once. A watchdog armed when
  each scene starts rendering — before `construct()` runs — releases a
  renderer blocked on the frame queue and raises `KeyboardInterrupt` in the
  render thread, which reaches Python anywhere: a dataset download or model
  fit before the first frame, a loop between animations, the final concat.
  The one thing it cannot interrupt is a single long C call (one cairo
  fill, one BLAS op), which has to return first.
- Manim is patched at runtime to:
  - Use Cairo via the `pycairo` compat layer (the `manimpango` C extension
    is partially excluded under ITMS-90338 — Apple flags some of its
    symbols as private API).
  - Register real font files with Pango before any `Text()` runs.
    `NotoSans-Regular.ttf` is the default family, with
    `NotoSansMath-Regular.ttf` and `KaTeX_Main-Regular.ttf` registered as
    fallbacks — neither Noto face is sufficient alone (Sans carries the
    sub/superscript digits, Math the mathematical alphanumerics). CJK faces
    join the fontconfig `<prefer>` chain when bundled.
  - Patch `Scene.play` for per-animation cleanup (frees Mobjects between
    animations to keep iPad memory ceiling under 3 GB).
  - Accept `ImageMobject` inside `VGroup` (manim's strict isinstance check
    breaks otherwise).
- **Background-aware** — `BackgroundTaskGuard` claims a
  `UIApplication.beginBackgroundTask` token so a render survives a brief
  app-switch. It holds the **idle timer** for the duration too, because
  auto-lock was ending long renders outright.
  It does **not** touch `AVAudioSession`: an earlier build activated an
  `.ambient` / `mixWithOthers` session to qualify for the `audio`
  background mode, and **App Review 2.5.4 rejected build 74** for declaring
  that mode without a real audio feature. Both the Info.plist key and the
  activation were removed; the standard `beginBackgroundTask` grace window
  is the correct API for finishing-up work.
- **Output size &amp; format** — presets from 480p to **14K** plus **Custom**
  width × height with 9:16 / 1:1 / 4:5 / 16:9 one-tap presets. Custom has no
  upper bound — a cap that quietly substitutes another size is worse than an
  encoder that refuses — but dimensions are rounded to even, because
  `yuv420p` subsamples chroma 2×2 and an odd width has no valid encoding.
  The wrapper re-derives an aspect-correct frame, so vertical and square
  renders are not stretched.
- **Transparent (alpha) export** — the `mov` format flips manim's
  `config.transparent`, which switches the writer to `.mov` + `qtrle` with a
  real alpha channel. The concat path uses `qtrle`/`argb` for those runs;
  re-encoding them to `h264`/`yuv420p` would silently discard the alpha and
  hand back a black background.
- **Resolution-aware concat codec** — VideoToolbox's H.264 encoder will not
  open above ~4K, and it fails *lazily* at the first frame, long after
  `add_stream()` returned OK, so a `try` around `add_stream` never sees it.
  Past the ceiling the concat uses `hevc_videotoolbox`, and opens the
  encoder eagerly so an unusable codec can still be swapped instead of
  producing an empty file.
- **Render-complete sheet** auto-presents on success: Save to Files /
  Save to Photos / Share. Original lands in `Documents/ToolOutputs/<run>/`
  regardless. Partial movie files are auto-deleted after concat.

### Diagnostics

- **`Documents/Logs/manim_studio.log`** — captures every byte the PTY
  emits, every Swift `NSLog` call, uncaught NSExceptions, and signal-level
  backtraces (SIGSEGV / SIGBUS / SIGILL / SIGABRT / SIGFPE) via an
  async-signal-safe handler that uses only `write(2)` and
  `backtrace_symbols_fd`. Python's `faulthandler.enable` is pointed at the
  same file so C-extension crashes leave a Python traceback before the
  process dies.
- **In-app log viewer** — Settings → Diagnostics → "View log". Tail mode
  polls mtime every 0.8 s and auto-scrolls. Reads only the last 256 KB so
  multi-MB logs never freeze SwiftUI.
- Auto-rotates to `manim_studio.log.1` when the file passes 5 MB.
- **System tab** reads the device, not a table of constants: live memory and
  storage meters, thermal state, Low Power Mode, hardware model identifier,
  the embedded CPython version *derived from the bundle* (`lib-dynload`
  holds `_ssl.cpython-314-…`, so "314" → 3.14), site-package count, sizes of
  everything under `ToolOutputs`, and a one-tap **Copy report** for bug
  reports. The expensive directory walk runs off the main actor.
- **Developer menu** — hidden behind **seven taps on Settings → About →
  Version**, the same gesture Android uses. Carries the build number (which
  appears nowhere else in the UI), a raw dump of every `manim_*` preference,
  and per-bucket storage tools: caches, temporary files, Python bytecode,
  the log file, and rendered outputs. "Free up space" clears the safe
  buckets and never touches renders. **Check network stack** imports `ssl`,
  `certifi` and `requests` inside the embedded Python and fetches
  `https://example.com`, reporting the OpenSSL version (statically linked
  into `_ssl`), whether certifi's CA bundle is present, the
  `REQUESTS_CA_BUNDLE` the app set before Python booted, and a live status
  code. Each piece is easy to verify alone; they fail together.

### Layout

- **iPad** (regular size class): three-pane layout — editor + preview side
  by side on top, terminal below, ControlsSidebar floating right with
  Quick Preview / Final Render quality pickers.
- **iPhone** (compact size class): a native **bottom tab bar** for
  navigation (thumb-reachable, instead of a third stacked top row) and a
  segmented pane picker for Editor / Preview / Terminal. The Workspace opens
  on the **editor**, not the preview. The compact header carries a live
  **RAM sparkline** between the scene picker and Run, and an overflow Menu
  for secondary actions.
- **Magic Keyboard menu bar** (iPad with hardware keyboard): full menu
  hierarchy — File / Code / Render / View / Help — with all 30+
  shortcuts. Implemented via SwiftUI `.commands { ... }` posting
  `NotificationCenter` events that the relevant view observes.

---

## Build prerequisites

1. **Xcode 26+** on macOS (1.5 (22) was built with Xcode 27). Deployment
   target **17.0**; Swift language mode **5** with
   `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` and
   `SWIFT_APPROACHABLE_CONCURRENCY` on — unannotated types are main-actor
   isolated, so anything touching the filesystem off-main is explicitly
   `nonisolated`.
2. **Apple Developer team** (`LYK4LV2859` is hard-coded in `project.pbxproj`
   — change for your own team).
3. **`_vendor/python-ios-lib/`** and **`_vendor/beeware/Python.xcframework/`**
   trees as siblings of the project root. Both are large (~1.5 GB total)
   and **not vendored** into this branch — clone them from upstream:
   ```sh
   mkdir -p _vendor && cd _vendor
   git clone https://github.com/yu314-coder/python-ios-lib.git
   # Python.xcframework comes from BeeWare:
   #   https://briefcase.readthedocs.io/en/stable/reference/platforms/iOS.html
   # or pull from the python-ios-lib release artifacts
   ```
4. **busytex web build** (~237 MB, optional — only needed for LaTeX
   rendering). Drop the unpacked bundle at
   `ManimStudio/ManimStudio/Resources/Busytex/`, keeping the tracked
   `busytex_pipeline.js` (it adds the plain-TeX driver).
5. SwiftPM resolves [SwiftTerm](https://github.com/migueldeicaza/SwiftTerm)
   and [Manim SPM stubs from python-ios-lib](https://github.com/yu314-coder/python-ios-lib)
   automatically on first build.
6. **Metal Toolchain.** Xcode 27 treats it as a separate download, and
   SwiftTerm 1.13 ships a `Shaders.metal` that fails without it ("missing
   Metal Toolchain"). Install it with
   `xcodebuild -downloadComponent MetalToolchain`, or skip that one file by
   adding `'EXCLUDED_SOURCE_FILE_NAMES=$(inherited) Shaders.metal'` to the
   `xcodebuild` command. Skipping it is safe here: SwiftTerm's Metal
   renderer is off by default and ManimStudio never turns it on.

```sh
xcodebuild -project ManimStudio/ManimStudio.xcodeproj \
           -scheme ManimStudio -configuration Release \
           -archivePath build/ManimStudio.xcarchive archive
```

---

## Repository layout

```
ManimStudio/                         ← Xcode project root
├── ManimStudio.xcodeproj/
└── ManimStudio/
    ├── ManimStudioApp.swift         · @main, kicks off Python boot
    ├── ContentView.swift            · tab shell, render dispatch, save sheet
    ├── HeaderView.swift             · iPad / iPhone responsive header
    ├── WorkspaceView.swift          · iPad split + iPhone segmented panes
    ├── EditorPane.swift             · Monaco toolbar (Open / Insert image)
    ├── MonacoEditor.swift           · SwiftUI wrapper for the WKWebView
    ├── MonacoEditorView.swift       · UIView with WKWebView + Swift↔JS IPC
    ├── Resources/editor.html        · Monaco entry point
    ├── PreviewPane.swift            · AVPlayer for the rendered MP4
    ├── TerminalPane.swift           · SwiftUI host for SwiftTerm
    ├── TerminalPaneViewController.swift
    ├── KeyBar.swift                 · extra keys over the on-screen keyboard
    ├── PTYBridge.swift              · PTY pipes, line filter, Magic Keyboard observer
    ├── PythonRuntime.swift          · Py_Initialize, GIL, redirect, render wrapper
    ├── PackagesView.swift           · importlib.metadata browser
    ├── PackageInspector.swift       · background introspection driver
    ├── LibrarySymbolBuilder.swift   · caches Monaco completion index
    ├── AssetsView.swift             · Documents/Assets file browser
    ├── HistoryView.swift            · Documents/ToolOutputs scanner
    ├── SystemView.swift             · live device diagnostics + copy report
    ├── DeveloperMenu.swift          · hidden dev menu (7-tap), storage, network
    ├── GalleryView.swift            · cold-launch scene gallery
    ├── PencilKitView.swift          · Apple Pencil sketch → Manim source
    ├── PresentationMode.swift       · full-screen playback + library strip
    ├── RenderLibrary.swift          · past renders, thumbnails, media info
    ├── ExternalDisplayManager.swift · inert by design; keeps mirroring
    ├── CommandPalette.swift         · ⇧⌘P palette over menu notifications
    ├── RenderResolution.swift       · quality ladder, pixel sizes, migrations
    ├── VideoEncoderProbe.swift      · native VideoToolbox capability probe
    ├── RAMMonitorView.swift         · iPad RAM HUD + iPhone sparkline
    ├── SceneDetector.swift          · finds Scene subclasses in source
    ├── Theme.swift                  · accent + glass-card design tokens
    ├── AppTab.swift                 · top-level tab enum
    ├── TabBarView.swift             · iPad pill strip / iPhone bottom bar
    ├── Haptics.swift                · selection / impact / notify wrappers
    ├── ControlsSidebar.swift        · quality / fps / format pickers
    ├── BackgroundTaskGuard.swift    · background task + idle-timer hold
    ├── CrashLogger.swift            · signal handlers + persistent log file
    ├── LogViewerView.swift          · in-app tailing log viewer
    ├── MenuCommands.swift           · iPad menu bar (.commands) wiring
    ├── PythonFormatter.swift        · pure-Swift Python whitespace cleanup
    ├── BusytexEngine.swift          · LaTeX → SVG via busytex.wasm
    ├── JSEngine.swift               · JavaScriptCore for the terminal's js / node
    ├── PrivacyInfo.xcprivacy        · required-reason API manifest
    └── Info.plist                   · capabilities + usage descriptions
PythonSupport/
└── manimstudio_shell.py             · fits the bundled shell to this app
scripts/
├── fix-macho-type.py                · MH_BUNDLE → MH_DYLIB on framework binaries
├── gen-bundled-packages.py          · regenerates BundledPackages.swift
├── gen-library-symbols.py           · bakes Resources/LibrarySymbols.json
├── inject-swift-support-archive.sh  · scheme post-action: dSYMs + SwiftSupport
├── inject-swift-support.sh          · same fix for an exported IPA (by hand)
├── install-python-stdlib.sh         · main build phase (stdlib + framework wrapping)
├── normalize-fwork-postembed.sh     · post-Embed-Frameworks .fwork normalizer
├── patch-cython-lapack.py           · rebinds cython_lapack to a stub dylib (by hand)
└── terminal-selftest.py             · runs every terminal command in the app
_appstore_screens/                   · 6× iPad screenshots, 2752×2064 / 2064×2752
_appstore_screens_iphone/            · 4× iPhone screenshots, 1284×2778
```

---

## Build phases (in execution order)

The Xcode target runs **seven** phases per build. Order matters — Embed
Frameworks must run before .fwork normalization, and wrap-loose-dylibs
only runs for archive builds.

1. **Sources** — Swift compilation to `arm64-iphoneos`.
2. **Frameworks** — links Python.xcframework + Accelerate.
3. **Resources** — copies app assets, Info.plist, PrivacyInfo.xcprivacy.
4. **Install Python stdlib** ([`scripts/install-python-stdlib.sh`](scripts/install-python-stdlib.sh)):
   - Copies BeeWare stdlib + lib-dynload into `<App>.app/python-stdlib/`.
   - Bundles ffmpeg dylibs and rewrites `/tmp/ffmpeg-ios/...` install names
     to `@rpath/...`.
   - Consolidates SwiftPM `python-ios-lib_*.bundle/` directories into
     `app_packages/site-packages/` so wrap-loose-dylibs.sh and BeeWare's
     import hook see the layout they expect.
   - Copies the pure-Python packages python-ios-lib's SwiftPM products do
     not expose, from a hand-maintained list: fontTools, the `requests`
     stack (urllib3, certifi, idna, charset_normalizer), PyYAML, jsonschema,
     and `joblib` + `threadpoolctl`, which scikit-learn imports unguarded —
     without those two, `import sklearn` fails outright.
   - **Builds `libscipy_blas_stubs.framework`** — a 10-line C stub
     providing `dcabs1_` and `lsame_`, two BLAS reference helpers iOS
     Accelerate doesn't export. Without them
     `scipy.linalg.cython_blas.so` fails to flat-namespace-resolve at
     dlopen time.
   - **Bundles `libfortran_io_stubs.framework`** (the prebuilt LLVM
     Flang Fortran I/O runtime stubs from
     [python-ios-lib/fortran/](https://github.com/yu314-coder/python-ios-lib/tree/main/fortran))
     so scipy arpack/propack can resolve `__FortranA*` symbols.
   - **Archive builds only:** makes every copied package writable, then runs
     [`fix-macho-type.py`](scripts/fix-macho-type.py) to flip framework
     executables from `MH_BUNDLE` to `MH_DYLIB`. Apple rejects a bundle-typed
     framework binary (ITMS-90124), and files copied out of SwiftPM's
     read-only checkout kept their permissions, so without the `chmod` the
     flip failed silently — which is what got 1.5 (8) and (9) rejected.
5. **Wrap loose dylibs (App Store)** — *archive only*. Runs upstream's
   [`wrap-loose-dylibs.sh`](https://github.com/yu314-coder/python-ios-lib/blob/main/scripts/appstore/wrap-loose-dylibs.sh)
   from python-ios-lib to convert every loose `.so` and `.dylib` into a
   `.framework` directory matching App Store bundle requirements.
6. **Embed Frameworks** — Python.xcframework + every wrapped framework.
7. **Normalize Python .fwork (post-embed)** ([`scripts/normalize-fwork-postembed.sh`](scripts/normalize-fwork-postembed.sh)):
   - Strips `@executable_path/` prefixes from every `.fwork` text file.
     dyld treats this prefix as a literal directory in `dlopen` paths,
     so unfixed it produces
     `<App>.app/@executable_path/Frameworks/_struct.framework/_struct → no such file`.
   - Tears out residual `python-ios-lib_*.bundle/` directories that
     Xcode's resource-copy pass repopulates after our Step 9 deletes
     them — prevents shipping both the consolidated `app_packages/`
     layout AND the unsigned-original SwiftPM-bundle layout side by side.

---

## Runtime startup

`ManimStudioApp.init` kicks off two tasks on `DispatchQueue.main.async`:

### 1. PTY + Python boot (background queue inside `PythonRuntime`)

```
CrashLogger.install()                ← signal handlers, log file open
                ↓
migrateRetiredSelection()            ← RenderResolution: a stored 16K
                                       choice becomes 14K
                ↓
PTYBridge.shared.setupIfNeeded()     ← pipe(2), dup2 onto stdin/out/err
                ↓
preloadScipySupportFrameworks()      ← dlopen libscipy_blas_stubs +
                                       libfortran_io_stubs with
                                       RTLD_GLOBAL so their symbols
                                       enter the flat namespace BEFORE
                                       any scipy import runs
                ↓
Py_Initialize()                      ← embedded interpreter starts
                ↓
sys.stdout/stderr ← io.TextIOWrapper(io.FileIO(fd), write_through=True)
                                       (unbuffered — shell prompts
                                       without trailing \n flush
                                       immediately)
                ↓
python_ios_lib_import_hook.install() ← routes wrapped-framework module
                                       imports to
                                       <App>.app/Frameworks/site-packages.X.framework/X
                ↓
faulthandler.enable(file=manim_studio.log, all_threads=True)
                ↓
HOME = Documents/, chdir Documents/Workspace/
                ↓
sed-rebrand monkeypatch + manimstudio_shell.install(offlinai_shell)
                ↓
offlinai_shell.repl() on a daemon thread → PS1 prompt
```

### 2. LaTeX preload (main queue, deferred)

`BusytexEngine.shared.preload()` + `LaTeXEngine.shared.initialize()` on
a small delay so they don't fight Python boot for CPU on the first
~3 seconds.

---

## Render dispatch

User taps **Render** or **Preview** (header) → `ContentView.triggerRender(quick:)`:

1. `BackgroundTaskGuard.shared.begin()` — extends app lifetime and holds the
   idle timer so auto-lock cannot end the render mid-encode.
2. **Preview** reads the Quick Preview pickers (`manim_preview_quality` /
   `_fps`, default 480p at 15 fps); **Render** reads the Final ones
   (`manim_final_*`, default 1080p at 30 fps). The labels are converted to a
   preset index at render time, so the choice applies whichever settings
   surface is on screen.
3. `PythonRuntime.execute(code:targetScene:onOutput:)` runs the wrapper
   script in `<offlinai-python-tool>`. The wrapper exec's user code,
   discovers Scene subclasses, calls each one in source order, and writes
   the final MP4 path to a Python global the Swift side reads back.
4. Stdout/stderr stream through the PTY → SwiftTerm + log file. The
   `[manim-debug]` line filter strips internal pipeline traces from the
   visible terminal but keeps the log file unfiltered.
5. **On success:**
   - `cleanupPartials()` removes the `partial_movie_files/` subtree
     (~500 MB on a 30-animation 1080p run).
   - `RenderCompleteSheet` auto-presents: Save to Files / Save to Photos /
     Share via UIActivityViewController.
   - File appears in `HistoryView`'s scan of `Documents/ToolOutputs/`.
6. **On failure:**
   - `parseTracebackMarkers` regexes `File "<string>", line N` out of
     stderr.
   - `editorSetMarkers` notification posts; `EditorPane` forwards to
     `MonacoController.setMarkers([…])` which calls
     `monaco.editor.setModelMarkers` via the JS bridge.
   - Red markers appear on the offending source lines.

---

## High-resolution rendering (4K and up)

8K renders. Getting there needed three separate things, and the first one
masqueraded as the other two for a long time.

### The encoder ceiling is a property of the chip

`h264_videotoolbox` is not a software codec with a slow path — ffmpeg's
wrapper only ever binds Apple's *hardware* H.264 encoder. Above the size that
encoder supports, `avcodec_open2` fails outright. Measured directly with
VideoToolbox:

| Device | H.264 hardware | HEVC hardware |
|---|---|---|
| M4 Mac mini / M3 iPad Air | up to **4096×2304** | up to **8192×4320** |
| iPhone 17 Pro Max | reported working at 8K | 8K |

Because the ceiling moves between devices it is **asked for at run time**, not
written down. [`manim/utils/ios_encoder.py`](https://github.com/yu314-coder/python-ios-lib)
creates a throwaway compression session and reads
`UsingHardwareAcceleratedVideoEncoder`, which the session refuses to report
when no hardware encoder took the job. Anything H.264 cannot take goes to
`hevc_videotoolbox`; if neither has a hardware path, the caller's `mpeg4`
fallback finishes the job slowly.

This failure was hard to read because **`avcodec_open2` is lazy**: it runs at
the first *encode*, long after `add_stream()` returned OK, so the fallback
guarding `add_stream` never saw it. Every partial file encoded zero frames and
the run ended in a `FileNotFoundError` for `partial_movie_file_list.txt` —
which looks like a missing-file bug, not an encoder one.

### HEVC in an mp4 must be tagged `hvc1`

ffmpeg defaults to `hev1`, which is legal and which AVFoundation reports as
neither playable nor decodable: the render finishes, reports success, and
leaves a file **the device that made it cannot open**. Both encode paths tag
it, and so does the app's concat — including its stream-copy branch, since
`add_stream_from_template` carries the codec but *not* the tag.

### The frame queue is bounded by bytes, not frames

The encoder hand-off queue was capped at 32 *frames*, chosen when a frame was
1080p and 8 MB (~256 MB). The same 32 frames at 8K is 132 MB each — 4.25 GB of
RGBA buffers, well past what any iPad gives one app. The cap that existed to
prevent a jetsam kill was causing one. The byte budget is what is fixed now,
so the depth follows the resolution: **1080p queues 32, 4K queues 8, 8K
queues 2** — never fewer, or the renderer and encoder stop overlapping.
**Controls → Encoding → Queue depth** can force a depth from 2 to 32
instead. The figure shown for a forced depth is the queue's *capacity* —
what it could hold — not what it is holding; the RAM HUD shows that.

### No pre-flight memory gate

An earlier build estimated peak footprint before a render and offered a lower
quality when it looked too large. That estimate modelled the encoder queue as
32 full-resolution frames — correct when written, wrong once the queue became
byte-bounded, and it over-predicted by roughly 4x. **8K at 120 fps measures
under 2 GB on an iPad Air M3.** A pre-flight that refuses work the device can
actually do is worse than none, so it was removed; the memory watchdog in the
render path is the real safety net.

### Choosing the encoder

**Controls → Encoding → Encoder** offers `auto` / `h264` / `hevc` / `mpeg4`
and applies to Preview as well as Render. Auto follows the probe. A forced choice is still checked against the hardware and
falls back rather than handing back an encoder that cannot open — returning
one that fails is the bug the probe exists to prevent. The note under the
picker calls VideoToolbox natively (`VideoEncoderProbe.swift`) for the
resolution currently selected, so it reports what *this* device can do without
starting Python.

### Above 8K: 12K and 14K

12K (11520×6480) and 14K (13440×7560) are 3× and 3.5× the 4K frame, so they
stay exactly 16:9 and even on both axes. manim has no preset above 4K, so
everything from 8K up sets the pixel size directly, from a table in the
render wrapper that mirrors `RenderResolution` on the Swift side.

MP4 at those sizes has one hard constraint: the `mpeg4` software fallback
stores frame dimensions in 13 bits and refuses anything past **8191 px** a
side ("dimensions too large for MPEG-4" — 8191 encodes, 8192 does not). The
transparent `.mov` path uses `qtrle`, which has no such limit.

**16K** (15360×8640) was offered briefly and removed in 1.5 (20): it could
not complete a render on device. A device that still had it selected is
moved to 14K at launch, rather than left with an empty picker and a silent
1080p fallback.

---

## Known limitations

### Not verified on device

Apple Pencil sketch and transparent export are compile-verified and
inspected but have not been exercised on hardware.

### The Simulator runs the UI, not renders

The app launches in the iOS Simulator. It used to crash there about four
seconds in — an `NSLog("%s")` handed a Swift `String` on the stub-framework
failure path, which only the Simulator takes — fixed in 1.5 (20). Screens
and layout can be checked there, but nothing renders: python-ios-lib ships
no simulator builds of numpy, scipy, cairo, Pillow, manimpango or PyAV, and
the prebuilt Fortran stubs are device-only. Rendering needs a device. (A
development build also launches on an Apple-silicon Mac as a
Designed-for-iPad app; rendering there has not been verified.)

### Terminal downloads

Through 1.5 (20) the bundled shell's `curl` read the whole response into
memory when it wasn't given `-o`, then converted all of it to text to print
the first 4 KB — about 4.4× the download's size at peak, enough to get the
app killed on a large file. From 1.5 (21) `manimstudio_shell` replaces that
transport: without `-o` it reads only what it shows, and `wget` and
`curl -L -o <file> <url>` stream to disk as before.

---

## App Store submission status

| Item | Status |
|------|--------|
| Bundle ID | `euleryu.ManimStudio` |
| Apple ID | `6764472686` |
| Privacy Policy URL | https://yu314-coder.github.io/privacy.html#manim-studio-ios |
| Privacy nutrition label | **Data Not Collected** |
| Categories | Graphics & Design (primary) / Education (secondary) |
| iPad screenshots | 6 × `2752×2064` / `2064×2752` (in [`_appstore_screens/`](_appstore_screens/)) |
| iPhone screenshots | 4 × `1284×2778` (in [`_appstore_screens_iphone/`](_appstore_screens_iphone/)) |
| App Accessibility | Dark Interface · Differentiate Without Color Alone |
| Support URL | https://github.com/yu314-coder/python-ios-lib |
| Marketing URL | https://yu314-coder.github.io/ |
| On the App Store | **1.4** (build 8) |
| Latest TestFlight | **1.5** (build 22) |
| Build numbers | The project stays at build 1; each upload's build number is set in the archive |

---

## Acknowledgments

- **[python-ios-lib](https://github.com/yu314-coder/python-ios-lib)** — the entire embedded Python stack
  (manim, numpy, scipy, matplotlib, plotly, PyAV, pycairo, busytex, ffmpeg)
  is built and signed by that repo's pipelines. The build phases here
  consume its SwiftPM products + `wrap-loose-dylibs.sh` script.
- **[CodeBench](https://github.com/yu314-coder/CodeBench)** (App Store: **BenchCode**) — sister iOS Python IDE
  that pioneered the App Store-compliant layout (the consolidated
  `app_packages/` tree, the `.so → .framework` wrap pattern, the
  `offlinai_shell` builtin set used here for ManimStudio's terminal).
  This app's build pipeline closely follows CodeBench's known-working
  order, and the terminal experience is essentially BenchCode's shell
  hosted inside ManimStudio's render-focused UI.
- **[BeeWare](https://beeware.org/)** — Python.xcframework embedding shape and stdlib loader.
- **[Manim Community](https://www.manim.community/)** — the engine itself.
- **[SwiftTerm](https://github.com/migueldeicaza/SwiftTerm)** — terminal emulator.
- **[Monaco Editor](https://github.com/microsoft/monaco-editor)** — the code editor.
- **[busytex](https://github.com/jamesgao/busytex)** — WASM LaTeX.

---

## Branch convention

- `main` = original Windows / Electron desktop app. **Do not merge** —
  the architectures don't overlap.
- `ios` = this branch. Tag releases as `ios/v1.0`, `ios/v1.1`, etc. when
  shipping to the App Store.
