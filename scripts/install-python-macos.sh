#!/bin/bash
# install-python-macos.sh — Run Script build phase for the
# ManimStudio_macos target.
#
# Bundles a complete Python runtime + the desktop app's pip
# dependencies into <App>.app/Contents/Resources/, so the embedded
# interpreter started by PythonHost.swift can `import app` without
# touching the user's system Python.
#
# Layout we produce:
#   <App>.app/Contents/Resources/
#       python-stdlib/        — full Python stdlib (compiled)
#       site-packages/        — manim, numpy, scipy, kokoro-onnx, …
#       PythonApp/            — app.py, bootstrap_macos.py, friends
#                                (already in the synchronized group)
#
# Unlike the iOS build, macOS doesn't need:
#   • wrap-loose-dylibs.sh    (App Store bundle layout requirement)
#   • .fwork normalization    (BeeWare's iOS .fwork files only)
#   • BLAS / Fortran I/O stubs (iOS Accelerate symbol gaps)
#   • flat-namespace dlopen preload
# macOS dyld's @rpath + Mach-O linking covers all of it natively.
set -e

if [ "$PLATFORM_NAME" != "macosx" ]; then
  echo "note: install-python-macos.sh — skipping (not macOS)"
  exit 0
fi

APP_RESOURCES="${TARGET_BUILD_DIR}/${UNLOCALIZED_RESOURCES_FOLDER_PATH}"
[ -d "$APP_RESOURCES" ] || APP_RESOURCES="${BUILT_PRODUCTS_DIR}/${UNLOCALIZED_RESOURCES_FOLDER_PATH}"
mkdir -p "$APP_RESOURCES"

BEEWARE_XCFW="${SRCROOT}/../_vendor/beeware/Python.xcframework"
SLICE="$BEEWARE_XCFW/macos-arm64_x86_64"
[ ! -d "$SLICE" ] && SLICE="$BEEWARE_XCFW/macos-arm64"
[ ! -d "$SLICE" ] && SLICE="$BEEWARE_XCFW/macos-x86_64"

if [ ! -d "$SLICE" ]; then
  echo "warning: no macos slice found under $BEEWARE_XCFW — skipping"
  echo "         (macOS Python.xcframework slice not vendored)"
  exit 0
fi

# ── 1. Stdlib ────────────────────────────────────────────────────
STDLIB_SRC=""
for cand in \
    "$BEEWARE_XCFW/lib/python3.14" \
    "$SLICE/lib/python3.14" \
    "$SLICE/Python.framework/Versions/3.14/lib/python3.14"; do
  [ -d "$cand" ] && STDLIB_SRC="$cand" && break
done
if [ -z "$STDLIB_SRC" ]; then
  echo "warning: stdlib not found in $BEEWARE_XCFW — skipping"
  exit 0
fi
DST_STDLIB="$APP_RESOURCES/python-stdlib"
mkdir -p "$DST_STDLIB"
rsync -a --delete --exclude '__pycache__' \
    "$STDLIB_SRC/" "$DST_STDLIB/"
echo "note: stdlib bundled (slice=$(basename $SLICE))"

# ── 2. site-packages — pip-installed once into a vendor cache,
#       then rsync'd into the .app at build time. The cache lives
#       at _vendor/macos-site-packages/ so we don't pip-install on
#       every build.
#
# Pip needs an *executable* Python interpreter, which BeeWare's
# embed-only macOS slice doesn't ship — its framework is just
# Python.framework/Versions/3.14/Python (the dylib). So we use a
# host python3.14 from PATH for the pip step. As long as both are
# CPython 3.14 with the same ABI flags, the installed wheels load
# fine inside the embedded interpreter.
VENDOR_SITE="${SRCROOT}/../_vendor/macos-site-packages"
REQS="${SRCROOT}/../requirements-macos.txt"
if [ ! -d "$VENDOR_SITE" ] && [ -f "$REQS" ]; then
  HOST_PY=""
  for cand in python3.14 python3.13 python3.12 python3 ; do
    if command -v "$cand" >/dev/null 2>&1; then
      HOST_PY="$(command -v $cand)"
      break
    fi
  done
  if [ -z "$HOST_PY" ]; then
    echo "warning: no python3.* on PATH — pip-install skipped."
    echo "         Install Python 3.14 from python.org or 'brew install python@3.14'"
    echo "         and rebuild to populate $VENDOR_SITE."
  else
    PY_VER=$("$HOST_PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    if [ "$PY_VER" != "3.14" ]; then
      echo "warning: host Python is $PY_VER, BeeWare slice is 3.14 — ABI mismatch likely."
      echo "         pip-install proceeds but C extensions may fail at runtime."
      echo "         Install python3.14 (brew install python@3.14) for clean wheels."
    fi
    echo "note: priming $VENDOR_SITE via $HOST_PY (one-time, ~5 min)"
    "$HOST_PY" -m pip install --no-warn-script-location \
        --target "$VENDOR_SITE" -r "$REQS" \
      && echo "note: pip install OK" \
      || echo "warning: pip install failed; continuing without site-packages"
  fi
fi
if [ -d "$VENDOR_SITE" ]; then
  DST_SITE="$APP_RESOURCES/site-packages"
  mkdir -p "$DST_SITE"
  rsync -a --delete --exclude '__pycache__' \
      "$VENDOR_SITE/" "$DST_SITE/"
  echo "note: site-packages bundled from $VENDOR_SITE"
fi

# ── 3. Python.framework — link-time linkage already pulls the
#       framework into the binary's @rpath search; we just need
#       the framework copied into Contents/Frameworks. Xcode's
#       Embed Frameworks build phase normally handles this when
#       the xcframework is in the target's Link Binary list. If
#       it's missing on first archive, this script does the copy
#       as a safety net.
FRAMEWORK_SRC=""
for cand in \
    "$SLICE/Python.framework" \
    "$SLICE/Python.xcframework/macos-arm64_x86_64/Python.framework"; do
  [ -d "$cand" ] && FRAMEWORK_SRC="$cand" && break
done
if [ -n "$FRAMEWORK_SRC" ]; then
  FW_DST="${TARGET_BUILD_DIR}/${FRAMEWORKS_FOLDER_PATH}"
  mkdir -p "$FW_DST"
  if [ ! -d "$FW_DST/Python.framework" ]; then
    rsync -a "$FRAMEWORK_SRC/" "$FW_DST/Python.framework/"
    IDENT="${EXPANDED_CODE_SIGN_IDENTITY:-${CODE_SIGN_IDENTITY:--}}"
    codesign --force --sign "$IDENT" --timestamp=none --deep \
        "$FW_DST/Python.framework" 2>/dev/null || true
    echo "note: Python.framework copied + signed (safety-net path)"
  fi
fi

echo "note: install-python-macos.sh done"
