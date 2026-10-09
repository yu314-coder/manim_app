#!/bin/bash
# Archive, patch, export and verify ManimStudio for App Store Connect.
# Uploads only when --upload is given; without it this is a full dry run.
#
#   scripts/appstore/ship.sh --build 25            # dry run: archive → patch → export → verify
#   scripts/appstore/ship.sh --build 25 --upload   # the same, then altool upload
#
# Everything happens on the internal drive (C):
#   Xcode     /Applications/Xcode.app (must be a release build, not a beta)
#   archive   ~/Library/Developer/Xcode/Archives/<date>/ManimStudio-<version>-<build>.xcarchive
#             (Xcode's own Archives folder, so it also shows in Organizer)
#   export    <archive>_export/ManimStudio.ipa, logs in <archive>_logs/
# Nothing is written under /Volumes/D/xcode.
#
# The project's CURRENT_PROJECT_VERSION is never touched: the build number is
# set in the archive only (app Info.plist + archive ApplicationProperties), and
# export is told not to manage it.
#
# Upload needs ASC_KEY_ID and ASC_ISSUER_ID in the environment and the matching
# AuthKey_<id>.p8 in ~/.private_keys. They are deliberately not in this repo.
set -euo pipefail

BUILD=""; UPLOAD=0
while [ $# -gt 0 ]; do
  case "$1" in
    --build) BUILD="$2"; shift 2 ;;
    --upload) UPLOAD=1; shift ;;
    *) echo "usage: $0 --build N [--upload]" >&2; exit 2 ;;
  esac
done
[[ "$BUILD" =~ ^[0-9]+$ ]] || { echo "--build N is required" >&2; exit 2; }

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT="$REPO/ManimStudio/ManimStudio.xcodeproj"
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
TEAM=LYK4LV2859
PUBLIC_MACOS_BUILD=25F80   # any public (non-beta) macOS build; see ARCHIVE_AND_PUSH.md §5-B

step() { printf '\n== %s\n' "$*"; }
fail() { printf '!! %s\n' "$*" >&2; exit 1; }

# ── 0. Preconditions ─────────────────────────────────────────────────
step "Xcode"
[ -d "$DEVELOPER_DIR" ] || fail "no Xcode at $DEVELOPER_DIR"
XV="$(xcodebuild -version)"; echo "$XV" | sed 's/^/   /'
XB="$(echo "$XV" | awk '/Build version/ {print $3}')"
[[ "$XB" =~ [A-Z]5[0-9]{3}[a-z]?$ ]] && fail "Xcode $XB is a beta; App Store Connect rejects beta builds"
case "$(xcodebuild -showsdks 2>/dev/null)" in *iphoneos*) ;; *) fail "no iOS SDK in this Xcode";; esac

VERSION="$(xcodebuild -project "$PROJECT" -scheme ManimStudio -showBuildSettings 2>/dev/null \
           | awk '/ MARKETING_VERSION =/ {print $3; exit}')"
[ -n "$VERSION" ] || fail "could not read MARKETING_VERSION"
echo "   ManimStudio $VERSION ($BUILD)"

DAY="$(date +%Y-%m-%d)"
ARCHIVE="$HOME/Library/Developer/Xcode/Archives/$DAY/ManimStudio-$VERSION-$BUILD.xcarchive"
EXPORT="${ARCHIVE%.xcarchive}_export"
LOGS="${ARCHIVE%.xcarchive}_logs"
mkdir -p "$(dirname "$ARCHIVE")" "$LOGS"
rm -rf "$ARCHIVE" "$EXPORT"
git -C "$REPO" log --oneline -1 > "$LOGS/HEAD.txt"
git -C "$REPO" status --short -- ManimStudio scripts >> "$LOGS/HEAD.txt"
if [ -s <(git -C "$REPO" status --short -- ManimStudio scripts) ]; then
  echo "   note: uncommitted changes in ManimStudio/ or scripts/ (listed in $LOGS/HEAD.txt)"
fi

