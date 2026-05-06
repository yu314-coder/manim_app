#!/bin/bash
# install-python-stdlib.sh — Run Script build phase.
# 1. Copies BeeWare's Python stdlib into <bundle>/python-stdlib/
# 2. Re-signs every .so/.dylib (rsync + SwiftPM strip signatures, iOS rejects unsigned)
# 3. Rewrites PyAV's hardcoded /tmp/ffmpeg-ios/... install_names → @rpath/...
# 4. Bundles standalone dylibs (libfortran_io_stubs, libsf_error_state) into Frameworks/
set -e

BEEWARE="${SRCROOT}/../_vendor/beeware/Python.xcframework"
PYIOSLIB_FW="${SRCROOT}/../_vendor/python-ios-lib/Frameworks"
# CRITICAL: during archive builds, BUILT_PRODUCTS_DIR and CODESIGNING_FOLDER_PATH
# point at DIFFERENT bundle copies — Xcode signs the CODESIGNING_FOLDER_PATH copy.
# wrap-loose-dylibs.sh uses CODESIGNING_FOLDER_PATH; if we write to the other path
# our wrapped frameworks don't reach the validator. Always prefer CODESIGNING_FOLDER_PATH.
if [ -n "${CODESIGNING_FOLDER_PATH}" ] && [ -d "${CODESIGNING_FOLDER_PATH}" ]; then
  APP="${CODESIGNING_FOLDER_PATH}"
else
  APP="${BUILT_PRODUCTS_DIR}/${CONTENTS_FOLDER_PATH}"
fi
DST="$APP/python-stdlib"
FRAMEWORKS="$APP/Frameworks"
IDENT="${EXPANDED_CODE_SIGN_IDENTITY:-${CODE_SIGN_IDENTITY:--}}"
echo "install-python-stdlib: APP=$APP"

if [ ! -d "$BEEWARE" ]; then
  echo "warning: BeeWare Python.xcframework not at $BEEWARE — Python stdlib won't be bundled."
  exit 0
fi

# ── Pick the slice for this platform / arch.
case "$PLATFORM_NAME" in
  iphoneos)        SLICE="ios-arm64" ;;
  iphonesimulator) SLICE="ios-arm64_x86_64-simulator" ;;
  *) echo "warning: unknown PLATFORM_NAME '$PLATFORM_NAME'"; exit 0 ;;
esac
ARCH="${CURRENT_ARCH:-${ARCHS%% *}}"
[ "$ARCH" = "undefined_arch" ] && ARCH="arm64"

DYNLOAD_SRC="$BEEWARE/$SLICE/lib-$ARCH/python3.14/lib-dynload"
[ ! -d "$DYNLOAD_SRC" ] && DYNLOAD_SRC="$BEEWARE/$SLICE/lib/python3.14/lib-dynload"
PERARCH_DIR="$BEEWARE/$SLICE/lib-$ARCH/python3.14"
STDLIB_SRC="$BEEWARE/lib/python3.14"

# ── 1. Copy stdlib + per-arch lib-dynload + sysconfigdata.
mkdir -p "$DST"
rsync -a --delete --exclude '__pycache__' --exclude 'lib-dynload' \
  "$STDLIB_SRC/" "$DST/"
[ -d "$DYNLOAD_SRC" ] && rsync -a --delete "$DYNLOAD_SRC/" "$DST/lib-dynload/"
[ -d "$PERARCH_DIR" ] && find "$PERARCH_DIR" -maxdepth 1 -name "_sysconfigdata__*.py" -exec cp -f {} "$DST/" \;

# ── 2. Re-sign stdlib .so files.
echo "note: re-signing python-stdlib lib-dynload"
find "$DST/lib-dynload" -name "*.so" -print0 2>/dev/null | while IFS= read -r -d '' so; do
  codesign --force --sign "$IDENT" --timestamp=none --preserve-metadata=identifier,entitlements,flags "$so" 2>/dev/null \
    || codesign --force --sign "$IDENT" --timestamp=none "$so"
done

# ── 3. Bundle standalone dylibs from python-ios-lib/Frameworks/ → app Frameworks/
mkdir -p "$FRAMEWORKS"
DYLIB_COUNT=0
if [ -d "$PYIOSLIB_FW" ]; then
  while IFS= read -r -d '' src; do
    base=$(basename "$src")
    cp -f "$src" "$FRAMEWORKS/$base"
    codesign --force --sign "$IDENT" --timestamp=none "$FRAMEWORKS/$base" 2>/dev/null || true
    DYLIB_COUNT=$((DYLIB_COUNT + 1))
  done < <(find "$PYIOSLIB_FW" -maxdepth 2 -name "*.dylib" -print0)
fi
echo "note: bundled $DYLIB_COUNT dylib(s) from python-ios-lib/Frameworks → app Frameworks/"

