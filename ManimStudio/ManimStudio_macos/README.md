# ManimStudio (macOS)

Native macOS rewrite of the desktop ManimStudio that lives on `main`.
**Separate target** from the iOS / iPadOS app — only the AppIcon
asset is shared (regenerated from the iOS 1024×1024 master).

## Architecture

Pure SwiftUI + AppKit. **No** WKWebView shell, **no** embedded Python
interpreter, **no** PyWebView IPC. The render pipeline shells out to
a host `python3.*` (resolved by `PythonResolver`) running `python -m
manim render scene.py <SceneName>` against a bundled
`Resources/site-packages/` (manim, numpy, scipy, matplotlib, …).

This trades the Windows desktop app's PyWebView container for a real
native macOS app — proper NSWindow chrome, native menu bar, native
NSToolbar, NSTextView-based editor with Python syntax highlighting,
AVKit video preview, NSOpenPanel/NSSavePanel file dialogs.

## Files

```
ManimStudio_macos/
├── ManimStudio_macosApp.swift  · @main, NSWindow, menu bar, file IO
├── ContentView.swift            · NavigationSplitView + toolbar
├── AppState.swift               · ObservableObject central state
├── Theme.swift                  · color palette + reusable styling
├── EditorView.swift             · NSTextView + Python syntax highlight
├── PreviewView.swift            · AVKit player for rendered MP4/MOV
├── TerminalView.swift           · NSTextView console with ANSI strip
├── RenderManager.swift          · subprocess driver for manim CLI
├── PythonResolver.swift         · finds host python3.* on disk
├── Assets.xcassets/             · AppIcon (regen'd from iOS master)
├── ManimStudio_macos.entitlements
└── README.md  (this file)
```

## What Swift handles

| Concern | Implementation |
|---------|----------------|
| Window chrome | SwiftUI `WindowGroup` + native NSWindow titlebar |
| Sidebar nav | `NavigationSplitView` with five `SidebarSection` cases |
| Code editor | `NSTextView` + 200-line `PythonTokens` regex tokenizer |
| Preview | `AVKit.VideoPlayer` for MP4/MOV; `NSImage` for PNG/GIF |
| Terminal | `NSTextView` (read-only) with ANSI CSI stripping |
| File IO | `NSOpenPanel` / `NSSavePanel` |
| Menu bar | SwiftUI `.commands` modifier with `CommandGroup` / `CommandMenu` |
| Render | `Foundation.Process` + `Pipe` |
| Python deps | bundled `Resources/site-packages/` (no embedded interpreter) |

## What Python handles (subprocess only)

The host `python3.*` is invoked exactly once per render, with these
overrides:

```
PYTHONPATH = <App>.app/Contents/Resources/site-packages
PYTHONUNBUFFERED = 1
PYTHONDONTWRITEBYTECODE = 1
MANIM_DISABLE_RENDERER_CACHE = 1
```

The user's system Python install is never modified. Side-effect: if
they don't have a Python 3.14 on PATH, RenderManager surfaces a
helpful "install Python 3.14 from python.org or `brew install
python@3.14`" message in the terminal pane.

## Build dependencies

- **Xcode 26+** (Swift 6, macOS 26 SDK).
- **Apple Developer team** (`LYK4LV2859` is hard-coded — change in
  `project.pbxproj` for your own team).
- **Host Python 3.14** for the one-time `pip install` step that
  populates `_vendor/macos-site-packages/` (~508 MB, runs ~5 min).
  Subsequent builds rsync from that cache and complete in seconds.

```sh
xcodebuild -project ManimStudio/ManimStudio.xcodeproj \
           -scheme ManimStudio_macos -configuration Debug build
```

The `install-python-macos.sh` build phase will pip-install on first
clean build, then rsync the site-packages tree into
`<App>.app/Contents/Resources/site-packages/`.

## What's NOT here yet

This is the **first native cut**. Many features from the Windows
desktop app's `main` branch aren't ported yet:

- AI Edit panel (Codex / Claude Code subprocess driver) — needs
  `AIEditView.swift` + a JSONL pipe parser
- Auto narration with Kokoro TTS — needs `NarrationManager.swift`
  + `narrate("…")` source preprocessor
- basedpyright LSP integration — would need a Node.js launcher
- Real `Assets`, `Packages`, `History` views (currently placeholders)
- Drag-drop `.py` onto the window
- macOS notarization + DMG packaging

The structure is designed to slot these in without rewriting any of
the existing files — each becomes its own focused Swift file under
`ManimStudio_macos/`.

## Sharing convention

| Asset | iOS uses | macOS uses |
|-------|----------|------------|
| AppIcon (1024×1024 master) | `ManimStudio/Assets.xcassets/AppIcon` | regenerated into `ManimStudio_macos/Assets.xcassets/AppIcon` |
| Swift sources | iOS only | macOS only |
| Anything else | nothing shared | nothing shared |

By design, no Swift file is ever shared. The two targets can
diverge freely.
