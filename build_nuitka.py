#!/usr/bin/env python3
"""
Nuitka Build Script for Manim Studio
Builds ManimStudio.app (macOS) or ManimStudio.exe (Windows).
On macOS, also creates a distributable .dmg installer.

macOS: Supports both Apple Silicon (arm64) and Intel (x86_64) builds.
       Uses .venv for arm64 and venv_intel for x86_64 (Rosetta).

Feature modules included automatically via Python import chain:
  app.py -> ai_edit.py, narration_addon.py
Web assets included via --include-data-dir=web=web
"""

import os
import sys
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

# Configuration
APP_NAME = "ManimStudio"
MAIN_SCRIPT = "app.py"
OUTPUT_DIR = "dist_nuitka"  # Windows default; macOS overrides per-arch
BUILD_DIR = "build"
VERSION = "1.2.0"


def get_output_dir(arch=None):
    """Return arch-specific output directory on macOS."""
    if arch:
        return f"dist_nuitka_{arch}"
    return OUTPUT_DIR

BASE_DIR = Path(__file__).parent.absolute()
IS_MACOS = sys.platform == 'darwin'
IS_WINDOWS = sys.platform == 'win32'


# ── Helpers ──────────────────────────────────────────────────────────────────

def prompt_arch():
    """Ask user which architecture to build for (macOS only)."""
    print("\n" + "=" * 60)
    print("  Manim Studio — macOS Build")
    print("=" * 60)
    print("\n  Which architecture do you want to build for?\n")
    print("  [1] Apple Silicon (arm64)  — M1/M2/M3/M4")
    print("  [2] Intel (x86_64)         — via Rosetta / venv_intel")
    print()

    while True:
        choice = input("  Enter 1 or 2: ").strip()
        if choice == '1':
            return 'arm64'
        elif choice == '2':
            return 'x86_64'
        else:
            print("  Invalid choice. Please enter 1 or 2.")


def get_venv_python(arch):
    """Return the Python executable path for the given architecture."""
    if IS_MACOS:
        if arch == 'x86_64':
            venv = BASE_DIR / 'venv_intel'
            if not venv.exists():
                print(f"\n[ERROR] venv_intel not found at {venv}")
                print("  Create it with: arch -x86_64 python3 -m venv venv_intel")
                sys.exit(1)
            python = venv / 'bin' / 'python'
        else:
            venv = BASE_DIR / '.venv'
            if not venv.exists():
                print(f"\n[ERROR] .venv not found at {venv}")
                print("  Create it with: python3 -m venv .venv")
                sys.exit(1)
            python = venv / 'bin' / 'python'
    else:
        # Windows: use current interpreter
        return sys.executable

    if not python.exists():
        print(f"\n[ERROR] Python not found at {python}")
        sys.exit(1)

    return str(python)


def check_nuitka(python):
    """Check if Nuitka is installed, install if not."""
    try:
        result = subprocess.run(
            [python, "-m", "nuitka", "--version"],
            capture_output=True, text=True, check=True
        )
        print(f"[OK] Nuitka version: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[..] Nuitka not found. Installing...")
        try:
            subprocess.run(
                [python, "-m", "pip", "install", "nuitka", "ordered-set"],
                check=True
            )
            print("[OK] Nuitka installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to install Nuitka: {e}")
            return False


def clean_builds(output_dir=OUTPUT_DIR):
    """Clean previous build artifacts."""
    print("\n[CLEAN] Cleaning previous builds...")
    cleaned = False
    dirs_to_clean = [
        output_dir, BUILD_DIR,
        f"{MAIN_SCRIPT}.build", f"{MAIN_SCRIPT}.dist",
        f"{MAIN_SCRIPT}.onefile-build",
    ]
    for d in dirs_to_clean:
        path = BASE_DIR / d
        if path.exists():
            for attempt in range(3):
                try:
                    shutil.rmtree(path)
                    print(f"  [OK] Removed {d}/")
                    cleaned = True
                    break
                except PermissionError:
                    if attempt < 2:
                        time.sleep(1)
                    else:
                        print(f"  [WARN] Could not remove {d}")
                except Exception as e:
                    print(f"  [WARN] Could not remove {d}: {e}")
                    break
    if not cleaned:
        print("  No previous builds found")


def clean_temp_assets():
    """Clean temp_assets folder to prevent bloating the app."""
    temp_path = BASE_DIR / "web" / "temp_assets"
    if temp_path.exists():
        try:
            shutil.rmtree(temp_path)
            print("[OK] Removed web/temp_assets/")
        except Exception as e:
            print(f"[WARN] Could not remove temp_assets: {e}")


