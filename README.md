# ManimStudio (iOS / iPadOS)

iPad-native port of the manim_app workflow — Monaco editor, SwiftTerm
console, embedded Python 3.14 from BeeWare's Python.xcframework, and
the `python-ios-lib` SwiftPM bundle (manim, numpy, scipy, matplotlib,
plotly, …).

## Build prerequisites

1. **Xcode 15+** on macOS, signing identity + team configured.
2. **Busytex web build** — not in this repo (~237 MB, includes a
   100 MB `texlive-basic.data` that's at GitHub's per-file ceiling).
   Drop the unpacked bundle at:
   ```
   ManimStudio/ManimStudio/Resources/Busytex/
   ```
   so the LaTeX engine can find it at runtime.
3. SwiftPM resolves `python-ios-lib` and `Python.xcframework`
   automatically on first build.

## Layout

- `ManimStudio/` — Xcode project (Swift sources, Resources, Info.plist).
- `scripts/` — build-phase shell scripts (install Python stdlib, wrap
  loose dylibs into per-module frameworks for App Store, post-archive
  SwiftSupport injection).

## Branch

This is the **`ios`** branch of `manim_app` — desktop tree lives on
`main`. Source layout, embed pipeline, and SwiftPM dependencies are
iPad-specific and don't merge cleanly back.
