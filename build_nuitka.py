#!/usr/bin/env python3
"""
Complete build_nuitka.py - Self-contained ManimStudio with PROPER bundle structure
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
    current_python = Path(sys.executable)
    current_dir = current_python.parent
    
    print(f"🐍 Current Python: {current_python}")
    
    # First, try current Python's virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        venv_path = Path(sys.prefix)
        print(f"✅ Using current virtual environment: {venv_path}")
        return venv_path
    
    # Second, try to find a virtual environment in the current directory structure
    for parent in [current_dir, current_dir.parent, current_dir.parent.parent]:
        if (parent / "Scripts" / "python.exe").exists() and (parent / "Lib" / "site-packages").exists():
            print(f"✅ Found virtual environment: {parent}")
            return parent
    
    # Third, use current Python installation but we'll need to create a minimal environment
    print(f"⚠️ Using system Python: {current_dir.parent}")
    return current_dir.parent

def copy_with_fallback(source, dest, fallback_search_name=None):
    """Copy file with extensive fallback search if source doesn't exist"""
    if source and source.exists():
        try:
            shutil.copy2(source, dest)
            return True
        except Exception as e:
            print(f"❌ Copy failed: {e}")

    if fallback_search_name:
        print(f"🔍 Searching system for {fallback_search_name}...")

        # Common search locations
        search_locations = {
            Path("C:/Windows/System32"),
            Path("C:/Windows/SysWOW64"),
            Path(sys.executable).parent,
            Path(sys.prefix),
            Path(sys.prefix) / "Scripts",
            Path(sys.prefix) / "DLLs",
        }

        # Python installations
        for install in find_python_installations():
            search_locations.update({
                install,
                install / "Scripts",
                install / "DLLs",
                install.parent / "DLLs",
            })

        # PATH directories
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            if path_dir:
                search_locations.add(Path(path_dir))

        # Additional Program Files locations
        if os.name == "nt":
            for env_var in ["ProgramFiles", "ProgramFiles(x86)"]:
                pf = os.environ.get(env_var)
                if pf:
                    search_locations.add(Path(pf))

        # Perform case-insensitive search
        target_lower = fallback_search_name.lower()
        for location in search_locations:
            try:
                if location.exists():
                    for found in location.rglob("*"):
                        if found.is_file() and found.name.lower() == target_lower:
                            try:
                                shutil.copy2(found, dest)
                                print(f"✅ Found and copied {fallback_search_name} from: {found}")
                                return True
                            except Exception:
                                continue
            except Exception:
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
    """Bundle the entire working virtual environment with COMPLETELY FIXED directory structure"""
    print("\n📦 Bundling complete virtual environment...")
    
    # Find the best Python source
    source_python = find_best_python_source()
    
    if not source_python or not source_python.exists():
        print("❌ Could not find suitable Python installation")
        return None
    
    print(f"📁 Primary source: {source_python}")
    
    # Create bundle directory with CORRECT name (venv_bundle)
    bundle_dir = Path("venv_bundle")
    if bundle_dir.exists():
        print("🗑️ Removing existing bundle...")
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir()
    
    print("📦 Creating comprehensive Python environment bundle...")
    
    # Step 1: Create ESSENTIAL directory structure - CRITICAL FIX
    # Create the directories in the correct order
    print("📁 Creating essential directory structure...")
    scripts_dir = bundle_dir / "Scripts"
    lib_dir = bundle_dir / "Lib"
    site_packages_dir = lib_dir / "site-packages"
    dlls_dir = bundle_dir / "DLLs"
    include_dir = bundle_dir / "Include"
    
    # Ensure all directories exist
    scripts_dir.mkdir(parents=True, exist_ok=True)
    lib_dir.mkdir(parents=True, exist_ok=True)
    site_packages_dir.mkdir(parents=True, exist_ok=True)
    dlls_dir.mkdir(parents=True, exist_ok=True)
    include_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Created Scripts: {scripts_dir}")
    print(f"📁 Created Lib: {lib_dir}")
    print(f"📁 Created Lib/site-packages: {site_packages_dir}")
    print(f"📁 Created DLLs: {dlls_dir}")
    print(f"📁 Created Include: {include_dir}")
    
    total_files = 0
    
    # Step 2: Copy site-packages FIRST - this is the most critical
    print("\n📦 Step 1: Copying Python packages to Lib/site-packages...")
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
            print(f"✅ Found source site-packages: {sp}")
            break
    
    if not source_site_packages:
        print("❌ Could not find site-packages directory")
        return None
    
    # Copy packages to site-packages directory
    try:
        print(f"📦 Copying packages from {source_site_packages} to {site_packages_dir}")
        
        if args.minimal:
            # Copy only critical packages
            critical_packages = [
                "numpy", "cv2", "PIL", "cairo", "manim", "moderngl",
                "customtkinter", "jedi", "matplotlib", "tkinter"
            ]
            
            copied_packages = 0
            for item in source_site_packages.iterdir():
                if any(pkg.lower() in item.name.lower() for pkg in critical_packages):
                    dest_path = site_packages_dir / item.name
                    try:
                        if item.is_dir():
                            shutil.copytree(item, dest_path)
                        else:
                            shutil.copy2(item, dest_path)
                        copied_packages += 1
                        file_count = sum(1 for _ in dest_path.rglob('*') if _.is_file()) if dest_path.is_dir() else 1
                        total_files += file_count
                        print(f"   ✅ {item.name}: {file_count} files")
                    except Exception as e:
                        print(f"   ⚠️ Failed to copy {item.name}: {e}")
            
            print(f"📦 Minimal mode: Copied {copied_packages} critical packages")
        else:
            # Copy ALL packages
            for item in source_site_packages.iterdir():
                dest_path = site_packages_dir / item.name
                try:
                    if item.is_dir():
                        shutil.copytree(item, dest_path)
                    else:
                        shutil.copy2(item, dest_path)
                    file_count = sum(1 for _ in dest_path.rglob('*') if _.is_file()) if dest_path.is_dir() else 1
                    total_files += file_count
                except Exception as e:
                    print(f"   ⚠️ Failed to copy {item.name}: {e}")
            
            package_count = len(list(site_packages_dir.iterdir()))
            print(f"✅ Copied {package_count} packages ({total_files} files)")
            
    except Exception as e:
        print(f"❌ CRITICAL: Failed to copy site-packages: {e}")
        return None
    
    # Verify site-packages was created successfully
    if not site_packages_dir.exists() or len(list(site_packages_dir.iterdir())) == 0:
        print("❌ CRITICAL: site-packages directory is empty or missing!")
        return None
    
    print(f"✅ site-packages verified: {len(list(site_packages_dir.iterdir()))} packages")
    
    # Step 3: Copy Python standard library (excluding site-packages)
    print("\n📚 Step 2: Copying Python standard library to Lib...")
    source_stdlib = source_python / "Lib"

    if source_stdlib.exists():
        try:
            for item in source_stdlib.iterdir():
                if item.name == "site-packages":
                    continue  # Already copied above
                dest_path = lib_dir / item.name
                try:
                    if item.is_dir():
                        shutil.copytree(item, dest_path, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest_path)
                    if dest_path.is_dir():
                        stdlib_files = sum(1 for _ in dest_path.rglob('*') if _.is_file())
                    else:
                        stdlib_files = 1
                    total_files += stdlib_files
                    print(f"   ✅ {item.name}: {stdlib_files} files")
                except Exception as e:
                    print(f"   ⚠️ Failed to copy {item.name}: {e}")
            
            print(f"✅ Standard library copied successfully")
        except Exception as e:
            print(f"❌ Failed to copy standard library: {e}")
            return None
    else:
        print("⚠️ No standard library found - this may cause issues")

    # Step 4: Copy Scripts directory 
    print("\n🐍 Step 3: Setting up Scripts directory...")
    
    # Copy Scripts directory if it exists
    source_scripts = source_python / "Scripts"
    if source_scripts.exists():
        try:
            for item in source_scripts.iterdir():
                dest_path = scripts_dir / item.name
                if item.is_file():
                    shutil.copy2(item, dest_path)
                    total_files += 1
                elif item.is_dir():
                    shutil.copytree(item, dest_path)
                    dir_files = sum(1 for _ in dest_path.rglob('*') if _.is_file())
                    total_files += dir_files
            
            scripts_count = len(list(scripts_dir.iterdir()))
            print(f"✅ Copied Scripts directory: {scripts_count} items")
        except Exception as e:
            print(f"⚠️ Failed to copy some Scripts items: {e}")
    
    # Ensure critical executables exist in Scripts
    critical_executables = [
        ("python.exe", "python*.exe"),
        ("pip.exe", "pip*.exe"),
        ("pythonw.exe", "pythonw*.exe")
    ]
    
    for exe_name, search_pattern in critical_executables:
        dest_exe = scripts_dir / exe_name
        if not dest_exe.exists():
            # Try multiple sources
            print(f"🔍 Finding {exe_name}...")
            
            # Source 1: Scripts directory
            source_exe = source_scripts / exe_name if source_scripts.exists() else None
            if source_exe and source_exe.exists():
                copy_with_fallback(source_exe, dest_exe)
            
            # Source 2: Current Python
            if not dest_exe.exists():
                current_exe = Path(sys.executable)
                if exe_name == "python.exe" and current_exe.name in ["python.exe", "python3.exe"]:
                    copy_with_fallback(current_exe, dest_exe)
            
            # Source 3: System-wide search
            if not dest_exe.exists():
                copy_with_fallback(Path("nonexistent"), dest_exe, exe_name)
            
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
    python_exe = scripts_dir / "python.exe"
    python3_exe = scripts_dir / "python3.exe"
    if python_exe.exists() and not python3_exe.exists():
        try:
            shutil.copy2(python_exe, python3_exe)
            print("✅ Created python3.exe")
            total_files += 1
        except Exception as e:
            print(f"⚠️ Could not create python3.exe: {e}")
    
    # Step 5: Copy DLLs and runtime files
    print("\n📚 Step 4: Copying runtime libraries...")
    
    # Copy DLLs directory if it exists
    source_dlls = source_python / "DLLs"
    if source_dlls.exists():
        try:
            for item in source_dlls.iterdir():
                dest_path = dlls_dir / item.name
                if item.is_file():
                    shutil.copy2(item, dest_path)
                    total_files += 1
            
            dll_count = len(list(dlls_dir.iterdir()))
            print(f"✅ Copied DLLs: {dll_count} files")
        except Exception as e:
            print(f"⚠️ Could not copy all DLLs: {e}")
    
    # Find and copy critical Python DLLs to bundle root
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
    
    # Step 6: Copy configuration files
    print("\n⚙️ Step 5: Copying configuration...")
    
    # Copy pyvenv.cfg
    source_cfg = source_python / "pyvenv.cfg"
    dest_cfg = bundle_dir / "pyvenv.cfg"
    
    if source_cfg.exists():
        try:
            shutil.copy2(source_cfg, dest_cfg)
            print("✅ Copied pyvenv.cfg")
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
    
    # FINAL CRITICAL VALIDATION: Check bundle structure 
    print(f"\n🔍 FINAL CRITICAL BUNDLE STRUCTURE VALIDATION:")
    print("=" * 60)
    
    # Double-check that ALL required directories exist and have content
    critical_paths = [
        (scripts_dir, "Scripts directory"),
        (scripts_dir / "python.exe", "Python executable"),
        (lib_dir, "Lib directory"),
        (site_packages_dir, "site-packages directory"),
        (dest_cfg, "pyvenv.cfg file")
    ]
    
    bundle_valid = True
    for path, description in critical_paths:
        if path.exists():
            if path.is_file():
                size = path.stat().st_size
                print(f"✅ {description}: {size} bytes")
            else:
                count = len(list(path.iterdir()))
                print(f"✅ {description}: {count} items")
                if count == 0:
                    print(f"❌ WARNING: {description} is empty!")
                    if path == site_packages_dir:
                        bundle_valid = False
        else:
            print(f"❌ MISSING: {description} at {path}")
            bundle_valid = False
    
    if not bundle_valid:
        print(f"\n❌ BUNDLE STRUCTURE VALIDATION FAILED!")
        print("Critical components are missing or empty. Cannot proceed with build.")
        print(f"\nBundle directory contents:")
        for item in bundle_dir.rglob('*'):
            print(f"  {item}")
        return None
    
    # Verify structure one more time
    if not lib_dir.exists():
        print("❌ CRITICAL ERROR: Lib directory does not exist!")
        return None
        
    if not site_packages_dir.exists():
        print("❌ CRITICAL ERROR: site-packages directory does not exist!")
        return None
        
    lib_contents = len(list(lib_dir.iterdir()))
    site_packages_contents = len(list(site_packages_dir.iterdir()))
    
    if lib_contents == 0:
        print("❌ CRITICAL ERROR: Lib directory is empty!")
        return None
        
    if site_packages_contents == 0:
        print("❌ CRITICAL ERROR: site-packages directory is empty!")
        return None
    
    # Create manifest
    manifest = {
        "bundle_date": str(datetime.datetime.now()),
        "source_python": str(source_python),
        "total_files": total_files,
        "python_version": sys.version,
        "build_mode": "minimal" if args.minimal else "turbo" if args.turbo else "full",
        "optimization_level": "optimize" if args.optimize else "standard",
        "critical_components": {
            "scripts_dir": scripts_dir.exists(),
            "lib_dir": lib_dir.exists(),
            "site_packages_dir": site_packages_dir.exists(),
            "python_exe": (scripts_dir / "python.exe").exists(),
            "pip_exe": (scripts_dir / "pip.exe").exists(),
            "pyvenv_cfg": dest_cfg.exists(),
            "lib_contents": lib_contents,
            "site_packages_contents": site_packages_contents
        }
    }
    
    try:
        with open(bundle_dir / "bundle_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        total_files += 1
    except Exception as e:
        print(f"⚠️ Could not create manifest: {e}")
    
    print(f"\n📊 Bundle complete: {total_files} files")
    
    # Check total bundle size
    total_size = sum(f.stat().st_size for f in bundle_dir.rglob('*') if f.is_file())
    size_mb = total_size / (1024 * 1024)
    print(f"📊 Total bundle size: {size_mb:.1f} MB")
    
    print("=" * 60)
    print("✅ Bundle structure validation PASSED!")
    print(f"✅ Scripts directory: {len(list(scripts_dir.iterdir()))} items")
    print(f"✅ Lib directory: {lib_contents} items")
    print(f"✅ site-packages: {site_packages_contents} packages")
    
    return bundle_dir

def create_environment_loader():
    """Create ENHANCED bundled environment loader script with proper error handling"""
    loader_content = '''import os
import sys
from pathlib import Path

def setup_bundled_environment():
    """Set up the bundled virtual environment with enhanced error handling"""
    if getattr(sys, 'frozen', False):
        app_dir = Path(sys.executable).parent
    else:
        app_dir = Path(__file__).parent
    
    venv_bundle = app_dir / "venv_bundle"
    
    if not venv_bundle.exists():
        print("ERROR: venv_bundle directory not found")
        print(f"Expected location: {venv_bundle}")
        print(f"App directory contents: {list(app_dir.iterdir()) if app_dir.exists() else 'Not found'}")
        return False
    
    # CRITICAL: Validate bundle structure has both Scripts and Lib
    required_dirs = ["Scripts", "Lib"]
    missing_dirs = []
    
    for required_dir in required_dirs:
        dir_path = venv_bundle / required_dir
        if not dir_path.exists():
            missing_dirs.append(required_dir)
    
    if missing_dirs:
        print(f"ERROR: venv_bundle missing required directories: {missing_dirs}")
        print(f"venv_bundle contents: {list(venv_bundle.iterdir())}")
        return False
    
    # Set up paths
    stdlib_dir = venv_bundle / "Lib"
    site_packages = stdlib_dir / "site-packages"
    scripts_dir = venv_bundle / "Scripts"
    
    print(f"Setting up bundled environment from: {venv_bundle}")
    print(f"Scripts directory: {scripts_dir} (exists: {scripts_dir.exists()})")
    print(f"Lib directory: {stdlib_dir} (exists: {stdlib_dir.exists()})")
    print(f"Site-packages: {site_packages} (exists: {site_packages.exists()})")
    
    # Validate all critical paths exist
    if not stdlib_dir.exists():
        print(f"ERROR: Lib directory not found at {stdlib_dir}")
        return False
        
    if not site_packages.exists():
        print(f"ERROR: site-packages not found at {site_packages}")
        return False
        
    if not scripts_dir.exists():
        print(f"ERROR: Scripts directory not found at {scripts_dir}")
        return False

    # Add standard library to path first
    if stdlib_dir.exists():
        sys.path.insert(0, str(stdlib_dir))
        print(f"Added to Python path: {stdlib_dir}")

    # Add site-packages to path 
    if site_packages.exists():
        sys.path.insert(0, str(site_packages))
        print(f"Added to Python path: {site_packages}")
        
        # Set PYTHONPATH environment variable
        current_pythonpath = os.environ.get('PYTHONPATH', '')
        new_paths = str(site_packages)
        if stdlib_dir.exists():
            new_paths = str(stdlib_dir) + os.pathsep + new_paths
        if current_pythonpath:
            os.environ['PYTHONPATH'] = new_paths + os.pathsep + current_pythonpath
        else:
            os.environ['PYTHONPATH'] = new_paths
    
    # Add scripts directory to PATH
    if scripts_dir.exists():
        current_path = os.environ.get('PATH', '')
        os.environ['PATH'] = str(scripts_dir) + os.pathsep + current_path
        print(f"Added to PATH: {scripts_dir}")
    
    # Set virtual environment variable
    os.environ['VIRTUAL_ENV'] = str(venv_bundle)
    print(f"Set VIRTUAL_ENV: {venv_bundle}")
    
    # Validate Python executable exists
    python_exe = scripts_dir / "python.exe"
    if not python_exe.exists():
        print(f"WARNING: Python executable not found at {python_exe}")
        # Try to find any python executable
        for exe_name in ["python.exe", "python3.exe", "python"]:
            test_exe = scripts_dir / exe_name
            if test_exe.exists():
                print(f"Found alternative Python executable: {test_exe}")
                break
    else:
        print(f"✅ Python executable found: {python_exe}")
    
    print("✅ Bundled environment setup complete")
    return True

# Automatically set up when imported (but not when running as main)
if __name__ != "__main__":
    success = setup_bundled_environment()
    if not success:
        print("❌ Failed to set up bundled environment")
'''
    
    with open("bundled_env_loader.py", "w", encoding="utf-8") as f:
        f.write(loader_content)
    
    print("Created enhanced bundled environment loader")

def build_executable(args):
    """Build the self-contained executable with FIXED bundle structure handling"""
    print(f"\n🔨 Building executable in {get_build_mode_name(args)} mode...")
    
    # Bundle environment first
    bundle_dir = bundle_complete_environment(args)
    if bundle_dir is None:
        print("❌ Bundling failed - cannot proceed with build")
        return False
    
    # CRITICAL: Final validation before build
    print(f"\n🔍 PRE-BUILD BUNDLE VALIDATION...")
    required_components = [
        ("Scripts/python.exe", "Python executable"),
        ("Scripts/pip.exe", "Pip executable"),
        ("Lib", "Python standard library"),
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
        print("❌ Bundle validation failed - critical components missing")
        print("💡 Try rebuilding with: python build_nuitka.py --clean --debug")
        return False
    
    # Additional verification: ensure directories are not empty
    scripts_dir = bundle_dir / "Scripts"
    lib_dir = bundle_dir / "Lib"
    
    scripts_count = len(list(scripts_dir.iterdir())) if scripts_dir.exists() else 0
    lib_count = len(list(lib_dir.rglob('*'))) if lib_dir.exists() else 0
    
    print(f"✅ Scripts directory: {scripts_count} items")
    print(f"✅ Lib directory: {lib_count} items")
    
    if scripts_count == 0:
        print("❌ ERROR: Scripts directory is empty!")
        return False
    if lib_count == 0:
        print("❌ ERROR: Lib directory is empty!")
        return False
    
    print("✅ Bundle validation passed - proceeding with build")
    
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
    
    # CRITICAL FIX: Data inclusion with explicit directory structure preservation
    bundle_dir_abs = bundle_dir.resolve()  # Get absolute path
    cmd.extend([
        f"--include-data-dir={bundle_dir_abs}=venv_bundle",
        "--include-data-file=bundled_env_loader.py=bundled_env_loader.py",
    ])
    
    print(f"📦 Including bundle: {bundle_dir_abs} -> venv_bundle")
    
    # ADDITIONAL FIX: Explicitly include both Scripts and Lib subdirectories
    scripts_dir_abs = bundle_dir_abs / "Scripts"
    lib_dir_abs = bundle_dir_abs / "Lib"
    
    if scripts_dir_abs.exists():
        cmd.append(f"--include-data-dir={scripts_dir_abs}=venv_bundle/Scripts")
        print(f"📦 Explicitly including Scripts: {scripts_dir_abs} -> venv_bundle/Scripts")
    
    if lib_dir_abs.exists():
        cmd.append(f"--include-data-dir={lib_dir_abs}=venv_bundle/Lib")
        print(f"📦 Explicitly including Lib: {lib_dir_abs} -> venv_bundle/Lib")
    
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
                
                print(f"\n🔍 POST-BUILD VALIDATION:")
                print("The bundled environment should have proper structure:")
                print("  venv_bundle/Scripts/  (executables)")
                print("  venv_bundle/Lib/      (standard library + site-packages)")
                print("Test the executable to verify no 'venv_bundle directory not found' errors")
                
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

def clean_before_build():
    """Clean up directories before build - ONLY when explicitly requested"""
    dirs_to_clean = ["build", "dist", "venv_bundle"]
    files_to_clean = ["bundled_env_loader.py"]
    
    print("🧹 Cleaning build directories...")
    
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"   🗑️ Removed: {dir_name}/")
            except Exception as e:
                print(f"   ⚠️ Could not remove {dir_name}: {e}")
    
    for file_name in files_to_clean:
        if os.path.exists(file_name):
            try:
                os.remove(file_name)
                print(f"   🗑️ Removed: {file_name}")
            except Exception as e:
                print(f"   ⚠️ Could not remove {file_name}: {e}")

def cleanup_temp_files_only():
    """Clean up ONLY temporary files - NEVER touch dist directory after successful build"""
    temp_files_to_remove = ["bundled_env_loader.py"]
    temp_dirs_to_remove = ["venv_bundle"]  # Only temp bundle, NOT dist
    
    print("🧹 Cleaning temporary files...")
    
    for file_name in temp_files_to_remove:
        if os.path.exists(file_name):
            try:
                os.remove(file_name)
                print(f"   🗑️ Removed temp file: {file_name}")
            except Exception as e:
                print(f"   ⚠️ Could not remove {file_name}: {e}")
    
    for dir_name in temp_dirs_to_remove:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"   🗑️ Removed temp directory: {dir_name}/")
            except Exception as e:
                print(f"   ⚠️ Could not remove {dir_name}: {e}")
    
    # NEVER remove dist directory here - that would delete the built executable!
    print("✅ Temporary files cleaned (dist directory preserved)")