# ── 4. Re-sign every .so/.dylib in python-ios-lib_*.bundle (SwiftPM strips sigs).
SO_COUNT=0
for b in "$APP"/python-ios-lib_*.bundle; do
  [ -d "$b" ] || continue
  while IFS= read -r -d '' lib; do
    codesign --force --sign "$IDENT" --timestamp=none --preserve-metadata=identifier,entitlements,flags "$lib" 2>/dev/null \
      || codesign --force --sign "$IDENT" --timestamp=none "$lib"
    SO_COUNT=$((SO_COUNT + 1))
  done < <(find "$b" \( -name "*.so" -o -name "*.dylib" \) -print0)
done
echo "note: re-signed $SO_COUNT shared libs across python-ios-lib_*.bundle"

# ── 5. Rewrite PyAV's hardcoded /tmp/ffmpeg-ios/... → @rpath/... and re-sign.
AV_BUNDLE="$APP/python-ios-lib_FFmpegPyAV.bundle"
fix_install_names() {
  local lib="$1"
  for old in $(otool -L "$lib" 2>/dev/null | awk '/\/tmp\/ffmpeg-ios/{print $1}'); do
    base=$(basename "$old")
    install_name_tool -change "$old" "@rpath/$base" "$lib" 2>/dev/null || true
  done
  for old in $(otool -D "$lib" 2>/dev/null | awk 'NR==2 && /\/tmp\/ffmpeg-ios/{print $1}'); do
    base=$(basename "$old")
    install_name_tool -id "@rpath/$base" "$lib" 2>/dev/null || true
  done
}
FIXED=0
for lib in "$FRAMEWORKS"/libav*.dylib "$FRAMEWORKS"/libsw*.dylib; do
  [ -f "$lib" ] && { fix_install_names "$lib"; FIXED=$((FIXED + 1)); \
    codesign --force --sign "$IDENT" --timestamp=none "$lib" 2>/dev/null || true; }
done
if [ -d "$AV_BUNDLE/av" ]; then
  while IFS= read -r -d '' so; do
    fix_install_names "$so"
    codesign --force --sign "$IDENT" --timestamp=none --preserve-metadata=identifier,entitlements,flags "$so" 2>/dev/null \
      || codesign --force --sign "$IDENT" --timestamp=none "$so"
    FIXED=$((FIXED + 1))
  done < <(find "$AV_BUNDLE/av" -name "*.so" -print0)
fi
echo "note: install_name fixups + re-sign on $FIXED dylib/so for PyAV"

# ── 6. Copy *.dist-info metadata dirs into <bundle>/python-metadata/.
# python-ios-lib's SwiftPM products only copy the package source folders
# (click/, cloup/, …) but skip *-*.dist-info dirs. importlib.metadata
# requires those dirs to resolve `version("click")` (cloup/_util.py
# crashes on this at import time). We harvest them once from the source
# repo's app_packages/site-packages/ and put them all in one dir.
META_SRC="${SRCROOT}/../_vendor/python-ios-lib/app_packages/site-packages"
META_DST="$APP/python-metadata"
META_COUNT=0
if [ -d "$META_SRC" ]; then
  mkdir -p "$META_DST"
  while IFS= read -r -d '' d; do
    base=$(basename "$d")
    cp -R "$d" "$META_DST/$base"
    META_COUNT=$((META_COUNT + 1))
  done < <(find "$META_SRC" -maxdepth 1 -type d -name "*.dist-info" -print0)
fi
echo "note: copied $META_COUNT *.dist-info dirs to $META_DST"

# ── 6b. offlinai_shell isn't exposed as a SwiftPM product but ships in
# the same site-packages tree. Without it, the in-app terminal's
# `offlinai_shell.run_line(...)` call fails with ModuleNotFoundError.
# Copy the .py and its dist-info into python-metadata/ which is on
# PYTHONPATH (set by PythonRuntime.configurePythonPathsIfNeeded).
SHELL_SRC="${SRCROOT}/../_vendor/python-ios-lib/app_packages/site-packages"
if [ -f "$SHELL_SRC/offlinai_shell.py" ]; then
  cp -f "$SHELL_SRC/offlinai_shell.py" "$META_DST/offlinai_shell.py"
  if [ -d "$SHELL_SRC/offlinai_shell-0.1.0.dist-info" ]; then
    rm -rf "$META_DST/offlinai_shell-0.1.0.dist-info"
    cp -R "$SHELL_SRC/offlinai_shell-0.1.0.dist-info" "$META_DST/"
  fi
  # Hard rebrand: rewrite "CodeBench shell" → "ManimStudio shell"
  # directly in the bundled source. The runtime monkey-patch on
  # builtins.print was unreliable (something about __builtins__ in
  # the offlinai_shell module's globals), so we just sed the literal
  # at install time and skip the dance entirely. Two banner sites in
  # the file (line ~504 in `python` builtin help, ~6286 in repl()
  # banner) — sed catches both.
  sed -i '' 's/CodeBench shell/ManimStudio shell/g' "$META_DST/offlinai_shell.py"
  echo "note: bundled offlinai_shell.py into python-metadata/ (rebranded)"
