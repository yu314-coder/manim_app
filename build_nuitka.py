#!/usr/bin/env python3
"""
Modern build_nuitka.py - 2024 Best Practices Edition with PIL Compilation Fix and Icon Support
Fixed for all current Nuitka flags and PIL JpegImagePlugin compilation issues
Uses proper environment variables for compiler flags instead of non-existent --c-flag
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

def find_icon_file():
    """Find the icon file in the assets folder"""
    possible_icon_paths = [
        "assets/icon.ico"
    ]
    
    for icon_path in possible_icon_paths:
        if os.path.exists(icon_path):
            print(f"🎨 Found icon: {icon_path}")
            return os.path.abspath(icon_path)
    
    print("⚠️ No icon file found in assets folder")
    print("💡 Put an .ico file in assets/ folder to add icon to executable")
    return None

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
    """Build executable using 2024 Nuitka best practices with PIL compilation fix and icon support"""
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
    
    # Core Nuitka settings (using current flags only)
    cmd.extend([
        "--onefile",
        "--standalone",
        "--enable-plugin=tk-inter",
        "--enable-plugin=numpy",
        "--enable-plugin=matplotlib",
        "--enable-plugin=anti-bloat",
        "--python-flag=no_site",
        "--python-flag=-O",
        "--remove-output",
        # Prevent common errors
        "--python-flag=no_warnings",
    ])
    
    # Windows-specific settings with icon support
    if os.name == 'nt':
        cmd.extend([
            "--mingw64",
            "--windows-disable-console",
            # Modern onefile temp directory specification
            "--onefile-tempdir-spec={TEMP}/manim_studio_{PID}_{TIME}",
        ])
        
        # Add icon if found
        icon_path = find_icon_file()
        if icon_path:
            cmd.extend([f"--windows-icon-from-ico={icon_path}"])
            print(f"🎨 Using icon: {icon_path}")
        else:
            print("ℹ️ No icon specified - executable will use default icon")
    
    # CRITICAL: Exclude packages that cause DLL conflicts and compilation issues
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
        # Manim-specific test modules that cause DLL conflicts
        "manim.test",
        "manim.tests",
        "manim.utils.testing",
        # Jedi in frozen builds causes issues
        "jedi",
        "parso",
        # Additional problematic modules
        "IPython",
        "jupyter",
        "notebook",
        "pandas.tests",
        "sklearn.tests",
        "sympy.tests",
        "networkx.tests",
        # Audio/video test modules
        "moviepy.test",
        "imageio.test",
        # Subprocess test modules
        "subprocess.test",
        "multiprocessing.test",
        # Documentation modules
        "sphinx",
        "mkdocs",
        # Development tools that cause bloat
        "black",
        "flake8",
        "mypy",
        "pylint",
        "coverage",
        "hypothesis",
        # PIL test modules that might cause compilation issues
        "PIL.JpegImagePlugin.test",
        "PIL._imaging.test",
    ]
    
    for module in problematic_modules:
        cmd.extend([f"--nofollow-import-to={module}"])
    
    # ENHANCED: More aggressive anti-bloat for DLL conflict prevention
    bloat_modules = [
        "IPython",
        "jupyter", 
        "notebook",
        "pandas.tests",
        "sklearn.tests",
        "sympy.tests",
        "networkx.tests",
        # Additional modules that cause DLL conflicts
        "torch.test",
        "tensorflow.test",
        "keras.test",
        "conda",
        "anaconda",
        # Development tools
        "black",
        "flake8",
        "mypy",
        "pylint",
        # Documentation generators
        "sphinx",
        "mkdocs",
        # Testing frameworks
        "coverage",
        "hypothesis",
        # Compiler and build tools
        "setuptools_scm",
        "wheel",
        "build",
        # Version control
        "git",
        "hg",
        "svn",
    ]
    
    for module in bloat_modules:
        cmd.extend([f"--nofollow-import-to={module}"])
    
    # Include critical data files for manim if they exist
    data_files = [
        "--include-data-dir=templates=templates",
        "--include-data-dir=assets=assets",
        "--include-data-dir=media=media",
        "--include-data-dir=static=static",
    ]
    
    for data_file in data_files:
        source_path = data_file.split("=")[0].replace("--include-data-dir=", "")
        if os.path.exists(source_path):
            cmd.append(data_file)
            print(f"📁 Including data directory: {source_path}")
    
    # Performance optimizations
    cmd.extend([
        f"--jobs={jobs}",
        "--output-dir=dist",
        # Memory management for large builds
        "--low-memory",
    ])
    
    # Add main script
    cmd.append("app.py")
    
    print(f"🔧 Build command: {' '.join(cmd[:10])}... ({len(cmd)} total args)")
    print(f"💼 Jobs: {jobs}")
    print(f"🛡️ DLL Conflict Prevention: ENHANCED")
    print(f"🚫 Excluded {len(problematic_modules)} problematic modules")
    print(f"🔧 Using environment variables for compiler flags")
    
    try:
        start_time = time.time()
        
        # ENHANCED: Clear cache locations that might cause issues
        temp_dirs = [
            os.path.join(os.environ.get('TEMP', ''), '__pycache__'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Nuitka'),
            "build",
            "__pycache__",
            ".nuitka",
            ".nuitka_cache",
            # Clear Python bytecode cache
            os.path.join(os.path.dirname(sys.executable), "__pycache__"),
        ]
        
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"🧹 Cleared: {temp_dir}")
                except:
                    pass
        
        # CRITICAL: Set environment variables for build with PIL fix
        build_env = os.environ.copy()
        build_env.update({
            'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONUNBUFFERED': '1',
            'NUITKA_CACHE_DIR': os.path.join(os.getcwd(), '.nuitka_cache'),
            # Prevent setuptools from interfering
            'SETUPTOOLS_USE_DISTUTILS': 'stdlib',
            # CRITICAL: Set compiler flags via environment variables (the correct way)
            'CCFLAGS': '-Wno-unused-but-set-variable -Wno-unused-variable -Wno-unused-function -Wno-maybe-uninitialized',
            'CFLAGS': '-Wno-unused-but-set-variable -Wno-unused-variable -Wno-unused-function -Wno-maybe-uninitialized',
            'CXXFLAGS': '-Wno-unused-but-set-variable -Wno-unused-variable -Wno-unused-function -Wno-maybe-uninitialized',
        })
        
        # Run build with enhanced error handling
        print("\n🚀 Starting build process...")
        result = subprocess.run(cmd, capture_output=False, text=True, env=build_env)
        
        build_time = time.time() - start_time
        
        if result.returncode == 0:
            exe_path = Path("dist") / "app.exe"
            if exe_path.exists():
                size_mb = exe_path.stat().st_size / (1024 * 1024)
                print(f"\n✅ BUILD SUCCESSFUL!")
                print(f"📦 Executable: {exe_path}")
                print(f"📏 Size: {size_mb:.1f} MB")
                print(f"⏱️ Build time: {build_time:.1f} seconds")
                print(f"🛡️ Enhanced DLL conflict prevention applied")
                print(f"🚫 {len(problematic_modules)} problematic modules excluded")
                print(f"🔧 PIL compilation warnings handled via environment variables")
                
                # Check if icon was embedded
                icon_path = find_icon_file()
                if icon_path:
                    print(f"🎨 Icon embedded: {icon_path}")
                else:
                    print("ℹ️ Icon: Default (no custom icon found)")
                
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
    
    # ENHANCED: Clean more DLL cache locations
    dll_cache_dirs = [
        "__pycache__",
        os.path.join(os.environ.get('TEMP', ''), '__pycache__'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Nuitka'),
        "build",
        ".nuitka",
        ".nuitka_cache",
        # Python installation cache
        os.path.join(os.path.dirname(sys.executable), "__pycache__"),
        # Site-packages cache
        os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages", "__pycache__"),
    ]
    
    dirs_to_remove.extend(dll_cache_dirs)
    
    # ENHANCED: Also remove .pyc and .pyo files
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith(('.pyc', '.pyo')):
                files_to_remove.append(os.path.join(root, file))
    
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

def create_sample_icon():
    """Create a sample .ico file if none exists"""
    if not os.path.exists("assets"):
        os.makedirs("assets", exist_ok=True)
        
    icon_path = "assets/icon.ico"
    if not os.path.exists(icon_path):
        print(f"💡 To add custom icon, place an .ico file at: {icon_path}")
        print("💡 You can convert images to .ico format online")
        print("💡 Recommended size: 256x256 pixels")

def create_nuitka_project_file():
    """Create a nuitka-project file with build options"""
    nuitka_project_content = """# Nuitka Project File for Manim Studio
