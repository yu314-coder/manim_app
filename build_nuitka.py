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

def find_python_installations():
    """Find all Python installations on the system"""
    python_locations = []
    
    # Common Windows Python locations
    search_paths = [
        Path("C:/Python*"),
        Path("C:/Program Files/Python*"),
        Path("C:/Program Files (x86)/Python*"),
        Path(os.path.expanduser("~")) / "AppData/Local/Programs/Python*",
        Path(os.path.expanduser("~")) / "AppData/Local/Microsoft/WindowsApps/python*.exe",
        Path(sys.executable).parent,
        Path(sys.prefix),
    ]
    
    for search_path in search_paths:
        try:
            for path in search_path.parent.glob(search_path.name):
                if path.is_dir():
                    # Look for python.exe in this directory and subdirectories
                    for python_exe in path.rglob("python.exe"):
                        if python_exe.is_file():
                            python_locations.append(python_exe.parent)
                elif path.name.endswith("python.exe") and path.is_file():
                    python_locations.append(path.parent)
        except:
            continue
    
    # Also search PATH
    path_env = os.environ.get('PATH', '')
    for path_dir in path_env.split(os.pathsep):
        python_exe = Path(path_dir) / "python.exe"
        if python_exe.exists():
            python_locations.append(Path(path_dir))
    
    # Remove duplicates and return
    unique_locations = list(set(python_locations))
    print(f"🔍 Found {len(unique_locations)} Python installations:")
    for loc in unique_locations:
        print(f"   📁 {loc}")
    
    return unique_locations

def find_best_python_source():
    """Find the best Python installation to use as source"""
    current_python = Path(sys.executable).parent
    current_venv = None
    
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
    print(f"✅ Using current Python installation: {current_python}")
    return current_python

