#!/bin/bash
# fetch-macos-python.sh — adds BeeWare's macOS Python slice to the
# vendored Python.xcframework so the macOS target can link.
#
# What this does:
#   1. Looks up the latest BeeWare Python-Apple-support release that
#      contains a macOS tarball matching the iOS major.minor we already
#      have vendored (so we don't accidentally mix Python 3.14 iOS with
#      3.13 macOS — those would be ABI-incompatible at the C extension
#      level).
#   2. Downloads the macOS support tarball.
#   3. Extracts the macOS Python.framework (and lib + bin tooling).
#   4. Reconstructs Python.xcframework via `xcodebuild -create-xcframework`
#      so Apple's tools recognize the new slice. The original iOS slices
#      stay in place — we copy them into the new xcframework alongside
#      the macOS slice.
#
# Usage:  scripts/fetch-macos-python.sh
# Idempotent: if a macos-* slice is already present, the script exits
# unless --force is passed.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$REPO_ROOT/_vendor/beeware"
XCF="$VENDOR/Python.xcframework"
WORK="$VENDOR/.macos-python-fetch"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

if [ ! -d "$XCF" ]; then
  echo "error: $XCF not found. Run this from a clone with iOS slices already vendored."
  exit 1
fi

# ── Detect the iOS slice's Python version so we ask BeeWare for a
# compatible macOS tarball.
detect_python_version() {
  local plist="$XCF/Info.plist"
  if [ -f "$plist" ]; then
    /usr/libexec/PlistBuddy -c "Print :MinimumDeploymentTarget" "$plist" \
      2>/dev/null || true
  fi
  # Fallback: walk the iOS lib dir for python3.X.
  for d in "$XCF"/ios-arm64/lib/python3.* \
           "$XCF"/lib/python3.* ; do
    [ -d "$d" ] && basename "$d" | sed -E 's/python(3\.[0-9]+)/\1/' && return
  done
  echo ""
}
PY_VER="$(detect_python_version)"
[ -z "$PY_VER" ] && PY_VER="3.14"   # safe default
echo "▸ targeting Python $PY_VER"

# ── Bail-out: already merged?
for slice in "$XCF"/macos-* ; do
  if [ -d "$slice" ] && [ "$FORCE" -ne 1 ]; then
    echo "▸ macOS slice already present at $(basename $slice) — pass --force to redo"
    exit 0
  fi
done

# ── Resolve the latest BeeWare release URL for the requested Python
# version. The asset naming convention is
#   Python-<X.Y>-macOS-support.b<N>.tar.gz
# under github.com/beeware/Python-Apple-support/releases. The release
# tag itself looks like "3.14-b<N>" (matching iOS).
echo "▸ querying GitHub releases…"
RELEASES_API="https://api.github.com/repos/beeware/Python-Apple-support/releases"
ASSET_URL="$(curl -sSL "$RELEASES_API" \
  | python3 -c "
import json, sys, re
data = json.load(sys.stdin)
needle = re.compile(r'Python-${PY_VER}-macOS-support\.[^/]+\.tar\.gz')
for rel in data:
    if not rel.get('tag_name','').startswith('${PY_VER}-'):
        continue
    for a in rel.get('assets', []):
        if needle.match(a['name']):
            print(a['browser_download_url'])
            sys.exit(0)
sys.exit(1)
")"

if [ -z "$ASSET_URL" ]; then
  echo "error: no Python-${PY_VER}-macOS-support tarball found on releases"
  echo "       browse https://github.com/beeware/Python-Apple-support/releases"
  echo "       and update PY_VER above to a version that has macOS assets"
  exit 1
fi
echo "▸ asset:  $ASSET_URL"

# ── Download + extract.
mkdir -p "$WORK"
TAR="$WORK/$(basename "$ASSET_URL")"
[ -f "$TAR" ] || curl -L --fail "$ASSET_URL" -o "$TAR"
echo "▸ extracting $(basename $TAR)…"
EXTRACT_DIR="$WORK/extract"
rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"
tar -xzf "$TAR" -C "$EXTRACT_DIR"

# ── Locate the macOS slice in the extracted tree. BeeWare's tarballs
# typically ship a full Python.xcframework with macos-arm64_x86_64
# already inside, but some older revs ship a bare Python.framework —
# handle both.
MACOS_SLICE_SRC=""
for cand in \
    "$EXTRACT_DIR/Python.xcframework/macos-arm64_x86_64" \
    "$EXTRACT_DIR/Python.xcframework/macos-arm64" ; do
  [ -d "$cand" ] && MACOS_SLICE_SRC="$cand" && break
done
if [ -z "$MACOS_SLICE_SRC" ]; then
  # Bare framework form — synthesize a slice directory.
  if [ -d "$EXTRACT_DIR/Python.framework" ]; then
    MACOS_SLICE_SRC="$WORK/synth/macos-arm64_x86_64"
    mkdir -p "$MACOS_SLICE_SRC"
    cp -R "$EXTRACT_DIR/Python.framework" "$MACOS_SLICE_SRC/"
  fi
fi
[ -z "$MACOS_SLICE_SRC" ] && {
  echo "error: couldn't find Python.framework in extracted tarball"
  exit 1
}
echo "▸ macOS slice source:  $MACOS_SLICE_SRC"

# ── Reconstruct the xcframework with both old + new slices.
# `xcodebuild -create-xcframework` writes a new xcframework directory
# containing the supplied slices and a fresh Info.plist describing them.
NEW_XCF="$WORK/Python.xcframework"
rm -rf "$NEW_XCF"

CREATE_ARGS=()
for ios_slice in "$XCF"/ios-* ; do
  [ -d "$ios_slice" ] || continue
  fw="$ios_slice/Python.framework"
  [ ! -d "$fw" ] && fw="$ios_slice"  # some layouts put .framework loose
  CREATE_ARGS+=("-framework" "$fw")
done
fw_macos="$MACOS_SLICE_SRC/Python.framework"
[ ! -d "$fw_macos" ] && fw_macos="$MACOS_SLICE_SRC"
CREATE_ARGS+=("-framework" "$fw_macos")

echo "▸ creating new xcframework with $((${#CREATE_ARGS[@]} / 2)) slices…"
xcodebuild -create-xcframework \
    "${CREATE_ARGS[@]}" \
    -output "$NEW_XCF" \
    >/dev/null

# ── Replace the vendored xcframework atomically.
BACKUP="$VENDOR/Python.xcframework.bak.$(date +%s)"
mv "$XCF" "$BACKUP"
mv "$NEW_XCF" "$XCF"
echo "▸ done — old xcframework backed up at $(basename $BACKUP)"
echo "▸ slices now present:"
ls "$XCF" | grep -E '^(ios|macos)-' | sed 's/^/      /'