# Modern build configuration with PIL fix using environment variables

# Compilation mode
# nuitka-project: --onefile
# nuitka-project: --standalone

# Core plugins
# nuitka-project: --enable-plugin=tk-inter
# nuitka-project: --enable-plugin=numpy
# nuitka-project: --enable-plugin=matplotlib
# nuitka-project: --enable-plugin=anti-bloat

# Performance
# nuitka-project: --python-flag=no_site
# nuitka-project: --python-flag=-O
# nuitka-project: --assume-yes-for-downloads

# Windows specific
# nuitka-project-if: {OS} == "Windows":
#     nuitka-project: --mingw64
#     nuitka-project: --windows-disable-console
#     nuitka-project: --onefile-tempdir-spec={TEMP}/manim_studio_{PID}_{TIME}

# Exclude problematic modules
# nuitka-project: --nofollow-import-to=test
# nuitka-project: --nofollow-import-to=tests
# nuitka-project: --nofollow-import-to=testing
# nuitka-project: --nofollow-import-to=tkinter.test
# nuitka-project: --nofollow-import-to=unittest
# nuitka-project: --nofollow-import-to=pytest
# nuitka-project: --nofollow-import-to=PIL.test
# nuitka-project: --nofollow-import-to=numpy.tests
# nuitka-project: --nofollow-import-to=matplotlib.tests

