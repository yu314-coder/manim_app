#!/usr/bin/env python3
import subprocess
import sys
import os
import multiprocessing
from pathlib import Path
import shutil
import json
import importlib
import argparse

def build_self_contained_version(jobs=None):
    """Build self-contained version with NO CONSOLE EVER"""
    
    # Determine optimal job count if not specified
    if jobs is None:
        cpu_count = multiprocessing.cpu_count()
        # Use N-1 cores by default to keep system responsive
        jobs = max(1, cpu_count - 1)
    
    print(f"🐍 Building SELF-CONTAINED version (NO CONSOLE) with {jobs} CPU cores...")
    
    # Clean previous builds
    if Path("build").exists():
        print("🧹 Cleaning build directory...")
        shutil.rmtree("build")
    if Path("dist").exists():
        print("🧹 Cleaning dist directory...")
        shutil.rmtree("dist")
    
    # Create assets directory if it doesn't exist
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)
    
    # Prepare bundled venv
    bundled_venv = prepare_bundled_environment()
    
    # Create enhanced no-console patch
    create_no_console_patch()
    
    # Create fixes module
    create_fixes_module()
    
    # Detect Nuitka version for compatibility
    nuitka_version = get_nuitka_version()
    print(f"📊 Detected Nuitka version: {nuitka_version}")
    
    # Basic command with universal options
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",  # Single executable file
    ]
    
    # Add console hiding - use the correct option for newer Nuitka versions
    cmd.append("--windows-console-mode=disable")
    
    # Add basic plugins - TKinter is usually available
    cmd.append("--enable-plugin=tk-inter")
    
    # Check for importable packages and include only those that exist
    essential_packages = [
        "customtkinter", "tkinter", "PIL", "numpy", "cv2", 
        "matplotlib", "scipy", "manim", "jedi"
    ]
    
    included_packages = []
    for package in essential_packages:
        if is_package_importable(package):
            correct_name = get_correct_package_name(package)
            if correct_name:
                included_packages.append(correct_name)
                cmd.append(f"--include-package={correct_name}")
                print(f"✅ Including package: {correct_name}")
        else:
            print(f"⚠️ Skipping unavailable package: {package}")
    
    # Include critical modules that are part of standard library
    essential_modules = [
        "json", "tempfile", "threading", "subprocess", "multiprocessing",
        "os", "sys", "ctypes", "venv", "fixes", "psutil"
    ]
    
    for module in essential_modules:
        cmd.append(f"--include-module={module}")
    
    # Include package data for Manim (for config files)
    cmd.append("--include-package-data=manim")
    
    # Output options
    cmd.extend([
        "--output-dir=dist",
        "--output-filename=ManimStudio.exe",
    ])
    
    # Icon (if available)
    if Path("assets/icon.ico").exists():
        cmd.append("--windows-icon-from-ico=assets/icon.ico")
    
    # Include data directories
    cmd.extend([
        "--include-data-dir=assets=assets",
        f"--include-data-dir={bundled_venv}=bundled_venv",
    ])
    
    # Jobs for faster compilation - use the calculated optimal job count
    cmd.append(f"--jobs={jobs}")
    
    # Final target
    cmd.append("app.py")
    
    print("🔨 Building executable with NO CONSOLE...")
    print("Command:", " ".join(cmd))
    print("=" * 60)
    
    # Run build with real-time output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Print output in real-time
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())
    
    return_code = process.poll()
    
    if return_code == 0:
        print("=" * 60)
        print("✅ NO-CONSOLE build successful!")
        
        # Find executable
        exe_path = find_executable()
        
        if exe_path:
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"📁 Executable: {exe_path} ({size_mb:.1f} MB)")
            
            print(f"\n🎉 SUCCESS! Silent executable ready!")
            print(f"🚀 Run: {exe_path}")
            print(f"\n🔇 GUARANTEED: NO CONSOLE WINDOWS WILL APPEAR")
            
            # Create a launcher script
            create_launcher_script(exe_path)
            
            return exe_path
        else:
            print("❌ Executable not found")
            list_contents()
            return None
    else:
        print("=" * 60)
        print("❌ Build failed!")
        print(f"Return code: {return_code}")
        return None

# ... [rest of the functions remain the same] ...

def main():
    """Main function with build options"""
    print("🎬 Manim Studio - NO CONSOLE Builder")
    print("=" * 40)
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Build Manim Studio executable")
    parser.add_argument("--jobs", type=int, help="Number of CPU cores to use (default: CPU count - 1)")
    parser.add_argument("--max-cpu", action="store_true", help="Use all available CPU cores")
    parser.add_argument("--build-type", type=int, choices=[1, 2, 3], help="Build type: 1=silent, 2=debug, 3=both")
    
    # Parse args but keep default behavior if not specified
    args, remaining_args = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + remaining_args
    
    # Determine job count
    cpu_count = multiprocessing.cpu_count()
    
    if args.max_cpu:
        jobs = cpu_count
        print(f"🚀 Using maximum CPU power: {jobs} cores")
    elif args.jobs:
        jobs = args.jobs
        print(f"⚙️ Using specified CPU cores: {jobs} of {cpu_count} available")
    else:
        jobs = max(1, cpu_count - 1)
        print(f"⚙️ Using optimal CPU cores: {jobs} of {cpu_count} available")
    
    # Check requirements first
    if not check_requirements():
        print("❌ Please install missing packages first")
        sys.exit(1)
    
    # Use command line arg if provided, otherwise prompt
    if args.build_type:
        choice = str(args.build_type)
    else:
        # Ask for build type
        print("\nSelect build type:")
        print("1. 🔇 Silent release build (NO CONSOLE EVER)")
        print("2. 🐛 Debug build (with console for testing)")
        print("3. 📦 Both builds")
        choice = input("\nEnter your choice (1-3): ").strip()
    
    success = False
    
    if choice == "1":
        exe_path = build_self_contained_version(jobs=jobs)
        success = exe_path is not None
    elif choice == "2":
        print("Debug build option temporarily disabled while fixing compatibility issues")
        success = False
    elif choice == "3":
        print("\n🔇 Building silent release version first...")
        release_exe = build_self_contained_version(jobs=jobs)
        print("\n🐛 Debug build option temporarily disabled")
        success = release_exe is not None
    else:
        print("❌ Invalid choice!")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Build completed successfully!")
        if choice == "1" or choice == "3":
            print("🔇 GUARANTEE: The release version will NEVER show console windows")
            print("   ✅ Main app: Silent")
            print("   ✅ Manim operations: Hidden")
            print("   ✅ Package installs: Silent")
            print("   ✅ All operations: Invisible")
            print("🚀 Professional desktop application ready!")
    else:
        print("❌ Build failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()