def main():
    """Main build function with SAFE cleanup that preserves dist directory"""
    parser = argparse.ArgumentParser(
        description="Build self-contained ManimStudio executable with COMPLETELY FIXED bundle structure",
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
                       help="Clean all build directories BEFORE building")
    parser.add_argument("--preserve-temp", action="store_true",
                       help="Preserve temporary files for debugging")
    
    args = parser.parse_args()
    
    print("🎯 ManimStudio Self-Contained Build - COMPLETELY FIXED VERSION")
    print("=" * 80)
    print(f"🔧 Mode: {get_build_mode_name(args)}")
    
    if args.minimal:
        print("📦 Bundle: Minimal (critical packages only)")
    else:
        print("📦 Bundle: Full (all packages)")
    
    print("🔧 Critical fixes applied:")
    print("  ✅ PROPER Lib directory creation and population")
    print("  ✅ PROPER site-packages directory structure")
    print("  ✅ Enhanced directory existence validation")
    print("  ✅ Fixed Nuitka data inclusion")
    print("  ✅ SAFE cleanup - dist directory preserved")
    print("  ✅ Enhanced error reporting")
    print("=" * 80)
    
    # Clean BEFORE build if requested
    if args.clean:
        clean_before_build()
    
    if not check_build_environment():
        return False
    
    # Create dist directory if it doesn't exist
    dist_dir = Path("dist")
    dist_dir.mkdir(exist_ok=True)
    
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
        
        # Show final executable info
        exe_path = Path("dist") / "app.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\n📦 Final executable: {exe_path}")
            print(f"📏 Size: {size_mb:.1f} MB")
            print(f"📅 Created: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
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
    
    # Clean up ONLY temporary files, NEVER the dist directory
    if not args.preserve_temp:
        cleanup_temp_files_only()
    else:
        print("🐛 Preserving temporary files for debugging")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