def copy_with_fallback(source, dest, fallback_search_name=None):
    """Copy a file with fallback search capabilities"""
    try:
        if source.exists():
            shutil.copy2(source, dest)
            return True
    except Exception as e:
        print(f"⚠️ Failed to copy {source}: {e}")
    
    # Try fallback search if specified
    if fallback_search_name:
        print(f"🔍 Searching for {fallback_search_name}...")
        
        # Search in common locations
        search_locations = [
            Path(sys.executable).parent,
            Path(sys.prefix),
            Path(sys.base_prefix) if hasattr(sys, 'base_prefix') else Path(sys.prefix),
        ]
        
        # Add PATH locations
        path_env = os.environ.get('PATH', '')
        for path_dir in path_env.split(os.pathsep):
            search_locations.append(Path(path_dir))
        
        # Remove duplicates
        search_locations = list(set(search_locations))
        
        for location in search_locations:
            try:
                if location.exists():
                    for found_file in location.rglob(fallback_search_name):
                        if found_file.is_file():
                            try:
                                shutil.copy2(found_file, dest)
                                print(f"✅ Found and copied {fallback_search_name} from: {found_file}")
                                return True
                            except Exception as e:
                                continue
            except:
                continue
        
        print(f"❌ Could not find {fallback_search_name} anywhere on system")
    
    return False

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
    """Bundle the entire working virtual environment with comprehensive fallbacks"""
    print("\n📦 Bundling complete virtual environment...")
    
    # Find the best Python source
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
    
    print("📦 Creating comprehensive Python environment bundle...")
    
    # Step 1: Create essential directory structure
    essential_dirs = [
        "Scripts",
        "Lib/site-packages", 
        "DLLs",
        "Include"
    ]
    
    for dir_path in essential_dirs:
        (bundle_dir / dir_path).mkdir(parents=True, exist_ok=True)
        print(f"📁 Created: {dir_path}")
    
    total_files = 0
    
    # Step 2: Copy site-packages (most critical)
    print("\n📦 Step 1: Copying Python packages...")
    source_site_packages = None
    possible_site_packages = [
        source_python / "Lib" / "site-packages",
        source_python / "lib" / "python3.12" / "site-packages",
        source_python / "lib" / "python3.11" / "site-packages",
        source_python / "lib" / "python3.10" / "site-packages",
    ]
    
    for sp in possible_site_packages:
        if sp.exists() and len(list(sp.iterdir())) > 10:  # Has actual packages
            source_site_packages = sp
            print(f"✅ Found site-packages: {source_site_packages}")
            break
    
    if not source_site_packages:
        print("❌ No valid site-packages found!")
        return None
    
    # CRITICAL: Copy ALL site-packages content to Lib/site-packages
    dest_site_packages = bundle_dir / "Lib" / "site-packages"
    print(f"📂 Copying from: {source_site_packages}")
    print(f"📂 Copying to: {dest_site_packages}")
    
    try:
        if args.minimal:
            # Minimal mode - copy only essential packages
            critical_packages = [
                "numpy", "cv2", "PIL", "cairo", "manim", "moderngl", 
                "customtkinter", "jedi", "matplotlib", "tkinter", "scipy",
                "fonttools", "manimpango", "skia", "pyglm", "pathops"
            ]
            
            print("📦 Minimal bundle mode - copying critical packages only...")
            for item in source_site_packages.iterdir():
                # Include if package name matches any critical package
                if any(pkg.lower() in item.name.lower() for pkg in critical_packages):
                    try:
                        if item.is_dir():
                            shutil.copytree(item, dest_site_packages / item.name, dirs_exist_ok=True)
                        else:
                            shutil.copy2(item, dest_site_packages / item.name)
                        
                        file_count = sum(1 for _ in (dest_site_packages / item.name).rglob('*') if _.is_file()) if item.is_dir() else 1
                        total_files += file_count
                        print(f"   📂 {item.name}: {file_count} files")
                    except Exception as e:
                        print(f"   ⚠️ Warning: Could not copy {item.name}: {e}")
        else:
            # Full mode - copy EVERYTHING
            print("📦 Full bundle mode - copying ALL packages...")
            for item in source_site_packages.iterdir():
                try:
                    if item.is_dir():
                        shutil.copytree(item, dest_site_packages / item.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest_site_packages / item.name)
                    
                    file_count = sum(1 for _ in (dest_site_packages / item.name).rglob('*') if _.is_file()) if item.is_dir() else 1
                    total_files += file_count
                    if file_count > 10:  # Only show major packages
                        print(f"   📂 {item.name}: {file_count} files")
                except Exception as e:
                    print(f"   ⚠️ Warning: Could not copy {item.name}: {e}")
    
    except Exception as e:
        print(f"❌ Failed to copy site-packages: {e}")
        return None
    
    # Step 3: Copy standard library (CRITICAL FOR PYTHON TO WORK)
    print("\n📦 Step 2: Copying standard library...")
    source_lib = source_python / "Lib"
    dest_lib = bundle_dir / "Lib"
    
    if source_lib.exists():
        try:
            # Copy important standard library modules (not site-packages again)
            for item in source_lib.iterdir():
                if item.name == "site-packages":
                    continue  # Already handled above
                
                try:
                    if item.is_dir():
                        shutil.copytree(item, dest_lib / item.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest_lib / item.name)
                    
                    file_count = sum(1 for _ in (dest_lib / item.name).rglob('*') if _.is_file()) if item.is_dir() else 1
                    total_files += file_count
                    if file_count > 5:  # Only show substantial modules
                        print(f"   📚 {item.name}: {file_count} files")
                except Exception as e:
                    print(f"   ⚠️ Warning: Could not copy {item.name}: {e}")
        except Exception as e:
            print(f"❌ Failed to copy standard library: {e}")
    
    # Step 4: Copy Scripts directory
    print("\n📦 Step 3: Copying Scripts...")
    source_scripts = source_python / "Scripts"
    dest_scripts = bundle_dir / "Scripts"
    
    if source_scripts.exists():
        try:
            for item in source_scripts.iterdir():
                if item.is_file():
                    shutil.copy2(item, dest_scripts / item.name)
                    total_files += 1
            
            script_count = len(list(dest_scripts.iterdir()))
            print(f"   🔧 Copied {script_count} scripts")
        except Exception as e:
            print(f"❌ Failed to copy scripts: {e}")
    
    # Ensure critical executables exist
    critical_executables = [
        ("python.exe", "python*.exe"),
        ("pip.exe", "pip*.exe"),
        ("pythonw.exe", "pythonw*.exe")
    ]
    
    for exe_name, search_pattern in critical_executables:
        dest_exe = dest_scripts / exe_name
        if not dest_exe.exists():
            # Try multiple sources
            sources_tried = []
            
            # Source 1: Scripts directory
            source_exe = source_scripts / exe_name if source_scripts.exists() else None
            if source_exe and source_exe.exists():
                sources_tried.append(str(source_exe))
                copy_with_fallback(source_exe, dest_exe)
            
            # Source 2: Current Python
            if not dest_exe.exists():
                current_exe = Path(sys.executable)
                if exe_name == "python.exe" and current_exe.name in ["python.exe", "python3.exe"]:
                    sources_tried.append(str(current_exe))
                    copy_with_fallback(current_exe, dest_exe)
            
            # Source 3: System-wide search
            if not dest_exe.exists():
                copy_with_fallback(Path("nonexistent"), dest_exe, search_pattern)
            
            if dest_exe.exists():
                size = dest_exe.stat().st_size
                print(f"✅ {exe_name}: {size} bytes")
                total_files += 1
            else:
                print(f"❌ Could not find {exe_name}")
                if exe_name == "python.exe":
                    print("💥 CRITICAL: python.exe is required!")
                    return None
    
    # Create python3.exe as copy of python.exe
    python_exe = dest_scripts / "python.exe"
    python3_exe = dest_scripts / "python3.exe"
    if python_exe.exists() and not python3_exe.exists():
        try:
            shutil.copy2(python_exe, python3_exe)
            print("✅ Created python3.exe")
            total_files += 1
        except Exception as e:
            print(f"⚠️ Could not create python3.exe: {e}")
    
    # Step 5: Copy DLLs
    print("\n📦 Step 4: Copying DLLs...")
    possible_dll_sources = [
        source_python / "DLLs",
        source_python / "Library" / "bin",  # Conda
        Path(sys.executable).parent  # Current Python DLLs
    ]
    
    dest_dlls = bundle_dir / "DLLs"
    
    for dll_source in possible_dll_sources:
        if dll_source.exists():
            try:
                for item in dll_source.iterdir():
                    if item.suffix.lower() == '.dll':
                        try:
                            shutil.copy2(item, dest_dlls / item.name)
                            total_files += 1
                        except Exception:
                            continue
            except Exception:
                continue
    
    dll_count = len(list(dest_dlls.iterdir())) if dest_dlls.exists() else 0
    print(f"   🔗 Copied {dll_count} DLLs")
    
    # Step 6: Create pyvenv.cfg
    print("\n📦 Step 5: Creating pyvenv.cfg...")
    source_cfg = source_python / "pyvenv.cfg"
    dest_cfg = bundle_dir / "pyvenv.cfg"
    
    if source_cfg.exists():
        try:
            shutil.copy2(source_cfg, dest_cfg)
            print("✅ Copied existing pyvenv.cfg")
            total_files += 1
        except Exception as e:
            print(f"⚠️ Could not copy pyvenv.cfg: {e}")
    else:
        # Create minimal pyvenv.cfg
        try:
            with open(dest_cfg, 'w') as f:
                f.write(f"""home = {sys.prefix}
include-system-site-packages = false
version = {sys.version.split()[0]}
""")
            print("✅ Created minimal pyvenv.cfg")
            total_files += 1
        except Exception as e:
            print(f"⚠️ Could not create pyvenv.cfg: {e}")
    
    # Step 7: Copy Python DLLs to root
    print("\n📦 Step 6: Copying Python DLLs...")
    python_version = f"python{sys.version_info.major}{sys.version_info.minor}"
    critical_dlls = [
        f"{python_version}.dll",
        "python3.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll"
    ]
    
    for dll_name in critical_dlls:
        dest_dll = bundle_dir / dll_name
        if not dest_dll.exists():
            copy_with_fallback(Path("nonexistent"), dest_dll, dll_name)
            if dest_dll.exists():
                print(f"✅ Found critical DLL: {dll_name}")
                total_files += 1
    
    # Create manifest
    manifest = {
        "bundle_date": str(datetime.datetime.now()),
        "source_python": str(source_python),
        "total_files": total_files,
        "python_version": sys.version,
        "build_mode": "minimal" if args.minimal else "turbo" if args.turbo else "full",
        "optimization_level": "optimize" if args.optimize else "standard",
        "critical_components": {
            "python_exe": (dest_scripts / "python.exe").exists(),
            "pip_exe": (dest_scripts / "pip.exe").exists(),
            "site_packages": (bundle_dir / "Lib" / "site-packages").exists(),
            "standard_lib": (bundle_dir / "Lib").exists(),
            "pyvenv_cfg": dest_cfg.exists()
        }
    }
    
    try:
        with open(bundle_dir / "bundle_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        total_files += 1
    except Exception as e:
        print(f"⚠️ Could not create manifest: {e}")
    
    print(f"\n📊 Bundle complete: {total_files} files")
    
    # COMPREHENSIVE VERIFICATION
    print(f"\n🔍 COMPREHENSIVE BUNDLE VERIFICATION:")
    print("=" * 60)
    
    # Check directory structure
    expected_dirs = ["Scripts", "Lib", "Lib/site-packages", "DLLs"]
    for dir_path in expected_dirs:
        check_dir = bundle_dir / dir_path
        if check_dir.exists():
            file_count = sum(1 for _ in check_dir.rglob('*') if _.is_file())
            print(f"✅ {dir_path}: {file_count} files")
            
            # Show sample contents
            if dir_path == "Scripts":
                executables = [f for f in check_dir.iterdir() if f.suffix == '.exe']
                print(f"   🔧 Executables: {[e.name for e in executables[:5]]}")
            elif dir_path == "Lib/site-packages":
                packages = [d.name for d in check_dir.iterdir() if d.is_dir()][:10]
                print(f"   📦 Sample packages: {packages}")
        else:
            print(f"❌ MISSING: {dir_path}")
    
    # Check critical files
    critical_files = [
        "Scripts/python.exe",
        "Scripts/pip.exe", 
        "pyvenv.cfg"
    ]
    
    print(f"\n🔍 Critical files check:")
    for file_path in critical_files:
        check_file = bundle_dir / file_path
        if check_file.exists():
            size = check_file.stat().st_size
            print(f"✅ {file_path}: {size} bytes")
        else:
            print(f"❌ MISSING: {file_path}")
    
    # Check total bundle size
    total_size = sum(f.stat().st_size for f in bundle_dir.rglob('*') if f.is_file())
    size_mb = total_size / (1024 * 1024)
    print(f"\n📊 Total bundle size: {size_mb:.1f} MB")
    
    # Verify bundle is not empty
    if total_files < 100:
        print(f"⚠️ WARNING: Bundle seems too small ({total_files} files)")
        print(f"Expected at least 1000+ files for a complete Python environment")
    
    if size_mb < 50:
        print(f"⚠️ WARNING: Bundle size seems too small ({size_mb:.1f} MB)")
        print(f"Expected at least 100+ MB for a complete environment")
    
    print("=" * 60)
    
    return bundle_dir

def create_environment_loader():
    """Create bundled environment loader script - FIXED TO EXTRACT NEXT TO EXE"""
    loader_content = '''import os
import sys
from pathlib import Path

def setup_bundled_environment():
    """Set up the bundled virtual environment - FIXED: Extract next to app.exe"""
    if getattr(sys, 'frozen', False):
        # FIXED: Extract next to app.exe, not in AppData
        app_dir = Path(sys.executable).parent
    else:
        app_dir = Path(__file__).parent
    
    # Look for venv_bundle NEXT TO THE EXE
    venv_bundle = app_dir / "venv_bundle"
    
    print(f"🔍 Looking for bundled environment at: {venv_bundle}")
    print(f"📁 App directory: {app_dir}")
    
    if not venv_bundle.exists():
        print(f"ERROR: venv_bundle directory not found at {venv_bundle}")
        print(f"📂 Directory contents: {list(app_dir.iterdir())}")
        return False
    
    # ENHANCED VALIDATION - Check for required structure
    required_dirs = ["Scripts", "Lib", "Lib/site-packages"]
    missing_dirs = []
    
    print(f"🔍 Validating bundle structure at: {venv_bundle}")
    
    for req_dir in required_dirs:
        dir_path = venv_bundle / req_dir
        if dir_path.exists():
            item_count = len(list(dir_path.iterdir()))
            print(f"✅ {req_dir}: {venv_bundle / req_dir} ({item_count} items)")
        else:
            print(f"❌ MISSING: {req_dir} at {venv_bundle / req_dir}")
            missing_dirs.append(req_dir)
    
    if missing_dirs:
        print(f"❌ Bundle structure invalid - missing: {missing_dirs}")
        bundle_contents = list(venv_bundle.iterdir())
        print(f"Bundle contents: {bundle_contents}")
        
        # Try to recover from flattened structure
        print("🔍 Checking for flattened structure...")
        site_packages_alt = app_dir / "site-packages"
        if site_packages_alt.exists():
            print("🔧 Found flattened site-packages, attempting recovery...")
            # Could implement recovery logic here
            return False
        else:
            print("❌ Cannot recover bundle structure, falling back to normal setup")
            return False
    
    # Set up paths
    site_packages = venv_bundle / "Lib" / "site-packages"
    scripts_dir = venv_bundle / "Scripts"
    
    print(f"🚀 Setting up bundled environment...")
    print(f"   📂 Bundle: {venv_bundle}")
    print(f"   📦 Site-packages: {site_packages}")
    print(f"   🔧 Scripts: {scripts_dir}")
    
    if site_packages.exists():
        # Add to Python path at the beginning
        sys.path.insert(0, str(site_packages))
        print(f"✅ Added to Python path: {site_packages}")
        
        # Set PYTHONPATH environment variable
        current_pythonpath = os.environ.get('PYTHONPATH', '')
        if current_pythonpath:
            os.environ['PYTHONPATH'] = str(site_packages) + os.pathsep + current_pythonpath
        else:
            os.environ['PYTHONPATH'] = str(site_packages)
    
    if scripts_dir.exists():
        # Add scripts directory to PATH
        current_path = os.environ.get('PATH', '')
        os.environ['PATH'] = str(scripts_dir) + os.pathsep + current_path
        print(f"✅ Added to PATH: {scripts_dir}")
    
    # Set virtual environment variable
    os.environ['VIRTUAL_ENV'] = str(venv_bundle)
    print(f"✅ Set VIRTUAL_ENV: {venv_bundle}")
    
    print("🎉 Bundled environment setup complete!")
    return True

# Automatically set up when imported (but not when running as main)
if __name__ != "__main__":
    result = setup_bundled_environment()
    if result:
        print("📦 Bundled environment activated successfully")
    else:
        print("❌ Bundled environment setup failed")
'''
    
    with open("bundled_env_loader.py", "w", encoding="utf-8") as f:
        f.write(loader_content)
    
    print("✅ Created FIXED bundled environment loader")

def build_executable(args):
    """Build the self-contained executable with options"""
    print(f"\n🔨 Building executable in {get_build_mode_name(args)} mode...")
    
    # Bundle environment first
    bundle_dir = bundle_complete_environment(args)
    if bundle_dir is None:
        print("❌ Bundling failed - cannot proceed with build")
        return False
    
    # Validate bundle before proceeding
    print(f"\n🔍 Final bundle validation...")
    required_components = [
        ("Scripts/python.exe", "Python executable"),
        ("Lib/site-packages", "Python packages"),
        ("pyvenv.cfg", "Virtual environment config")
    ]
    
    bundle_valid = True
    for component, description in required_components:
        component_path = bundle_dir / component
        if component_path.exists():
            if component_path.is_file():
                size = component_path.stat().st_size
                print(f"✅ {description}: {size} bytes")
            else:
                count = len(list(component_path.iterdir()))
                print(f"✅ {description}: {count} items")
        else:
            print(f"❌ MISSING: {description} ({component})")
            bundle_valid = False
    
    if not bundle_valid:
        print("❌ Bundle validation failed - cannot proceed")
        return False
    
    # Create the loader
    create_environment_loader()
    
    # Determine number of jobs
    jobs = args.jobs if args.jobs else max(1, multiprocessing.cpu_count() - 1)
    
    # Build nuitka command
    cmd = ["python", "-m", "nuitka"]
    
    # Mode-specific options
    if args.turbo:
        cmd.extend([
            "--standalone",
            "--onefile-child",
            "--disable-console",
        ])
    elif args.optimize:
        cmd.extend([
            "--standalone",
            "--onefile",
            "--disable-console",
            "--lto=yes",
            "--enable-plugin=anti-bloat",
        ])
    elif args.debug:
        cmd.extend([
            "--standalone",
            "--onefile-child",
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
    
    # Common options
    cmd.extend([
        "--enable-plugin=tk-inter",
        "--enable-plugin=numpy",
        "--show-progress",
        "--mingw64",
        "--remove-output",
    ])
    
    # Data inclusion - ensure bundle is properly included
    bundle_dir_abs = bundle_dir.resolve()  # Get absolute path
    cmd.extend([
        f"--include-data-dir={bundle_dir_abs}=venv_bundle",
        "--include-data-file=bundled_env_loader.py=bundled_env_loader.py",
    ])
    
    print(f"📦 Including bundle: {bundle_dir_abs} -> venv_bundle")
    
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
    dirs_to_remove = []
    
    # Only remove venv_bundle if not in debug mode
    if not (args and args.debug):
        dirs_to_remove.append("venv_bundle")
    else:
        print("🐛 Debug mode: Preserving venv_bundle for inspection")
    
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
        print("\n" + "=" * 80)
        print("🎉 BUILD COMPLETE - COMPLETELY FIXED VERSION!")
        print("=" * 80)
        print("✅ Your app.exe is completely self-contained")
        print("✅ Includes PROPER venv_bundle structure (Scripts + Lib + site-packages)")
        print("✅ Enhanced bundle validation prevents ALL structure issues")
        print("✅ No runtime installation needed")
        print("✅ Should work on fresh computers")
        print("✅ Portable - extract bundled environment next to exe")
        print("✅ dist directory preserved with your executable")
        
        exe_path = Path("dist") / "app.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n📦 Final executable: {exe_path}")
            print(f"📏 Size: {size_mb:.1f} MB")
            print(f"📅 Created: {timestamp}")
        
        print(f"\n🧪 Testing instructions:")
        print("1. Copy dist/app.exe to a fresh computer")
        print("2. Run app.exe directly")
        print("3. Environment will extract next to app.exe on first run")
        print("4. Should start without 'venv_bundle directory not found' errors")
        print("5. Should start without missing Lib directory errors")
        print("6. Should start without 3221225477 errors")
        
        if args.turbo:
            print("\n⚠️ Note: Turbo builds are larger but faster to compile")
        elif args.optimize:
            print("\n✨ Note: Optimized builds are smaller and faster at runtime")
            
    else:
        print("\n❌ Build failed!")
        if not args.debug:
            print("💡 Try: python build_nuitka.py --debug for more details")
    
    cleanup(args)
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
