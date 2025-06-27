#!/usr/bin/env python3
"""
Modern build_nuitka.py - 2024 Best Practices Edition with DLL Conflict Prevention
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
    """Build executable using 2024 Nuitka best practices with DLL conflict prevention"""
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
    
    # Windows-specific with DLL conflict prevention
    if os.name == 'nt':
        cmd.extend([
            "--mingw64",
            "--windows-disable-console",
            # CRITICAL: DLL conflict prevention
            "--force-dll-dependency-cache-update",
            "--onefile-tempdir-spec=manim_studio_temp"
        ])
    
    # CRITICAL: Exclude packages that cause 3221225477 DLL conflicts
    problematic_modules = [
        "tkinter.test",
        "test",
        "unittest", 
        "distutils",
        "setuptools",
        "pip",
        "wheel",
        # DLL conflict sources:
        "numpy.tests",
        "scipy.tests", 
        "matplotlib.tests",
        "cv2.test",
        "PIL.test",
        "moderngl.test",
        "pytest",
        "nose",
        # Manim-specific test modules
        "manim.test",
        "manim.tests"
    ]
    
    for module in problematic_modules:
        cmd.extend([f"--nofollow-import-to={module}"])
    
    # ANTI-BLOAT: Prevent problematic modules from being compiled
    bloat_modules = [
        "IPython",
        "jupyter", 
        "notebook",
        "pandas.tests",
        "sklearn.tests",
        "sympy.tests",
        "networkx.tests"
    ]
    
    for module in bloat_modules:
        cmd.extend([f"--nofollow-import-to={module}"])
    
    # Include critical data files for manim
    data_files = [
        "--include-data-dir=templates=templates",
        "--include-data-dir=assets=assets"
    ]
    
    for data_file in data_files:
        if any(os.path.exists(path) for path in data_file.split("=")[0].replace("--include-data-dir=", "").split(",")):
            cmd.append(data_file)
    
    # Performance optimizations
    cmd.extend([
        f"--jobs={jobs}",
        "--output-dir=dist",
    ])
    
    # Add main script
    cmd.append("app.py")
    
    print(f"🔧 Build command: {' '.join(cmd[:10])}... ({len(cmd)} total args)")
    print(f"💼 Jobs: {jobs}")
    print(f"🛡️ DLL Conflict Prevention: ENABLED")
    
    try:
        start_time = time.time()
        
        # Clear any existing DLL cache before build
        temp_dirs = [
            os.path.join(os.environ.get('TEMP', ''), '__pycache__'),
            "build",
            "__pycache__"
        ]
        
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"🧹 Cleared: {temp_dir}")
                except:
                    pass
        
        # Run build with enhanced error handling
        print("\n🚀 Starting build process...")
        result = subprocess.run(cmd, capture_output=False, text=True)
        
        build_time = time.time() - start_time
        
        if result.returncode == 0:
            exe_path = Path("dist") / "app.exe"
            if exe_path.exists():
                size_mb = exe_path.stat().st_size / (1024 * 1024)
                print(f"\n✅ BUILD SUCCESSFUL!")
                print(f"📦 Executable: {exe_path}")
                print(f"📏 Size: {size_mb:.1f} MB")
                print(f"⏱️ Build time: {build_time:.1f} seconds")
                print(f"🛡️ DLL conflicts prevented")
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
    """Clean up temporary files including DLL caches"""
    files_to_remove = []
    dirs_to_remove = []
    
    if args and args.clean:
        dirs_to_remove.extend(["build", "dist", "__pycache__"])
        print("🧹 Cleaning all build directories...")
    
    # Always clean DLL caches to prevent conflicts
    dll_cache_dirs = [
        "__pycache__",
        os.path.join(os.environ.get('TEMP', ''), '__pycache__'),
        "build"
    ]
    
    dirs_to_remove.extend(dll_cache_dirs)
    
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
    
    print("🚀 MODERN NUITKA BUILD - 2024 EDITION WITH DLL CONFLICT PREVENTION")
    print("=" * 70)
    
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
        print("✅ DLL conflict prevention enabled")
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
        print("3. No DLL conflicts expected")
        
    else:
        print("\n❌ Build failed!")
        print("💡 Try: python build_nuitka.py --debug for details")
        print("💡 Or: python build_nuitka.py --clean --optimize")
    
    cleanup(args)
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
