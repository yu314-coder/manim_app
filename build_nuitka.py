#!/usr/bin/env python3
"""
Nuitka Build Script for Manim Studio
Compiles the application into a standalone executable with all dependencies
Based on 2025 best practices for PyWebView + Nuitka
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# Configuration
APP_NAME = "ManimStudio"
MAIN_SCRIPT = "app.py"
OUTPUT_DIR = "dist_nuitka"
BUILD_DIR = "build"

# Get the directory where this script is located
BASE_DIR = Path(__file__).parent.absolute()

def check_nuitka():
    """Check if Nuitka is installed, install if not"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"[OK] Nuitka version: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[X] Nuitka not found. Installing...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "nuitka", "ordered-set"],
                check=True
            )
            print("[OK] Nuitka installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[X] Failed to install Nuitka: {e}")
            return False

def clean_builds():
    """Clean previous builds"""
    print("\n[CLEAN] Cleaning previous builds...")
    cleaned = False

    for directory in [OUTPUT_DIR, BUILD_DIR, f"{MAIN_SCRIPT}.build", f"{MAIN_SCRIPT}.dist", f"{MAIN_SCRIPT}.onefile-build"]:
        if os.path.exists(directory):
            try:
                # On Windows, files can be locked. Try multiple times with delay.
                import time
                for attempt in range(3):
                    try:
                        shutil.rmtree(directory)
                        print(f"  [OK] Removed {directory}/")
                        cleaned = True
                        break
                    except PermissionError as e:
                        if attempt < 2:
                            print(f"  [RETRY] File locked, waiting... (attempt {attempt + 1}/3)")
                            time.sleep(1)
                        else:
                            print(f"  [WARN] Could not remove {directory}: {e}")
                            print(f"  [WARN] Please close any running instances of ManimStudio.exe and try again")
            except Exception as e:
                print(f"  [WARN] Could not remove {directory}: {e}")

    if not cleaned:
        print("  No previous builds found")

def clean_temp_assets():
    """Clean temp_assets folder to prevent bloating the EXE"""
    print("\n[CLEAN] Cleaning temp assets (prevents large EXE size)...")
    temp_assets_path = os.path.join(BASE_DIR, "web", "temp_assets")

    if os.path.exists(temp_assets_path):
        try:
            shutil.rmtree(temp_assets_path)
            print(f"  [OK] Removed web/temp_assets/ (prevents bundling user files)")
        except Exception as e:
            print(f"  [WARN] Could not remove temp_assets: {e}")
    else:
        print("  No temp_assets folder to clean")

