#!/bin/bash
# inject-swift-support.sh — fix ITMS-90426 / ITMS-90429 by post-processing
# an exported IPA file after Xcode's Distribute App → Export.
#
# Apple's App Store validator demands that every libswift*.dylib listed
# in <IPA>/SwiftSupport/iphoneos/ ALSO exist inside Payload/<App>.app/
# Frameworks/. Xcode's exportArchive strips Swift system dylibs from
# the .app during distribution because deployment target ≥ 12.2 means
# the OS provides them at runtime — but the validator still wants them
# present at submission time. This is a contradictory Apple requirement.
#
# This script:
#   1. Unzips the IPA Xcode produced
#   2. Copies all 40 Swift 5 dylibs (XCTest excluded) into both:
#        SwiftSupport/iphoneos/
#        Payload/<App>.app/Frameworks/
#   3. Codesigns the dylibs in Payload/<App>.app/Frameworks/ with the
#      same identity that signed the main app binary (so the bundle's
#      signature stays consistent)
#   4. Re-zips into a *_fixed.ipa ready for Transporter upload
#
# Usage:
#   ./scripts/inject-swift-support.sh <path/to/MyApp.ipa>
#   → produces <path/to/MyApp_fixed.ipa>

set -e

IPA="$1"
[ -z "$IPA" ] && { echo "usage: $0 <path/to/app.ipa>"; exit 1; }
[ -f "$IPA" ] || { echo "not a file: $IPA"; exit 1; }

# Find Swift 5 ABI toolchain
DEV=$(xcode-select -p)
TC=""
for cand in \
  "$DEV/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift-5.0/iphoneos" \
  "$DEV/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift-5.5/iphoneos"; do
  if [ -d "$cand" ]; then
    N=$(ls "$cand"/libswift*.dylib 2>/dev/null | wc -l | tr -d ' ')
    [ "$N" -gt "10" ] && { TC="$cand"; echo "→ toolchain: $TC ($N dylibs)"; break; }
  fi
done
[ -z "$TC" ] && { echo "❌ no usable Swift toolchain"; exit 1; }

IPA_DIR=$(cd "$(dirname "$IPA")" && pwd)
IPA_NAME=$(basename "$IPA")
APP_NAME=${IPA_NAME%.ipa}
WORK=$(mktemp -d)
OUT="$IPA_DIR/${APP_NAME}_fixed.ipa"
trap "rm -rf $WORK" EXIT

echo "→ unzipping $IPA"
unzip -q "$IPA" -d "$WORK"
APP=$(ls -d "$WORK/Payload/"*.app 2>/dev/null | head -1)
[ -d "$APP" ] || { echo "❌ no .app in Payload/"; exit 1; }
APP_BIN_NAME=$(basename "$APP" .app)
echo "  app: $APP"

# Determine the signing identity from the main app binary so we re-sign
# our injected dylibs with the matching distribution cert.
SIG_AUTH=$(codesign -dv "$APP/$APP_BIN_NAME" 2>&1 | grep "^Authority=" | head -1 | sed 's/^Authority=//')
SIG_TEAM=$(codesign -dv "$APP/$APP_BIN_NAME" 2>&1 | grep "^TeamIdentifier=" | sed 's/^TeamIdentifier=//')
echo "  app's signing authority: $SIG_AUTH (team $SIG_TEAM)"

# Find a matching identity in keychain — match Apple Distribution for the
# right team. Fall back to ad-hoc signing if no match (the IPA will then
# need to be re-signed by Transporter / App Store Connect's auto-resign).
IDENT=""
if [ -n "$SIG_TEAM" ]; then
  # Look for "Apple Distribution: ... (<team>)" first, fallback to "Apple Development".
  IDENT=$(security find-identity -v -p codesigning 2>/dev/null \
    | grep "Apple Distribution.*$SIG_TEAM\|Apple Distribution" | head -1 \
    | awk -F\" '{print $2}')
  [ -z "$IDENT" ] && IDENT=$(security find-identity -v -p codesigning 2>/dev/null \
    | grep "$SIG_TEAM" | head -1 | awk -F\" '{print $2}')
fi
echo "  re-sign identity: ${IDENT:-(ad-hoc)}"

# Inject SwiftSupport/iphoneos/ + Payload/<App>.app/Frameworks/ in lockstep.
mkdir -p "$WORK/SwiftSupport/iphoneos"
mkdir -p "$APP/Frameworks"
COUNT=0
for dylib in "$TC"/libswift*.dylib; do
  [ -f "$dylib" ] || continue
  base=$(basename "$dylib")
  [ "$base" = "libswiftXCTest.dylib" ] && continue   # ITMS-90726 — forbidden

  # SwiftSupport (manifest at IPA root)
  cp -f "$dylib" "$WORK/SwiftSupport/iphoneos/$base"

  # Bundle copy (what the validator checks)
  cp -f "$dylib" "$APP/Frameworks/$base"
  # Strip Apple's "Software Signing" Authority + re-sign with the user's
  # cert so the IPA's overall signature is internally consistent.
  codesign --remove-signature "$APP/Frameworks/$base" 2>/dev/null || true
  if [ -n "$IDENT" ]; then
    codesign --force --sign "$IDENT" --timestamp=none "$APP/Frameworks/$base" 2>/dev/null || true
  else
    # Ad-hoc — App Store Connect's auto-resign-on-upload will re-sign
    # if your account is configured for managed signing. Otherwise you
    # need the Apple Distribution cert in keychain.
    codesign --force --sign - "$APP/Frameworks/$base" 2>/dev/null || true
  fi
  COUNT=$((COUNT + 1))
done
echo "→ injected $COUNT dylibs into BOTH SwiftSupport/iphoneos/ AND Payload/$APP_BIN_NAME.app/Frameworks/"

# Re-sign the .app bundle as a whole so its CodeResources reflects the
# new dylibs we added. Without this, the .app's overall signature is
# stale and Apple's validator may reject with "code object is invalid".
if [ -n "$IDENT" ]; then
  echo "→ re-signing $APP_BIN_NAME.app (deep) with $IDENT"
  codesign --force --sign "$IDENT" --timestamp=none --deep \
    --preserve-metadata=identifier,entitlements,flags \
    "$APP" 2>&1 | tail -5 || true
fi

# Re-zip
echo "→ packaging $OUT"
rm -f "$OUT"
(cd "$WORK" && zip -qr "$OUT" Payload SwiftSupport)

# Verify
echo ""
echo "=== verification ==="
echo "SwiftSupport/iphoneos/:        $(unzip -l "$OUT" | grep -c "SwiftSupport/iphoneos/libswift")"
echo "Payload/.../Frameworks libswift: $(unzip -l "$OUT" | grep -c "Payload/.*\.app/Frameworks/libswift")"
echo "libswiftXCTest present?        $(unzip -l "$OUT" | grep -c libswiftXCTest)  (must be 0)"

echo ""
echo "✓ done: $OUT"
echo ""
echo "Upload via Transporter.app (drag & drop) or:"
echo "  xcrun altool --upload-app -f \"$OUT\" -t ios -u <appleid> -p <app-pwd>"
