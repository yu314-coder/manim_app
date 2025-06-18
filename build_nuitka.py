#!/usr/bin/env python3
"""
Enhanced Nuitka Build Script for Manim Studio
Includes Visual C++ redistributable DLL bundling, mapbox_earcut fix, and debug capabilities
"""

import os
import sys
import subprocess
import shutil
import tempfile
import multiprocessing
import importlib
import argparse
import glob
from pathlib import Path

# ASCII vs Unicode output control
USE_ASCII_ONLY = False

def run_hidden_process(command, **kwargs):
    """Run process with hidden window on Windows"""
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = startupinfo
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    
    return subprocess.run(command, **kwargs)

def create_debug_app():
    """Create a debug version of app.py that shows startup progress"""
    debug_content = '''
import sys
import os
import traceback

def debug_print(msg):
    """Print debug message to both console and file"""
    print(f"[DEBUG] {msg}")
    try:
        with open("debug_startup.log", "a", encoding="utf-8") as f:
            f.write(f"[DEBUG] {msg}\\n")
    except:
        pass

try:
    debug_print("=== DEBUG STARTUP ===")
    debug_print(f"Python executable: {sys.executable}")
    debug_print(f"Python version: {sys.version}")
    debug_print(f"Current working directory: {os.getcwd()}")
    debug_print(f"Frozen: {getattr(sys, 'frozen', False)}")
    debug_print(f"sys.argv: {sys.argv}")
    
    # Test basic imports
    debug_print("Testing basic imports...")
    
    import tkinter
    debug_print("✓ tkinter imported")
    
    import customtkinter
    debug_print("✓ customtkinter imported")
    
    # Test the problematic import
    debug_print("Testing mapbox_earcut import...")
    try:
        import mapbox_earcut
        debug_print("✓ mapbox_earcut imported successfully")
    except Exception as e:
        debug_print(f"✗ mapbox_earcut import failed: {e}")
        debug_print(f"Error type: {type(e)}")
        debug_print(f"Error traceback: {traceback.format_exc()}")
    
    # Test other critical imports
    try:
        import numpy
        debug_print("✓ numpy imported")
    except Exception as e:
        debug_print(f"✗ numpy import failed: {e}")
    
    try:
        import PIL
        debug_print("✓ PIL imported")
    except Exception as e:
        debug_print(f"✗ PIL import failed: {e}")
    
    try:
        import cv2
        debug_print("✓ cv2 imported")
    except Exception as e:
        debug_print(f"✗ cv2 import failed: {e}")
    
    try:
        import matplotlib
        debug_print("✓ matplotlib imported")
    except Exception as e:
        debug_print(f"✗ matplotlib import failed: {e}")
    
    debug_print("All imports tested, attempting to create simple window...")
    
    # Create a simple test window
    import tkinter as tk
    root = tk.Tk()
    root.title("Debug Test Window")
    root.geometry("400x300")
    
    label = tk.Label(root, text="DEBUG: App started successfully!\\nCheck debug_startup.log for details", 
                     font=("Arial", 12), wraplength=350)
    label.pack(expand=True)
    
    button = tk.Button(root, text="Close", command=root.destroy)
    button.pack(pady=20)
    
    debug_print("Test window created, starting mainloop...")
    root.mainloop()
    debug_print("Window closed normally")
    
except Exception as e:
    debug_print(f"CRITICAL ERROR: {e}")
    debug_print(f"Error type: {type(e)}")
    debug_print(f"Full traceback: {traceback.format_exc()}")
    
    # Try to show error in a message box
    try:
        import tkinter.messagebox as messagebox
        messagebox.showerror("Debug Error", f"Critical startup error:\\n{e}\\n\\nCheck debug_startup.log for details")
    except:
        pass
    
    # Keep console open
    input("Press Enter to exit...")
'''
    
    with open("debug_app.py", "w", encoding="utf-8") as f:
        f.write(debug_content)
    
    print("✅ Created debug_app.py")