def build():
    """Build the application with Nuitka"""
    print("=" * 60)
    print(f"Building {APP_NAME} with Nuitka")
    print("=" * 60)

    # Check Nuitka installation
    if not check_nuitka():
        return 1

    # Clean previous builds
    clean_builds()

    # Clean temp assets (prevents bloating EXE with user files)
    clean_temp_assets()

    # Check if icon exists
    icon_path = "icon.ico"
    icon_exists = os.path.exists(icon_path)

    if not icon_exists:
        print(f"\n[WARN] Warning: Icon file not found at {icon_path}")
        print("  Building without custom icon")

    # Build the Nuitka command (based on 2025 best practices)
    nuitka_cmd = [
        sys.executable,
        "-m",
        "nuitka",

        # Basic options
        "--standalone",  # Create standalone distribution
        "--onefile",  # Create single executable file
        "--assume-yes-for-downloads",  # Auto-accept downloads

        # Application info
        f"--output-filename={APP_NAME}.exe",
        "--company-name=ManimStudio",
        "--product-name=Manim Studio",
        "--file-version=1.0.0.0",
        "--product-version=1.0.0",
        "--file-description=Manim Animation Studio",
        "--copyright=Manim Studio 2025",

        # Windows-specific options
        # Use 'disable' for NO console flash (completely GUI-only application)
        # Combined with multiprocessing plugin and freeze_support() in code
        "--windows-console-mode=disable",  # Disable console completely (no flash)

        # Enable multiprocessing plugin (REQUIRED for pywebview with disabled console)
        "--plugin-enable=multiprocessing",

        # Output error logging for debugging (helps troubleshoot issues)
        "--force-stdout-spec={CACHE_DIR}/ManimStudio.out.txt",
        "--force-stderr-spec={CACHE_DIR}/ManimStudio.err.txt",
    ]

    # Add icon if exists
    if icon_exists:
        nuitka_cmd.append(f"--windows-icon-from-ico={icon_path}")

    # Continue with remaining options
    nuitka_cmd.extend([
        # Include data directories
        "--include-data-dir=web=web",  # Include entire web folder

        # Note: pywebview plugin is always enabled by Nuitka, no need to specify it

        # Don't follow these imports (saves size)
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=test",
        "--nofollow-import-to=tests",
        "--nofollow-import-to=matplotlib",
        "--nofollow-import-to=scipy",
        "--nofollow-import-to=IPython",
        "--nofollow-import-to=notebook",

        # Windows UAC settings (for antivirus compatibility)
        # Note: By default, Nuitka doesn't request admin or uiaccess
        # We're explicitly NOT adding --windows-uac-admin or --windows-uac-uiaccess
        # This ensures the exe runs with normal user privileges

        # Progress and debugging
        "--show-progress",
        "--show-memory",

        # Optimization
        "--lto=yes",  # Link Time Optimization for smaller size

        # Deployment flags (antivirus compatibility)
        "--no-deployment-flag=self-execution",  # Prevent app from calling itself
        "--no-deployment-flag=uninstall-on-shutdown",  # Don't auto-uninstall

        # Output options
        f"--output-dir={OUTPUT_DIR}",

        # Main script
        MAIN_SCRIPT
    ])

    print("\n[BUILD] Starting Nuitka compilation...")
    print(f"\nCommand options:")
    for i, arg in enumerate(nuitka_cmd):
        if arg.startswith("--") or arg == MAIN_SCRIPT:
            print(f"  {arg}")
    print()

    try:
        # Run Nuitka compilation
        result = subprocess.run(
            nuitka_cmd,
            cwd=BASE_DIR,
            check=True
        )

        print("\n" + "=" * 60)
        print("[SUCCESS] Build completed successfully!")
        print("=" * 60)

        # Find and report the executable
        exe_path = None
        if os.path.exists(OUTPUT_DIR):
            for file in os.listdir(OUTPUT_DIR):
                if file.endswith(".exe"):
                    exe_path = os.path.join(OUTPUT_DIR, file)
                    break

        if exe_path:
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n[INFO] Executable Information:")
            print(f"   Location: {exe_path}")
            print(f"   Size: {size_mb:.2f} MB")
            print(f"\n[RUN] To run the application:")
            print(f"   {exe_path}")
        else:
            print(f"\n[WARN] Executable not found in {OUTPUT_DIR}/")
            print("   Check the build logs above for errors")

        return 0

    except subprocess.CalledProcessError as e:
        print("\n" + "=" * 60)
        print("[FAILED] Build failed!")
        print("=" * 60)
        print(f"\nError code: {e.returncode}")
        print("\n[TIP] Troubleshooting tips:")
        print("1. Ensure all dependencies are installed:")
        print("   pip install nuitka ordered-set pywebview")
        print("2. Make sure app.py runs correctly before building")
        print("3. Check that the web/ folder exists with all files")
        print("4. Try building with console enabled to see errors:")
        print("   Change --windows-console-mode=disable to attach")
        print("5. Check Nuitka documentation: https://nuitka.net/")
        return 1

    except KeyboardInterrupt:
        print("\n\n[WARN] Build cancelled by user")
        return 1

    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    try:
        exit_code = build()
        print("\n" + "=" * 60)
        if exit_code == 0:
            print("Build script completed successfully")
        else:
            print("Build script completed with errors")
        print("=" * 60)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nBuild interrupted")
        sys.exit(1)