fi

# ── 7. Copy Monaco editor bundle (14 MB). Has duplicate filenames in
# subfolders (vs/basic-languages/*/monaco.contribution.js, etc.) so
# synchronized-folder flattening breaks it — rsync preserves structure.
MONACO_SRC="${SRCROOT}/../_vendor/python-ios-lib/Monaco"
MONACO_DST="$APP/Monaco"
if [ -d "$MONACO_SRC" ]; then
  rsync -a --delete --exclude '__pycache__' "$MONACO_SRC/" "$MONACO_DST/"
  echo "note: Monaco editor bundle installed at $MONACO_DST"
fi
echo "note: Python stdlib installed at $DST (slice=$SLICE, arch=$ARCH)"

# ── 8. Copy the import hook companion to wrap-loose-dylibs.sh.
# Read by PythonRuntime right after Py_Initialize so wrapped C
# extensions resolve to <App>.app/Frameworks/<X>.framework/<X>
# instead of the original (now placeholder) .so path.
HOOK_SRC=""
for cand in \
  "${BUILD_ROOT}/../../SourcePackages/checkouts/python-ios-lib/scripts/appstore/python_ios_lib_import_hook.py" \
  "${SRCROOT}/../_vendor/python-ios-lib/scripts/appstore/python_ios_lib_import_hook.py"
do
  if [ -f "$cand" ]; then HOOK_SRC="$cand"; break; fi
done
if [ -n "$HOOK_SRC" ]; then
  cp -f "$HOOK_SRC" "$DST/python_ios_lib_import_hook.py"
  echo "note: import hook installed at $DST/python_ios_lib_import_hook.py"
fi