def create_no_console_patch():
    """Create patch to disable console windows"""
    patch_content = '''
import subprocess
import sys

# Store original subprocess functions
_original_run = subprocess.run
_original_popen = subprocess.Popen

def hidden_run(*args, **kwargs):
    """Run subprocess with hidden window on Windows"""
    if sys.platform == "win32" and 'startupinfo' not in kwargs:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = startupinfo
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    return _original_run(*args, **kwargs)

def hidden_popen(*args, **kwargs):
    """Popen subprocess with hidden window on Windows"""
    if sys.platform == "win32" and 'startupinfo' not in kwargs:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = startupinfo
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    return _original_popen(*args, **kwargs)

# Patch subprocess module
subprocess.run = hidden_run
subprocess.Popen = hidden_popen
'''
    
    with open("no_console_patch.py", "w", encoding="utf-8") as f:
        f.write(patch_content)
    
    print("🔧 Created no console patch")

def create_fixes_module():
    """Create enhanced fixes module"""
    fixes_content = '''
import os
import sys
import subprocess

def patch_subprocess():
    """Enhanced subprocess patching for Nuitka builds"""
    try:
        if hasattr(subprocess, '_manimstudio_patched'):
            return True
            
        original_run = subprocess.run
        original_popen = subprocess.Popen
        
        def safe_run_wrapper(*args, **kwargs):
            if sys.platform == "win32":
                startupinfo = kwargs.get('startupinfo')
                if startupinfo is None:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    kwargs['startupinfo'] = startupinfo
                
                if 'creationflags' not in kwargs:
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
            return original_run(*args, **kwargs)
        
        def safe_popen_wrapper(*args, **kwargs):
            if sys.platform == "win32":
                startupinfo = kwargs.get('startupinfo')
                if startupinfo is None:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    kwargs['startupinfo'] = startupinfo
                
                if 'creationflags' not in kwargs:
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
            return original_popen(*args, **kwargs)
        
        subprocess.run = safe_run_wrapper
        subprocess.Popen = safe_popen_wrapper
        subprocess._manimstudio_patched = True
        
        return True
    except Exception as e:
        print(f"Subprocess patching failed: {e}")
        return False

def fix_dll_loading():
    """Fix DLL loading for compiled extensions like mapbox_earcut"""
    try:
        import ctypes
        import os
        
        # Get executable directory
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            
            # Add DLL directories to search path
            dll_dirs = [
                exe_dir,
                os.path.join(exe_dir, 'dlls'),
                os.path.join(exe_dir, 'lib'),
            ]
            
            for dll_dir in dll_dirs:
                if os.path.exists(dll_dir):
                    # Add to PATH
                    current_path = os.environ.get('PATH', '')
                    if dll_dir not in current_path:
                        os.environ['PATH'] = dll_dir + os.pathsep + current_path
                    
                    # Use AddDllDirectory on Windows 10+
                    if hasattr(ctypes.windll.kernel32, 'AddDllDirectory'):
                        try:
                            ctypes.windll.kernel32.AddDllDirectory(dll_dir)
                        except Exception:
                            pass
            
            # Pre-load critical DLLs
            critical_dlls = [
                'msvcp140.dll',
                'vcruntime140.dll', 
                'vcruntime140_1.dll',
                'concrt140.dll'
            ]
            
            for dll_name in critical_dlls:
                try:
                    ctypes.CDLL(dll_name)
                except Exception:
                    pass
        
        return True
    except Exception as e:
        print(f"DLL loading fix failed: {e}")
        return False

# Apply fixes automatically when imported
patch_subprocess()
fix_dll_loading()
'''
    
    with open("fixes.py", "w", encoding="utf-8") as f:
        f.write(fixes_content)
    
    print("🔧 Created enhanced fixes module")

def create_subprocess_helper():
    """Create subprocess helper for process utilities"""
    helper_content = '''
import subprocess
import sys

# Store original functions to prevent recursion
popen_original = subprocess.Popen
run_original = subprocess.run

def run_hidden_subprocess(command, **kwargs):
    """Run subprocess with hidden window"""
    if sys.platform == "win32":
        startupinfo = kwargs.get('startupinfo')
        if startupinfo is None:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = startupinfo
        
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    
    return run_original(command, **kwargs)
'''
    
    with open("process_utils.py", "w", encoding="utf-8") as f:
        f.write(helper_content)
    
    print("🔧 Created subprocess helper")

