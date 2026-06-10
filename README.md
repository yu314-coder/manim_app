# Manim Animation Studio — macOS (native)

**Native macOS app that renders mathematical animations on-device with an embedded Python + Manim runtime.**

![Platform](https://img.shields.io/badge/platform-macOS-black)
![UI](https://img.shields.io/badge/UI-SwiftUI%20%2F%20AppKit-orange)
![Python](https://img.shields.io/badge/python-embedded-green)
![License](https://img.shields.io/badge/license-MIT-orange)

> **Branch map** — `ios` = iPhone / iPad (App Store) · **`macos` = this native Mac app** · `MacOS-version` = the older PyWebView desktop build · `main` = the original Windows desktop app.
> This branch shares its Xcode project with `ios` and does **not** merge back into `main`.

---

## What it is

A real Mac app — `ManimStudio.app`, shipped as a `.dmg` — built from `ManimStudio.xcodeproj`. It bundles:

- a **Monaco** code editor in a `WKWebView` (Python autocomplete, find/replace, multi-cursor, the usual editor shortcuts),
- a **SwiftTerm** terminal bridged to Python over a PTY,
- an **embedded CPython** runtime with the full Manim stack,

so you write Python, hit Render, and watch the math become a video — entirely offline, with nothing to install or configure.

The macOS-specific UI lives in the **`ManimStudio_macos`** target; the core logic is shared with the iOS app on the `ios` branch.

## Bundled Python stack

Installed into `ManimStudio.app/Contents/Resources/site-packages/` from [`requirements-macos.txt`](requirements-macos.txt):

`manim` · `numpy` · `scipy` · `matplotlib` · `Pillow` · `webvtt-py` (auto-narration captions) · optional Kokoro ONNX TTS.

## Building

The embedded Python is **fetched at build time** rather than committed to git — that is what dropped the DMG from ~505 MB to ~8.6 MB. The `scripts/` folder drives the setup:

| Script | Role |
|---|---|
| `fetch-macos-python.sh` | downloads the macOS CPython framework |
| `install-python-macos.sh` | `pip install -r requirements-macos.txt` → `Resources/site-packages` |
| `install-python-stdlib.sh` | copies the trimmed standard library into the app |
| `inject-swift-support*.sh`, `normalize-fwork-postembed.sh`, `fix-macho-type.py` | code-signing / framework-embedding fix-ups |

Run those once, then build the **`ManimStudio_macos`** scheme in `ManimStudio.xcodeproj` with Xcode; the result is distributed as a `.dmg`.

## Related

- **iOS / iPadOS** app → [`ios`](https://github.com/yu314-coder/manim_app/tree/ios) branch (on the App Store).
- **PyWebView desktop** build → [`MacOS-version`](https://github.com/yu314-coder/manim_app/tree/MacOS-version) branch.
- **Embedded Python for iOS (arm64)** → [yu314-coder/python-ios-lib](https://github.com/yu314-coder/python-ios-lib).