# ── 1. Archive ───────────────────────────────────────────────────────
# Shaders.metal is SwiftTerm's optional Metal renderer, which ManimStudio never
# turns on; excluding it is how 1.5 (20)–(24) were built.
step "Archive → $ARCHIVE"
xcodebuild archive -project "$PROJECT" -scheme ManimStudio -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" -allowProvisioningUpdates \
  'EXCLUDED_SOURCE_FILE_NAMES=$(inherited) Shaders.metal' > "$LOGS/archive.log" 2>&1 \
  || { grep -E "error:" "$LOGS/archive.log" | head -20; fail "archive failed (see $LOGS/archive.log)"; }
grep -q "ARCHIVE SUCCEEDED" "$LOGS/archive.log" || fail "archive did not succeed"
echo "   ARCHIVE SUCCEEDED"

# ── 2. Patch ─────────────────────────────────────────────────────────
step "Patch (APPL→FMWK, BuildMachineOSBuild→$PUBLIC_MACOS_BUILD, CFBundleVersion=$BUILD)"
python3 - "$ARCHIVE" "$BUILD" "$PUBLIC_MACOS_BUILD" <<'PY'
import glob, os, plistlib, sys
archive, build, osbuild = sys.argv[1:4]
app = glob.glob(os.path.join(archive, "Products/Applications/*.app"))[0]
def edit(path, fn):
    raw = open(path, "rb").read()
    data = plistlib.loads(raw)
    if fn(data):
        fmt = plistlib.FMT_BINARY if raw.startswith(b"bplist") else plistlib.FMT_XML
        with open(path, "wb") as f: plistlib.dump(data, f, fmt=fmt)
        return True
    return False
def to_fmwk(d):
    if d.get("CFBundlePackageType") == "APPL":
        d["CFBundlePackageType"] = "FMWK"; return True
    return False
fmwk = sum(edit(p, to_fmwk) for p in glob.glob(os.path.join(app, "Frameworks/*.framework/Info.plist")))
def to_public(d):
    if "BuildMachineOSBuild" in d and d["BuildMachineOSBuild"] != osbuild:
        d["BuildMachineOSBuild"] = osbuild; return True
    return False
stamped = 0
for root, _, files in os.walk(app):
    if "Info.plist" in files:
        try: stamped += edit(os.path.join(root, "Info.plist"), to_public)
        except Exception as e: print("   skip", root, e)
edit(os.path.join(app, "Info.plist"), lambda d: d.__setitem__("CFBundleVersion", build) or True)
edit(os.path.join(archive, "Info.plist"),
     lambda d: d.setdefault("ApplicationProperties", {}).__setitem__("CFBundleVersion", build) or True)
print(f"   APPL→FMWK: {fmwk}   BuildMachineOSBuild restamped: {stamped}   CFBundleVersion={build}")
PY

# ── 3. Export ────────────────────────────────────────────────────────
step "Export → $EXPORT"
OPTS="$LOGS/ExportOptions.plist"
cat > "$OPTS" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key><string>app-store-connect</string>
  <key>teamID</key><string>$TEAM</string>
  <key>signingStyle</key><string>automatic</string>
  <key>destination</key><string>export</string>
  <key>uploadSymbols</key><true/>
  <key>manageAppVersionAndBuildNumber</key><false/>
</dict>
</plist>
PLIST
xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportPath "$EXPORT" \
  -exportOptionsPlist "$OPTS" -allowProvisioningUpdates > "$LOGS/export.log" 2>&1 \
  || { grep -E "error" "$LOGS/export.log" | head -20; fail "export failed (see $LOGS/export.log)"; }
IPA="$EXPORT/ManimStudio.ipa"
[ -f "$IPA" ] || fail "no IPA at $IPA"
echo "   EXPORT SUCCEEDED ($(du -h "$IPA" | cut -f1))"

