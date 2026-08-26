# ManimStudio — iOS / iPadOS

> **Branch:** `ios` &nbsp;·&nbsp; **App:** [`euleryu.ManimStudio`](https://apps.apple.com/app/id6764472686) (App Store ID `6764472686`) &nbsp;·&nbsp;
> **Version:** 1.4 &nbsp;·&nbsp; **Min iOS:** 17.0 &nbsp;·&nbsp; **Architectures:** `arm64-iphoneos` &nbsp;·&nbsp; **Python:** 3.14
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
| 🎬 **Manim** | [3b1b/manim](https://github.com/ManimCommunity/manim) (Community edition, patched for iOS Cairo + h264_videotoolbox) |
| 🧮 **LaTeX** | [busytex](https://github.com/jamesgao/busytex) WASM build for Tex / MathTex rendering |

---

## Features

### Editor

- **Monaco** in a WKWebView with full Python autocomplete, find/replace,
  comment toggle, indent/outdent, multi-cursor, snippets — every standard
  shortcut works.
- **Symbol completion** ships pre-built. `scripts/gen-library-symbols.py`
  introspects the bundled packages at *build* time and writes
  `Resources/LibrarySymbols.json`, which Monaco loads directly — no Python
  runs to populate it, so there is no first-launch penalty.
  `LibrarySymbolBuilder` remains only as the on-device fallback.
- **Render error gutter** — when a render fails, `parseTracebackMarkers`
  regexes `File "<string>", line N` out of the captured stderr and pushes
  red markers into Monaco at the offending lines.
- **Pure-Swift formatter** (⌥⌘L) — whitespace cleanup, leading-tab → 4-space
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
  playback of the latest render with tap-to-reveal transport, the status bar
  and home indicator hidden. Reaching a TV is plain **AirPlay / HDMI
  mirroring**: `ExternalDisplayManager` is deliberately **inert** and never
  claims the external scene, because an app that attaches its own window to
  that scene *replaces* the mirror with its own UI.
- **Command palette** (⇧⌘P) — one list over the existing menu
  notifications: render, preview, stop, file ops, sketch, present, tabs.

### Terminal

- **SwiftTerm** xterm-256color emulator backed by a real PTY pair.
- The bundled **`offlinai_shell`** (originally written for
  [CodeBench / BenchCode](https://github.com/yu314-coder/CodeBench),
  rebranded to `ManimStudio shell` at install time via `sed`) provides
  ~150 builtins — `ls`, `cd`, `cat`, `top`, `find`, `grep`, `clear`,
  `python`, `tree`, etc. `pip` is intentionally hidden: iOS sandboxes
  have no writable site-packages, and most wheels need a toolchain iOS
  forbids.
- **Custom `top`** built on `sysctlbyname` (kern.boottime, hw.memsize,
  hw.ncpu, hw.machine) + `resource.getrusage` so process / system stats
  work without psutil's private-API native module.
- **Magic Keyboard support** — every shortcut you'd want (⌘C / ⌘V / Ctrl-C
  / arrow keys / Tab) is wired through `LineBuffer` to the PTY.
- **Live render output** is teed to both the visible terminal AND
  `Documents/Logs/manim_studio.log`. The `[manim-debug]` filter strips
  internal pipeline traces from the visible terminal but keeps the
  log file unfiltered for diagnosis.

### Render pipeline

- **VideoToolbox H.264** hardware encoder by default (~5× faster than
  software libx264 on iPad Pro M4). Toggleable from the Settings sheet.
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
- **Output size &amp; format** — 480p → 8K presets plus **Custom** width ×
  height with 9:16 / 1:1 / 4:5 / 16:9 one-tap presets. The wrapper rounds to
  even dimensions for H.264 and re-derives an aspect-correct frame, so
  vertical and square renders are not stretched.
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
- **Pre-render memory guard** (`RenderMemoryGuard.swift`) — peak footprint is
  estimated as a baseline plus **34 live full-resolution frames** (the
  encoder hand-off queue in `scene_file_writer.py` is capped at 32 *frames*,
  not bytes) and checked against 55% of physical RAM. Over budget, the app
  offers the highest quality that fits.
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
  buckets and never touches renders.

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

1. **Xcode 26+** on macOS. Deployment target **17.0**; Swift language
   mode **5** with `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` and
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
   `ManimStudio/ManimStudio/Resources/Busytex/`.
5. SwiftPM resolves [SwiftTerm](https://github.com/migueldeicaza/SwiftTerm)
   and [Manim SPM stubs from python-ios-lib](https://github.com/yu314-coder/python-ios-lib)
   automatically on first build.

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
    ├── PTYBridge.swift              · PTY pipes, line filter, Magic Keyboard observer
    ├── PythonRuntime.swift          · Py_Initialize, GIL, redirect, render wrapper
    ├── PackagesView.swift           · importlib.metadata browser
    ├── PackageInspector.swift       · background introspection driver
    ├── LibrarySymbolBuilder.swift   · caches Monaco completion index
    ├── AssetsView.swift             · Documents/Assets file browser
    ├── HistoryView.swift            · Documents/ToolOutputs scanner
    ├── SystemView.swift             · live device diagnostics + copy report
    ├── DeveloperMenu.swift          · hidden dev menu (7-tap) + storage tools
    ├── GalleryView.swift            · cold-launch scene gallery
    ├── PencilKitView.swift          · Apple Pencil sketch → Manim source
    ├── PresentationMode.swift       · full-screen looping playback
    ├── ExternalDisplayManager.swift · inert by design; keeps mirroring
    ├── CommandPalette.swift         · ⇧⌘P palette over menu notifications
    ├── RenderMemoryGuard.swift      · pre-render peak-footprint estimate
    ├── RAMMonitorView.swift         · iPad RAM HUD + iPhone sparkline
    ├── SceneDetector.swift          · finds Scene subclasses in source
    ├── Theme.swift                  · accent + glass-card design tokens
    ├── AppTab.swift                 · top-level tab enum
    ├── TabBarView.swift             · iPad pill strip / iPhone bottom bar
    ├── Haptics.swift                · selection / impact / notify wrappers
    ├── ControlsSidebar.swift        · quality / fps / format pickers
    ├── BackgroundTaskGuard.swift    · UIBackgroundTask + AVAudioSession glue
    ├── CrashLogger.swift            · signal handlers + persistent log file
    ├── LogViewerView.swift          · in-app tailing log viewer
    ├── MenuCommands.swift           · iPad menu bar (.commands) wiring
    ├── PythonFormatter.swift        · pure-Swift Python whitespace cleanup
    ├── BusytexEngine.swift          · LaTeX → SVG via busytex.wasm
    ├── PrivacyInfo.xcprivacy        · required-reason API manifest
    └── Info.plist                   · capabilities + usage descriptions
scripts/
├── gen-library-symbols.py           · bakes Resources/LibrarySymbols.json
├── install-python-stdlib.sh         · main build phase (stdlib + framework wrapping)
└── normalize-fwork-postembed.sh     · post-Embed-Frameworks .fwork normalizer
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
   - **Builds `libscipy_blas_stubs.framework`** — a 10-line C stub
     providing `dcabs1_` and `lsame_`, two BLAS reference helpers iOS
     Accelerate doesn't export. Without them
     `scipy.linalg.cython_blas.so` fails to flat-namespace-resolve at
     dlopen time.
   - **Bundles `libfortran_io_stubs.framework`** (the prebuilt LLVM
     Flang Fortran I/O runtime stubs from
     [python-ios-lib/fortran/](https://github.com/yu314-coder/python-ios-lib/tree/main/fortran))
     so scipy arpack/propack can resolve `__FortranA*` symbols.
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
sed-rebrand monkeypatch + pip removal + custom top builtin
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

1. **Memory pre-flight** (`RenderMemoryGuard`) — estimates peak footprint
   for the chosen resolution and, if it will not fit, offers a quality that
   does rather than letting jetsam kill the render at 90%. Advisory:
   "Render anyway" is always available.
2. `BackgroundTaskGuard.shared.begin()` — extends app lifetime and holds the
   idle timer so auto-lock cannot end the render mid-encode.
3. **Preview** always uses `low_quality / 15 fps`. **Render** reads the
   user's Final settings from `@AppStorage("manim_final_*")` keys.
4. `PythonRuntime.execute(code:targetScene:onOutput:)` runs the wrapper
   script in `<offlinai-python-tool>`. The wrapper exec's user code,
   discovers Scene subclasses, calls each one in source order, and writes
   the final MP4 path to a Python global the Swift side reads back.
5. Stdout/stderr stream through the PTY → SwiftTerm + log file. The
   `[manim-debug]` line filter strips internal pipeline traces from the
   visible terminal but keeps the log file unfiltered.
6. **On success:**
   - `cleanupPartials()` removes the `partial_movie_files/` subtree
     (~500 MB on a 30-animation 1080p run).
   - `RenderCompleteSheet` auto-presents: Save to Files / Save to Photos /
     Share via UIActivityViewController.
   - File appears in `HistoryView`'s scan of `Documents/ToolOutputs/`.
7. **On failure:**
   - `parseTracebackMarkers` regexes `File "<string>", line N` out of
     stderr.
   - `editorSetMarkers` notification posts; `EditorPane` forwards to
     `MonacoController.setMarkers([…])` which calls
     `monaco.editor.setModelMarkers` via the JS bridge.
   - Red markers appear on the offending source lines.

---

## Known limitations

### 8K does not currently render

The quality picker offers 8K and the config path is correct — index 5 sets
`pixel_width = 7680, pixel_height = 4320` and nothing clamps it. The render
still fails, in the **encoder**:

```
[manim-debug]   stream added OK (h264_videotoolbox)
[manim-debug] ! encode CRASH on batch #1: ExternalError:
    avcodec_open2("h264_videotoolbox", …)
```

VideoToolbox's H.264 encoder will not open at 7680×4320. Two details make it
present confusingly:

- `avcodec_open2` is **lazy**. `add_stream()` succeeds because the codec
  *exists*; the encoder only opens on the first frame. In
  `scene_file_writer.py` the `stream.width/height` assignments sit *after*
  the `try/except` that falls back to `mpeg4`, so the fallback never fires.
- Every partial file therefore encodes zero frames, `partial_movie_file_list.txt`
  is never written, and the run ends in a `FileNotFoundError` that looks like
  a missing-file bug rather than an encoder one.

This is **not** a memory problem — the render dies in seconds with the memory
system holding fine. The fix belongs in
[python-ios-lib](https://github.com/yu314-coder/python-ios-lib)'s per-segment
encoder: select `hevc_videotoolbox` (already in the bundled ffmpeg, and able
to do 8K on Apple silicon) above the H.264 ceiling, and open the codec
eagerly so the existing fallback can act. This app's **concat** stage already
does exactly that; the per-segment writer does not.

A second, latent issue sits behind it: that writer's encoder queue is
`Queue(maxsize=32)` — a bound on *frames*, not bytes. Its own comment budgets
≈256 MB, which holds at 1080p (32 × 7.9 MB) but is ≈4 GB at 8K (126 MB a
frame). It has never bitten because the encoder fails first.

### Not verified on device

Apple Pencil sketch, Presentation mode and transparent export are
compile-verified and inspected but have not been exercised on hardware. The
app **cannot run in the Simulator** — `preloadScipySupportFrameworks` dlopens
device-only frameworks and SIGSEGVs at launch — so the Simulator can build
this project but never run it. TestFlight on a real device is the only
runtime test path.

---

## App Store submission status

| Item | Status |
|------|--------|
| Bundle ID | `euleryu.ManimStudio` |
| Apple ID | `6764472686` |
| Privacy Policy URL | https://yu314-coder.github.io/privacy.html#manim-studio-ios |
| Privacy nutrition label | **Data Not Collected** |
| Categories | Developer Tools (primary) / Education (secondary) |
| iPad screenshots | 6 × `2752×2064` / `2064×2752` (in [`_appstore_screens/`](_appstore_screens/)) |
| iPhone screenshots | 4 × `1284×2778` (in [`_appstore_screens_iphone/`](_appstore_screens_iphone/)) |
| App Accessibility | Dark Interface · Differentiate Without Color Alone |
| Support URL | https://github.com/yu314-coder/python-ios-lib |
| Marketing URL | https://yu314-coder.github.io/ |
| Shipping version | **1.4** (build 8) |

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
