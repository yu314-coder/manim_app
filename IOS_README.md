# ManimStudio — iOS / iPadOS port

iPad-first port of [manim_app](https://github.com/yu314-coder/manim_app) — full
offline Manim animation studio for iPad and iPhone. Live in the App Store
review pipeline as **ManimStudio** (bundle id `euleryu.ManimStudio`,
Apple ID `6764472686`).

This branch contains the complete native iOS port. The Windows / Electron
desktop app on `main` is unaffected.

## What works

- **Python 3.14** embedded via [BeeWare's Python.xcframework] with
  [yu314-coder/python-ios-lib] supplying `manim`, `numpy`, `scipy`,
  `matplotlib`, `plotly`, `PyAV`, `pycairo`, `pangocairo`, and `busytex`
  (LaTeX). All compiled for `arm64-iphoneos`, all signed, all App Store
  layout-compliant.
- **Native rendering pipeline.** Manim scenes encode to MP4 / MOV / GIF /
  PNG using Apple **VideoToolbox** for hardware H.264 (with software
  libx264 fallback). PyAV wraps the bundled ffmpeg dylibs.
- **In-app code editor** (Monaco in WKWebView) with Python autocomplete,
  find/replace, format-document, comment toggle, error-gutter markers
  parsed from render tracebacks, drag-drop image insert as
  `ImageMobject`.
- **Real terminal** (SwiftTerm) bridged to Python's stdin/stdout/stderr
  via a PTY pair. Runs the bundled `offlinai_shell` (rebranded
  `ManimStudio shell`) — `ls`, `cd`, `cat`, `top`, `find`, `grep`, all
  with proper iOS-sandbox-aware path handling.
- **Magic Keyboard menu bar.** ⌘R render, ⇧⌘R preview, ⌘1–5 tabs,
  ⌘F find, ⌥⌘L format, etc. All actions are also reachable from the
  on-screen header.
- **iPhone responsive layout.** A separate compact-size-class layout
  (segmented pane picker + sheet for controls) so the same binary is
  usable on iPhone 12 Pro through iPhone 16 Pro Max, not just iPad.
- **Crash log** persisted to `Documents/Logs/manim_studio.log` capturing
  Python tracebacks, render output, signal-level Mach handlers, and
  `faulthandler` C-extension crashes. Viewable in-app or in the Files
  app.

## Architecture quick map

```
ManimStudio/                         # Xcode project root
├── ManimStudio.xcodeproj/
└── ManimStudio/
    ├── ManimStudioApp.swift         # @main, kicks off Python boot
    ├── ContentView.swift            # tab shell, render dispatch, save sheet
    ├── HeaderView.swift             # iPad / iPhone responsive header
    ├── WorkspaceView.swift          # iPad split + iPhone segmented panes
    ├── EditorPane.swift             # Monaco toolbar, Open/Insert image
    ├── MonacoEditor.swift           # SwiftUI wrapper for the WKWebView
    ├── MonacoEditorView.swift       # UIView subclass with WKWebView + IPC
    ├── Resources/editor.html        # Monaco bundle entry point
    ├── PreviewPane.swift            # AVPlayer for the rendered MP4
    ├── TerminalPane.swift           # SwiftUI host for SwiftTermContainer
    ├── TerminalPaneViewController.swift  # SwiftTerm UIViewController
    ├── PTYBridge.swift              # PTY pipes, [manim-debug] filter, magic-keyboard observers
    ├── PythonRuntime.swift          # Py_Initialize, GIL, redirect, render wrapper
    ├── PackagesView.swift           # `importlib.metadata` browser
    ├── PackageInspector.swift       # background introspection driver
    ├── LibrarySymbolBuilder.swift   # caches Monaco completion index
    ├── AssetsView.swift             # Documents/Assets file browser
    ├── HistoryView.swift            # Documents/ToolOutputs scanner
    ├── SystemView.swift             # device + library facts
    ├── ControlsSidebar.swift        # quality / fps / format pickers
    ├── ManimQuality.swift           # quality enum bridging
    ├── SceneDetector.swift          # regex scan for `class … (Scene)`
    ├── BackgroundTaskGuard.swift    # UIBackgroundTask + AVAudioSession glue
    ├── CrashLogger.swift            # signal handlers + persistent log file
    ├── LogViewerView.swift          # in-app tailing log viewer
    ├── MenuCommands.swift           # iPad menu bar (.commands)
    ├── PythonFormatter.swift        # pure-Swift Python whitespace cleanup
    ├── BusytexEngine.swift          # LaTeX → SVG via busytex.wasm
    ├── LaTeXEngine.swift            # higher-level LaTeX dispatch
    ├── WebLaTeXEngine.swift         # in-browser LaTeX renderer fallback
    ├── PrivacyInfo.xcprivacy        # required-reason API manifest
    └── Info.plist                   # capabilities + usage descriptions
scripts/
├── install-python-stdlib.sh         # main build phase: stdlib + framework wrapping
└── normalize-fwork-postembed.sh     # post-Embed-Frameworks .fwork normalizer
```

## Build phases

The Xcode target runs four custom build phases in order:

1. **Sources** (Swift → arm64).
2. **Frameworks** (links Python.xcframework + Accelerate).
3. **Resources** (assets, Info.plist, PrivacyInfo.xcprivacy).
4. **Install Python stdlib** (`scripts/install-python-stdlib.sh`)
   - Copies BeeWare stdlib + lib-dynload into `<App>.app/python-stdlib/`.
   - Bundles ffmpeg dylibs (libavcodec/format/util/swscale/swresample/avfilter)
     and rewrites their `/tmp/ffmpeg-ios/...` install_names to `@rpath/...`.
   - Consolidates SwiftPM `python-ios-lib_*.bundle/` directories into
     `app_packages/site-packages/` so wrap-loose-dylibs.sh and BeeWare's
     import hook see the layout they expect.
   - Builds **`libscipy_blas_stubs.framework`** — a 10-line C stub
     providing `dcabs1_` and `lsame_` (the two BLAS reference helpers
     iOS Accelerate doesn't export — without them
     `scipy.linalg.cython_blas` fails to flat-namespace-resolve).
   - Bundles **`libfortran_io_stubs.framework`** (the prebuilt LLVM Flang
     I/O runtime stubs needed by scipy arpack/propack) into the same
     loose-dylib path that wrap-loose-dylibs.sh expects.
5. **Wrap loose dylibs (App Store)** (archive only — runs upstream's
   `wrap-loose-dylibs.sh` from python-ios-lib to convert every loose
   `.so` and `.dylib` into a `.framework` directory matching App Store
   bundle requirements).
6. **Embed Frameworks** (Python.xcframework + everything wrapped above).
7. **Normalize Python .fwork (post-embed)** (`scripts/normalize-fwork-postembed.sh`)
   - Strips `@executable_path/` prefixes from every `.fwork` text file
     (dyld treats it as a literal directory in `dlopen` paths, which
     fails for stdlib `_struct.fwork` etc.).
   - Tears out residual `python-ios-lib_*.bundle/` dirs that Xcode's
     resource-copy pass repopulates after our Step 9 deletes them.

## Runtime startup (Python boot path)

`ManimStudioApp.init` kicks off two parallel queues:

1. **PTY + Python boot** (background queue inside `PythonRuntime`):
   - `PTYBridge.shared.setupIfNeeded()` — pipe(2) + dup2 onto stdin/stdout/stderr.
   - `preloadScipySupportFrameworks()` — `dlopen` the BLAS / Fortran stubs
     with `RTLD_GLOBAL` so their symbols enter the flat namespace **before**
     any scipy import runs.
   - `Py_Initialize()` — embedded interpreter starts.
   - `sys.stdout` / `sys.stderr` are replaced by an **unbuffered**
     `io.TextIOWrapper(io.FileIO(fd), write_through=True)` so the shell
     prompt (no trailing `\n`) reaches the terminal immediately.
   - `python_ios_lib_import_hook` is installed (routes wrapped-framework
     module imports to `<App>.app/Frameworks/site-packages.X.framework/X`).
   - `offlinai_shell.repl()` starts on a daemon thread, taking over
     stdin/stdout for the user's terminal.
2. **LaTeX + busytex preload** (main queue, after a short delay).

## Render dispatch

User taps `Render` or `Preview` (header) → `ContentView.triggerRender(quick:)`:

1. `BackgroundTaskGuard.shared.begin()` — extends app lifetime + activates
   an `.ambient` `mixWithOthers` `AVAudioSession` so the render survives
   screen lock.
2. Quality + FPS resolved: Preview always uses `low_quality / 15 fps`;
   Render reads ControlsSidebar's `@AppStorage("manim_final_*")` keys.
3. `PythonRuntime.execute(code:targetScene:onOutput:)` runs the wrapper
   script in `<offlinai-python-tool>`. The wrapper exec's the user code,
   discovers Scene subclasses, calls each one, and writes the final
   MP4 path to `__codebench_plot_path`.
4. `PTYBridge` tees stdout/stderr to both SwiftTerm and the persistent
   log file, with the `[manim-debug]` line filter stripping internal
   render-pipeline traces from the visible terminal.
5. On success: `cleanupPartials()` removes the `partial_movie_files/`
   subtree; `RenderCompleteSheet` auto-presents (Save to Files / Save
   to Photos / Share); the file is also added to `HistoryView`'s scan.
6. On failure: `parseTracebackMarkers` regexes `File "<string>", line N`
   out of stderr and posts `editorSetMarkers` so Monaco's gutter shows
   a red marker on the offending line.

## App Store status

| Item | Status |
|------|--------|
| Bundle ID | `euleryu.ManimStudio` |
| App Store Connect ID | `6764472686` |
| Privacy Policy URL | https://yu314-coder.github.io/privacy.html#manim-studio-ios |
| Privacy nutrition label | Data Not Collected |
| Categories | Developer Tools / Education |
| iPad screenshots | 6 × 2752×2064 / 2064×2752 (in `_appstore_screens/`) |
| iPhone screenshots | 4 × 1284×2778 (in `_appstore_screens_iphone/`) |
| Build | Build 73 (matches `CURRENT_PROJECT_VERSION`) |
| Min iOS | 17.0 (per `IPHONEOS_DEPLOYMENT_TARGET`) |
| Architectures | arm64 only (no simulator slice in the shipped artifact) |

## Reproducing the build

Requirements:
- Xcode 26+ (deployment target 17, Swift 6 toolchain).
- Apple Developer team ID `LYK4LV2859` (set in `project.pbxproj`).
- The `_vendor/python-ios-lib/` and `_vendor/beeware/Python.xcframework/`
  trees from upstream — those are referenced as `SOURCE_ROOT/../_vendor/...`
  by the build scripts and are **not** vendored into this branch (~1.5 GB).
  Clone them as siblings of this directory.

```sh
# Layout expected:
# /Volumes/D/ManimStudio/        ← this repo
# /Volumes/D/ManimStudio/_vendor/python-ios-lib/
# /Volumes/D/ManimStudio/_vendor/beeware/Python.xcframework/

xcodebuild -project ManimStudio/ManimStudio.xcodeproj \
           -scheme ManimStudio -configuration Release \
           -archivePath build/ManimStudio.xcarchive archive
```

## Branch conventions

`main` = Windows / Electron app (unrelated). `ios` = this branch, never
merged back. Tag releases as `ios/v1.0`, `ios/v1.1`, etc. when shipping
to the App Store.
