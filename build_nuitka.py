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
import ctypes
import psutil
import time
import threading
import io
import codecs

# Global flag to use ASCII instead of Unicode symbols
USE_ASCII_ONLY = True

# Comprehensive list of modules to exclude for faster builds
PROBLEMATIC_MODULES = [
    "zstandard", "zstandard.backend_cffi", "setuptools",
    "test.support", "_distutils_hack", "distutils",
    "numpy.distutils", "setuptools_scm",
    # Exclude ALL test modules to speed up compilation
    "sympy.*.tests.*", "sympy.*.test_*", "sympy.tests.*",
    "sympy.polys.benchmarks.*", "sympy.physics.quantum.tests.*",
    "sympy.solvers.ode.tests.*", "sympy.polys.tests.*",
    "sympy.geometry.tests.*", "sympy.core.tests.*",
    "sympy.functions.tests.*", "sympy.matrices.tests.*",
    "sympy.plotting.tests.*", "sympy.printing.tests.*",
    "sympy.simplify.tests.*", "sympy.stats.tests.*",
    "sympy.tensor.tests.*", "sympy.utilities.tests.*",
    # Exclude benchmark modules
    "*.benchmarks.*", "*.test_*", "*.tests.*",
    # Exclude other problematic modules
    "matplotlib.tests.*", "numpy.tests.*", "PIL.tests.*",
    "cv2.tests.*", "jedi.test.*", "pytest.*",
    # Specifically exclude the problematic sympy modules
    "sympy.polys.polyquinticconst", "sympy.polys.benchmarks.bench_solvers",
    "sympy.physics.quantum.tests.test_spin", "sympy.solvers.ode.tests.test_systems"
]

def create_subprocess_helper():
    """Create a unified helper module for subprocess handling"""
    helper_content = '''# process_utils.py - Unified helper for subprocess handling with NO CONSOLE
import subprocess
import sys
import os

# Store original references to subprocess functions before they get patched
# This ensures we always have direct access to the original functions
if not hasattr(subprocess, '_original_stored'):
    subprocess._original_run = subprocess.run
    subprocess._original_popen = subprocess.Popen
    subprocess._original_call = subprocess.call
    subprocess._original_check_output = subprocess.check_output
    subprocess._original_check_call = subprocess.check_call
    subprocess._original_stored = True

def run_hidden_process(command, **kwargs):
    """Run a process with hidden console window
    
    This is a unified helper function that properly handles console hiding
    across different platforms. Use this instead of direct subprocess calls.
    """
    # Always use the original functions to prevent recursion
    original_run = subprocess._original_run
    
    # Configure for Windows console hiding
    startupinfo = None
    creationflags = 0
    
    if sys.platform == "win32":
        # For Windows, use both methods for maximum compatibility
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        # Add the CREATE_NO_WINDOW flag
        if not hasattr(subprocess, "CREATE_NO_WINDOW"):
            subprocess.CREATE_NO_WINDOW = 0x08000000
        creationflags = subprocess.CREATE_NO_WINDOW
        
        # Add startupinfo and creationflags to kwargs
        kwargs['startupinfo'] = startupinfo
        
        # Merge with existing creationflags if any
        if 'creationflags' in kwargs:
            kwargs['creationflags'] |= creationflags
        else:
            kwargs['creationflags'] = creationflags
    
    # Handle capture_output conflict with stdout/stderr
    if kwargs.get('capture_output') and ('stdout' in kwargs or 'stderr' in kwargs):
        kwargs.pop('stdout', None)
        kwargs.pop('stderr', None)
    
    # Run the process using original run to avoid recursion
    return original_run(command, **kwargs)

def popen_hidden_process(command, **kwargs):
    """Get a Popen object with hidden console window
    
    For longer-running processes when you need to interact with stdout/stderr
    during execution.
    """
    # Always use the original functions to prevent recursion
    original_popen = subprocess._original_popen
    
    # Configure for Windows console hiding
    startupinfo = None
    creationflags = 0
    
    if sys.platform == "win32":
        # For Windows, use both methods for maximum compatibility
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        # Add the CREATE_NO_WINDOW flag
        if not hasattr(subprocess, "CREATE_NO_WINDOW"):
            subprocess.CREATE_NO_WINDOW = 0x08000000
        creationflags = subprocess.CREATE_NO_WINDOW
        
        # Add startupinfo and creationflags to kwargs
        kwargs['startupinfo'] = startupinfo
        
        # Merge with existing creationflags if any
        if 'creationflags' in kwargs:
            kwargs['creationflags'] |= creationflags
        else:
            kwargs['creationflags'] = creationflags
    
    # Handle stdout/stderr if not specified
    if kwargs.get('stdout') is None:
        kwargs['stdout'] = subprocess.PIPE
    if kwargs.get('stderr') is None:
        kwargs['stderr'] = subprocess.PIPE
    
    # Create the process using original Popen to avoid recursion
    return original_popen(command, **kwargs)

# Add direct access to original functions
run_original = subprocess._original_run
popen_original = subprocess._original_popen
call_original = subprocess._original_call
check_output_original = subprocess._original_check_output
check_call_original = subprocess._original_check_call

# Export all functions
__all__ = [
    'run_hidden_process', 
    'popen_hidden_process',
    'run_original',
    'popen_original',
    'call_original',
    'check_output_original',
    'check_call_original'
]
'''
    
    # Write with explicit UTF-8 encoding to avoid character encoding issues
    with open("process_utils.py", "w", encoding="utf-8") as f:
        f.write(helper_content)
    
    print("📄 Created subprocess helper module")

