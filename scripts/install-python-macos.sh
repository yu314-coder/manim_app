#!/bin/bash
# install-python-macos.sh — Run Script build phase for the native
# ManimStudio_macos target.
#
# What it does:
#   • rsyncs _vendor/macos-site-packages/ into
#     <App>.app/Contents/Resources/site-packages/
#
# That's it. The native rewrite uses a host python3.* (resolved at
# launch by PythonResolver.swift) and runs `python -m manim render
# scene.py <SceneName>` as a subprocess. We bundle site-packages
# only so that subprocess Python finds manim/numpy/scipy etc.
# without contaminating the user's system Python install.
#
# Phase 1/2's stdlib + Python.framework copy paths are gone — we
# don't embed an interpreter anymore, the user's host Python does
# the heavy lifting.
set -e

if [ "$PLATFORM_NAME" != "macosx" ]; then
  echo "note: install-python-macos.sh — skipping (PLATFORM_NAME=$PLATFORM_NAME)"
  exit 0
fi

APP_RESOURCES="${TARGET_BUILD_DIR}/${UNLOCALIZED_RESOURCES_FOLDER_PATH}"
[ -d "$APP_RESOURCES" ] || APP_RESOURCES="${BUILT_PRODUCTS_DIR}/${UNLOCALIZED_RESOURCES_FOLDER_PATH}"
mkdir -p "$APP_RESOURCES"

VENDOR_SITE="${SRCROOT}/../_vendor/macos-site-packages"
REQS="${SRCROOT}/../requirements-macos.txt"

# ── 1. One-time: pip-install the requirements into the vendor cache.
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
    echo "         Install Python 3.14 (brew install python@3.14 OR python.org)"
    echo "         and rebuild to populate $VENDOR_SITE"
  else
    echo "note: priming $VENDOR_SITE via $HOST_PY (one-time, ~5 min)"
    "$HOST_PY" -m pip install --no-warn-script-location \
        --target "$VENDOR_SITE" -r "$REQS" \
      && echo "note: pip install OK" \
      || echo "warning: pip install failed; continuing without site-packages"
  fi
fi

# ── 2. Sync the cache into the .app bundle.
# Bundling site-packages is gated on the BUNDLE_PYTHON env var. The
# default for the macOS native rewrite is OFF — VenvManager creates
# a per-user venv via the host Python and pip-installs manim there,
# so the ~400 MB bundled site-packages tree is redundant. Set
# BUNDLE_PYTHON=1 in the build settings if you want the legacy
# "ships with manim out of the box" experience back.
if [ "${BUNDLE_PYTHON:-0}" != "0" ] && [ -d "$VENDOR_SITE" ]; then
  DST_SITE="$APP_RESOURCES/site-packages"
  mkdir -p "$DST_SITE"
  rsync -a --delete --exclude '__pycache__' --exclude '.DS_Store' \
      "$VENDOR_SITE/" "$DST_SITE/"
  count=$(ls "$DST_SITE" 2>/dev/null | wc -l | tr -d ' ')
  echo "note: bundled $count packages from $VENDOR_SITE into Resources/site-packages/"
else
  # Make sure no stale bundle from a prior build sticks around.
  rm -rf "$APP_RESOURCES/site-packages"
  echo "note: site-packages NOT bundled (BUNDLE_PYTHON=${BUNDLE_PYTHON:-0})"
fi

echo "note: install-python-macos.sh done"
