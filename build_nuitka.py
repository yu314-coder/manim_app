#!/usr/bin/env python3
"""
Modern build_nuitka.py - 2024 Best Practices Edition
Follows current Nuitka anti-bloat and plugin standards
Usage: python build_nuitka.py [options]
"""

import os
import sys
import subprocess
import shutil
import multiprocessing
import argparse
import logging
from pathlib import Path
import json
import datetime
import time

def find_best_python_source():
    """Find the best Python installation to use as source"""
    # Method 1: Check if we're in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        current_venv = Path(sys.prefix)
        print(f"✅ Found current virtual environment: {current_venv}")
        return current_venv
    
    # Method 2: Try to find venv from executable path
    exe_parent = Path(sys.executable).parent
    if (exe_parent / "Scripts" / "activate").exists() or (exe_parent / "bin" / "activate").exists():
        current_venv = exe_parent
        print(f"✅ Found venv from executable path: {current_venv}")
        return current_venv
    
    # Method 3: Use current Python installation
    current_python = Path(sys.executable).parent
    print(f"✅ Using current Python installation: {current_python}")
    return current_python

def check_build_environment():
    """Check if build environment is ready"""
    print("🔍 Checking build environment...")
    
    # Only check essential packages - let bundled environment handle the rest
    required_packages = ["nuitka"]
    missing = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}: OK")
        except ImportError:
            missing.append(package)
            print(f"❌ {package}: Missing")
    
    if missing:
        print(f"\n❌ Missing packages: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing))
        return False
    
    print("✅ Build environment ready")
    return True

def build_executable(args):
    """Build executable using 2024 Nuitka best practices"""
    print(f"\n🔨 Building executable in {get_build_mode_name(args)} mode...")
    
    # Determine jobs
    jobs = args.jobs if args.jobs else max(1, multiprocessing.cpu_count() - 1)
    
    # Build command using modern Nuitka best practices
    cmd = [sys.executable, "-m", "nuitka"]
    
    # Performance settings
    if args.turbo:
        cmd.extend([
            "--assume-yes-for-downloads",
            "--lto=yes",
            "--clang",
            "--msvc=latest",
            "--mingw64",
        ])
    elif args.optimize:
        cmd.extend([
            "--assume-yes-for-downloads",
            "--lto=auto",
        ])
    elif args.debug:
        cmd.extend([
            "--debug",
            "--show-progress",
            "--show-memory",
            "--assume-yes-for-downloads",
        ])
    else:
        cmd.extend([
            "--assume-yes-for-downloads",
        ])
    
    # Core Nuitka settings
    cmd.extend([
        "--onefile",
        "--standalone",
        "--enable-plugin=tk-inter",
        "--enable-plugin=numpy",
        "--enable-plugin=matplotlib",
        "--enable-plugin=anti-bloat",
        "--assume-yes-for-downloads",
        "--python-flag=no_site",
        "--python-flag=-O",
        "--remove-output",
    ])
    
    # Windows-specific
    if os.name == 'nt':
        cmd.extend([
            "--mingw64",
            "--windows-disable-console",
        ])
    
    # ANTI-BLOAT: Prevent problematic modules from being compiled
    problematic_modules = [
        "IPython",          # Interactive Python bloat
        "jupyter",          # Jupyter notebook bloat
        "notebook",         # Notebook interface bloat
        "tkinter.test",     # Test modules
        "test",             # Python test suite
        "unittest",         # Unit testing bloat
        "doctest",          # Documentation test bloat
        "pytest",           # Testing framework bloat
    ]
    
    for module in problematic_modules:
        cmd.extend([
            f"--nofollow-import-to={module}",
        ])
    
    # MINIMAL COMPILATION: Only compile what's absolutely necessary
    essential_only = ["tkinter"]  # Minimal GUI support
    
    for package in essential_only:
        cmd.extend([
            f"--include-package={package}",
        ])
    
    # Core modules (always safe to compile)
    core_modules = ["os", "sys", "json", "pathlib", "logging"]
    for module in core_modules:
        cmd.append(f"--include-module={module}")
    
    # Output settings
    cmd.extend([
        "--output-dir=dist",
        f"--jobs={jobs}",
        "app.py"
    ])
    
    # Add icon if available
    if Path("assets/icon.ico").exists():
        cmd.append("--windows-icon-from-ico=assets/icon.ico")
    
    # Show command if debug
    if args.debug:
        print(f"🔧 Build command:")
        print(" ".join(cmd))
    
    # Run build
    start_time = time.time()
    
    try:
        result = subprocess.run(cmd, check=False)
        
        end_time = time.time()
        build_time = end_time - start_time
        
        if result.returncode == 0:
            exe_path = Path("dist") / "app.exe"
            if exe_path.exists():
                size_mb = exe_path.stat().st_size / (1024 * 1024)
                print(f"\n✅ Build successful!")
                print(f"📦 Executable: {exe_path}")
                print(f"📏 Size: {size_mb:.1f} MB")
                print(f"⏱️ Build time: {build_time:.1f} seconds")
                return True
        
        print(f"\n❌ Build failed with exit code {result.returncode}")
        print(f"⏱️ Failed after: {build_time:.1f} seconds")
        return False
        
    except Exception as e:
        print(f"❌ Build error: {e}")
        return False

def get_build_mode_name(args):
    """Get friendly name for build mode"""
    if args.turbo:
        return "TURBO"
    elif args.optimize:
        return "OPTIMIZE" 
    elif args.debug:
        return "DEBUG"
    else:
        return "STANDARD"

def cleanup(args=None):
    """Clean up temporary files"""
    files_to_remove = []
    dirs_to_remove = []
    
    if args and args.clean:
        dirs_to_remove.extend(["build", "dist"])
        print("🧹 Cleaning all build directories...")
    
    for file in files_to_remove:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"🗑️ Removed: {file}")
            except Exception as e:
                print(f"⚠️ Could not remove {file}: {e}")
    
    for directory in dirs_to_remove:
        if os.path.exists(directory):
            try:
                shutil.rmtree(directory)
                print(f"🗑️ Removed directory: {directory}")
            except Exception as e:
                print(f"⚠️ Could not remove {directory}: {e}")