def create_fixes_module():
    """Create fixes module to handle runtime issues"""
    fixes_content = '''# fixes.py - Applied patches for the build process
import os
import sys
from pathlib import Path
import subprocess
import shutil
import site

# Import the unified process helper early
try:
    from process_utils import run_hidden_process, popen_hidden_process, run_original, popen_original
except ImportError:
    # Fallback implementation if module is missing
    def run_hidden_process(command, **kwargs):
        startupinfo = None
        creationflags = 0
        
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
            
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
            
        if kwargs.get('capture_output'):
            kwargs.pop('stdout', None)
            kwargs.pop('stderr', None)
        
        return subprocess.run(command, **kwargs)
        
    def popen_hidden_process(command, **kwargs):
        startupinfo = None
        creationflags = 0
        
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
            
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
        
        return subprocess.Popen(command, **kwargs)
    
    run_original = subprocess.run
    popen_original = subprocess.Popen

# Disable zstandard to avoid linking issues - do this as early as possible
try:
    import sys
    sys.modules['zstandard'] = None
except:
    pass

def apply_fixes():
    """Apply all fixes at startup"""
    patch_subprocess()

def patch_subprocess():
    """Patch subprocess to use our hidden process helpers"""
    try:
        # Check if already patched to prevent recursion
        if hasattr(subprocess, '_manimstudio_patched'):
            return True
            
        # Save originals
        original_run = subprocess.run
        original_popen = subprocess.Popen
        
        # Define wrappers that don't trigger recursion
        def safe_run_wrapper(*args, **kwargs):
            # Add window hiding for Windows
            if sys.platform == "win32":
                startupinfo = kwargs.get('startupinfo')
                if not startupinfo:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    kwargs['startupinfo'] = startupinfo
                
                # Add creation flags to hide console
                if 'creationflags' not in kwargs:
                    kwargs['creationflags'] = 0
                kwargs['creationflags'] |= subprocess.CREATE_NO_WINDOW
                
            # Handle capture_output conflict
            if kwargs.get('capture_output') and ('stdout' in kwargs or 'stderr' in kwargs):
                kwargs.pop('stdout', None)
                kwargs.pop('stderr', None)
            
            # Call the original directly
            return original_run(*args, **kwargs)
        
        def safe_popen_wrapper(*args, **kwargs):
            # Add window hiding for Windows
            if sys.platform == "win32":
                startupinfo = kwargs.get('startupinfo')
                if not startupinfo:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    kwargs['startupinfo'] = startupinfo
                
                # Add creation flags to hide console
                if 'creationflags' not in kwargs:
                    kwargs['creationflags'] = 0
                kwargs['creationflags'] |= subprocess.CREATE_NO_WINDOW
            
            # Call the original directly
            return original_popen(*args, **kwargs)
        
        # Replace with our wrappers
        subprocess.run = safe_run_wrapper
        subprocess.Popen = safe_popen_wrapper
        
        # Mark as patched to prevent infinite recursion
        subprocess._manimstudio_patched = True
        
        return True
    except Exception as e:
        print(f"Error patching subprocess: {e}")
        return False
'''
    
    # Write with explicit UTF-8 encoding to avoid character encoding issues
    with open("fixes.py", "w", encoding="utf-8") as f:
        f.write(fixes_content)
    
    print("📄 Created fixes module")

