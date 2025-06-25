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
    """Copy file with fallback search if source doesn't exist"""
    if source.exists():
        try:
            shutil.copy2(source, dest)
            return True
        except Exception as e:
            print(f"❌ Copy failed: {e}")
    
    if fallback_search_name:
        print(f"🔍 Searching system for {fallback_search_name}...")
        
        # Search common locations
        search_locations = [
            Path("C:/Windows/System32"),
            Path("C:/Windows/SysWOW64"),
            Path(sys.executable).parent,
            Path(sys.prefix),
            Path(sys.prefix) / "Scripts",
            Path(sys.prefix) / "DLLs",
        ]
        
        # Add all Python installations
        python_installs = find_python_installations()
        for install in python_installs:
            search_locations.extend([
                install,
                install / "Scripts",
                install / "DLLs",
                install.parent / "DLLs"
            ])
        
        # Search PATH directories
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
    print("\n📦 Step 2: Copying Python packages...")
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
            break
    
    if source_site_packages:
        dest_site_packages = bundle_dir / "Lib" / "site-packages"
        print(f"📦 Copying from: {source_site_packages}")
        
        try:
            if args.minimal:
                # Copy only critical packages
                critical_packages = [
                    "numpy", "cv2", "PIL", "cairo", "manim", "moderngl",
                    "customtkinter", "jedi", "matplotlib", "tkinter"
                ]
                
                copied_packages = 0
                for item in source_site_packages.iterdir():
                    if any(pkg.lower() in item.name.lower() for pkg in critical_packages):
                        dest_path = dest_site_packages / item.name
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
                # Copy everything
                shutil.copytree(source_site_packages, dest_site_packages, dirs_exist_ok=True)
                file_count = sum(1 for _ in dest_site_packages.rglob('*') if _.is_file())
                total_files += file_count
                print(f"✅ Copied {len(list(dest_site_packages.iterdir()))} packages ({file_count} files)")
        except Exception as e:
            print(f"❌ Failed to copy site-packages: {e}")
            return None
    else:
        print("❌ No site-packages directory found!")
        return None
    
    # Step 3: Copy Python standard library (excluding site-packages)
    print("\n📚 Step 3: Copying Python standard library...")
    source_stdlib = source_python / "Lib"
    dest_stdlib = bundle_dir / "Lib"

    if source_stdlib.exists():
        try:
            for item in source_stdlib.iterdir():
                if item.name == "site-packages":
                    continue
                dest_path = dest_stdlib / item.name
                if item.is_dir():
                    shutil.copytree(item, dest_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest_path)
            stdlib_count = sum(1 for _ in dest_stdlib.rglob('*') if _.is_file())
            total_files += stdlib_count
            print(f"✅ Copied standard library: {stdlib_count} files")
        except Exception as e:
            print(f"❌ Failed to copy standard library: {e}")
            return None
    else:
        print("❌ Standard library not found!")
        return None

    # Step 4: Copy and find Python executables
    print("\n🐍 Step 4: Setting up Python executables...")
    scripts_dest = bundle_dir / "Scripts"
    
    # Copy Scripts directory if it exists
    source_scripts = source_python / "Scripts"
    if source_scripts.exists():
        try:
            for item in source_scripts.iterdir():
                if item.is_file():
                    shutil.copy2(item, scripts_dest / item.name)
            print(f"✅ Copied existing scripts")
        except Exception as e:
            print(f"⚠️ Some scripts failed to copy: {e}")
    
    # Ensure critical executables exist
    critical_executables = [
        ("python.exe", "python*.exe"),
        ("pip.exe", "pip*.exe"),
        ("pythonw.exe", "pythonw*.exe")
    ]
    
    for exe_name, search_pattern in critical_executables:
        dest_exe = scripts_dest / exe_name
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
    python_exe = scripts_dest / "python.exe"
    python3_exe = scripts_dest / "python3.exe"
    if python_exe.exists() and not python3_exe.exists():
        try:
            shutil.copy2(python_exe, python3_exe)
            print("✅ Created python3.exe")
            total_files += 1
        except Exception as e:
            print(f"⚠️ Could not create python3.exe: {e}")
    
    # Step 5: Copy DLLs and runtime files
    print("\n📚 Step 5: Copying runtime libraries...")
    
    # Copy DLLs directory if it exists
    source_dlls = source_python / "DLLs"
    dest_dlls = bundle_dir / "DLLs"
    
    if source_dlls.exists():
        try:
            shutil.copytree(source_dlls, dest_dlls, dirs_exist_ok=True)
            dll_count = sum(1 for _ in dest_dlls.rglob('*') if _.is_file())
            total_files += dll_count
            print(f"✅ Copied DLLs: {dll_count} files")
        except Exception as e:
            print(f"⚠️ Could not copy DLLs: {e}")
    
    # Find and copy critical Python DLLs
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
    print("\n⚙️ Step 6: Copying configuration...")
    
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
    
    # Create manifest
    manifest = {
        "bundle_date": str(datetime.datetime.now()),
        "source_python": str(source_python),
        "total_files": total_files,
        "python_version": sys.version,
        "build_mode": "minimal" if args.minimal else "turbo" if args.turbo else "full",
        "optimization_level": "optimize" if args.optimize else "standard",
        "critical_components": {
            "python_exe": (scripts_dest / "python.exe").exists(),
            "pip_exe": (scripts_dest / "pip.exe").exists(),
            "site_packages": (bundle_dir / "Lib" / "site-packages").exists(),
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
    components_check = [
        ("Scripts", "Python executables"),
        ("Lib/site-packages", "Python packages"),
        ("DLLs", "Runtime libraries"),
        ("pyvenv.cfg", "Virtual env config")
    ]
    
    bundle_valid = True
    for component, description in components_check:
        component_path = bundle_dir / component
        if component_path.exists():
            if component_path.is_file():
                size = component_path.stat().st_size
                print(f"✅ {description}: {size} bytes")
            else:
                count = len(list(component_path.iterdir()))
                file_count = sum(1 for _ in component_path.rglob('*') if _.is_file())
                print(f"✅ {description}: {count} items ({file_count} files)")
        else:
            print(f"❌ MISSING: {description}")
            if component in ["Scripts", "Lib/site-packages"]:
                bundle_valid = False
    
    # Check critical files
    critical_files = [
        "Scripts/python.exe",
        "Scripts/pip.exe"
    ]
    
    print(f"\n🔍 Critical executables:")
    for file_path in critical_files:
        check_file = bundle_dir / file_path
        if check_file.exists():
            size = check_file.stat().st_size
            print(f"✅ {file_path}: {size} bytes")
        else:
            print(f"❌ MISSING: {file_path}")
            if file_path == "Scripts/python.exe":
                bundle_valid = False
    
    # Check total bundle size
    total_size = sum(f.stat().st_size for f in bundle_dir.rglob('*') if f.is_file())
    size_mb = total_size / (1024 * 1024)
    print(f"\n📊 Total bundle size: {size_mb:.1f} MB")
    
    if not bundle_valid:
        print(f"\n❌ BUNDLE VALIDATION FAILED!")
        print("Critical components are missing. Cannot proceed with build.")
        return None
    
    if total_files < 100:
        print(f"\n⚠️ WARNING: Bundle seems small ({total_files} files)")
    
    if size_mb < 30:
        print(f"⚠️ WARNING: Bundle size seems small ({size_mb:.1f} MB)")
    
    print("=" * 60)
    print("✅ Bundle validation passed!")
    
    return bundle_dir
    """Bundle the entire working virtual environment"""
    print("\n📦 Bundling complete virtual environment...")
    
    # Get current venv path with better detection
    current_venv = None
    
    # Method 1: Check if we're in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        current_venv = Path(sys.prefix)
        print(f"✅ Detected virtual environment: {current_venv}")
    else:
        # Method 2: Try to find venv from executable path
        exe_parent = Path(sys.executable).parent
        if (exe_parent / "Scripts" / "activate").exists() or (exe_parent / "bin" / "activate").exists():
            current_venv = exe_parent
            print(f"✅ Found venv from executable path: {current_venv}")
        else:
            # Method 3: Default fallback
            current_venv = exe_parent.parent
            print(f"⚠️ Using fallback venv path: {current_venv}")
    
    print(f"📁 Bundling from: {current_venv}")
    
    # Verify the source has the basic structure
    if not current_venv.exists():
        print(f"❌ Source venv directory doesn't exist: {current_venv}")
        return None
    
    site_packages = current_venv / "Lib" / "site-packages"
    if not site_packages.exists():
        print(f"❌ Site-packages not found at: {site_packages}")
        # Try alternative location
        site_packages = current_venv / "lib" / "python3.12" / "site-packages"
        if not site_packages.exists():
            print(f"❌ No site-packages found in venv!")
            return None
    
    print(f"✅ Found site-packages: {site_packages}")
    
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
        if not source_site_packages.exists():
            source_site_packages = current_venv / "lib" / "python3.12" / "site-packages"
        
        if not source_site_packages.exists():
            print("❌ Cannot find site-packages in virtual environment!")
            return None
            
        dest_site_packages = bundle_dir / "Lib" / "site-packages"
        dest_site_packages.mkdir(parents=True)
        
        critical_packages = [
            "numpy", "cv2", "PIL", "cairo", "manim", "moderngl", 
            "customtkinter", "jedi", "matplotlib", "tkinter"
        ]
        
        total_files = 0
        for item in source_site_packages.iterdir():
            if any(pkg.lower() in item.name.lower() for pkg in critical_packages):
                try:
                    if item.is_dir():
                        shutil.copytree(item, dest_site_packages / item.name)
                    else:
                        shutil.copy2(item, dest_site_packages / item.name)
                    file_count = sum(1 for _ in (dest_site_packages / item.name).rglob('*') if _.is_file()) if item.is_dir() else 1
                    total_files += file_count
                    print(f"   📂 {item.name}: {file_count} files")
                except Exception as e:
                    print(f"   ⚠️ Warning: Could not copy {item.name}: {e}")
    else:
        # Full bundle - copy ALL essential parts of virtual environment
        print("📦 Full bundle mode - copying complete virtual environment...")
        
        # Define all essential virtual environment components
        venv_components = [
            ("Lib/site-packages", "Essential Python packages"),
            ("Scripts", "Python executables and scripts"),
            ("Include", "Header files"),
            ("DLLs", "Dynamic libraries"),
            ("tcl", "Tcl/Tk libraries"),
            ("Tools", "Python tools")
        ]
        
        total_files = 0
        
        # Verify essential directories exist
        lib_site_packages = current_venv / "Lib" / "site-packages"
        if not lib_site_packages.exists():
            lib_site_packages = current_venv / "lib" / "python3.12" / "site-packages"
        
        if not lib_site_packages.exists():
            print("❌ Cannot find site-packages for full bundle!")
            return None
        
        print(f"✅ Found site-packages with {len(list(lib_site_packages.iterdir()))} packages")
        
        # Copy each component
        for dir_name, description in venv_components:
            if dir_name == "Lib/site-packages":
                source_dir = lib_site_packages
                dest_dir = bundle_dir / "Lib" / "site-packages"
            else:
                source_dir = current_venv / dir_name
                dest_dir = bundle_dir / dir_name
                
            if source_dir.exists():
                print(f"📂 Copying {dir_name} ({description})...")
                
                try:
                    # Ensure destination parent exists
                    dest_dir.parent.mkdir(parents=True, exist_ok=True)
                    
                    if args.turbo:
                        # Fast copy - ignore some non-essential files
                        def ignore_patterns(dir, files):
                            ignore = []
                            for file in files:
                                if file.endswith(('.pyc', '.pyo')) or file == '__pycache__':
                                    ignore.append(file)
                                # Skip very large cache directories
                                elif file in ('__pycache__', '.pytest_cache', '.mypy_cache', 'node_modules'):
                                    ignore.append(file)
                            return ignore
                        
                        shutil.copytree(source_dir, dest_dir, ignore=ignore_patterns, dirs_exist_ok=True)
                    else:
                        shutil.copytree(source_dir, dest_dir, dirs_exist_ok=True)
                    
                    # Count files and verify
                    file_count = sum(1 for _ in dest_dir.rglob('*') if _.is_file())
                    total_files += file_count
                    print(f"   ✅ {file_count} files copied successfully")
                    
                    # Special verification for critical directories
                    if dir_name == "Lib/site-packages":
                        # Verify critical packages are there
                        critical_packages = ['numpy', 'manim', 'PIL', 'cv2']
                        found_packages = []
                        for pkg in critical_packages:
                            pkg_dirs = list(dest_dir.glob(f"{pkg}*"))
                            if pkg_dirs:
                                found_packages.append(pkg)
                        print(f"   ✅ Critical packages found: {found_packages}")
                        
                    elif dir_name == "Scripts":
                        # Verify Python executables
                        python_exe = dest_dir / "python.exe"
                        pip_exe = dest_dir / "pip.exe"
                        print(f"   ✅ python.exe: {python_exe.exists()}")
                        print(f"   ✅ pip.exe: {pip_exe.exists()}")
                        
                except Exception as e:
                    print(f"   ❌ Failed to copy {dir_name}: {e}")
                    import traceback
                    print(f"   Full error: {traceback.format_exc()}")
                    # For critical directories, this is a fatal error
                    if dir_name in ["Lib/site-packages", "Scripts"]:
                        print(f"❌ Critical component {dir_name} failed - aborting bundle")
                        return None
            else:
                print(f"   ⚠️ {dir_name} not found in source venv (skipping)")
                if dir_name in ["Lib/site-packages", "Scripts"]:
                    print(f"❌ Critical component {dir_name} missing - aborting bundle")
                    return None
    
    # Copy/verify essential executables (do this AFTER the main copy loop)
    scripts_dest = bundle_dir / "Scripts"
    if not scripts_dest.exists():
        scripts_dest.mkdir(parents=True)
        print("📂 Created Scripts directory")
    
    # Ensure critical executables exist
    python_exe_dest = scripts_dest / "python.exe"
    if not python_exe_dest.exists():
        # Try different sources for python.exe
        python_sources = [
            current_venv / "Scripts" / "python.exe",  # Virtual env
            Path(sys.executable),  # Current Python
            Path(sys.executable).parent / "python.exe"  # System Python
        ]
        
        for python_source in python_sources:
            if python_source.exists():
                try:
                    shutil.copy2(python_source, python_exe_dest)
                    print(f"✅ Copied python.exe from: {python_source}")
                    break
                except Exception as e:
                    print(f"❌ Failed to copy python.exe from {python_source}: {e}")
                    continue
        else:
            print(f"❌ CRITICAL: Could not find python.exe to copy!")
            return None
    
    # Ensure pip.exe exists
    pip_exe_dest = scripts_dest / "pip.exe"
    if not pip_exe_dest.exists():
        pip_sources = [
            current_venv / "Scripts" / "pip.exe",
            current_venv / "Scripts" / "pip3.exe",
            Path(sys.executable).parent / "pip.exe"
        ]
        
        for pip_source in pip_sources:
            if pip_source.exists():
                try:
                    shutil.copy2(pip_source, pip_exe_dest)
                    print(f"✅ Copied pip.exe from: {pip_source}")
                    break
                except Exception as e:
                    continue
        else:
            print(f"⚠️ Could not find pip.exe to copy")
    
    # Create python3.exe as a copy of python.exe if it doesn't exist
    python3_exe_dest = scripts_dest / "python3.exe"
    if not python3_exe_dest.exists() and python_exe_dest.exists():
        try:
            shutil.copy2(python_exe_dest, python3_exe_dest)
            print(f"✅ Created python3.exe")
        except Exception as e:
            print(f"⚠️ Could not create python3.exe: {e}")
    
    # Copy pyvenv.cfg
    pyvenv_cfg = current_venv / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        try:
            shutil.copy2(pyvenv_cfg, bundle_dir / "pyvenv.cfg")
        except Exception as e:
            print(f"⚠️ Warning: Could not copy pyvenv.cfg: {e}")
    
    # Copy DLLs directory if it exists (important for Windows)
    dlls_source = current_venv / "DLLs"
    if dlls_source.exists():
        dlls_dest = bundle_dir / "DLLs"
        try:
            shutil.copytree(dlls_source, dlls_dest)
            dll_files = sum(1 for _ in dlls_dest.rglob('*') if _.is_file())
            total_files += dll_files
            print(f"📂 DLLs: {dll_files} files")
        except Exception as e:
            print(f"⚠️ Warning: Could not copy DLLs directory: {e}")
    
    # Copy python DLLs from system if they exist and are missing
    python_dll_dest = bundle_dir / "python312.dll"  # Adjust version as needed
    if not python_dll_dest.exists():
        # Look for python DLL in various locations
        python_dll_sources = [
            current_venv / "python312.dll",
            Path(sys.executable).parent / "python312.dll",
            Path(sys.executable).parent / "python311.dll",
            Path(sys.executable).parent / "python310.dll",
        ]
        
        for dll_source in python_dll_sources:
            if dll_source.exists():
                try:
                    shutil.copy2(dll_source, bundle_dir / dll_source.name)
                    print(f"✅ Copied {dll_source.name}")
                    break
                except Exception as e:
                    continue
    
    # Create manifest
    manifest = {
        "bundle_date": str(datetime.datetime.now()),
        "source_venv": str(current_venv),
        "total_files": total_files,
        "python_version": sys.version,
        "build_mode": "minimal" if args.minimal else "turbo" if args.turbo else "full",
        "optimization_level": "optimize" if args.optimize else "standard"
    }
    
    with open(bundle_dir / "bundle_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"📊 Bundle complete: {total_files} files")
    
    # COMPREHENSIVE DIAGNOSTIC: Verify bundle completeness
    print(f"\n🔍 COMPREHENSIVE BUNDLE VERIFICATION:")
    print("=" * 50)
    
    # Check directory structure
    expected_dirs = ["Scripts", "Lib/site-packages"]
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
    
    print("=" * 50)
    
    return bundle_dir

def create_environment_loader():
    """Create bundled environment loader script"""
    loader_content = '''import os
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
        print("ERROR: venv_bundle directory not found")
        return False
    
    stdlib_dir = venv_bundle / "Lib"
    site_packages = stdlib_dir / "site-packages"
    scripts_dir = venv_bundle / "Scripts"
    
    print(f"Setting up bundled environment from: {venv_bundle}")
    
    if stdlib_dir.exists():
        sys.path.insert(0, str(stdlib_dir))
        print(f"Added to Python path: {stdlib_dir}")

    if site_packages.exists():
        # Add to Python path after stdlib
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
    
    if scripts_dir.exists():
        # Add scripts directory to PATH
        current_path = os.environ.get('PATH', '')
        os.environ['PATH'] = str(scripts_dir) + os.pathsep + current_path
        print(f"Added to PATH: {scripts_dir}")
    
    # Set virtual environment variable
    os.environ['VIRTUAL_ENV'] = str(venv_bundle)
    print(f"Set VIRTUAL_ENV: {venv_bundle}")
    
    return True

# Automatically set up when imported (but not when running as main)
if __name__ != "__main__":
    setup_bundled_environment()
'''
    
    with open("bundled_env_loader.py", "w", encoding="utf-8") as f:
        f.write(loader_content)
    
    print("Created bundled environment loader")

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
        print("\n" + "=" * 50)
        print("🎉 BUILD COMPLETE!")
        print("=" * 50)
        print("✅ Your app.exe is completely self-contained")
        print("✅ Includes all required packages and DLLs")
        print("✅ No runtime installation needed")
        print("✅ Should work on fresh computers")
        print("✅ Portable - extract bundled environment next to exe")
        
        print(f"\n🧪 Testing instructions:")
        print("1. Copy dist/app.exe to a fresh computer")
        print("2. Run app.exe directly")
        print("3. Environment will extract next to app.exe on first run")
        print("4. Should start without 3221225477 errors")
        
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