def main():
    """Main build function with argument parsing"""
    parser = argparse.ArgumentParser(description="Build Manim Studio executable with Nuitka")
    
    # Build modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--debug", action="store_true", help="Debug build with verbose output")
    mode_group.add_argument("--optimize", action="store_true", help="Optimized build")
    mode_group.add_argument("--turbo", action="store_true", help="Maximum optimization (slow build)")
    
    # Build options
    parser.add_argument("--jobs", type=int, help="Number of parallel jobs (default: CPU count - 1)")
    parser.add_argument("--clean", action="store_true", help="Clean build and dist directories first")
    parser.add_argument("--minimal", action="store_true", help="Minimal bundle (faster build)")
    
    args = parser.parse_args()
    
    print("🚀 MODERN NUITKA BUILD - 2024 EDITION")
    print("=" * 50)
    
    # Check environment
    if not check_build_environment():
        return False
    
    # Clean if requested
    if args.clean:
        cleanup(args)
    
    # Build executable
    success = build_executable(args)
    
    if success:
        print("\n" + "=" * 80)
        print("✅ Build completed successfully!")
        print("=" * 80)
        print("✅ Self-contained executable")
        print("✅ Modern anti-bloat prevents compilation issues")
        print("✅ Optimized for Python 3.12 compatibility")
        
        exe_path = Path("dist") / "app.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n📦 Final executable: {exe_path}")
            print(f"📏 Size: {size_mb:.1f} MB")
            print(f"📅 Created: {timestamp}")
        
        print(f"\n🧪 Ready to deploy:")
        print("1. Copy dist/app.exe anywhere")
        print("2. Run directly - no installation needed")
        
    else:
        print("\n❌ Build failed!")
        print("💡 Try: python build_nuitka.py --debug for details")
    
    cleanup(args)
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