def create_no_console_patch():
    """Create a more aggressive patch file to ensure NO subprocess calls show console windows"""
    patch_content = '''# ENHANCED_NO_CONSOLE_PATCH.py
# This ensures all subprocess calls hide console windows

import subprocess
import sys
import os
import ctypes

# Check if already patched to prevent recursion
if hasattr(subprocess, '_manimstudio_patched'):
    print("Subprocess already patched, skipping additional patching")
else:
    # Define the Windows constants here to guarantee they're available
    if sys.platform == "win32":
        # Define this constant if not available
        if not hasattr(subprocess, "CREATE_NO_WINDOW"):
            subprocess.CREATE_NO_WINDOW = 0x08000000
        
        # Other Windows constants
        CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
        DETACHED_PROCESS = 0x00000008
        SW_HIDE = 0
        STARTF_USESHOWWINDOW = 0x00000001

    # Store original functions BEFORE defining any wrappers
    _original_run = subprocess.run
    _original_popen = subprocess.Popen
    _original_call = subprocess.call
    _original_check_output = subprocess.check_output
    _original_check_call = subprocess.check_call

    def run_hidden_process(command, **kwargs):
        """Run a process with hidden console window"""
        startupinfo = None
        creationflags = 0
        
        if sys.platform == "win32":
            # Set up startupinfo to hide window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = SW_HIDE
            
            # Set creation flags to hide console
            creationflags = CREATE_NO_WINDOW | DETACHED_PROCESS
            
            # Add to kwargs
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
            
            # Handle capture_output conflict
            if kwargs.get('capture_output') and ('stdout' in kwargs or 'stderr' in kwargs):
                kwargs.pop('stdout', None)
                kwargs.pop('stderr', None)
        
        # Run the process using original run
        return _original_run(command, **kwargs)

    def popen_hidden_process(command, **kwargs):
        """Create a Popen object with hidden console window"""
        startupinfo = None
        creationflags = 0
        
        if sys.platform == "win32":
            # Set up startupinfo to hide window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = SW_HIDE
            
            # Set creation flags to hide console
            creationflags = CREATE_NO_WINDOW | DETACHED_PROCESS
            
            # Add to kwargs
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
            
            # Handle stdout/stderr if not specified
            if 'stdout' not in kwargs:
                kwargs['stdout'] = subprocess.PIPE
            if 'stderr' not in kwargs:
                kwargs['stderr'] = subprocess.PIPE
        
        # Create the process using original Popen
        return _original_popen(command, **kwargs)

    # Helper functions for the other subprocess functions
    def _no_console_call(*args, **kwargs):
        return run_hidden_process(*args, **kwargs).returncode

    def _no_console_check_output(*args, **kwargs):
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.DEVNULL
        result = run_hidden_process(*args, **kwargs)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, args[0], result.stdout, result.stderr)
        return result.stdout

    def _no_console_check_call(*args, **kwargs):
        result = run_hidden_process(*args, **kwargs)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, args[0])
        return 0

    # Monkey patch ALL subprocess functions
    subprocess.run = run_hidden_process
    subprocess.Popen = popen_hidden_process
    subprocess.call = _no_console_call
    subprocess.check_output = _no_console_check_output
    subprocess.check_call = _no_console_check_call

    # Mark as patched to prevent recursive patching
    subprocess._manimstudio_patched = True
    subprocess._original_run = _original_run
    subprocess._original_popen = _original_popen

    print("Subprocess patching complete - all console windows will be hidden")

# Export the utility functions so they can be imported
__all__ = ['run_hidden_process', 'popen_hidden_process']
'''
    
    # Write with explicit UTF-8 encoding
    with open("ENHANCED_NO_CONSOLE_PATCH.py", "w", encoding="utf-8") as f:
        f.write(patch_content)
    
    print("📄 Created enhanced no-console patch file")

