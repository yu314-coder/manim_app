# Manim Animation Studio — macOS (desktop)

**The PyWebView desktop app, packaged as a native macOS `.dmg` for Apple Silicon and Intel.**

![Platform](https://img.shields.io/badge/platform-macOS-black)
![Python](https://img.shields.io/badge/python-3.8+-green)
![UI](https://img.shields.io/badge/UI-PyWebView-blue)
![License](https://img.shields.io/badge/license-MIT-orange)

> **Branch map** — `main` = original Windows desktop · **`MacOS-version` = this macOS DMG build** · `macos` = the newer native Swift Mac app · `ios` = the iPhone / iPad app.

---

## What it is

The same Python + **PyWebView** desktop application as the [`main`](https://github.com/yu314-coder/manim_app/tree/main) branch (`app.py` — Monaco editor, AI edit panel, Manim rendering), built and packaged for macOS. `create_dmg.py` turns the compiled `ManimStudio.app` into a distributable `.dmg` for `arm64` and/or `x86_64`.

For the full feature list — Monaco editor with basedpyright IntelliSense, the AI Edit panel (Claude Code / Codex + agent mode), narration, render farm, and the rest — see the [`main`](https://github.com/yu314-coder/manim_app/tree/main) README. This branch is the same app, macOS-packaged.

## Run from source

```bash
pip install -r requirements.txt   # pywebview, pillow, psutil, …
python3 app.py
```

## Build a macOS app + DMG

```bash
python3 build_nuitka.py                # compile ManimStudio.app
python3 create_dmg.py --arch arm64     # package → ManimStudio-arm64.dmg
#                     --arch x86_64     # Intel
#                     --arch both       # both architectures
```

## Related

- **Windows desktop** (original) → [`main`](https://github.com/yu314-coder/manim_app/tree/main).
- **Native Swift Mac app** → [`macos`](https://github.com/yu314-coder/manim_app/tree/macos).
- **iOS / iPadOS** → [`ios`](https://github.com/yu314-coder/manim_app/tree/ios).