# ── 9. Consolidate SwiftPM `python-ios-lib_*.bundle/<pkg>/` into a
# BeeWare-shaped `app_packages/site-packages/<pkg>/` tree. The
# App Store wrap script (wrap-loose-dylibs.sh) only scans
# `app_packages/`, so without this consolidation our SwiftPM-shipped
# .so files never get wrapped/re-signed and dlopen rejects them on
# device with "code signature invalid". Once consolidated, the wrap
# script sees the same layout it was designed for in CodeBench.
SITE="$APP/app_packages/site-packages"
mkdir -p "$SITE"
CONSOLIDATED=0
shopt -s nullglob
for b in "$APP"/python-ios-lib_*.bundle; do
  [ -d "$b" ] || continue
  for child in "$b"/*; do
    [ -e "$child" ] || continue
    name=$(basename "$child")
    # Skip Info.plist + _CodeSignature — bundle-only artifacts.
    case "$name" in
      Info.plist|_CodeSignature) continue ;;
    esac
    if [ -d "$child" ]; then
      # Sub-package directory — rsync into site-packages/<name>/
      # (so two bundles contributing to same pkg name merge).
      rsync -a "$child/" "$SITE/$name/"
    else
      # Single-file modules (decorator.py, six.py, etc.) — copy direct.
      cp -f "$child" "$SITE/$name"
    fi
    CONSOLIDATED=$((CONSOLIDATED + 1))
  done
  rm -rf "$b"
done
shopt -u nullglob
echo "note: consolidated $CONSOLIDATED entries into $SITE (SwiftPM bundles flattened to BeeWare layout)"

# ── 10. Wrap every .so into <name>.framework + .fwork pointer.
# This mirrors BeeWare's `install_dylib` from Python.xcframework/build/utils.sh.
# App Store rejects raw .so files anywhere in the bundle; they MUST be
# repackaged as <name>.framework/<name> with an Info.plist, and the original
# .so location replaced with a .fwork text file containing the framework
# path. BeeWare's patched _imp module reads .fwork at import time and
# dlopens the framework binary instead.
#
# Without this step, App Store Connect rejects the upload with ~250
# "binary file is not permitted" errors covering python-stdlib/lib-dynload
# and app_packages/site-packages.
PLIST_TPL="$BEEWARE/build/iOS-dylib-Info-template.plist"
BUNDLE_ID="${PRODUCT_BUNDLE_IDENTIFIER:-ai.manimstudio.app}"
WRAPPED=0

wrap_so_to_framework() {
  local FULL_EXT="$1"      # absolute path to .so
  local INSTALL_BASE="$2"  # path inside $APP, e.g. "python-stdlib/lib-dynload/" or "app_packages/"
  local EXT MODULE_PATH MODULE_NAME RELATIVE_EXT PYTHON_EXT FULL_MODULE_NAME
  local FRAMEWORK_BUNDLE_ID FRAMEWORK_FOLDER FW_DIR FW_BIN FWORK_FILE

  EXT=$(basename "$FULL_EXT")
  MODULE_PATH=$(dirname "$FULL_EXT")
  MODULE_NAME=$(echo "$EXT" | cut -d "." -f 1)
  RELATIVE_EXT=${FULL_EXT#$APP/}                      # e.g. python-stdlib/lib-dynload/_struct.cpython-...so
  PYTHON_EXT=${RELATIVE_EXT#$INSTALL_BASE}            # e.g. _struct.cpython-...so OR site-packages/numpy/_core/foo.so
  FULL_MODULE_NAME=$(echo "$PYTHON_EXT" | cut -d "." -f 1 | tr "/" ".")

  # ITMS-90338 private-API blocklist: these C extensions reference
  # private CoreText / IOKit symbols (CTFontCopyDefaultCascadeList,
  # IOPSCopyPowerSourcesInfo, etc). Per python-ios-lib README, the
  # pure-Python shims in manimpango/__init__.py and psutil's iOS subset
  # cover their public API without these binaries. Delete the .so
  # outright instead of wrapping — wrap-loose-dylibs.sh would normally
  # delete the wrapped .framework in Step 0, but only if it actually
  # runs in the right order on the right APP path. Doing it here is
  # idempotent and order-independent.
  case "$FULL_MODULE_NAME" in
    site-packages.manimpango._register_font|\
    site-packages.manimpango.cmanimpango|\
    site-packages.manimpango.enums|\
    site-packages.psutil._psutil_osx)
      rm -f "$FULL_EXT"
      return 0
      ;;
  esac

  FRAMEWORK_BUNDLE_ID=$(echo "$BUNDLE_ID.$FULL_MODULE_NAME" | tr "_" "-")
  FRAMEWORK_FOLDER="Frameworks/$FULL_MODULE_NAME.framework"
  FW_DIR="$APP/$FRAMEWORK_FOLDER"
  FW_BIN="$FW_DIR/$FULL_MODULE_NAME"
  FWORK_FILE="${FULL_EXT%.so}.fwork"

  if [ ! -d "$FW_DIR" ]; then
    mkdir -p "$FW_DIR"
    cp "$PLIST_TPL" "$FW_DIR/Info.plist"
    plutil -replace CFBundleExecutable -string "$FULL_MODULE_NAME" "$FW_DIR/Info.plist"
    plutil -replace CFBundleIdentifier -string "$FRAMEWORK_BUNDLE_ID" "$FW_DIR/Info.plist"
    # ITMS-90208 fix: BeeWare's iOS-dylib-Info-template.plist hardcodes
    # MinimumOSVersion=13.0, but the binaries are built with LC_BUILD_VERSION
    # minos matching the app's IPHONEOS_DEPLOYMENT_TARGET (17.0+). App Store
    # rejects mismatch with "does not support the minimum OS Version".
    plutil -replace MinimumOSVersion -string "${IPHONEOS_DEPLOYMENT_TARGET:-17.0}" "$FW_DIR/Info.plist"
  fi
  mv -f "$FULL_EXT" "$FW_BIN"
  echo "$FRAMEWORK_FOLDER/$FULL_MODULE_NAME" > "$FWORK_FILE"
  echo "${RELATIVE_EXT%.so}.fwork" > "$FW_DIR/$FULL_MODULE_NAME.origin"
  # Leave Mach-O as MH_BUNDLE for now — wrap-loose-dylibs.sh's
  # fix-macho-type.py handles the MH_BUNDLE→MH_DYLIB flip + LC_ID_DYLIB
  # insertion properly for archive builds. Don't run install_name_tool here:
  # it can't add a new LC_ID_DYLIB to a precompiled binary that lacks header
  # padding, leading to "MH_DYLIB is missing LC_ID_DYLIB" runtime errors.
  #
  # DO re-sign with the correct identifier matching CFBundleIdentifier.
  # iOS install rejects the bundle when the binary's code-sign identifier
  # (e.g. "codeccontext.cpython-314-iphoneos" inherited from the original
  # .so) doesn't match the framework's CFBundleIdentifier (e.g.
  # "euleryu.ManimStudio.site-packages.av.video.codeccontext").
  # codesign --remove-signature first because --preserve-metadata=identifier
  # would keep the original mismatched identifier; explicit --identifier
  # forces the new value.
  codesign --remove-signature "$FW_BIN" 2>/dev/null || true
  codesign --force --sign "$IDENT" --timestamp=none \
    --identifier "$FRAMEWORK_BUNDLE_ID" "$FW_BIN" 2>/dev/null || true
  WRAPPED=$((WRAPPED + 1))
}

if [ -f "$PLIST_TPL" ]; then
  echo "note: wrapping .so files into Frameworks/ (BeeWare install_dylib pattern)"
  # 10a. python-stdlib/lib-dynload/*.so → Frameworks/<modname>.framework/
  if [ -d "$DST/lib-dynload" ]; then
    while IFS= read -r -d '' so; do
      wrap_so_to_framework "$so" "python-stdlib/lib-dynload/"
    done < <(find "$DST/lib-dynload" -name "*.so" -type f -print0)
  fi
  # 10b. app_packages/site-packages/**/*.so → Frameworks/site-packages.<dotted>.framework/
  if [ -d "$APP/app_packages" ]; then
    while IFS= read -r -d '' so; do
      wrap_so_to_framework "$so" "app_packages/"
    done < <(find "$APP/app_packages" -name "*.so" -type f -print0)
  fi
  echo "note: wrapped $WRAPPED .so files into Frameworks/<name>.framework/"