# ── 4. Verify the IPA ────────────────────────────────────────────────
step "Verify"
WORK="$LOGS/verify"; rm -rf "$WORK"; mkdir -p "$WORK"; unzip -q "$IPA" -d "$WORK"
APP="$(ls -d "$WORK"/Payload/*.app)"; BIN="$APP/ManimStudio"
problems=0
bad() { echo "   FAIL $*"; problems=$((problems + 1)); }
ok()  { echo "   ok   $*"; }
V=$(/usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" "$APP/Info.plist")
B=$(/usr/libexec/PlistBuddy -c "Print CFBundleVersion" "$APP/Info.plist")
[ "$V" = "$VERSION" ] && [ "$B" = "$BUILD" ] && ok "version $V ($B)" || bad "version is $V ($B), expected $VERSION ($BUILD)"
total=0; fmwk=0; notdylib=0
for fw in "$APP"/Frameworks/*.framework; do
  total=$((total + 1))
  [ "$(/usr/libexec/PlistBuddy -c 'Print CFBundlePackageType' "$fw/Info.plist" 2>/dev/null)" = FMWK ] && fmwk=$((fmwk + 1))
  exe=$(/usr/libexec/PlistBuddy -c 'Print CFBundleExecutable' "$fw/Info.plist" 2>/dev/null)
  file "$fw/$exe" | grep -q "dynamically linked shared library" || { notdylib=$((notdylib + 1)); echo "        not MH_DYLIB: $(basename "$fw")"; }
done
[ "$total" -gt 0 ] && [ "$fmwk" = "$total" ] && ok "$total frameworks, all FMWK" || bad "$fmwk of $total frameworks are FMWK"
[ "$notdylib" = 0 ] && ok "every framework executable is MH_DYLIB" || bad "$notdylib framework executables are not MH_DYLIB"
# (grep finding nothing is the good outcome, so its exit status mustn't trip set -e)
beta=$(find "$APP" -name Info.plist -exec /usr/libexec/PlistBuddy -c "Print :BuildMachineOSBuild" {} \; 2>/dev/null | { grep -E '[a-z]$' || true; } | sort -u | tr '\n' ' ')
[ -z "$beta" ] && ok "no beta BuildMachineOSBuild stamps" || bad "beta stamps: $beta"
codesign -v --deep --strict "$APP" 2>"$LOGS/codesign.txt" && ok "codesign valid" || bad "codesign: $(head -2 "$LOGS/codesign.txt")"
for m in manimstudio_shell manimstudio_encoder; do
  [ -f "$APP/python-metadata/$m.py" ] && ok "$m.py bundled" || bad "$m.py missing from python-metadata/"
done
/usr/libexec/PlistBuddy -c 'Print :BGTaskSchedulerPermittedIdentifiers:0' "$APP/Info.plist" 2>/dev/null \
  | grep -qx 'euleryu.ManimStudio.render.\*' && ok "render task identifier in Info.plist" || bad "render task identifier missing"
# Temporary test hooks use launch-argument keys starting with "MS…"; none may ship.
hooks=$(strings -a "$BIN" | { grep -oE 'MS(Debug|Shot|AutoRender|Hold)[A-Za-z]*' || true; } | sort -u | tr '\n' ' ')
[ -z "$hooks" ] && ok "no temporary test hooks in the binary" || bad "test hooks in the binary: $hooks"
[ "$problems" = 0 ] || fail "$problems verification problem(s); not uploading"

# ── 5. Upload (only with --upload) ───────────────────────────────────
if [ "$UPLOAD" = 0 ]; then
  step "Dry run complete — not uploaded. IPA: $IPA"
  exit 0
fi
step "Upload"
: "${ASC_KEY_ID:?set ASC_KEY_ID}" "${ASC_ISSUER_ID:?set ASC_ISSUER_ID}"
API_PRIVATE_KEYS_DIR="$HOME/.private_keys" xcrun altool --upload-app -t ios -f "$IPA" \
  --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID" 2>&1 | tee "$LOGS/upload.log"
grep -q "UPLOAD SUCCEEDED" "$LOGS/upload.log" || fail "upload failed (see $LOGS/upload.log)"
grep -o "Delivery UUID: [0-9a-f-]*" "$LOGS/upload.log"