def run_hidden_process(command, **kwargs):
    """Unified helper to run processes with hidden console"""
    startupinfo = None
    creationflags = 0
    
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        # Define if not available
        if not hasattr(subprocess, "CREATE_NO_WINDOW"):
            subprocess.CREATE_NO_WINDOW = 0x08000000
            
        creationflags = subprocess.CREATE_NO_WINDOW
        
    # Add startupinfo and creationflags to kwargs if on Windows
    if sys.platform == "win32":
        kwargs['startupinfo'] = startupinfo
        if 'creationflags' in kwargs:
            kwargs['creationflags'] |= creationflags
        else:
            kwargs['creationflags'] = creationflags
    
    # Run the process
    return subprocess.run(command, **kwargs)

def check_system_prerequisites():
    """Check system prerequisites for Nuitka build"""
    # Apply zstandard patch early
    try:
        import zstandard
        # Disable it to prevent linking issues
        import sys
        sys.modules['zstandard'] = None
        print("✅ Applied zstandard patch")
        
        # Log the patch
        import logging
        logging.info("Applied zstandard patch")
    except ImportError:
        # Already not available, that's fine
        print("✅ Applied zstandard patch")
        
        # Log the patch
        import logging
        logging.info("Applied zstandard patch")
    
    # Set matplotlib backend to TkAgg
    try:
        import matplotlib
        matplotlib.use('TkAgg')
        print(f"✅ Matplotlib backend set to: {matplotlib.get_backend()}")
        
        # Log the backend setting
        import logging
        logging.info(f"Matplotlib backend set to: {matplotlib.get_backend()}")
    except ImportError:
        print("⚠️ WARNING: matplotlib not available")
    
    print("🔍 Checking system prerequisites")
    
    # Check for Nuitka
    try:
        import nuitka
        # Get Nuitka version using subprocess instead of directly accessing attribute
        try:
            result = run_hidden_process([sys.executable, "-m", "nuitka", "--version"], 
                               capture_output=True, text=True)
            if result.returncode == 0:
                nuitka_version = result.stdout.strip()
                print(f"✅ Nuitka version {nuitka_version} detected")
                logging.info(f"Nuitka version {nuitka_version} detected")
            else:
                print("✅ Nuitka detected, but couldn't determine version")
        except Exception as e:
            # Simpler version check fallback
            print("✅ Nuitka detected")
            logging.info("Nuitka detected")
    except ImportError:
        print("❌ ERROR: Nuitka not found! Please install it with: pip install nuitka")
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