def bundle_vcredist_dlls():
    """Bundle Visual C++ redistributable DLLs with the executable"""
    print("🔧 Bundling Visual C++ redistributable DLLs...")
    
    # Common locations for VC++ redistributable DLLs
    system_dirs = [
        r"C:\Windows\System32",
        r"C:\Windows\SysWOW64",
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Redist\MSVC\*\x64\Microsoft.VC143.CRT",
        r"C:\Program Files\Microsoft Visual Studio\2022\*\VC\Redist\MSVC\*\x64\Microsoft.VC143.CRT",
        r"C:\Program Files (x86)\Microsoft Visual Studio\2019\*\VC\Redist\MSVC\*\x64\Microsoft.VC142.CRT",
        r"C:\Program Files\Microsoft Visual Studio\2019\*\VC\Redist\MSVC\*\x64\Microsoft.VC142.CRT"
    ]
    
    required_dlls = [
        "msvcp140.dll",
        "vcruntime140.dll", 
        "vcruntime140_1.dll",
        "concrt140.dll"
    ]
    
    dll_dir = Path("dist/dlls")
    dll_dir.mkdir(parents=True, exist_ok=True)
    
    found_dlls = []
    for dll_name in required_dlls:
        dll_found = False
        for sys_dir in system_dirs:
            try:
                dll_paths = glob.glob(os.path.join(sys_dir, dll_name))
                if dll_paths:
                    # Use the first found DLL
                    src_path = dll_paths[0]
                    dst_path = dll_dir / dll_name
                    shutil.copy2(src_path, dst_path)
                    found_dlls.append(dll_name)
                    print(f"📦 Bundled DLL: {dll_name} from {src_path}")
                    dll_found = True
                    break
            except Exception as e:
                continue
        
        if not dll_found:
            print(f"⚠️ Could not find {dll_name}")
    
    if found_dlls:
        print(f"✅ Successfully bundled {len(found_dlls)} DLLs")
    else:
        print("❌ No VC++ redistributable DLLs found")
    
    return found_dlls

def check_system_prerequisites():
    """Check system prerequisites for building"""
    print("🔍 Checking system prerequisites...")
    
    # Check Nuitka
    try:
        import nuitka
        print("  ✅ Nuitka available")
    except ImportError:
        print("  ❌ Nuitka not available")
        print("Please install it with: pip install nuitka")
        return False
    
    return True

def is_package_importable(package_name):
    """Check if a package can be imported"""
    try:
        # Handle special cases
        if package_name == "PIL":
            import PIL
            return True
        elif package_name == "cv2":
            import cv2
            return True
        elif package_name == "process_utils":
            # This is our own module, will be included
            return True
        else:
            importlib.import_module(package_name)
            return True
    except ImportError:
        return False

def get_correct_package_name(package_name):
    """Get the correct package name for Nuitka"""
    # Special cases
    if package_name == "PIL":
        return "PIL"
    elif package_name == "cv2":
        return "cv2"
    elif package_name == "process_utils":
        return "process_utils"
    return package_name