else
  echo "warning: $PLIST_TPL missing — skipping .so→framework wrap (App Store will reject)"
fi

# ── 11. Relocate vendored .dylib files OUT of app_packages/ (App Store
# rejects raw dylibs anywhere; wrap-loose-dylibs.sh only wraps things in
# Frameworks/ top-level + scans app_packages/ but our ffmpeg/scipy dylibs
# need to be visible there for it to find them). Move into Frameworks/.
echo "note: relocating vendored .dylib from app_packages/ → Frameworks/"
RELOC=0
# 11a. ffmpeg dylibs (libavcodec, libavformat, libavutil, libswscale, libswresample, libavfilter, libavdevice)
if [ -d "$APP/app_packages/site-packages/ffmpeg" ]; then
  while IFS= read -r -d '' d; do
    mv -f "$d" "$FRAMEWORKS/$(basename "$d")"
    RELOC=$((RELOC + 1))
  done < <(find "$APP/app_packages/site-packages/ffmpeg" -name "*.dylib" -type f -print0)
  rm -rf "$APP/app_packages/site-packages/ffmpeg"
fi
# 11b. scipy_runtime dylibs
if [ -d "$APP/app_packages/site-packages/scipy_runtime" ]; then
  while IFS= read -r -d '' d; do
    mv -f "$d" "$FRAMEWORKS/$(basename "$d")"
    RELOC=$((RELOC + 1))
  done < <(find "$APP/app_packages/site-packages/scipy_runtime" -name "*.dylib" -type f -print0)
  rm -rf "$APP/app_packages/site-packages/scipy_runtime"
fi
# 11c. scipy/.dylibs/ (macOS-arm64 fortran runtimes — wrap-loose-dylibs deletes these in Step 0)
if [ -d "$APP/app_packages/site-packages/scipy/.dylibs" ]; then
  rm -rf "$APP/app_packages/site-packages/scipy/.dylibs"
fi
# 11d. scipy/special/libsf_error_state.dylib — duplicate of one in scipy_runtime
[ -f "$APP/app_packages/site-packages/scipy/special/libsf_error_state.dylib" ] && \
  rm -f "$APP/app_packages/site-packages/scipy/special/libsf_error_state.dylib"
echo "note: relocated $RELOC dylib(s) from app_packages → Frameworks/"

# ── 12. Delete nested xcframeworks under app_packages/site-packages/latex/.
# App Store validator rejects any Mach-O binary anywhere in the bundle
# except inside top-level Frameworks/<X>.framework/. The latex/ directory
# ships pdftex.xcframework + kpathsea.xcframework + ios_system.xcframework
# from the busytex bundle — but per python-ios-lib's README, the native
# pdflatex builtin is "gated off pending replacement of the 2019-era
# pdftex.xcframework" (math rendering goes through SwiftMath instead).
# So these binaries aren't called at runtime and can be safely deleted —
# the .py loader code in latex/__init__.py just skips initialization
# when the binaries are absent.
LATEX_DIR="$APP/app_packages/site-packages/latex"
DELETED_XC=0
if [ -d "$LATEX_DIR" ]; then
  while IFS= read -r -d '' xcfw; do
    rm -rf "$xcfw"
    DELETED_XC=$((DELETED_XC + 1))
  done < <(find "$LATEX_DIR" -maxdepth 2 -type d -name "*.xcframework" -print0)
fi
echo "note: deleted $DELETED_XC unused xcframework(s) from app_packages/site-packages/latex/"

# ── 13. NO Swift dylib bundling. CodeBench (which uploads successfully)
# has zero libswift*.dylib in its app/Frameworks AND zero @rpath/libswift
# references anywhere. Apple's validator only demands SwiftSupport when
# it detects a @rpath/libswift reference. The moment we bundle libswift
# dylibs, those dylibs reference each other via @rpath/libswift* — which
# triggers the validator into demanding SwiftSupport, which triggers
# ITMS-90429 "files aren't at app/Frameworks". Don't bundle. Match
# CodeBench's known-working layout: use system Swift (/usr/lib/swift),
# bundle nothing, no SwiftSupport, no @rpath/libswift refs.
echo "note: skipping Swift dylib bundling — system Swift (deployment target ≥ 17) is sufficient"

