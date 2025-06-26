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

def bundle_complete_environment(args):
    """Bundle the entire working virtual environment - OPTIMIZED"""
    print("\n📦 Bundling complete virtual environment...")
    
    source_python = find_best_python_source()
    if not source_python or not source_python.exists():
        print("❌ Could not find suitable Python installation")
        return None
    
    print(f"📁 Primary source: {source_python}")
    
    # Create bundle directory
    bundle_dir = Path("venv_bundle")
    if bundle_dir.exists():
        print("🗑️ Removing existing bundle...")
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir()
    
    # Create essential directory structure
    essential_dirs = ["Scripts", "Lib/site-packages", "DLLs"]
    for dir_path in essential_dirs:
        (bundle_dir / dir_path).mkdir(parents=True, exist_ok=True)
        print(f"📁 Created: {dir_path}")
    
    total_files = 0
    
    # Find source site-packages
    source_site_packages = None
    possible_locations = [
        source_python / "Lib" / "site-packages",
        source_python / "lib" / "python3.12" / "site-packages",
        source_python / "lib" / "python3.11" / "site-packages",
    ]
    
    for location in possible_locations:
        if location.exists() and len(list(location.iterdir())) > 10:
            source_site_packages = location
            print(f"✅ Found site-packages: {source_site_packages}")
            break
    
    if not source_site_packages:
        print("❌ No valid site-packages found!")
        return None
    
    # Copy ALL site-packages (bundled environment strategy)
    dest_site_packages = bundle_dir / "Lib" / "site-packages"
    print(f"📦 Copying complete site-packages...")
    
    try:
        for item in source_site_packages.iterdir():
            try:
                if item.is_dir():
                    shutil.copytree(item, dest_site_packages / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest_site_packages / item.name)
                total_files += 1
            except Exception as e:
                print(f"   ⚠️ Skipped {item.name}: {e}")
    except Exception as e:
        print(f"❌ Failed to copy site-packages: {e}")
        return None
    
    # Copy essential Scripts
    source_scripts = source_python / "Scripts"
    dest_scripts = bundle_dir / "Scripts"
    
    if source_scripts.exists():
        try:
            for item in source_scripts.iterdir():
                if item.is_file():
                    shutil.copy2(item, dest_scripts / item.name)
                    total_files += 1
            print(f"✅ Copied {len(list(dest_scripts.iterdir()))} scripts")
        except Exception as e:
            print(f"⚠️ Some scripts failed to copy: {e}")
    
    # Copy DLLs
    source_dlls = source_python / "DLLs"
    dest_dlls = bundle_dir / "DLLs"
    
    if source_dlls.exists():
        try:
            for item in source_dlls.iterdir():
                if item.suffix.lower() == '.dll':
                    shutil.copy2(item, dest_dlls / item.name)
                    total_files += 1
        except Exception:
            pass
    
    # Create pyvenv.cfg
    dest_cfg = bundle_dir / "pyvenv.cfg"
    try:
        with open(dest_cfg, 'w') as f:
            f.write(f"""home = {sys.prefix}
include-system-site-packages = false
version = {sys.version.split()[0]}
""")
        print("✅ Created pyvenv.cfg")
        total_files += 1
    except Exception as e:
        print(f"⚠️ Could not create pyvenv.cfg: {e}")
    
    # Create manifest
    manifest = {
        "bundle_date": str(datetime.datetime.now()),
        "source_python": str(source_python),
        "total_files": total_files,
        "python_version": sys.version,
        "build_mode": "minimal" if args.minimal else "full"
    }
    
    try:
        with open(bundle_dir / "bundle_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        total_files += 1
    except Exception as e:
        print(f"⚠️ Could not create manifest: {e}")
    
    print(f"📊 Bundle complete: {total_files} files")
    
    # Quick validation
    required_paths = ["Scripts", "Lib/site-packages", "pyvenv.cfg"]
    for path in required_paths:
        if (bundle_dir / path).exists():
            print(f"✅ {path}: OK")
        else:
            print(f"❌ MISSING: {path}")
            return None
    
    return bundle_dir

def create_environment_loader():
    """Create modern bundled environment loader"""
    loader_content = '''import os
import sys
from pathlib import Path

def setup_bundled_environment():
    """Set up bundled environment - MODERN 2024 VERSION"""
    if getattr(sys, 'frozen', False):
        app_dir = Path(sys.executable).parent
    else:
        app_dir = Path(__file__).parent
    
    venv_bundle = app_dir / "venv_bundle"
    
    if not venv_bundle.exists():
        print(f"ERROR: venv_bundle not found at {venv_bundle}")
        return False
    
    # Validate structure
    required_dirs = ["Scripts", "Lib/site-packages"]
    for req_dir in required_dirs:
        if not (venv_bundle / req_dir).exists():
            print(f"ERROR: Missing {req_dir} in bundle")
            return False
    
    # Set up paths
    site_packages = venv_bundle / "Lib" / "site-packages"
    scripts_dir = venv_bundle / "Scripts"
    
    if site_packages.exists():
        sys.path.insert(0, str(site_packages))
        
        current_pythonpath = os.environ.get('PYTHONPATH', '')
        if current_pythonpath:
            os.environ['PYTHONPATH'] = str(site_packages) + os.pathsep + current_pythonpath
        else:
            os.environ['PYTHONPATH'] = str(site_packages)
    
    if scripts_dir.exists():
        current_path = os.environ.get('PATH', '')
        os.environ['PATH'] = str(scripts_dir) + os.pathsep + current_path
    
    os.environ['VIRTUAL_ENV'] = str(venv_bundle)
    
    return True

if __name__ != "__main__":
    setup_bundled_environment()
'''
    
    with open("bundled_env_loader.py", "w", encoding="utf-8") as f:
        f.write(loader_content)
    
    print("✅ Created modern environment loader")

def build_executable(args):
    """Build executable using 2024 Nuitka best practices"""
    print(f"\n🔨 Building executable in {get_build_mode_name(args)} mode...")
    
    # Bundle environment first
    bundle_dir = bundle_complete_environment(args)
    if bundle_dir is None:
        print("❌ Bundling failed - cannot proceed with build")
        return False
    
    # Create the loader
    create_environment_loader()
    
    # Determine jobs
    jobs = args.jobs if args.jobs else max(1, multiprocessing.cpu_count() - 1)
    
    # Build command using modern Nuitka best practices
    cmd = [sys.executable, "-m", "nuitka"]
    
    # Mode-specific options - CORRECTED FOR 2024
    if args.turbo:
        cmd.extend([
            "--standalone",
            "--disable-console",
        ])
    elif args.optimize:
        cmd.extend([
            "--standalone",
            "--onefile",
            "--disable-console",
            "--lto=yes",
        ])
    elif args.debug:
        cmd.extend([
            "--standalone",
            "--enable-console",
            "--debug",
        ])
    else:
        # Standard mode
        cmd.extend([
            "--standalone",
            "--onefile",
            "--disable-console",
        ])
    
    # MODERN 2024 OPTIONS - Using current best practices
    cmd.extend([
        "--enable-plugin=tk-inter",          # GUI support
        "--enable-plugin=numpy",             # Numeric computing
        "--enable-plugin=anti-bloat",        # CRITICAL: Auto-reduces bloat
        "--show-progress",                   # Progress display
        "--mingw64",                         # Windows compiler
        "--remove-output",                   # Clean build
        "--assume-yes-for-downloads",        # Auto-download dependencies
    ])
    
    # PYTHON 3.12 COMPATIBILITY FIXES
    cmd.extend([
        "--nofollow-import-to=_xxinterpchannels",  # Fix Python 3.12 compatibility
    ])
    
    # MODERN ANTI-BLOAT: Let Nuitka handle problematic packages automatically
    problematic_modules = [
        "PIL",               # PIL compilation issues
        "matplotlib",        # Massive bloat + compilation issues  
        "scipy",            # Large and problematic
        "sklearn",          # Dependencies issues
        "pandas",           # Heavy dependencies
        "IPython",          # Development tool bloat
        "pytest",           # Testing framework bloat
    ]
    
    for module in problematic_modules:
        cmd.extend([
            f"--nofollow-import-to={module}",
        ])
    
    # Data inclusion
    bundle_dir_abs = bundle_dir.resolve()
    cmd.extend([
        f"--include-data-dir={bundle_dir_abs}=venv_bundle",
        "--include-data-file=bundled_env_loader.py=bundled_env_loader.py",
    ])
    
    print(f"📦 Including bundle: {bundle_dir_abs} -> venv_bundle")
    
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
    files_to_remove = ["bundled_env_loader.py"]
    dirs_to_remove = []
    
    if not (args and args.debug):
        dirs_to_remove.append("venv_bundle")
    
    if args and args.clean:
        dirs_to_remove.extend(["build", "dist"])
        print("🧹 Cleaning all build directories...")
    
    for file in files_to_remove:
        if os.path.exists(file):
            os.remove(file)
    
    for dir in dirs_to_remove:
        if os.path.exists(dir):
            shutil.rmtree(dir, ignore_errors=True)

def main():
    """Main build function with modern argument parsing"""
    parser = argparse.ArgumentParser(
        description="Build self-contained ManimStudio executable - 2024 Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modern Examples:
  python build_nuitka.py                    # Standard onefile build
  python build_nuitka.py --turbo            # Fast standalone build  
  python build_nuitka.py --optimize         # Optimized onefile build
  python build_nuitka.py --debug            # Debug build with console
  python build_nuitka.py --clean            # Clean build directories first
        """
    )
    
    # Build mode options
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--turbo", action="store_true", 
                           help="Fast standalone build (larger but faster compile)")
    mode_group.add_argument("--optimize", action="store_true", 
                           help="Optimized onefile build (best for release)")
    mode_group.add_argument("--debug", action="store_true", 
                           help="Debug build with console output")
    
    # Content options  
    parser.add_argument("--minimal", action="store_true",
                       help="Minimal bundle (only critical packages)")
    
    # Build options
    parser.add_argument("--jobs", type=int, metavar="N",
                       help="Number of parallel compilation jobs")
    parser.add_argument("--clean", action="store_true",
                       help="Clean build directories before building")
    
    args = parser.parse_args()
    
    print("🎯 ManimStudio Build - 2024 Edition")
    print("=" * 50)
    print(f"🔧 Mode: {get_build_mode_name(args)}")
    print(f"📦 Strategy: Modern anti-bloat + bundled environment")
    print("=" * 50)
    
    if args.clean:
        cleanup(args)
    
    if not check_build_environment():
        return False
    
    success = build_executable(args)
    
    if success:
        print("\n" + "=" * 80)
        print("🎉 BUILD COMPLETE - 2024 MODERN VERSION!")
        print("=" * 80)
        print("✅ Self-contained executable with bundled environment")
        print("✅ Modern anti-bloat prevents compilation issues")
        print("✅ Portable - works on fresh computers")
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
        print("3. All packages available via bundled environment")
        
    else:
        print("\n❌ Build failed!")
        print("💡 Try: python build_nuitka.py --debug for details")
    
    cleanup(args)
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