def get_nuitka_version():
    """Get Nuitka version for compatibility checks"""
    try:
        result = run_hidden_process(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "Unknown"
    except Exception:
        return "Unknown"

def create_launcher_script(exe_path):
    """Create a batch launcher script that sets the correct environment"""
    exe_dir = os.path.dirname(exe_path)
    launcher_content = f'''@echo off
REM Set environment variable so the app knows where it really is
set NUITKA_ONEFILE_PARENT={exe_path}
REM Launch the application
start "" "{exe_path}"
exit
'''
    
    launcher_path = Path("Launch_ManimStudio.bat")
    with open(launcher_path, 'w', encoding="utf-8") as f:
        f.write(launcher_content)
    
    # Also create a PowerShell launcher
    ps_launcher_content = f'''# PowerShell launcher for ManimStudio
$env:NUITKA_ONEFILE_PARENT = "{exe_path}"
Start-Process -FilePath "{exe_path}"
'''
    
    ps_launcher_path = Path("Launch_ManimStudio.ps1")
    with open(ps_launcher_path, 'w', encoding="utf-8") as f:
        f.write(ps_launcher_content)
    
    print(f"📝 Created launchers: {launcher_path} and {ps_launcher_path}")

def find_standalone_executable():
    """Find standalone executable"""
    dist_dir = Path("dist")
    if not dist_dir.exists():
        return None

    possible_paths = [
        dist_dir / "app.exe",
        dist_dir / "debug_app.exe",
        dist_dir / "app.dist" / "app.exe",
        dist_dir / "ManimStudio.exe",
    ]

    for path in possible_paths:
        if path.exists():
            return path

    for exe_file in dist_dir.rglob("*.exe"):
        if exe_file.name not in ["python.exe", "pythonw.exe"]:
            return exe_file

    return None

def list_contents():
    """List contents of build directories"""
    for dir_name in ["dist", "build"]:
        dir_path = Path(dir_name)
        if dir_path.exists():
            print(f"\n📂 Contents of {dir_name}:")
            for item in dir_path.iterdir():
                if item.is_file():
                    size = item.stat().st_size / (1024 * 1024)
                    print(f"  📄 {item.name} ({size:.1f} MB)")
                elif item.is_dir():
                    print(f"  📁 {item.name}/")

def check_requirements():
    """Check if all build requirements are met"""
    print("🔍 Checking build requirements...")
    
    required_packages = [
        "nuitka", "customtkinter", "PIL", "numpy", "cv2", 
        "matplotlib", "manim", "jedi", "psutil"
    ]
    
    missing = []
    for package in required_packages:
        try:
            if package == "PIL":
                import PIL
            elif package == "cv2":
                import cv2
            else:
                __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package}")
            missing.append(package)
    
    if missing:
        print(f"\n⚠️ Missing packages: {missing}")
        print("Install with: pip install " + " ".join(missing))
        return False
    
    print("✅ All requirements met!")
    return True

def check_dependencies_with_tools():
    """Use dependency checking tools if available"""
    print("🔍 Checking for dependency analysis tools...")
    
    # Check for Dependency Walker
    depends_paths = [
        r"C:\Program Files (x86)\Dependency Walker\depends.exe",
        r"C:\Program Files\Dependency Walker\depends.exe",
        "depends.exe"
    ]
    
    for path in depends_paths:
        if os.path.exists(path) or shutil.which(path):
            print(f"✅ Found Dependency Walker: {path}")
            print("💡 You can use this to analyze your exe:")
            print(f"   {path} dist\\app.exe")
            break
    else:
        print("❌ Dependency Walker not found")
        print("💡 Download from: http://www.dependencywalker.com/")
    
    # Check for dumpbin (Visual Studio tool)
    if shutil.which("dumpbin"):
        print("✅ Found dumpbin (Visual Studio tool)")
        print("💡 You can check dependencies with:")
        print("   dumpbin /dependents dist\\app.exe")
    else:
        print("❌ dumpbin not found (install Visual Studio Build Tools)")

def build_debug_executable(jobs=None):
    """Build a debug version that shows console windows"""
    
    cpu_count = multiprocessing.cpu_count()
    if jobs is None:
        jobs = max(1, cpu_count - 1)
    
    # Clean previous builds
    if Path("build").exists():
        shutil.rmtree("build")
    if Path("dist").exists():
        shutil.rmtree("dist")
    
    # Create debug app
    create_debug_app()
    
    print("🔧 Building DEBUG executable (with console windows)...")
    
    # Basic debug build command - SHOWS CONSOLE
    cmd = [
        sys.executable, "-m", "nuitka",
        "--onefile",
        "--onefile-tempdir-spec={PROGRAM_DIR}/temp_unpack",
        "--show-progress",
        "--remove-output",
        "--assume-yes-for-downloads",
        "--mingw64",
        "--show-memory",
        # DO NOT HIDE CONSOLE - we want to see errors
        # "--windows-console-mode=disable",  # COMMENTED OUT
        # "--windows-disable-console",       # COMMENTED OUT
        "--enable-plugin=tk-inter",
        "--lto=no",
        
        # Include essential packages
        "--include-package=tkinter",
        "--include-package=customtkinter", 
        "--include-package=mapbox_earcut",
        "--include-package=numpy",
        "--include-package=PIL",
        "--include-package=cv2",
        "--include-package=matplotlib",
        
        # Include data
        "--include-package-data=numpy",
        "--include-package-data=PIL",
        
        # Output
        "--output-dir=dist",
        f"--jobs={jobs}",
        
        # Target file
        "debug_app.py"
    ]
    
    print("Debug build command:")
    print(" ".join(cmd))
    print("=" * 60)
    
    # Run the build
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    if result.returncode == 0:
        print("✅ Debug build successful!")
        exe_path = Path("dist/debug_app.exe")
        if exe_path.exists():
            print(f"📁 Debug executable: {exe_path}")
            print("🚀 Run this to see startup messages and errors")
            return exe_path
        else:
            print("❌ Executable not found")
            list_contents()
    else:
        print("❌ Debug build failed!")
        print(f"Return code: {result.returncode}")
    
    return None