# ── 13b. Normalize .fwork file contents based on build type.
# For dev/Run builds: .fwork must contain RELATIVE paths like
#   "Frameworks/X.framework/X"
# BeeWare's _imp module resolves these against bundle root, then dlopen()
# loads them. dlopen on iOS treats @executable_path in user-passed path
# strings as a literal directory (not magic), so an @executable_path-
# prefixed .fwork content fails to load with
#   "no such file" at <App>.app/@executable_path/Frameworks/X.framework/X.
#
# For archive builds: wrap-loose-dylibs.sh's Step 0b3 rewrites .fwork to
#   "@executable_path/Frameworks/X.framework/X"
# which IS resolved by dyld in iOS hardened mode (which rejects relative
# paths). That step runs only during archive (we guarded the build phase).
#
# Problem: a previous archive run leaves @executable_path/-prefixed
# .fwork files in DerivedData. install-python-stdlib.sh's wrap function
# only rewrites .fwork if the .so is at its original location — after a
# previous run moved the .so, the wrap function skips. So old .fwork
# content lingers across builds.
#
# Fix: walk every .fwork in the build output. For dev/Run builds, strip
# any @executable_path/ prefix to restore the relative form.
IS_ARCHIVE_NOW=0
[ "$ACTION" = "install" ] && IS_ARCHIVE_NOW=1
[ -n "$ARCHIVE_PATH" ] && IS_ARCHIVE_NOW=1
if [ "$IS_ARCHIVE_NOW" != "1" ]; then
  echo "note: dev/Run build — normalizing .fwork files to relative paths"
  STRIPPED=0
  while IFS= read -r -d '' f; do
    content=$(cat "$f" 2>/dev/null)
    case "$content" in
      "@executable_path/"*)
        printf '%s' "${content#@executable_path/}" > "$f"
        STRIPPED=$((STRIPPED + 1))
        ;;
    esac
  done < <(find "$APP" -name "*.fwork" -type f -print0 2>/dev/null)
  echo "note: stripped @executable_path/ from $STRIPPED stale .fwork files"
fi

# ── 14. Flip MH_BUNDLE → MH_DYLIB + insert LC_ID_DYLIB on every wrapped
# framework binary. App Store rejects MH_BUNDLE inside .framework dirs
# ("type 'BUNDLE' that is not valid"). The proper tool is
# python-ios-lib's fix-macho-type.py which patches the byte-12 filetype
# AND inserts LC_ID_DYLIB into existing header padding (install_name_tool
# fails on padding-less precompiled binaries).
#
# Why do this here in install-python-stdlib.sh instead of relying on
# wrap-loose-dylibs.sh: that script's path resolution
# (BUILD_ROOT/../../SourcePackages/...) breaks across build configs,
# leading to silent skips. Calling fix-macho-type.py directly from
# our local scripts/ dir is reliable.
# GUARD: only run fix-macho-type.py for archive builds. For dev/Run builds
# (Xcode "build" action), we want to keep MH_BUNDLE so dlopen works
# normally — flipping to MH_DYLIB without proper LC_ID_DYLIB padding
# breaks _ctypes/_asyncio/etc loading at runtime. Apple's App Store
# validator only sees archive builds, where wrap-loose-dylibs.sh already
# runs fix-macho-type.py via its Step 3d.
IS_ARCHIVE=0
[ "$ACTION" = "install" ] && IS_ARCHIVE=1
[ -n "$ARCHIVE_PATH" ] && IS_ARCHIVE=1
case "$CONFIGURATION" in *[Rr]elease*) [ -n "$INSTALL_PATH" ] && IS_ARCHIVE=1 ;; esac