def build_onefile_executable(jobs=None, priority="normal"):
    """Build onefile executable that unpacks next to the exe"""
    
    cpu_count = multiprocessing.cpu_count()
    if jobs is None:
        jobs = max(1, cpu_count - 1)

    print(f"🚀 Building ONEFILE executable using {jobs} CPU threads...")

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

    # Create enhanced patches and helpers
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
        # DISABLE CONSOLE - NO WINDOWS
        "--windows-console-mode=disable",
        "--windows-disable-console",
        "--enable-plugin=tk-inter",
        "--lto=no",
        "--show-progress",
        "--remove-output",
        "--assume-yes-for-downloads",
        "--mingw64",
        "--disable-ccache",
        "--show-memory",
        "--disable-dll-dependency-cache",
        "--windows-force-stdout-spec=nul",
        "--windows-force-stderr-spec=nul",
        "--windows-onefile-tempdir-spec=CACHE",
        "--onefile-tempdir-spec={TEMP}\\nuitka-onefile-{PID}",
    ]

    # MINIMAL exclusions - only exclude test modules
    minimal_exclusions = [
        # Only exclude test modules
        "*.tests.*", "*.test_*", "test.*",
        "pytest.*", "*.benchmarks.*",
        # Still exclude problematic modules that cause build issues
        "zstandard.*", "setuptools.*", "_distutils_hack.*",
        # Exclude only specific problematic SymPy test modules
        "sympy.polys.benchmarks.bench_solvers",
        "sympy.physics.quantum.tests.test_spin", 
        "sympy.solvers.ode.tests.test_systems",
        "sympy.polys.polyquinticconst",
    ]

    for module in minimal_exclusions:
        cmd.append(f"--nofollow-import-to={module}")

    # Ensure subprocess related modules are included for onefile safety
    cmd.extend([
        "--include-module=subprocess",
        "--include-module=threading",
        "--include-module=tempfile",
        "--include-module=os",
    ])

    # Include ALL packages
    comprehensive_packages = [
        "customtkinter", "tkinter", "PIL", "numpy", "cv2",
        "matplotlib", "jedi", "psutil", "manim"
    ]

    included_packages = []
    for package in comprehensive_packages:
        if is_package_importable(package):
            correct_name = get_correct_package_name(package)
            if correct_name:
                included_packages.append(correct_name)
                cmd.append(f"--include-package={correct_name}")
                # Include package data for complete functionality
                cmd.append(f"--include-package-data={correct_name}")
                print(f"📦 Including full package: {correct_name}")

    # Include SymPy
    if is_package_importable("sympy"):
        cmd.append("--include-package=sympy")
        cmd.append("--include-package-data=sympy")
        
        # Only exclude the specific problematic modules from the build error
        sympy_test_exclusions = [
            "sympy.polys.benchmarks.bench_solvers",
            "sympy.physics.quantum.tests.test_spin",
            "sympy.solvers.ode.tests.test_systems", 
            "sympy.polys.polyquinticconst",
            # General test exclusions
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
    cmd.append("app.py")

    print("Building onefile executable...")
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
            # Create launcher scripts
            create_launcher_script(exe_path)
            
            print(f"📁 Executable: {exe_path}")
            print("🎉 ONEFILE FEATURES:")
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
    """Main function - Simple onefile build"""
    import sys  # Explicitly import here to fix scope issue
    
    print("🚀 Manim Studio - Simple Onefile Builder")
    print("=" * 50)
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Build Manim Studio as onefile executable")
    parser.add_argument("--jobs", type=int, help="Number of CPU threads to use (default: CPU count - 1)")
    parser.add_argument("--max-cpu", action="store_true", help="Use all available CPU cores with oversubscription")
    parser.add_argument("--turbo", action="store_true", help="Use turbo mode - maximum CPU with high priority")
    parser.add_argument("--ascii", action="store_true", help="Use ASCII output instead of Unicode symbols")
    
    # Parse args but keep default behavior if not specified
    args, remaining_args = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + remaining_args
    
    global USE_ASCII_ONLY
    if args.ascii:
        USE_ASCII_ONLY = True
    
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
    
    logging.info("Building onefile executable")
    
    # Display build information
    print("\n🎯 Building ONEFILE executable...")
    print("📋 This build includes:")
    print("  ✅ Single file executable")
    print("  ✅ Unpacks to folder next to .exe")
    print("  ✅ Smart caching system")
    print("  ✅ Complete functionality")
    print("  ✅ No console windows")
    print("  ✅ Latest Nuitka onefile features")
    
    # Confirmation
    confirm = input(f"\n🚀 Proceed with onefile build using {jobs} threads? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("❌ Build cancelled by user")
        sys.exit(0)
    
    # Execute the build
    print(f"\n🚀 Starting onefile build process...")
    exe_path = build_onefile_executable(jobs=jobs, priority=process_priority)
    success = exe_path is not None
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Build completed successfully!")
        print("🚀 ONEFILE BUILD: Single file executable ready!")
        print("   🆕 FEATURES:")
        print("   ✅ Single file executable")
        print("   ✅ Unpacks next to the .exe file")
        print("   ✅ Smart caching for better performance")
        print("   ✅ Latest Nuitka onefile technology")
        print("   ✅ Complete functionality included")
        print("   ✅ No console windows")
        print("   🎯 OPTIMIZED: Best onefile integration!")
        print("🚀 Professional desktop application ready!")
        
        # Show usage instructions
        print("\n📋 USAGE INSTRUCTIONS:")
        print(f"   📁 Executable location: {exe_path}")
        print("   🚀 Run the .exe file to start the application")
        print("   📂 App will unpack to 'temp_unpack' folder next to .exe")
        print("   ✅ Complete functionality ready out of the box")
        
    else:
        print("❌ Build failed!")
        print("💡 Check the logs above for error details.")
        print("   📄 Check build.log for detailed error information")
        sys.exit(1)

if __name__ == "__main__":
    main()
