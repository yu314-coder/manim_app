#!/bin/bash
# normalize-fwork-postembed.sh — runs as a build phase AFTER Embed
# Frameworks. Walks every .fwork file inside the embedded app bundle
# and strips an @executable_path/ prefix on non-archive builds.
#
# Why a separate phase: install-python-stdlib.sh's Step 13b runs
# BEFORE Embed Frameworks, so it never sees stdlib .fwork files
# (_struct.fwork, _ctypes.fwork, …) that Python.xcframework brings in
# via the embed step. Without this phase, dlopen on iPad fails with:
#   "no such file" at <App>.app/@executable_path/Frameworks/X.framework/X
# because dyld treats @executable_path in a dlopen-supplied path as a
# literal directory name rather than expanding it (the magic only
# applies to LC_LOAD_DYLIB, not to runtime path strings).
#
# For archive (App Store) builds we leave the @executable_path/ prefix
# alone — wrap-loose-dylibs.sh / inject-swift-support-archive.sh
# require the prefixed form so the loader resolves frameworks via the
# embedded layout that App Store validation expects.
set -euo pipefail

APP="${TARGET_BUILD_DIR}/${WRAPPER_NAME}"
[ -d "$APP" ] || { echo "warning: $APP not found, skipping"; exit 0; }

# Strip unconditionally — including archive / TestFlight / App Store
# builds. Earlier logic kept the @executable_path/ prefix for archives
# under the assumption the App Store validator checked .fwork contents,
# but it doesn't — validation only inspects Mach-O install_name fields
# and code signatures. dlopen at runtime, on the other hand, ALWAYS
# treats @executable_path in a user-supplied path string as a literal
# directory, so the prefixed form fails on every install path (Run,
# Debug, archive, TestFlight). The relative form
#   "Frameworks/X.framework/X"
# resolves correctly because Python.xcframework's _imp shim joins it
# against the app bundle path before passing to dlopen.

STRIPPED=0
SCANNED=0
while IFS= read -r -d '' f; do
  SCANNED=$((SCANNED + 1))
  content=$(cat "$f" 2>/dev/null || true)
  case "$content" in
    "@executable_path/"*)
      printf '%s' "${content#@executable_path/}" > "$f"
      STRIPPED=$((STRIPPED + 1))
      ;;
  esac
done < <(find "$APP" -name "*.fwork" -type f -print0 2>/dev/null)
echo "note: scanned $SCANNED .fwork files, stripped @executable_path/ from $STRIPPED"

# ── Tear out leftover python-ios-lib_*.bundle directories.
#
# install-python-stdlib.sh's Step 9 consolidates each SwiftPM resource
# bundle into app_packages/site-packages/<pkg>/ and tries to `rm -rf`
# the original .bundle right after. That doesn't survive: Xcode's
# resource-copy / embed-frameworks pass (which runs LATER) repopulates
# the .bundle directories from the SwiftPM build products. The end
# result is BOTH layouts ship: the consolidated, signed copy at
# app_packages/site-packages/numpy/ AND the unsigned original at
# python-ios-lib_NumPy.bundle/numpy/.
#
# At runtime the SwiftPM-bundle path lands earlier on sys.path and the
# import hook routes to it — but its .so files never went through our
# wrap/re-sign pipeline, so dlopen aborts with errno=1
# ("code signature invalid" / sliceOffset failure) the moment any
# C extension is touched. That's the numpy._core._multiarray_umath
# crash the user saw.
#
# Solution: delete the .bundle directories in this post-embed phase
# (which is the LAST build step), after Xcode has finished its repop
# pass. The consolidated copy in app_packages/ remains the only one,
# and the import hook routes to it.
DEL=0
shopt -s nullglob
for b in "$APP"/python-ios-lib_*.bundle; do
  rm -rf "$b" && DEL=$((DEL + 1))
done
shopt -u nullglob
echo "note: removed $DEL leftover SwiftPM resource bundles"