FIX_PY="${SRCROOT}/../scripts/fix-macho-type.py"
if [ "$IS_ARCHIVE" = "1" ] && [ -f "$FIX_PY" ]; then
  echo "note: archive build — running fix-macho-type.py on $APP"
  python3 "$FIX_PY" "$APP" 2>&1 | sed 's/^/  /'

  # fix-macho-type.py modifies the Mach-O bytes; re-sign each framework
  # binary with the correct CFBundleIdentifier-matching identifier so
  # the App Store validator's "code signature identifier" check passes.
  echo "note: re-signing wrapped frameworks after fix-macho-type"
  RESIGN_COUNT=0
  for fw in "$FRAMEWORKS"/site-packages.*.framework "$FRAMEWORKS"/[a-z_]*.framework; do
    [ -d "$fw" ] || continue
    plist="$fw/Info.plist"
    [ -f "$plist" ] || continue
    exe=$(/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" "$plist" 2>/dev/null)
    bid=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$plist" 2>/dev/null)
    bin="$fw/$exe"
    [ -f "$bin" ] || continue
    [ -z "$bid" ] && continue
    codesign --remove-signature "$bin" 2>/dev/null || true
    codesign --force --sign "$IDENT" --timestamp=none --identifier "$bid" "$bin" 2>/dev/null || true
    RESIGN_COUNT=$((RESIGN_COUNT + 1))
  done
  echo "note: re-signed $RESIGN_COUNT wrapped framework binaries"
elif [ "$IS_ARCHIVE" = "1" ]; then
  echo "warning: fix-macho-type.py not found at $FIX_PY — App Store will reject MH_BUNDLE"
else
  echo "note: dev/Run build (ACTION=$ACTION) — skipping fix-macho-type.py to keep dlopen working"
fi

# ── 15. Compile + bundle a BLAS stub framework for scipy.
#
# scipy.linalg.cython_blas.so links Accelerate.framework (which ships
# the bulk of BLAS / LAPACK) but references two Fortran-mangled symbols
# Apple's iOS Accelerate doesn't export:
#   _dcabs1_   — |Re(z)| + |Im(z)| for complex double
#   _lsame_    — case-insensitive single-char compare
# Both are tiny BLAS reference helpers. Without them dyld fails the
# load with "symbol not found in flat namespace '_dcabs1_'" the moment
# Python runs `from scipy.linalg import get_lapack_funcs` (or any
# scipy import that pulls cython_blas through scipy.sparse.linalg).
#
# Fix: compile a 10-line stub dylib that exports both symbols, wrap it
# as a .framework so iOS embeds it normally, and let dyld find them in
# the flat namespace. The framework is loaded eagerly by PythonRuntime
# at startup (see preloadBlasStubs) so symbols are visible before any
# `import scipy` runs.
BLAS_STUB_FW="$FRAMEWORKS/libscipy_blas_stubs.framework"
BLAS_STUB_BIN="$BLAS_STUB_FW/libscipy_blas_stubs"
if [ ! -f "$BLAS_STUB_BIN" ] || [ ! -f "$BLAS_STUB_FW/Info.plist" ]; then
  echo "note: building BLAS stub framework (libscipy_blas_stubs)"
  mkdir -p "$BLAS_STUB_FW"
  BLAS_STUB_C="${TEMP_DIR:-/tmp}/scipy_blas_stub.c"
  cat > "$BLAS_STUB_C" <<'STUB_EOF'
// libscipy_blas_stubs — provides the two Fortran-named BLAS reference
// helpers iOS Accelerate doesn't export. scipy.linalg.cython_blas.so
// references both via flat-namespace lookup; without these stubs the
// .so fails to load with "symbol not found in flat namespace".
#include <math.h>
#include <ctype.h>

// dcabs1(z) = |Re(z)| + |Im(z)|. Complex passed by reference as a
// 2-double struct (Fortran calling convention). Used by zaxpy / zrotg
// argument validation paths on tiny inputs.
double dcabs1_(const double *z) {
    return fabs(z[0]) + fabs(z[1]);
}

// lsame(ca, cb) — case-insensitive char compare returning Fortran
// LOGICAL (int 0/1). Called constantly by every BLAS routine to
// branch on UPLO / TRANS / DIAG flags ('U'/'L', 'N'/'T'/'C', etc.).
int lsame_(const char *ca, const char *cb) {
    if (!ca || !cb) return 0;
    return (toupper((unsigned char)*ca) == toupper((unsigned char)*cb)) ? 1 : 0;
}
STUB_EOF
  XCRUN_SDK="$(xcrun --sdk "$PLATFORM_NAME" --show-sdk-path)"
  if xcrun --sdk "$PLATFORM_NAME" clang \
      -arch "$ARCH" \
      -isysroot "$XCRUN_SDK" \
      -mios-version-min="${IPHONEOS_DEPLOYMENT_TARGET:-17.0}" \
      -dynamiclib \
      -install_name "@rpath/libscipy_blas_stubs.framework/libscipy_blas_stubs" \
      -o "$BLAS_STUB_BIN" \
      "$BLAS_STUB_C"; then
    cat > "$BLAS_STUB_FW/Info.plist" <<STUB_PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleDevelopmentRegion</key>      <string>en</string>
  <key>CFBundleExecutable</key>             <string>libscipy_blas_stubs</string>
  <key>CFBundleIdentifier</key>             <string>com.manimstudio.dylib.libscipy-blas-stubs</string>
  <key>CFBundleInfoDictionaryVersion</key>  <string>6.0</string>
  <key>CFBundleName</key>                   <string>libscipy_blas_stubs</string>
  <key>CFBundlePackageType</key>            <string>FMWK</string>
  <key>CFBundleShortVersionString</key>     <string>1.0</string>
  <key>CFBundleVersion</key>                <string>1</string>
  <key>MinimumOSVersion</key>               <string>${IPHONEOS_DEPLOYMENT_TARGET:-17.0}</string>
  <key>CFBundleSupportedPlatforms</key>     <array><string>iPhoneOS</string></array>
</dict></plist>
STUB_PLIST_EOF
    codesign --remove-signature "$BLAS_STUB_BIN" 2>/dev/null || true
    codesign --force --sign "$IDENT" --timestamp=none \
      --identifier "com.manimstudio.dylib.libscipy-blas-stubs" "$BLAS_STUB_BIN" || true
    echo "note: built libscipy_blas_stubs.framework"
  else
    echo "warning: failed to build libscipy_blas_stubs — scipy.linalg will trip flat-namespace lookup"
    rm -rf "$BLAS_STUB_FW"
  fi
fi

# ── 16. Bundle libfortran_io_stubs as a framework for scipy arpack/propack.
#
# scipy.sparse.linalg._eigen.arpack._arpack.so was compiled against
# the LLVM Flang Fortran runtime. It references symbols like
#   __FortranAioBeginExternalFormattedOutput
#   __FortranAStopStatement
# that are NOT in iOS Accelerate or libSystem. python-ios-lib ships a
# pre-built `libfortran_io_stubs.dylib` (66 KB) that provides every
# `__FortranA*` symbol arpack/propack pull in. Wrap it as a framework
# so iOS embeds it, then dlopen-preload at app launch (see
# preloadFortranStubs in PythonRuntime).
FORTRAN_STUB_LOOSE="$FRAMEWORKS/libfortran_io_stubs.dylib"
FORTRAN_STUB_SRC="${SRCROOT}/../_vendor/python-ios-lib/fortran/libfortran_io_stubs.dylib"
FORTRAN_STUB_FW="$FRAMEWORKS/libfortran_io_stubs.framework"
FORTRAN_STUB_BIN="$FORTRAN_STUB_FW/libfortran_io_stubs"
# Step 3 placed the loose dylib into Frameworks/. Promote it to a
# .framework here (App Store rejects raw dylibs at top level), then
# delete the loose form so wrap-loose-dylibs.sh doesn't double-wrap.
if [ ! -f "$FORTRAN_STUB_BIN" ] || [ ! -f "$FORTRAN_STUB_FW/Info.plist" ]; then
  echo "note: bundling libfortran_io_stubs.framework"
  mkdir -p "$FORTRAN_STUB_FW"
  if [ -f "$FORTRAN_STUB_LOOSE" ]; then
    mv -f "$FORTRAN_STUB_LOOSE" "$FORTRAN_STUB_BIN"
  elif [ -f "$FORTRAN_STUB_SRC" ]; then
    cp "$FORTRAN_STUB_SRC" "$FORTRAN_STUB_BIN"
  else
    echo "warning: libfortran_io_stubs.dylib not found at $FORTRAN_STUB_SRC; arpack/propack will fail to load"
    rm -rf "$FORTRAN_STUB_FW"
  fi
fi
# Always remove any leftover loose copy (idempotent across rebuilds).
rm -f "$FORTRAN_STUB_LOOSE"
# Only finalize the framework if we actually populated the binary.
if [ -f "$FORTRAN_STUB_BIN" ] && [ ! -f "$FORTRAN_STUB_FW/Info.plist" ]; then
  install_name_tool -id \
    "@rpath/libfortran_io_stubs.framework/libfortran_io_stubs" \
    "$FORTRAN_STUB_BIN" 2>/dev/null || true
  cat > "$FORTRAN_STUB_FW/Info.plist" <<FORTRAN_PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleDevelopmentRegion</key>      <string>en</string>
  <key>CFBundleExecutable</key>             <string>libfortran_io_stubs</string>
  <key>CFBundleIdentifier</key>             <string>com.manimstudio.dylib.libfortran-io-stubs</string>
  <key>CFBundleInfoDictionaryVersion</key>  <string>6.0</string>
  <key>CFBundleName</key>                   <string>libfortran_io_stubs</string>
  <key>CFBundlePackageType</key>            <string>FMWK</string>
  <key>CFBundleShortVersionString</key>     <string>1.0</string>
  <key>CFBundleVersion</key>                <string>1</string>
  <key>MinimumOSVersion</key>               <string>${IPHONEOS_DEPLOYMENT_TARGET:-17.0}</string>
  <key>CFBundleSupportedPlatforms</key>     <array><string>iPhoneOS</string></array>
</dict></plist>
FORTRAN_PLIST_EOF
  codesign --remove-signature "$FORTRAN_STUB_BIN" 2>/dev/null || true
  codesign --force --sign "$IDENT" --timestamp=none \
    --identifier "com.manimstudio.dylib.libfortran-io-stubs" "$FORTRAN_STUB_BIN" || true
  echo "note: bundled libfortran_io_stubs.framework"
fi