def create_icns():
    """Convert icon.ico to icon.icns for macOS app bundle.
    Returns the path to the .icns file, or None if conversion fails."""
    ico_path = BASE_DIR / "icon.ico"
    icns_path = BASE_DIR / "icon.icns"

    if icns_path.exists():
        print("[OK] icon.icns already exists")
        return str(icns_path)

    if not ico_path.exists():
        print("[WARN] icon.ico not found, building without icon")
        return None

    print("[..] Converting icon.ico -> icon.icns...")
    try:
        # Extract PNG from .ico using sips, then build iconset
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Convert .ico to a base PNG via sips
            base_png = tmp / "icon_base.png"
            subprocess.run(
                ["sips", "-s", "format", "png", str(ico_path),
                 "--out", str(base_png)],
                capture_output=True, check=True
            )

            # Create iconset with required sizes
            iconset = tmp / "icon.iconset"
            iconset.mkdir()
            sizes = [
                (16, "icon_16x16.png"),
                (32, "icon_16x16@2x.png"),
                (32, "icon_32x32.png"),
                (64, "icon_32x32@2x.png"),
                (128, "icon_128x128.png"),
                (256, "icon_128x128@2x.png"),
                (256, "icon_256x256.png"),
                (512, "icon_256x256@2x.png"),
                (512, "icon_512x512.png"),
                (1024, "icon_512x512@2x.png"),
            ]
            for size, name in sizes:
                subprocess.run(
                    ["sips", "-z", str(size), str(size),
                     str(base_png), "--out", str(iconset / name)],
                    capture_output=True, check=True
                )

            # Convert iconset to icns
            subprocess.run(
                ["iconutil", "-c", "icns", str(iconset),
                 "-o", str(icns_path)],
                check=True
            )
            print(f"[OK] Created {icns_path}")
            return str(icns_path)

    except Exception as e:
        print(f"[WARN] Icon conversion failed: {e}")
        return None


# ── macOS Build ──────────────────────────────────────────────────────────────

