#!/bin/bash
# inject-swift-support-archive.sh — Run as a SCHEME POST-ACTION after archive
# completes. Two responsibilities:
#
#   1. Populate <archive>/SwiftSupport/iphoneos/ with all Swift 5 system
#      dylibs from the Xcode toolchain (fixes ITMS-90426).
#
#   2. Generate dSYMs for every embedded framework + dylib in the .app
#      bundle, writing them to <archive>/dSYMs/. Apple's "Upload Symbols
#      Failed" warnings come from the App Store symbol service expecting
#      a dSYM-with-matching-UUID for every Mach-O in the bundle. Our 274
#      wrapped Python C-extension frameworks are pre-compiled .so files
#      with no DWARF debug info, but dsymutil still produces a minimal
#      .dSYM containing the UUID, which is all the service needs.

LOG="${PROJECT_DIR:-/tmp}/../scripts/last-archive-postaction.log"
exec > >(tee -a "$LOG") 2>&1
echo "============================================================"
echo "inject-swift-support-archive: $(date)"
echo "  ARCHIVE_PATH=${ARCHIVE_PATH:-(unset)}"
echo "  PROJECT_DIR=${PROJECT_DIR:-(unset)}"
echo "============================================================"

# Locate the archive. ARCHIVE_PATH is normally set by Xcode for archive
# post-actions. If it isn't, fall back to the most recently modified
# .xcarchive in the user's Archives folder.
ARC="$ARCHIVE_PATH"
if [ -z "$ARC" ] || [ ! -d "$ARC" ]; then
  ARC=$(ls -dt ~/Library/Developer/Xcode/Archives/*/ManimStudio*.xcarchive 2>/dev/null | head -1)
  echo "ARCHIVE_PATH was empty/invalid → falling back to: $ARC"
fi
[ -z "$ARC" ] || [ ! -d "$ARC" ] && { echo "❌ no archive found"; exit 1; }

APP=$(ls -d "$ARC/Products/Applications/"*.app 2>/dev/null | head -1)
[ -d "$APP" ] || { echo "❌ no .app inside archive"; exit 1; }

# ===========================================================================
# Part 1: SwiftSupport injection
# ===========================================================================
DEV=$(xcode-select -p)
TC=""
for cand in \
  "$DEV/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift-5.0/iphoneos" \
  "$DEV/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift-5.5/iphoneos"; do
  if [ -d "$cand" ]; then
    N=$(ls "$cand"/libswift*.dylib 2>/dev/null | wc -l | tr -d ' ')
    [ "$N" -gt "10" ] && { TC="$cand"; break; }
  fi
done

# SwiftSupport injection DISABLED — see install-python-stdlib.sh comment
# at step 13 for the full rationale. tl;dr: bundling libswift dylibs adds
# @rpath/libswift refs which trigger Apple's ITMS-90429 demand. CodeBench
# (which uploads successfully) has neither SwiftSupport nor bundled
# libswift dylibs. iOS 17+ provides Swift via /usr/lib/swift system path.
echo "→ SwiftSupport injection skipped (system Swift used; matching CodeBench layout)"
# Also REMOVE any stale SwiftSupport directory left from previous runs,
# since its presence is what triggers the validator's check chain.
rm -rf "$ARC/SwiftSupport"

# ===========================================================================
# Part 2: Generate dSYMs for every embedded framework + dylib
# ===========================================================================
# Apple's "Upload Symbols Failed" warnings require a .dSYM with a UUID
# matching each Mach-O. dsymutil produces this even for stripped binaries
# (it just won't have any actual debug symbols inside). The UUID match
# is what the symbol service checks; the empty body is fine.
echo "→ dSYM generation: walking $APP/Frameworks/"
mkdir -p "$ARC/dSYMs"

DSYM_COUNT=0
DSYM_SKIP=0

# Helper: generate dSYM for a single Mach-O binary.
gen_dsym() {
  local bin="$1"
  local dsym_name="$2"   # output filename, e.g. "_struct.framework.dSYM"
  local out="$ARC/dSYMs/$dsym_name"

  # Skip if dSYM already exists with matching UUID (Xcode generated it).
  if [ -d "$out" ]; then
    DSYM_SKIP=$((DSYM_SKIP + 1))
    return
  fi

  # dsymutil prints the dSYM file at <out>/Contents/Resources/DWARF/<exe>
  # If the binary has no debug info, dsymutil still creates the bundle
  # with the UUID record. Suppress its "no debug symbols" warning.
  if dsymutil "$bin" -o "$out" 2>/dev/null; then
    DSYM_COUNT=$((DSYM_COUNT + 1))
  fi
}

# Walk every <X>.framework/<X> binary in the app's Frameworks/.
while IFS= read -r -d '' fw; do
  plist="$fw/Info.plist"
  [ -f "$plist" ] || continue
  exe=$(/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" "$plist" 2>/dev/null)
  [ -z "$exe" ] && continue
  bin="$fw/$exe"
  [ -f "$bin" ] || continue
  gen_dsym "$bin" "$(basename "$fw").dSYM"
done < <(find "$APP/Frameworks" -maxdepth 1 -name "*.framework" -type d -print0 2>/dev/null)

# Walk every loose .dylib in Frameworks/ (e.g. Python.framework/Python is
# already covered above; this catches anything still loose).
while IFS= read -r -d '' dylib; do
  [ -f "$dylib" ] || continue
  gen_dsym "$dylib" "$(basename "$dylib").dSYM"
done < <(find "$APP/Frameworks" -maxdepth 1 -name "*.dylib" -type f -print0 2>/dev/null)

echo "  ✓ generated $DSYM_COUNT new dSYM bundles ($DSYM_SKIP already existed)"
echo "  total dSYMs in archive: $(ls "$ARC/dSYMs/" 2>/dev/null | wc -l | tr -d ' ')"

# ===========================================================================
# Final verification
# ===========================================================================
SS=$(ls "$ARC/SwiftSupport/iphoneos/"libswift*.dylib 2>/dev/null | wc -l | tr -d ' ')
DS=$(ls -d "$ARC/dSYMs/"*.dSYM 2>/dev/null | wc -l | tr -d ' ')
echo ""
echo "============================================================"
echo "Final archive state:"
echo "  SwiftSupport dylibs : $SS  (need ≥10)"
echo "  dSYM bundles        : $DS"
echo "============================================================"

if [ "$SS" -lt "10" ]; then
  echo "❌ SwiftSupport injection failed"
  exit 1
fi
echo "✓ archive ready for Distribute App → Upload"