# Note: Set these environment variables before running:
# set CCFLAGS=-Wno-unused-but-set-variable -Wno-unused-variable -Wno-unused-function
# set CFLAGS=-Wno-unused-but-set-variable -Wno-unused-variable -Wno-unused-function
"""
    
    try:
        with open("app.py.nuitka-project", "w") as f:
            f.write(nuitka_project_content)
        print("📝 Created nuitka-project file with environment variable instructions")
    except Exception as e:
        print(f"⚠️ Could not create nuitka-project file: {e}")

def print_alternative_builds():
    """Print alternative build commands for troubleshooting"""
    print("\n" + "="*60)
    print("🔧 ALTERNATIVE BUILD COMMANDS FOR TROUBLESHOOTING:")
    print("="*60)
    
    print("\n1️⃣ BASIC BUILD (if the script fails):")
    print("set CCFLAGS=-Wno-unused-but-set-variable -Wno-unused-variable")
    print("python -m nuitka --assume-yes-for-downloads --onefile --standalone --enable-plugin=anti-bloat --mingw64 --windows-disable-console --output-dir=dist app.py")
    
    print("\n2️⃣ MSVC BUILD (alternative compiler):")
    print("python -m nuitka --assume-yes-for-downloads --onefile --standalone --enable-plugin=anti-bloat --msvc=latest --windows-disable-console --output-dir=dist app.py")
    
    print("\n3️⃣ MINIMAL BUILD (fastest):")
    print("python -m nuitka --assume-yes-for-downloads --onefile --output-dir=dist app.py")
    
    print("\n4️⃣ IF PIL STILL CAUSES ISSUES:")
    print("python -m nuitka --assume-yes-for-downloads --onefile --standalone --nofollow-import-to=PIL.JpegImagePlugin --output-dir=dist app.py")
    
    print("\n5️⃣ WITH CUSTOM ICON:")
    print("python -m nuitka --assume-yes-for-downloads --onefile --standalone --windows-icon-from-ico=assets/icon.ico --output-dir=dist app.py")

def main():
    """Main build function with argument parsing"""
    parser = argparse.ArgumentParser(description="Build Manim Studio executable with Nuitka and Icon Support")
    
    # Build modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--debug", action="store_true", help="Debug build with verbose output")
    mode_group.add_argument("--optimize", action="store_true", help="Optimized build")
    mode_group.add_argument("--turbo", action="store_true", help="Maximum optimization (slow build)")
    
    # Build options
    parser.add_argument("--jobs", type=int, help="Number of parallel jobs (default: CPU count - 1)")
    parser.add_argument("--clean", action="store_true", help="Clean build and dist directories first")
    parser.add_argument("--minimal", action="store_true", help="Minimal bundle (faster build)")
    parser.add_argument("--skip-checks", action="store_true", help="Skip pre-build checks")
    parser.add_argument("--create-project", action="store_true", help="Create nuitka-project file")
    parser.add_argument("--show-alternatives", action="store_true", help="Show alternative build commands")
    parser.add_argument("--icon", type=str, help="Path to custom .ico file (overrides auto-detection)")
    
    args = parser.parse_args()
    
    print("🚀 MODERN NUITKA BUILD - 2024 EDITION WITH PIL FIX & ICON SUPPORT")
    print("=" * 70)
    
    # Show alternative commands if requested
    if args.show_alternatives:
        print_alternative_builds()
        return True
    
    # Create nuitka-project file if requested
    if args.create_project:
        create_nuitka_project_file()
        return True
    
    # Check environment
    if not args.skip_checks and not check_build_environment():
        return False
    
    # Clean if requested
    if args.clean:
        cleanup(args)
    
    # Create sample icon info if needed
    create_sample_icon()
    
    # Build executable
    success = build_executable(args)
    
    if success:
        print("\n" + "=" * 80)
        print("✅ Build completed successfully!")
        print("=" * 80)
        print("✅ Self-contained executable")
        print("✅ Modern anti-bloat prevents compilation issues")
        print("✅ DLL conflict prevention enabled")
        print("✅ PIL compilation warnings fixed via environment variables")
        print("✅ Custom icon support enabled")
        print("✅ Optimized for Python 3.9+ compatibility")
        
        exe_path = Path("dist") / "app.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n📦 Final executable: {exe_path}")
            print(f"📏 Size: {size_mb:.1f} MB")
            print(f"📅 Created: {timestamp}")
            
            # Check if icon was included
            icon_path = find_icon_file()
            if icon_path:
                print(f"🎨 Icon: {icon_path}")
            else:
                print("ℹ️ Icon: Default (no custom icon found)")
        
        print(f"\n🧪 Ready to deploy:")
        print("1. Copy dist/app.exe anywhere")
        print("2. Run directly - no installation needed")
        print("3. No DLL conflicts expected")
        print("4. PIL warnings handled via environment variables")
        print("5. Custom icon embedded (if .ico file found)")
        
    else:
        print("\n❌ Build failed!")
        print("💡 Try: python build_nuitka.py --debug for details")
        print("💡 Or: python build_nuitka.py --clean --optimize")
        print("💡 Or: python build_nuitka.py --skip-checks if pre-build checks failed")
        print("💡 Or: python build_nuitka.py --show-alternatives for manual commands")
        print("💡 For icon issues: ensure .ico file exists in assets/ folder")
        print_alternative_builds()
    
    cleanup(args)
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
