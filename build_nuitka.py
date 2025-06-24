#!/usr/bin/env python3
"""
Complete build_nuitka.py - Self-contained ManimStudio with command line options
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
import tempfile
import platform
import json
import datetime
import time

def check_build_environment():
    """Check if build environment is ready"""
    print("🔍 Checking build environment...")
    
    required_packages = ["nuitka", "manim", "numpy", "cv2", "PIL", "customtkinter"]
    missing = []
    
    for package in required_packages:
        try:
            if package == "PIL":
                import PIL
            elif package == "cv2":
                import cv2
            else:
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

def bundle_complete_environment(args):
    """Bundle the entire working virtual environment"""
    print("\n📦 Bundling complete virtual environment...")
    
    # Get current venv path
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        current_venv = Path(sys.prefix)
    else:
        current_venv = Path(sys.executable).parent.parent
    
    print(f"📁 Bundling from: {current_venv}")
    
    # Create bundle directory
    bundle_dir = Path("venv_bundle")
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir()
    
    # Essential directories to bundle
    if args.minimal:
        # Minimal bundle - only critical packages
        print("📦 Minimal bundle mode - copying only critical packages...")
        essential_dirs = ["Lib/site-packages"]
        # Copy only specific package directories
        source_site_packages = current_venv / "Lib" / "site-packages"
        dest_site_packages = bundle_dir / "Lib" / "site-packages"
        dest_site_packages.mkdir(parents=True)
        
        critical_packages = [
            "numpy", "cv2", "PIL", "cairo", "manim", "moderngl", 
            "customtkinter", "jedi", "matplotlib", "tkinter"
        ]
        
        total_files = 0
        for item in source_site_packages.iterdir():
            if any(pkg.lower() in item.name.lower() for pkg in critical_packages):
                if item.is_dir():
                    shutil.copytree(item, dest_site_packages / item.name, ignore_errors=True)
                else:
                    shutil.copy2(item, dest_site_packages / item.name)
                file_count = sum(1 for _ in (dest_site_packages / item.name).rglob('*') if _.is_file()) if item.is_dir() else 1
                total_files += file_count
                print(f"   📂 {item.name}: {file_count} files")
    else:
        # Full bundle
        essential_dirs = ["Lib/site-packages", "Scripts", "Include"]
        total_files = 0
        
        for dir_name in essential_dirs:
            source_dir = current_venv / dir_name
            if source_dir.exists():
                dest_dir = bundle_dir / dir_name
                print(f"📂 Copying {dir_name}...")
                
                if args.turbo:
                    # Fast copy - ignore some non-essential files
                    def ignore_patterns(dir, files):
                        ignore = []
                        for file in files:
                            if file.endswith(('.pyc', '.pyo', '__pycache__', '.dist-info')):
                                ignore.append(file)
                        return ignore
                    
                    shutil.copytree(source_dir, dest_dir, ignore=ignore_patterns, ignore_errors=True)
                else:
                    shutil.copytree(source_dir, dest_dir, ignore_errors=True)
                
                file_count = sum(1 for _ in dest_dir.rglob('*') if _.is_file())
                total_files += file_count
                print(f"   ✅ {file_count} files copied")
    
    # Copy Scripts directory for executables
    scripts_source = current_venv / "Scripts"
    if scripts_source.exists() and not (bundle_dir / "Scripts").exists():
        scripts_dest = bundle_dir / "Scripts"
        shutil.copytree(scripts_source, scripts_dest, ignore_errors=True)
        script_files = sum(1 for _ in scripts_dest.rglob('*') if _.is_file())
        total_files += script_files
        print(f"📂 Scripts: {script_files} files")
    
    # Copy pyvenv.cfg
    pyvenv_cfg = current_venv / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        shutil.copy2(pyvenv_cfg, bundle_dir / "pyvenv.cfg")
    
    # Create manifest
    manifest = {
        "bundle_date": str(datetime.datetime.now()),
        "source_venv": str(current_venv),
        "total_files": total_files,
        "python_version": sys.version,
        "build_mode": "minimal" if args.minimal else "turbo" if args.turbo else "full",
        "optimization_level": "optimize" if args.optimize else "standard"
    }
    
    with open(bundle_dir / "bundle_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"📊 Bundle complete: {total_files} files")
    return bundle_dir

def create_environment_loader():
    """Create bundled environment loader script"""
    loader_content = '''
import os
import sys
from pathlib import Path

def setup_bundled_environment():
    """Set up the bundled virtual environment"""
    if getattr(sys, 'frozen', False):
        app_dir = Path(sys.executable).parent
    else:
        app_dir = Path(__file__).parent
    
    venv_bundle = app_dir / "venv_bundle"
    
    if not venv_bundle.exists():
        return False
    
    site_packages = venv_bundle / "Lib" / "site-packages"
    scripts_dir = venv_bundle / "Scripts"
    
    if site_packages.exists():
        sys.path.insert(0, str(site_packages))
        os.environ['PYTHONPATH'] = str(site_packages) + os.pathsep + os.environ.get('PYTHONPATH', '')
    
    if scripts_dir.exists():
        current_path = os.environ.get('PATH', '')
        os.environ['PATH'] = str(scripts_dir) + os.pathsep + current_path
    
    os.environ['VIRTUAL_ENV'] = str(venv_bundle)
    return True

if __name__ != "__main__":
    setup_bundled_environment()
'''
    
    with open("bundled_env_loader.py", "w") as f:
        f.write(loader_content)
    
    print("📄 Created bundled environment loader")

def build_executable(args):
    """Build the self-contained executable with options"""
    print(f"\n🔨 Building executable in {get_build_mode_name(args)} mode...")
    
    # Bundle environment first
    bundle_dir = bundle_complete_environment(args)
    create_environment_loader()
    
    # Determine job count
    cpu_count = multiprocessing.cpu_count()
    
    if args.jobs:
        jobs = args.jobs
    elif args.turbo:
        jobs = cpu_count  # Use all cores for speed
    elif args.optimize:
        jobs = max(1, cpu_count - 2)  # Leave some cores free for stability
    else:
        jobs = max(1, cpu_count - 1)
    
    print(f"🚀 Using {jobs} parallel jobs")
    
    # Base command
    cmd = [
        sys.executable, "-m", "nuitka",
        "--onefile",
        "--onefile-tempdir-spec={CACHE_DIR}/ManimStudio",
    ]
    
    # Console options
    if args.debug:
        cmd.extend([
            "--windows-console-mode=force",
            "--show-scons",  # Show detailed compilation
        ])
        print("🐛 Debug mode: Console enabled, verbose output")
    else:
        cmd.extend([
            "--windows-console-mode=disable",
            "--windows-disable-console",
        ])
    
    # Optimization level
    if args.turbo:
        cmd.extend([
            "--lto=no",  # No link-time optimization
            "--onefile-no-compression",  # No compression
            "--disable-ccache",  # Disable cache for clean build
        ])
        print("🚀 Turbo mode: Fast compilation, larger executable")
        
    elif args.optimize:
        cmd.extend([
            "--lto=yes",  # Link-time optimization
            "--onefile-child-grace-time=10",
            "--assume-yes-for-downloads",
            "--enable-plugins=all",  # Enable all optimizations
        ])
        print("🎯 Optimize mode: Maximum optimization, smaller/faster executable")
        
    else:  # Standard mode
        cmd.extend([
            "--lto=no",  # Balanced approach
            "--assume-yes-for-downloads",
        ])
        print("⚖️ Standard mode: Balanced compilation")
    
    # Core settings (always included)
    cmd.extend([
        "--enable-plugin=tk-inter",
        "--enable-plugin=numpy",
        "--show-progress",
        "--mingw64",
        "--remove-output",
    ])
    
    # Data inclusion
    cmd.extend([
        f"--include-data-dir={bundle_dir}=venv_bundle",
        "--include-data-file=bundled_env_loader.py=bundled_env_loader.py",
    ])
    
    # Package inclusion
    if args.minimal:
        # Minimal package inclusion
        critical_packages = ["numpy", "cv2", "PIL", "cairo", "manim", "customtkinter", "tkinter"]
    else:
        # Full package inclusion
        critical_packages = [
            "numpy", "cv2", "PIL", "cairo", "manim", "moderngl", 
            "customtkinter", "jedi", "matplotlib", "tkinter"
        ]
    
    for package in critical_packages:
        cmd.extend([
            f"--include-package={package}",
            f"--include-package-data={package}"
        ])
    
    # Core modules
    core_modules = [
        "subprocess", "multiprocessing", "threading", "json", 
        "pathlib", "tempfile", "logging", "os", "sys"
    ]
    
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
        print(f"🔧 Build command: {' '.join(cmd)}")
    
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
                
                # Performance estimates
                if args.turbo:
                    print("🚀 Turbo build: Fast compilation, expect larger file size")
                elif args.optimize:
                    print("🎯 Optimized build: Better performance, smaller size")
                
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
    elif args.minimal:
        return "MINIMAL"
    elif args.debug:
        return "DEBUG"
    else:
        return "STANDARD"

def cleanup(args=None):
    """Clean up temporary files"""
    files_to_remove = ["bundled_env_loader.py"]
    dirs_to_remove = ["venv_bundle"]
    
    if args and args.clean:
        dirs_to_remove.extend(["build", "dist"])
        print("🧹 Cleaning all build directories...")
    
    for file in files_to_remove:
        if os.path.exists(file):
            os.remove(file)
            if args and args.clean:
                print(f"   🗑️ Removed: {file}")
    
    for dir in dirs_to_remove:
        if os.path.exists(dir):
            shutil.rmtree(dir, ignore_errors=True)
            if args and args.clean:
                print(f"   🗑️ Removed: {dir}/")

def main():
    """Main build function with command line arguments"""
    parser = argparse.ArgumentParser(
        description="Build self-contained ManimStudio executable",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python build_nuitka.py                    # Standard build
  python build_nuitka.py --turbo            # Fast build for testing
  python build_nuitka.py --optimize         # Best quality for release
  python build_nuitka.py --debug            # Debug build with console
  python build_nuitka.py --minimal --turbo  # Minimal fast build
  python build_nuitka.py --clean --optimize # Clean optimized build
        """
    )
    
    # Build mode options (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--turbo", action="store_true", 
                           help="Fast build: Quick compilation, larger executable")
    mode_group.add_argument("--optimize", action="store_true", 
                           help="Optimized build: Best performance, longer compilation")
    mode_group.add_argument("--debug", action="store_true", 
                           help="Debug build: Shows console, verbose output")
    
    # Content options
    parser.add_argument("--minimal", action="store_true", 
                       help="Minimal bundle: Only critical packages (smaller size)")
    
    # Build options
    parser.add_argument("--jobs", type=int, metavar="N",
                       help="Number of parallel compilation jobs")
    parser.add_argument("--clean", action="store_true", 
                       help="Clean all build directories before building")
    
    args = parser.parse_args()
    
    print("🎯 ManimStudio Self-Contained Build")
    print("=" * 50)
    print(f"🔧 Mode: {get_build_mode_name(args)}")
    
    if args.minimal:
        print("📦 Bundle: Minimal (critical packages only)")
    else:
        print("📦 Bundle: Full (all packages)")
    
    print("=" * 50)
    
    if args.clean:
        cleanup(args)
    
    if not check_build_environment():
        return False
    
    success = build_executable(args)
    
    if success:
        print("\n" + "=" * 50)
        print("🎉 BUILD COMPLETE!")
        print("=" * 50)
        print("✅ Your app.exe is completely self-contained")
        print("✅ Includes all required packages and DLLs")
        print("✅ No runtime installation needed")
        print("✅ Should work on fresh computers")
        
        print(f"\n🧪 Testing instructions:")
        print("1. Copy dist/app.exe to a fresh computer")
        print("2. Run app.exe directly")
        print("3. Should start without 3221225477 errors")
        
        if args.turbo:
            print("\n⚠️ Note: Turbo builds are larger but faster to compile")
        elif args.optimize:
            print("\n✨ Note: Optimized builds are smaller and faster at runtime")
            
    else:
        print("\n❌ Build failed!")
        if not args.debug:
            print("💡 Try: python build_nuitka.py --debug for more details")
    
    cleanup()
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