def build_onefile_executable(jobs=None, priority="normal", debug_mode=False):
    """Build onefile executable that unpacks next to the exe"""
    
    cpu_count = multiprocessing.cpu_count()
    if jobs is None:
        jobs = max(1, cpu_count - 1)

    print(f"🚀 Building {'DEBUG' if debug_mode else 'PRODUCTION'} ONEFILE executable using {jobs} CPU threads...")

    # Clean previous builds
    if Path("build").exists():
        shutil.rmtree("build")
    if Path("dist").exists():
        shutil.rmtree("dist")

    # Create assets directory
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("🔧 Creating enhanced build configuration...")

    # Create enhanced patches and helpers (only for production builds)
    if not debug_mode:
        create_no_console_patch()
        create_fixes_module()
        create_subprocess_helper()

    # Check prerequisites
    if not check_system_prerequisites():
        print("❌ System prerequisites check failed")
        sys.exit(1)

    # Get Nuitka version
    nuitka_version = get_nuitka_version()
    print(f"📊 Detected Nuitka version: {nuitka_version}")

    print("=" * 60)
    print("🔨 Building onefile executable...")

    # Basic command structure with latest onefile options
    cmd = [
        sys.executable, "-m", "nuitka",
        "--onefile",
        "--onefile-tempdir-spec={PROGRAM_DIR}/temp_unpack",  # Latest: unpack next to exe
        "--onefile-cache-mode=cached",  # Force persistent caching - NEVER delete
        "--enable-plugin=tk-inter",
        "--lto=no",
        "--show-progress",
        "--remove-output",
        "--assume-yes-for-downloads",
        "--mingw64",
        "--disable-ccache",
        "--show-memory",
        "--disable-dll-dependency-cache",
    ]

    # Console hiding (only for production builds)
    if not debug_mode:
        cmd.extend([
            "--windows-console-mode=disable",
            "--windows-disable-console",
            "--windows-force-stdout-spec=nul",
            "--windows-force-stderr-spec=nul",
        ])
    else:
        print("🐛 DEBUG MODE: Console windows will be visible")

    # CRITICAL: Include Visual C++ runtime dependencies for mapbox_earcut
    cmd.extend([
        # Include Visual C++ redistributables
        "--include-module=msvcrt",
        "--include-module=_ctypes",
        
        # Force inclusion of mapbox_earcut and its dependencies
        "--include-package=mapbox_earcut",
        "--follow-import-to=mapbox_earcut",
        
        # Include Python's dynamic loading support
        "--include-module=ctypes",
        "--include-module=ctypes.util",
        
        # Include NumPy which mapbox_earcut depends on
        "--include-package=numpy",
        "--include-package-data=numpy",
        
        # Include additional C extension support
        "--include-module=_ctypes_test",
        "--include-module=_multiprocessing",
    ])

    # MINIMAL exclusions - only exclude test modules
    minimal_exclusions = [
        # Only exclude test modules
        "*.tests.*", "*.test_*", "test.*",
        "pytest.*", "*.benchmarks.*",
        # Still exclude problematic modules that cause build issues
        "zstandard.*", "setuptools.*", "_distutils_hack.*"
    ]

    for exclusion in minimal_exclusions:
        cmd.append(f"--nofollow-import-to={exclusion}")

    # Track included packages for summary
    included_packages = []

    # Include essential packages
    essential_packages = [
        "customtkinter", "tkinter", "PIL", "numpy", "cv2", 
        "matplotlib", "psutil", "jedi", "requests"
    ]

    for package in essential_packages:
        if is_package_importable(package):
            package_name = get_correct_package_name(package)
            cmd.append(f"--include-package={package_name}")
            included_packages.append(package_name)
            print(f"📦 Including package: {package_name}")

    # Include Manim with special handling
    if is_package_importable("manim"):
        cmd.extend([
            "--include-package=manim",
            "--follow-import-to=manim",
            "--include-package-data=manim"
        ])
        included_packages.append("manim")
        print("🎬 Including Manim")

    # Include SymPy if available (needed for Manim)
    if is_package_importable("sympy"):
        cmd.append("--include-package=sympy")
        
        # Exclude SymPy test modules to reduce size
        sympy_test_exclusions = [
            "sympy.*.tests.*", "sympy.*.test_*"
        ]
        
        for exclusion in sympy_test_exclusions:
            cmd.append(f"--nofollow-import-to={exclusion}")
        
        included_packages.append("sympy")
        print("🧮 Including SymPy")

    # Include comprehensive system modules
    comprehensive_modules = [
        "json", "tempfile", "threading", "subprocess",
        "os", "sys", "ctypes", "venv", "fixes", "psutil",
        "process_utils", "logging", "pathlib", "shutil",
        "glob", "re", "time", "datetime", "uuid", "base64",
        "io", "codecs", "platform", "getpass", "signal",
        "atexit", "queue", "math", "random", "collections",
        "itertools", "functools", "operator", "copy",
        # Additional modules
        "xml", "xml.etree", "xml.etree.ElementTree",
        "urllib", "urllib.request", "urllib.parse",
        "zipfile", "tarfile", "gzip", "bz2", "lzma",
        "hashlib", "hmac", "ssl", "socket"
    ]

    for module in comprehensive_modules:
        cmd.append(f"--include-module={module}")

    # Include comprehensive data
    data_packages = ["manim", "matplotlib", "numpy", "sympy"]

    for package in data_packages:
        if is_package_importable(package):
            cmd.append(f"--include-package-data={package}")
            print(f"📊 Including comprehensive data for: {package}")

    # Add explicit data inclusion for compiled extensions
    try:
        import mapbox_earcut
        import os
        earcut_path = os.path.dirname(mapbox_earcut.__file__)
        cmd.append(f"--include-data-dir={earcut_path}=mapbox_earcut")
        print(f"📦 Including mapbox_earcut from: {earcut_path}")
    except ImportError:
        print("⚠️ mapbox_earcut not found in build environment")

    # Output configuration
    cmd.extend([
        "--output-dir=dist",
        f"--jobs={jobs}",
    ])

    # Icon if available
    if Path("assets/icon.ico").exists():
        cmd.append("--windows-icon-from-ico=assets/icon.ico")

    # Include all data directories
    data_dirs = ["assets=assets"]
    
    # Try to include matplotlib data
    try:
        import matplotlib
        mpl_data = Path(matplotlib.get_data_path())
        if mpl_data.exists():
            data_dirs.append(f"{mpl_data}=matplotlib/mpl-data")
            print("📊 Including matplotlib data directory")
    except ImportError:
        pass

    for data_dir in data_dirs:
        cmd.append(f"--include-data-dir={data_dir}")

    # Final target
    target_file = "debug_app.py" if debug_mode else "app.py"
    cmd.append(target_file)

    print(f"Building {'debug' if debug_mode else 'production'} onefile executable...")
    print("Command:", " ".join(cmd))
    print("=" * 60)

    # Environment setup
    env = os.environ.copy()
    env["GCC_LTO"] = "0"
    env["NUITKA_DISABLE_LTO"] = "1"
    env["GCC_COMPILE_ARGS"] = "-fno-lto"

    # Set process priority
    process_priority = 0
    if priority == "high" and sys.platform == "win32":
        print("🔥 Setting HIGH process priority for maximum CPU utilization")
        process_priority = 0x00000080

    # Run the build
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        env=env,
        creationflags=process_priority if sys.platform == "win32" else 0
    )

    # Display build info
    print(f"🖥️ CPU Info: {cpu_count} logical cores available")
    print(f"⚙️ Using {jobs} compilation threads")
    print(f"📦 Included {len(included_packages)} packages")

    # Stream compilation output
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            print(line.strip())

    return_code = process.poll()

    if return_code == 0:
        print("=" * 60)
        print("✅ Onefile build successful!")

        exe_path = find_standalone_executable()
        if exe_path:
            # Create launcher scripts (only for production builds)
            if not debug_mode:
                create_launcher_script(exe_path)
            
            print(f"📁 Executable: {exe_path}")
            if debug_mode:
                print("🐛 DEBUG FEATURES:")
                print("  ✅ Console windows visible")
                print("  ✅ Debug logging enabled")
                print("  ✅ Error messages displayed")
            else:
                print("🎉 PRODUCTION FEATURES:")
                print("  ✅ Single file executable")
                print("  ✅ Unpacks next to the .exe file")
                print("  ✅ Smart caching system")
                print("  ✅ No console windows")
                print("  ✅ Complete functionality included")

            return exe_path
        else:
            print("❌ Executable not found")
            list_contents()
            return None
    else:
        print("=" * 60)
        print("❌ Build failed!")
        print(f"Return code: {return_code}")
        sys.exit(1)

