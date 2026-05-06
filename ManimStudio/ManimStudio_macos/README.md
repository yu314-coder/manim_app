# ManimStudio (macOS)

Native macOS port of the desktop ManimStudio that lives on `main`.
**Separate target** from the iOS / iPadOS app — only the AppIcon asset
is shared (regenerated from the iOS 1024×1024 master).

## Strategy

Rather than rewriting 25 k+ LOC of Python + JS in Swift, this target
**reuses the entire `web/` frontend and `app.py` business logic** from
`main` and replaces only the platform shell. PyWebView's WKWebView+IPC
container is swapped for a native AppKit one, with an identical
`window.pywebview.api.*` JS contract so the existing JS calls work
unchanged.

## Phases

### ✅ Phase 1 — WKWebView shell (this commit)

- `ManimStudio_macosApp.swift` — `@main`, hosts a single `WindowGroup`.
- `ContentView.swift` — root SwiftUI view, embeds `WebHost`.
- `WebHost.swift` — `NSViewRepresentable` wrapping `WKWebView`:
  - Loads `Resources/web/index.html` as a file URL with directory read
    access so all relative asset paths resolve.
  - Injects a `window.pywebview` shim at document-start providing
    `pywebview.api.*` as a `Proxy` that posts to a `pywebviewBridge`
    message handler. Every method call is a Promise resolved by a
    later `webView.evaluateJavaScript("…_resolve(id, payload)…")`.
  - `IPCHandler` receives the JS messages. Phase 1 stub replies
    `null` to every call so the page loads without errors.
- `Assets.xcassets/AppIcon.appiconset/` — generated from the iOS
  1024×1024 master via `sips` into the 7 sizes macOS expects
  (16/32/64/128/256/512/1024 in @1x and @2x flavors).
- `Resources/web/` — the unmodified `web/` tree from `origin/main`
  (Monaco, xterm.js, FontAwesome, AI edit panel, modals, all CSS/JS).
- `Resources/prompts/` — the AI agent prompt pack.
- `PythonApp/` — `app.py`, `ai_edit.py`, `cli.py`, `narration_addon.py`
  copied from `origin/main`. Not yet executed; placeholder for Phase 2.

After this commit you can build the `ManimStudio_macos` scheme and
see the existing Windows-app UI render in a native macOS window. Every
button click hits the IPC stub and gets `null` back, so nothing
actually renders or saves yet — that's Phase 2.

### ⏳ Phase 2 — Embed Python + wire IPC

- `PythonHost.swift` — embeds `Python.framework` (BeeWare's
  arm64-macos slice), `Py_Initialize`, imports `app`, owns the GIL.
- `IPCHandler.dispatch` becomes a real `app.api.<method>(*args)` call
  via PyObject_CallMethod, with JSON serialization of args/return.
- macOS-specific shims in `app.py` for `winpty` → `pty.openpty`,
  `cmd.exe` → `/bin/zsh`, `\\` → `/`. ~50 LOC.
- Bundle `manim`, `numpy`, `scipy`, `matplotlib`, `kokoro-onnx`,
  `pywebview`-style helpers into `Resources/site-packages/` via a
  build-phase shell script (parallel to `install-python-stdlib.sh`
  but for macOS).

### ⏳ Phase 3 — Native macOS niceties

- `NSMenu` File / Edit / Render / View / Help with all keybindings.
- Drag-drop `.py` onto window via `NSDraggingDestination`.
- `NSOpenPanel` / `NSSavePanel` shim for `pywebview.create_file_dialog`.
- Real PTY-backed terminal via `posix_spawn` + `openpty`.
- macOS notarization + DMG packaging for distribution outside the
  App Store.

### ⏳ Phase 4 — Subsystem feature parity

Everything from `main`'s README that's Python-side (AI edit, Codex /
Claude Code integration, Kokoro TTS narration, asset manager, package
manager, render history, scene outline, basedpyright LSP) is
business logic in `app.py` / `ai_edit.py` and works without
modification once Phase 2 is in. Just verify on macOS and ship.

## Sharing convention

| Asset | iOS uses | macOS uses |
|-------|----------|------------|
| AppIcon (1024×1024 master) | `ManimStudio/Assets.xcassets/AppIcon` | regenerated into `ManimStudio_macos/Assets.xcassets/AppIcon` |
| Swift sources | iOS only | macOS only |
| `web/` frontend | n/a (uses Monaco directly) | bundled from `main` |
| `app.py` & friends | n/a | bundled from `main` |

By design, no Swift file is ever shared. iOS layouts (compact size
class, segmented panes) and macOS layouts (NSWindow + WKWebView) live
in separate files in their respective target folders.
