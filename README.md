# ManimStudio — iOS / iPadOS

> **Branch:** `ios` &nbsp;·&nbsp; **App:** [`euleryu.ManimStudio`](https://apps.apple.com/app/id6764472686) (App Store ID `6764472686`) &nbsp;·&nbsp;
> **Min iOS:** 17.0 &nbsp;·&nbsp; **Architectures:** `arm64-iphoneos` &nbsp;·&nbsp; **Python:** 3.14
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
| 📦 **Reference desktop app** | [yu314-coder/CodeBench (offlinai)](https://github.com/yu314-coder/CodeBench) — sister iOS Python IDE that pioneered the App Store layout this app follows |
| 🐚 **Embedded shell** | `offlinai_shell` (rebranded `ManimStudio shell`) — bundled inside python-ios-lib |
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
- **Symbol completion** is built from live introspection of the bundled
  Python packages. `LibrarySymbolBuilder` runs once per build, caches the
  resulting JSON to `Caches/manim_studio_symindex_v<build>.json`, and feeds
  it into Monaco. First launch of a new build pays the ~10 s cost; every
  subsequent launch reads the cache in milliseconds.
- **Render error gutter** — when a render fails, `parseTracebackMarkers`
  regexes `File "<string>", line N` out of the captured stderr and pushes
  red markers into Monaco at the offending lines.
- **Pure-Swift formatter** (⌥⌘L) — whitespace cleanup, leading-tab → 4-space
  conversion, blank-line collapse, single-newline EOF. Round-trips on its
  own output.
- **Drag-drop image as `ImageMobject`** — toolbar button copies an image
  into `Documents/Assets/`, inserts a working `ImageMobject(...).scale(2)`
  snippet at the cursor.

### Terminal

- **SwiftTerm** xterm-256color emulator backed by a real PTY pair.
- The bundled **`offlinai_shell`** (rebranded `ManimStudio shell` at install
  time via `sed`) provides ~150 builtins — `ls`, `cd`, `cat`, `top`, `find`,
  `grep`, `clear`, `python`, `tree`, etc. `pip` is intentionally hidden:
  iOS sandboxes have no writable site-packages, and most wheels need a
  toolchain iOS forbids.
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
  - Substitute a CJK-aware `Text()` factory that pre-registers
    `KaTeX_Main-Regular.ttf` (latin) + `NotoSansJP-Regular.otf` (CJK)
    so non-ASCII characters render without `Could not find font` errors.
  - Patch `Scene.play` for per-animation cleanup (frees Mobjects between
    animations to keep iPad memory ceiling under 3 GB).
  - Accept `ImageMobject` inside `VGroup` (manim's strict isinstance check
    breaks otherwise).
- **Background-aware** — `BackgroundTaskGuard` claims a
  `UIApplication.beginBackgroundTask` token AND activates an `.ambient`
  `mixWithOthers` `AVAudioSession` so the render keeps running through
  screen lock or app-switching.
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

### Layout

- **iPad** (regular size class): three-pane layout — editor + preview side
  by side on top, terminal below, ControlsSidebar floating right with
  Quick Preview / Final Render quality pickers.
- **iPhone** (compact size class): segmented pane picker (Editor / Preview
  / Terminal — one fills the screen at a time) + a sheet-presented
  ControlsSidebar. Header collapses to a compact row with an overflow
  Menu for secondary actions.
- **Magic Keyboard menu bar** (iPad with hardware keyboard): full menu
  hierarchy — File / Code / Render / View / Help — with all 30+
  shortcuts. Implemented via SwiftUI `.commands { ... }` posting
  `NotificationCenter` events that the relevant view observes.

---

## Build prerequisites

1. **Xcode 26+** on macOS (deployment target 17.0, Swift 6 toolchain).
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
    ├── SystemView.swift             · device + library facts
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

1. `BackgroundTaskGuard.shared.begin()` — extends app lifetime + activates
   an `.ambient` `mixWithOthers` AVAudioSession so the render survives
   screen lock and app switching.
2. **Preview** always uses `low_quality / 15 fps`. **Render** reads the
   user's Final settings from `@AppStorage("manim_final_*")` keys.
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
| Build | Build 73 (matches `CURRENT_PROJECT_VERSION`) |

---

## Acknowledgments

- **[python-ios-lib](https://github.com/yu314-coder/python-ios-lib)** — the entire embedded Python stack
  (manim, numpy, scipy, matplotlib, plotly, PyAV, pycairo, busytex, ffmpeg)
  is built and signed by that repo's pipelines. The build phases here
  consume its SwiftPM products + `wrap-loose-dylibs.sh` script.
- **[CodeBench / offlinai](https://github.com/yu314-coder/CodeBench)** — sister iOS Python IDE that pioneered
  the App Store-compliant layout (the consolidated `app_packages/` tree,
  the .so → .framework wrap pattern, the offlinai_shell builtin). This
  app's build pipeline closely follows CodeBench's known-working order.
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