def build_macos(arch, use_lto=True):
    """Build ManimStudio.app for macOS."""
    output_dir = get_output_dir(arch)
    python = get_venv_python(arch)
    arch_prefix = []
    if arch == 'x86_64':
        arch_prefix = ['arch', '-x86_64']

    print("=" * 60)
    print(f"  Building {APP_NAME}.app — macOS {arch}")
    print(f"  Output: {output_dir}/")
    print("=" * 60)

    if not check_nuitka(python):
        return 1

    clean_builds(output_dir)
    clean_temp_assets()

    icns_path = create_icns()

    nuitka_cmd = arch_prefix + [
        python, "-m", "nuitka",

        "--standalone",
        "--assume-yes-for-downloads",
        "--macos-create-app-bundle",
        f"--output-filename={APP_NAME}",
        f"--macos-app-name={APP_NAME}",
        f"--macos-app-version={VERSION}",

        f"--product-name={APP_NAME}",
        f"--product-version={VERSION}",
        f"--company-name={APP_NAME}",
        "--file-description=Manim Animation Studio",
        f"--copyright={APP_NAME} 2025",
    ]

    if icns_path:
        nuitka_cmd.append(f"--macos-app-icon={icns_path}")

    nuitka_cmd.extend([
        "--include-data-dir=web=web",

        # Terminal PTY modules (not auto-detected since they're
        # conditionally imported inside try/except)
        "--include-module=pty",
        "--include-module=fcntl",
        "--include-module=termios",
        "--include-module=select",
        "--include-module=struct",

        # pyobjc frameworks required by pywebview on macOS
        "--include-package=objc",
        "--include-package=WebKit",
        "--include-package=Cocoa",
        "--include-package=Quartz",

        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=test",
        "--nofollow-import-to=tests",
        "--nofollow-import-to=matplotlib",
        "--nofollow-import-to=scipy",
        "--nofollow-import-to=IPython",
        "--nofollow-import-to=notebook",

        "--show-progress",
        "--show-memory",

        f"--output-dir={output_dir}",
    ])

    if use_lto:
        nuitka_cmd.append("--lto=yes")
    else:
        nuitka_cmd.append("--lto=no")

    nuitka_cmd.append(MAIN_SCRIPT)

    print(f"\n[BUILD] Starting Nuitka compilation ({arch})...")
    print(f"\nUsing Python: {python}")
    print(f"Output dir:   {output_dir}/")
    print(f"\nCommand options:")
    for arg in nuitka_cmd:
        if isinstance(arg, str) and (arg.startswith("--") or arg == MAIN_SCRIPT):
            print(f"  {arg}")
    print()

    try:
        subprocess.run(nuitka_cmd, cwd=BASE_DIR, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[FAILED] Build failed (exit code {e.returncode})")
        print("\n[TIP] Troubleshooting:")
        print(f"  1. Ensure dependencies: {python} -m pip install nuitka ordered-set pywebview pillow psutil")
        print("  2. Make sure app.py runs correctly before building")
        print("  3. Check that the web/ folder exists")
        return 1
    except KeyboardInterrupt:
        print("\n\n[WARN] Build cancelled")
        return 1

    # Find the .app bundle and ensure it's named ManimStudio.app
    output_path = BASE_DIR / output_dir
    app_bundle = None
    for p in output_path.rglob("*.app"):
        if p.is_dir():
            app_bundle = p
            break

    if not app_bundle:
        print(f"\n[WARN] .app bundle not found in {output_dir}/")
        return 1

    expected = output_path / f"{APP_NAME}.app"
    if app_bundle != expected:
        print(f"[..] Renaming {app_bundle.name} -> {APP_NAME}.app")
        if expected.exists():
            shutil.rmtree(expected)
        app_bundle.rename(expected)
        app_bundle = expected

    size_mb = sum(
        f.stat().st_size for f in app_bundle.rglob("*") if f.is_file()
    ) / (1024 * 1024)

    print("\n" + "=" * 60)
    print("[SUCCESS] Build completed!")
    print("=" * 60)
    print(f"\n  App:  {app_bundle}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"  Arch: {arch}")

    return 0


# ── DMG Creation ─────────────────────────────────────────────────────────────

def create_dmg(arch):
    """Create a .dmg installer from the built .app bundle."""
    output_dir = get_output_dir(arch)
    output_path = BASE_DIR / output_dir

    # Find the .app bundle
    app_bundle = None
    for p in output_path.rglob("*.app"):
        if p.is_dir():
            app_bundle = p
            break

    if not app_bundle:
        print("[ERROR] No .app bundle found. Run the build first.")
        return 1

    arch_suffix = "arm64" if arch == "arm64" else "x86_64"
    dmg_name = f"{APP_NAME}-{VERSION}-macOS-{arch_suffix}.dmg"
    dmg_path = BASE_DIR / dmg_name

    # Remove old DMG if exists
    if dmg_path.exists():
        dmg_path.unlink()

    # Check if create-dmg is available (prettier DMGs)
    has_create_dmg = shutil.which("create-dmg") is not None

    if has_create_dmg:
        print(f"\n[DMG] Creating {dmg_name} with create-dmg...")
        cmd = [
            "create-dmg",
            "--volname", APP_NAME,
            "--window-pos", "200", "120",
            "--window-size", "660", "400",
            "--icon-size", "100",
            "--icon", app_bundle.name, "180", "190",
            "--app-drop-link", "480", "190",
            "--hide-extension", app_bundle.name,
        ]

        # Add background icon if .icns exists
        volicon = BASE_DIR / "icon.icns"
        if volicon.exists():
            cmd.extend(["--volicon", str(volicon)])

        cmd.extend([str(dmg_path), str(app_bundle.parent)])

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[WARN] create-dmg failed (exit code {e.returncode}), falling back to hdiutil")
            has_create_dmg = False

    if not has_create_dmg:
        # Fallback: hdiutil (always available on macOS)
        print(f"\n[DMG] Creating {dmg_name} with hdiutil...")
        with tempfile.TemporaryDirectory() as staging:
            staging = Path(staging)
            # Copy .app to staging
            staged_app = staging / app_bundle.name
            shutil.copytree(app_bundle, staged_app, symlinks=True)
            # Create Applications symlink
            (staging / "Applications").symlink_to("/Applications")

            subprocess.run([
                "hdiutil", "create",
                "-volname", APP_NAME,
                "-srcfolder", str(staging),
                "-ov", "-format", "UDZO",
                str(dmg_path),
            ], check=True)

    if dmg_path.exists():
        size_mb = dmg_path.stat().st_size / (1024 * 1024)
        print("\n" + "=" * 60)
        print("[SUCCESS] DMG created!")
        print("=" * 60)
        print(f"\n  DMG:  {dmg_path}")
        print(f"  Size: {size_mb:.1f} MB")
        return 0
    else:
        print("[ERROR] DMG creation failed")
        return 1


# ── Windows Build ────────────────────────────────────────────────────────────

def build_windows(onefile=True, console_mode="disable", use_lto=True,
                  onefile_profile="compact"):
    """Build ManimStudio.exe for Windows."""
    python = sys.executable

    print("=" * 60)
    print(f"  Building {APP_NAME}.exe — Windows")
    print("=" * 60)

    if not check_nuitka(python):
        return 1

    clean_builds()
    clean_temp_assets()

    icon_path = BASE_DIR / "icon.ico"

    nuitka_cmd = [
        python, "-m", "nuitka",

        "--standalone",
        "--assume-yes-for-downloads",

        f"--output-filename={APP_NAME}.exe",
        f"--company-name={APP_NAME}",
        f"--product-name={APP_NAME}",
        f"--file-version={VERSION}",
        f"--product-version={VERSION}",
        "--file-description=Manim Animation Studio",
        f"--copyright={APP_NAME} 2025",

        f"--windows-console-mode={console_mode}",
        "--plugin-enable=multiprocessing",

        "--force-stdout-spec={CACHE_DIR}/ManimStudio.out.txt",
        "--force-stderr-spec={CACHE_DIR}/ManimStudio.err.txt",
    ]

    if icon_path.exists():
        nuitka_cmd.append(f"--windows-icon-from-ico={icon_path}")

    nuitka_cmd.extend([
        "--include-data-dir=web=web",

        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=test",
        "--nofollow-import-to=tests",
        "--nofollow-import-to=matplotlib",
        "--nofollow-import-to=scipy",
        "--nofollow-import-to=IPython",
        "--nofollow-import-to=notebook",

        "--show-progress",
        "--show-memory",

        "--no-deployment-flag=self-execution",
        "--no-deployment-flag=uninstall-on-shutdown",

        f"--output-dir={OUTPUT_DIR}",
    ])

    if onefile:
        nuitka_cmd.insert(nuitka_cmd.index("--assume-yes-for-downloads"), "--onefile")
        nuitka_cmd.extend([
            "--onefile-tempdir-spec={CACHE_DIR}/{COMPANY}/{PRODUCT}/{VERSION}",
            "--onefile-cache-mode=cached",
            "--include-windows-runtime-dlls=yes",
        ])
        if onefile_profile == "stable":
            nuitka_cmd.append("--onefile-no-compression")

    nuitka_cmd.append("--lto=yes" if use_lto else "--lto=no")
    nuitka_cmd.append(MAIN_SCRIPT)

    print(f"\n[BUILD] Starting Nuitka compilation...")
    print(f"\nCommand options:")
    for arg in nuitka_cmd:
        if arg.startswith("--") or arg == MAIN_SCRIPT:
            print(f"  {arg}")
    print()

    try:
        subprocess.run(nuitka_cmd, cwd=BASE_DIR, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[FAILED] Build failed (exit code {e.returncode})")
        return 1
    except KeyboardInterrupt:
        print("\n\n[WARN] Build cancelled")
        return 1

    # Find executable
    output_path = BASE_DIR / OUTPUT_DIR
    exe_path = None
    for p in output_path.rglob("*.exe"):
        if p.name.lower() == f"{APP_NAME}.exe".lower():
            exe_path = p
            break

    if exe_path:
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print("\n" + "=" * 60)
        print("[SUCCESS] Build completed!")
        print("=" * 60)
        print(f"\n  EXE:  {exe_path}")
        print(f"  Size: {size_mb:.1f} MB")
    else:
        print(f"\n[WARN] Executable not found in {OUTPUT_DIR}/")

    return 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build Manim Studio with Nuitka")

    if IS_MACOS:
        parser.add_argument(
            "--arch", choices=["arm64", "x86_64"],
            help="Target architecture (prompted if not specified)"
        )
        parser.add_argument(
            "--no-dmg", action="store_true",
            help="Skip DMG creation after building the .app"
        )
    else:
        parser.add_argument(
            "--onefile", action="store_true", default=True,
            help="Build single-file executable (default)"
        )
        parser.add_argument(
            "--standalone-folder", action="store_true",
            help="Build folder-based standalone instead of onefile"
        )
        parser.add_argument(
            "--console-mode", choices=["disable", "attach"],
            default="disable", help="Windows console mode"
        )
        parser.add_argument(
            "--onefile-profile", choices=["stable", "compact"],
            default="compact", help="Onefile tuning profile"
        )

    parser.add_argument(
        "--no-lto", action="store_true",
        help="Disable link-time optimization"
    )

    args = parser.parse_args()

    if IS_MACOS:
        arch = args.arch or prompt_arch()
        print(f"\n[INFO] Building for: {arch}")

        rc = build_macos(arch=arch, use_lto=not args.no_lto)
        if rc != 0:
            sys.exit(rc)

        if not args.no_dmg:
            rc = create_dmg(arch)

        print("\n" + "=" * 60)
        print("  Build script completed" +
              (" successfully" if rc == 0 else " with errors"))
        print("=" * 60)
        sys.exit(rc)

    else:
        onefile = args.onefile and not args.standalone_folder
        rc = build_windows(
            onefile=onefile,
            console_mode=args.console_mode,
            use_lto=not args.no_lto,
            onefile_profile=args.onefile_profile,
        )
        print("\n" + "=" * 60)
        print("  Build script completed" +
              (" successfully" if rc == 0 else " with errors"))
        print("=" * 60)
        sys.exit(rc)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBuild interrupted")
        sys.exit(1)