def main():
    """Main function - Enhanced onefile build with DLL support and debug capabilities"""
    import sys  # Explicitly import here to fix scope issue
    
    print("🚀 Manim Studio - Enhanced Onefile Builder with DLL Support & Debug Mode")
    print("=" * 70)
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Build Manim Studio as onefile executable")
    parser.add_argument("--jobs", type=int, help="Number of CPU threads to use (default: CPU count - 1)")
    parser.add_argument("--max-cpu", action="store_true", help="Use all available CPU cores with oversubscription")
    parser.add_argument("--turbo", action="store_true", help="Use turbo mode - maximum CPU with high priority")
    parser.add_argument("--ascii", action="store_true", help="Use ASCII output instead of Unicode symbols")
    parser.add_argument("--debug", action="store_true", help="Build debug version with visible console windows")
    parser.add_argument("--debug-only", action="store_true", help="Build only debug version for troubleshooting")
    
    # Parse args but keep default behavior if not specified
    args, remaining_args = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + remaining_args
    
    global USE_ASCII_ONLY
    if args.ascii:
        USE_ASCII_ONLY = True
    
    # Debug mode handling
    if args.debug_only:
        print("🐛 DEBUG-ONLY MODE: Building debug version only")
        exe_path = build_debug_executable()
        if exe_path:
            print("\n" + "=" * 60)
            print("🎯 DEBUG BUILD COMPLETE!")
            print("📋 TROUBLESHOOTING STEPS:")
            print(f"1. Run: {exe_path}")
            print("2. Watch for console output and error messages")
            print("3. Check debug_startup.log file")
            check_dependencies_with_tools()
        return
    
    # Determine job count
    cpu_count = multiprocessing.cpu_count()
    process_priority = "normal"
    
    if args.turbo:
        # Turbo mode: maximum cores + oversubscription + high priority
        jobs = int(cpu_count * 2)  # Double the cores for extreme oversubscription
        process_priority = "high"
        print(f"🚀 TURBO MODE: Maximum CPU power with {jobs} threads and HIGH priority!")
    elif args.max_cpu:
        # Maximum cores with oversubscription
        jobs = int(cpu_count * 1.5)  # Oversubscription by 50%
        print(f"🔥 Maximum CPU mode: {jobs} threads (oversubscribed from {cpu_count} cores)")
    elif args.jobs:
        jobs = args.jobs
        print(f"⚙️ Using specified CPU threads: {jobs} of {cpu_count} available")
    else:
        jobs = max(1, cpu_count - 1)
        print(f"⚙️ Using optimal CPU threads: {jobs} of {cpu_count} available")
    
    # Check requirements first
    if not check_requirements():
        print("❌ Please install missing packages first")
        sys.exit(1)
    
    # Configure logging
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('build.log', mode='w', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    logging.info("Building enhanced onefile executable with DLL support")
    
    # Display build information
    build_type = "DEBUG" if args.debug else "PRODUCTION"
    print(f"\n🎯 Building {build_type} ONEFILE executable...")
    print("📋 This build includes:")
    print("  ✅ Single file executable")
    print("  ✅ Unpacks to folder next to .exe")
    print("  ✅ Smart caching system")
    print("  ✅ Complete functionality")
    if not args.debug:
        print("  ✅ No console windows")
    else:
        print("  🐛 Console windows visible (debug mode)")
    print("  ✅ Visual C++ redistributable DLLs")
    print("  ✅ mapbox_earcut DLL fix")
    print("  ✅ Latest Nuitka onefile features")
    
    # Before building, bundle required DLLs
    print("\n🔧 Bundling Visual C++ redistributable DLLs...")
    bundled_dlls = bundle_vcredist_dlls()
    
    if not bundled_dlls:
        print("⚠️ Warning: No VC++ DLLs found. You may need to install them separately.")
        print("   Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe")
        user_choice = input("Continue build anyway? (y/N): ").lower().strip()
        if user_choice not in ['y', 'yes']:
            print("❌ Build cancelled")
            sys.exit(1)
    
    # Confirmation
    confirm = input(f"\n🚀 Proceed with {build_type.lower()} onefile build using {jobs} threads? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("❌ Build cancelled by user")
        sys.exit(0)
    
    # Execute the build
    print(f"\n🚀 Starting {build_type.lower()} onefile build process...")
    exe_path = build_onefile_executable(jobs=jobs, priority=process_priority, debug_mode=args.debug)
    success = exe_path is not None
    
    # Post-build: Copy DLLs next to executable
    if success and exe_path and bundled_dlls:
        print("\n📦 Copying DLLs to executable directory...")
        exe_dir = os.path.dirname(exe_path)
        
        for dll in bundled_dlls:
            src = Path("dist/dlls") / dll
            dst = Path(exe_dir) / dll
            if src.exists():
                try:
                    shutil.copy2(src, dst)
                    print(f"  ✅ Copied {dll} to executable directory")
                except Exception as e:
                    print(f"  ⚠️ Failed to copy {dll}: {e}")
    
    print("\n" + "=" * 60)
    if success:
        print(f"🎉 {build_type} build completed successfully!")
        print(f"🚀 {build_type} ONEFILE BUILD: Single file executable ready!")
        print("   🆕 ENHANCED FEATURES:")
        print("   ✅ Single file executable")
        print("   ✅ Unpacks next to the .exe file")
        print("   ✅ Smart caching for better performance")
        print("   ✅ Visual C++ redistributable DLLs included")
        print("   ✅ mapbox_earcut DLL loading fixed")
        print("   ✅ Latest Nuitka onefile technology")
        print("   ✅ Complete functionality included")
        if not args.debug:
            print("   ✅ No console windows")
        else:
            print("   🐛 Console windows visible for debugging")
        print("   🎯 OPTIMIZED: Best onefile integration with DLL support!")
        print("🚀 Professional desktop application ready!")
        
        # Show usage instructions
        print("\n📋 USAGE INSTRUCTIONS:")
        print(f"   📁 Executable location: {exe_path}")
        print("   🚀 Run the .exe file to start the application")
        print("   📂 App will unpack to 'temp_unpack' folder next to .exe")
        print("   🔧 Visual C++ DLLs are bundled with the executable")
        if args.debug:
            print("   🐛 Console output will be visible for debugging")
            print("   📄 Check debug_startup.log for detailed startup info")
        print("   ✅ Complete functionality ready out of the box")
        
        if bundled_dlls:
            print(f"\n📦 Bundled DLLs: {', '.join(bundled_dlls)}")
        
        # Additional troubleshooting info for debug builds
        if args.debug:
            print("\n🔧 DEBUGGING INFO:")
            check_dependencies_with_tools()
        
    else:
        print("❌ Build failed!")
        print("💡 Check the logs above for error details.")
        print("   📄 Check build.log for detailed error information")
        print("   🐛 Try --debug flag to see console output")
        print("   🐛 Or use --debug-only for troubleshooting")
        sys.exit(1)

if __name__ == "__main__":
    main()
