#!/usr/bin/env python3
"""
Create DMG installer for Manim Studio.

Packages a built ManimStudio.app into a distributable .dmg file.
Supports both Apple Silicon (arm64) and Intel (x86_64) builds.

Usage:
    python3 create_dmg.py              # interactive — prompts for arch
    python3 create_dmg.py --arch arm64
    python3 create_dmg.py --arch x86_64
    python3 create_dmg.py --arch both  # creates both DMGs
"""

import os
import sys
import shutil
import subprocess
import tempfile
import argparse
from pathlib import Path

APP_NAME = "ManimStudio"
VERSION = "1.2.0"
BASE_DIR = Path(__file__).parent.absolute()


def find_app_bundle(arch):
    """Find the .app bundle for the given architecture."""
    dist_dir = BASE_DIR / f"dist_nuitka_{arch}"
    if not dist_dir.exists():
        return None, dist_dir

    # Look for ManimStudio.app first, then fall back to any .app
    app_path = dist_dir / f"{APP_NAME}.app"
    if app_path.exists():
        return app_path, dist_dir

    # Fallback: find any .app (e.g. app.app from older builds)
    for p in dist_dir.iterdir():
        if p.suffix == '.app' and p.is_dir():
            # Rename to ManimStudio.app
            target = dist_dir / f"{APP_NAME}.app"
            print(f"[..] Renaming {p.name} -> {APP_NAME}.app")
            p.rename(target)
            return target, dist_dir

    return None, dist_dir


def create_dmg_for_arch(arch):
    """Create a .dmg for the given architecture. Returns 0 on success."""
    app_bundle, dist_dir = find_app_bundle(arch)

    if not app_bundle:
        print(f"\n[ERROR] No .app bundle found in {dist_dir}/")
        print(f"  Build first with: python3 build_nuitka.py --arch {arch}")
        return 1

    arch_label = "Apple Silicon" if arch == "arm64" else "Intel"
    dmg_name = f"{APP_NAME}-{VERSION}-macOS-{arch}.dmg"
    dmg_path = BASE_DIR / dmg_name

    print(f"\n{'=' * 60}")
    print(f"  Creating DMG — {arch_label} ({arch})")
    print(f"{'=' * 60}")
    print(f"\n  App:    {app_bundle}")
    print(f"  Output: {dmg_path}")

    # App size
    app_size = sum(
        f.stat().st_size for f in app_bundle.rglob("*") if f.is_file()
    ) / (1024 * 1024)
    print(f"  App size: {app_size:.1f} MB")

    # Remove old DMG
    if dmg_path.exists():
        dmg_path.unlink()
        print(f"\n  [OK] Removed old {dmg_name}")

    # Try create-dmg first (prettier), fall back to hdiutil
    has_create_dmg = shutil.which("create-dmg") is not None

    if has_create_dmg:
        print(f"\n[..] Building DMG with create-dmg...")
        cmd = [
            "create-dmg",
            "--volname", APP_NAME,
            "--window-pos", "200", "120",
            "--window-size", "660", "400",
            "--icon-size", "100",
            "--icon", app_bundle.name, "180", "190",
            "--app-drop-link", "480", "190",
            "--hide-extension", app_bundle.name,
            "--no-internet-enable",
        ]

        # Add volume icon if available
        volicon = BASE_DIR / "icon.icns"
        if volicon.exists():
            cmd.extend(["--volicon", str(volicon)])

        cmd.extend([str(dmg_path), str(dist_dir)])

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[WARN] create-dmg failed (exit {e.returncode}), "
                  f"falling back to hdiutil")
            has_create_dmg = False

    if not has_create_dmg:
        print(f"\n[..] Building DMG with hdiutil...")
        with tempfile.TemporaryDirectory() as staging:
            staging = Path(staging)

            # Copy .app into staging area
            staged_app = staging / app_bundle.name
            print(f"  Copying {app_bundle.name} to staging...")
            shutil.copytree(app_bundle, staged_app, symlinks=True)

            # Create Applications symlink for drag-and-drop install
            (staging / "Applications").symlink_to("/Applications")

            subprocess.run([
                "hdiutil", "create",
                "-volname", APP_NAME,
                "-srcfolder", str(staging),
                "-ov",
                "-format", "UDZO",
                str(dmg_path),
            ], check=True)

    if dmg_path.exists():
        size_mb = dmg_path.stat().st_size / (1024 * 1024)
        print(f"\n{'=' * 60}")
        print(f"  [SUCCESS] {dmg_name}")
        print(f"  Size: {size_mb:.1f} MB")
        print(f"  Path: {dmg_path}")
        print(f"{'=' * 60}")
        return 0
    else:
        print(f"\n[ERROR] DMG creation failed")
        return 1


def prompt_arch():
    """Ask user which architecture to create DMG for."""
    # Check what builds exist
    has_arm64 = (BASE_DIR / "dist_nuitka_arm64").exists()
    has_x86 = (BASE_DIR / "dist_nuitka_x86_64").exists()

    print(f"\n{'=' * 60}")
    print(f"  Manim Studio — Create DMG Installer")
    print(f"{'=' * 60}")

    if has_arm64 and has_x86:
        print("\n  Found builds for both architectures.\n")
        print("  [1] Apple Silicon (arm64)")
        print("  [2] Intel (x86_64)")
        print("  [3] Both")
        print()
        while True:
            choice = input("  Enter 1, 2, or 3: ").strip()
            if choice == '1':
                return 'arm64'
            elif choice == '2':
                return 'x86_64'
            elif choice == '3':
                return 'both'
            print("  Invalid choice.")
    elif has_arm64:
        print("\n  Found build: dist_nuitka_arm64/")
        return 'arm64'
    elif has_x86:
        print("\n  Found build: dist_nuitka_x86_64/")
        return 'x86_64'
    else:
        print("\n  [ERROR] No builds found.")
        print("  Run build_nuitka.py first to create a .app bundle.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Create DMG installer for Manim Studio"
    )
    parser.add_argument(
        "--arch", choices=["arm64", "x86_64", "both"],
        help="Target architecture (prompted if not specified)"
    )
    args = parser.parse_args()

    arch = args.arch or prompt_arch()

    if arch == 'both':
        rc1 = create_dmg_for_arch('arm64')
        rc2 = create_dmg_for_arch('x86_64')
        rc = rc1 or rc2
    else:
        rc = create_dmg_for_arch(arch)

    if rc == 0:
        print(f"\nDone!")
    sys.exit(rc)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(1)
