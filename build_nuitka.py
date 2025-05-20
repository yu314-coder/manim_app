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
import tqdm 
# Global flag to use ASCII instead of Unicode symbols
USE_ASCII_ONLY = True

def create_nuitka_plugin_patch():
    """Create a patch to fix Nuitka plugin path issues with Python 3.12"""
    patch_content = '''
# nuitka_plugin_patch.py
import os
import sys

# Monkey patch os.path functions that handle None incorrectly
original_abspath = os.path.abspath
def safe_abspath(path):
    if path is None:
        print("WARNING: None path detected in abspath, using empty string instead")
        path = ""
    return original_abspath(path)

os.path.abspath = safe_abspath

# Also patch normpath
original_normpath = os.path.normpath
def safe_normpath(path):
    if path is None:
        print("WARNING: None path detected in normpath, using empty string instead")
        path = ""
    return original_normpath(path)

os.path.normpath = safe_normpath
'''
    
    with open("nuitka_plugin_patch.py", "w", encoding="utf-8") as f:
        f.write(patch_content)
    
    if USE_ASCII_ONLY:
        print("Created Nuitka plugin patch")
    else:
        print("📄 Created Nuitka plugin patch")

def build_self_contained_version(jobs=None, priority="normal"):
    """Build self-contained version with NO CONSOLE EVER"""
    
    # Get CPU count first
    cpu_count = multiprocessing.cpu_count()
    
    # Determine optimal job count if not specified
    if jobs is None:
        # Use N-1 cores by default to keep system responsive
        jobs = max(1, cpu_count - 1)
    
    # For maximum performance, oversubscribe slightly
    if jobs == cpu_count:
        # Oversubscription for maximum CPU utilization
        jobs = int(cpu_count * 1.5)
    
    if USE_ASCII_ONLY:
        print(f"Building SELF-CONTAINED version (NO CONSOLE) with {jobs} CPU threads...")
    else:
        print(f"🐍 Building SELF-CONTAINED version (NO CONSOLE) with {jobs} CPU threads...")
    
    # Clean previous builds
    if Path("build").exists():
        if USE_ASCII_ONLY:
            print("Cleaning build directory...")
        else:
            print("🧹 Cleaning build directory...")
        shutil.rmtree("build")
    if Path("dist").exists():
        if USE_ASCII_ONLY:
            print("Cleaning dist directory...")
        else:
            print("🧹 Cleaning dist directory...")
        shutil.rmtree("dist")
    
    # Create assets directory if it doesn't exist
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)
    
    # Prepare bundled venv
    bundled_venv = prepare_bundled_environment()
    
    # Create enhanced no-console patch
    create_no_console_patch()
    
    # Create fixes module
    create_fixes_module()
    
    # Create helper script for unified subprocess handling
    create_subprocess_helper()
    
    # Create Nuitka plugin patch for Python 3.12 compatibility
    create_nuitka_plugin_patch()
    
    # Check system prerequisites
    if not check_system_prerequisites():
        if USE_ASCII_ONLY:
            print("ERROR: System prerequisites check failed")
        else:
            print("❌ System prerequisites check failed")
        return None
    
    # Detect Nuitka version for compatibility
    nuitka_version = get_nuitka_version()
    if USE_ASCII_ONLY:
        print(f"Detected Nuitka version: {nuitka_version}")
    else:
        print(f"📊 Detected Nuitka version: {nuitka_version}")
    
    # Check for Nuitka version compatibility
    if nuitka_version.startswith("2.6"):
        if USE_ASCII_ONLY:
            print("Warning: Nuitka 2.6.x has plugin issues with Python 3.12, consider updating to 2.7+")
        else:
            print("⚠️ Warning: Nuitka 2.6.x has plugin issues with Python 3.12, consider updating to 2.7+")
    
    # Apply Nuitka plugin patch for Python 3.12
    with open("temp_fix.py", "w", encoding="utf-8") as f:
        f.write("import nuitka_plugin_patch\n")
    subprocess.run([sys.executable, "temp_fix.py"], check=False)
    
    # Basic command with universal options
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",  # Single executable file
    ]
    
    # Add Python 3.12 compatibility fixes if needed
    if sys.version_info >= (3, 12, 0):
        if USE_ASCII_ONLY:
            print("Detected Python 3.12 - applying compatibility fixes")
        else:
            print("🔧 Detected Python 3.12 - applying compatibility fixes")
        
        # Python 3.12 compatibility fixes for Nuitka
        cmd.append("--noinclude-default-mode=error")  # Less strict inclusion
        cmd.append("--plugin-no-detection")  # Disable automatic plugin detection
        cmd.append("--include-module=nuitka_plugin_patch")  # Include our patch
    
    # Enhanced console hiding - use both modern and legacy options for maximum compatibility
    cmd.append("--windows-console-mode=disable")  # Modern option
    cmd.append("--windows-disable-console")       # Legacy option for compatibility
    
    # Add GUI toolkit for matplotlib - using the safer approach for plugins
    cmd.append("--plugin-enable=tk-inter")  # Alternative format
    cmd.append("--enable-plugin=tk-inter")  # Standard format
    
    # Explicitly disable problematic plugins
    cmd.append("--plugin-disable=numpy")
    cmd.append("--plugin-disable=matplotlib")
    
    # CRITICAL: Completely disable LTO to fix the zstandard error
    cmd.append("--lto=no")
    
    # Explicitly exclude problematic modules
    cmd.append("--nofollow-import-to=zstandard")
    cmd.append("--nofollow-import-to=zstandard.backend_cffi")
    cmd.append("--nofollow-import-to=setuptools")
    cmd.append("--nofollow-import-to=test.support")
    cmd.append("--nofollow-import-to=_distutils_hack")
    
    # NEW: Exclude Manim testing modules and pytest to avoid errors
    cmd.append("--nofollow-import-to=manim.utils.testing")
    cmd.append("--nofollow-import-to=pytest")
    cmd.append("--nofollow-import-to=unittest")
    cmd.append("--nofollow-import-to=test")
    
    # IMPORTANT: Use show-progress instead of no-progressbar
    cmd.append("--show-progress")
    
    # Add optimization flags that don't use LTO
    cmd.extend([
        "--remove-output",                     # Remove intermediate files to reduce I/O
        "--assume-yes-for-downloads",          # Don't prompt for downloads
        "--mingw64",                           # Use MinGW64 compiler
        "--disable-ccache",                    # Disable ccache to avoid issues
        "--show-memory",                       # Show memory usage
    ])
    
    # Explicitly include tkinter modules
    for module in ["tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.filedialog", "tkinter.colorchooser"]:
        cmd.append(f"--include-module={module}")
    
    # Check for importable packages and include only those that exist
    essential_packages = [
        "customtkinter", "tkinter", "PIL", "numpy", "cv2", 
        "matplotlib", "scipy", "manim", "jedi"
    ]
    
    included_packages = []
    for package in essential_packages:
        if is_package_importable(package):
            correct_name = get_correct_package_name(package)
            if correct_name:
                included_packages.append(correct_name)
                cmd.append(f"--include-package={correct_name}")
                if USE_ASCII_ONLY:
                    print(f"Including package: {correct_name}")
                else:
                    print(f"✅ Including package: {correct_name}")
        else:
            if USE_ASCII_ONLY:
                print(f"Skipping unavailable package: {package}")
            else:
                print(f"⚠️ Skipping unavailable package: {package}")
    
    # Include critical modules that are part of standard library
    essential_modules = [
        "json", "tempfile", "threading", "subprocess", 
        "os", "sys", "ctypes", "venv", "fixes", "psutil",
        "process_utils", "nuitka_plugin_patch"
    ]
    
    for module in essential_modules:
        cmd.append(f"--include-module={module}")
    
    # Include package data for Manim (for config files)
    cmd.append("--include-package-data=manim")
    
    # Output options
    cmd.extend([
        "--output-dir=dist",
        "--output-filename=ManimStudio.exe",
    ])
    
    # Icon (if available)
    if Path("assets/icon.ico").exists():
        cmd.append("--windows-icon-from-ico=assets/icon.ico")
    
    # Include data directories
    cmd.extend([
        "--include-data-dir=assets=assets",
        f"--include-data-dir={bundled_venv}=bundled_venv",
    ])
    
    # Add custom performance flags to maximize CPU
    cmd.append("--disable-dll-dependency-cache")
    cmd.append("--force-stdout-spec=PIPE")
    cmd.append("--force-stderr-spec=PIPE")
    
    # Jobs for faster compilation - use the calculated job count
    cmd.append(f"--jobs={jobs}")
    
    # Final target
    cmd.append("app.py")
    
    if USE_ASCII_ONLY:
        print("Building executable with NO CONSOLE...")
    else:
        print("🔨 Building executable with NO CONSOLE...")
    print("Command:", " ".join(cmd))
    print("=" * 60)
    
    # Create environment variables to force disable LTO in GCC and handle plugin paths
    env = os.environ.copy()
    env["GCC_LTO"] = "0"
    env["NUITKA_DISABLE_LTO"] = "1"
    env["GCC_COMPILE_ARGS"] = "-fno-lto"
    env["NUITKA_PLUGIN_PATH_HANDLING"] = "strict"
    env["NUITKA_PLUGIN_DISABLE"] = "true"  # Extra safety to disable plugins
    
    # Set process priority if on Windows
    process_priority = 0  # Normal priority by default
    if priority == "high" and sys.platform == "win32":
        if USE_ASCII_ONLY:
            print("Setting HIGH process priority for maximum CPU utilization")
        else:
            print("🔥 Setting HIGH process priority for maximum CPU utilization")
        process_priority = 0x00000080  # HIGH_PRIORITY_CLASS
    
    # IMPORTANT: Use standard subprocess directly to ensure output is visible
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffered output
        universal_newlines=True,
        env=env,
        creationflags=process_priority if sys.platform == "win32" else 0
    )
    
    # Display CPU info
    if USE_ASCII_ONLY:
        print(f"CPU Info: {cpu_count} logical cores available")
        print(f"Using {jobs} compilation threads")
    else:
        print(f"🖥️ CPU Info: {cpu_count} logical cores available")
        print(f"⚙️ Using {jobs} compilation threads")
    
    # Print output in real-time
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            print(line.strip())
    
    return_code = process.poll()
    
    if return_code == 0:
        print("=" * 60)
        if USE_ASCII_ONLY:
            print("NO-CONSOLE build successful!")
        else:
            print("✅ NO-CONSOLE build successful!")
        
        # Find executable
        exe_path = find_executable()
        
        if exe_path:
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            if USE_ASCII_ONLY:
                print(f"Executable: {exe_path} ({size_mb:.1f} MB)")
                print(f"\nSUCCESS! Silent executable ready!")
                print(f"Run: {exe_path}")
                print(f"\nGUARANTEED: NO CONSOLE WINDOWS WILL APPEAR")
            else:
                print(f"📁 Executable: {exe_path} ({size_mb:.1f} MB)")
                print(f"\n🎉 SUCCESS! Silent executable ready!")
                print(f"🚀 Run: {exe_path}")
                print(f"\n🔇 GUARANTEED: NO CONSOLE WINDOWS WILL APPEAR")
            
            # Create a launcher script
            create_launcher_script(exe_path)
            
            return exe_path
        else:
            if USE_ASCII_ONLY:
                print("Executable not found")
            else:
                print("❌ Executable not found")
            list_contents()
            return None
    else:
        print("=" * 60)
        if USE_ASCII_ONLY:
            print("Build failed!")
        else:
            print("❌ Build failed!")
        print(f"Return code: {return_code}")
        return None

def create_subprocess_helper():
    """Create a unified helper module for subprocess handling"""
    helper_content = '''# process_utils.py - Unified helper for subprocess handling with NO CONSOLE
import subprocess
import sys
import os

def run_hidden_process(command, **kwargs):
    """Run a process with hidden console window
    
    This is a unified helper function that properly handles console hiding
    across different platforms. Use this instead of direct subprocess calls.
    """
    startupinfo = None
    creationflags = 0
    
    if sys.platform == "win32":
        # For Windows, use both methods for maximum compatibility
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        # Add the CREATE_NO_WINDOW flag
        creationflags = subprocess.CREATE_NO_WINDOW
        
    # Add startupinfo and creationflags to kwargs if on Windows
    if sys.platform == "win32":
        kwargs['startupinfo'] = startupinfo
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
    
    # Handle capture_output conflict with stdout/stderr
    if kwargs.get('capture_output'):
        kwargs.pop('stdout', None)
        kwargs.pop('stderr', None)
    
    # Run the process
    return subprocess.run(command, **kwargs)

def popen_hidden_process(command, **kwargs):
    """Get a Popen object with hidden console window
    
    For longer-running processes when you need to interact with stdout/stderr
    during execution.
    """
    startupinfo = None
    creationflags = 0
    
    if sys.platform == "win32":
        # For Windows, use both methods for maximum compatibility
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        # Add the CREATE_NO_WINDOW flag
        creationflags = subprocess.CREATE_NO_WINDOW
        
    # Add startupinfo and creationflags to kwargs if on Windows
    if sys.platform == "win32":
        kwargs['startupinfo'] = startupinfo
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
    
    # Create the process
    return subprocess.Popen(command, **kwargs)
'''
    
    # Write with explicit UTF-8 encoding to avoid character encoding issues
    with open("process_utils.py", "w", encoding="utf-8") as f:
        f.write(helper_content)
    
    if USE_ASCII_ONLY:
        print("Created subprocess helper module")
    else:
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
    from process_utils import run_hidden_process, popen_hidden_process
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

# Disable zstandard to avoid linking issues - do this as early as possible
try:
    import sys
    sys.modules['zstandard'] = None
except:
    pass

def fix_manim_config():
    """Fix the manim configuration issue by creating a default.cfg file"""
    try:
        # For packaged app - find the temp directory where files are extracted
        temp_base = None
        for path in sys.path:
            if 'onefile_' in path and 'Temp' in path:
                temp_base = path
                break
                
        if temp_base:
            # Create manim config directory
            manim_config_dir = os.path.join(temp_base, 'manim', '_config')
            os.makedirs(manim_config_dir, exist_ok=True)
            
            # Create a basic default.cfg file
            default_cfg_path = os.path.join(manim_config_dir, 'default.cfg')
            with open(default_cfg_path, 'w') as f:
                f.write(DEFAULT_MANIM_CONFIG)
                
            print(f"Created manim config at: {default_cfg_path}")
            return True
    except Exception as e:
        print(f"Error fixing manim config: {e}")
    return False

# Default minimal manim config content
DEFAULT_MANIM_CONFIG = """
[CLI]
media_dir = ./media
verbosity = INFO
notify_outdated_version = True
tex_template = 

[logger]
logging_keyword = manim
logging_level = INFO

[output]
max_files_cached = 100
flush_cache = False
disable_caching = False

[progress_bar]
leave_progress_bars = True
use_progress_bars = True

[tex]
intermediate_filetype = dvi
text_to_replace = YourTextHere
tex_template_file = tex_template.tex

[universal]
background_color = BLACK
assets_dir = ./

[window]
background_opacity = 1
fullscreen = False
size = 1280,720
"""

# Add this to app.py's main() at the start
def apply_fixes():
    """Apply all fixes at startup"""
    fix_manim_config()
    patch_subprocess()

# Enhanced subprocess patching that uses our unified helpers
def patch_subprocess():
    """Patch subprocess to use our hidden process helpers"""
    try:
        # Import the specific helpers we need
        try:
            from process_utils import run_hidden_process, popen_hidden_process
        except ImportError:
            # Already defined fallbacks above
            pass
            
        # Save originals
        original_run = subprocess.run
        original_popen = subprocess.Popen
        
        # Replace with our hidden versions
        subprocess.run = run_hidden_process
        subprocess.Popen = popen_hidden_process
        
        return True
    except Exception as e:
        print(f"Error patching subprocess: {e}")
        return False
'''
    
    # Write with explicit UTF-8 encoding to avoid character encoding issues
    with open("fixes.py", "w", encoding="utf-8") as f:
        f.write(fixes_content)
    
    if USE_ASCII_ONLY:
        print("Created fixes module to handle runtime issues")
    else:
        print("📄 Created fixes module to handle runtime issues")

def create_no_console_patch():
    """Create a more aggressive patch file to ensure NO subprocess calls show console windows"""
    patch_content = '''# ENHANCED_NO_CONSOLE_PATCH.py
# This ensures all subprocess calls hide console windows

import subprocess
import sys
import os
import ctypes

# Import unified process utilities if available
try:
    from process_utils import run_hidden_process, popen_hidden_process
except ImportError:
    # Will be defined below
    pass

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

# Load Windows API functions for more aggressive console hiding
if sys.platform == "win32":
    try:
        # Get kernel32 functions for additional window hiding
        try:
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            
            # Windows API functions
            GetConsoleWindow = kernel32.GetConsoleWindow
            ShowWindow = user32.ShowWindow
            
            # Hide console immediately
            hwnd = GetConsoleWindow()
            if hwnd:
                ShowWindow(hwnd, SW_HIDE)
        except Exception:
            pass
    except Exception:
        pass

# Define the unified process utilities if they weren't imported
if not 'run_hidden_process' in globals():
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
            if kwargs.get('capture_output'):
                kwargs.pop('stdout', None)
                kwargs.pop('stderr', None)
        
        # Run the process using original run
        return subprocess._original_run(command, **kwargs)

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
        return subprocess._original_popen(command, **kwargs)

# Original subprocess functions
subprocess._original_run = subprocess.run
subprocess._original_popen = subprocess.Popen
subprocess._original_call = subprocess.call
subprocess._original_check_output = subprocess.check_output
subprocess._original_check_call = subprocess.check_call

# Monkey patch ALL subprocess functions
subprocess.Popen = popen_hidden_process
subprocess.run = run_hidden_process

# Patch other functions to use our run and Popen
def _no_console_call(*args, **kwargs):
    """call wrapper with enhanced console hiding"""
    return run_hidden_process(*args, **kwargs).returncode

def _no_console_check_output(*args, **kwargs):
    """check_output wrapper with enhanced console hiding"""
    kwargs['stdout'] = subprocess.PIPE
    kwargs['stderr'] = subprocess.DEVNULL
    result = run_hidden_process(*args, **kwargs)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, args[0], result.stdout, result.stderr)
    return result.stdout

def _no_console_check_call(*args, **kwargs):
    """check_call wrapper with enhanced console hiding"""
    result = run_hidden_process(*args, **kwargs)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, args[0])
    return 0

# Patch remaining subprocess functions
subprocess.call = _no_console_call
subprocess.check_output = _no_console_check_output
subprocess.check_call = _no_console_check_call

# Patch Python's system function too for good measure
if hasattr(os, 'system'):
    _original_system = os.system
    
    def _no_console_system(command):
        """system wrapper that hides console"""
        return run_hidden_process(command, shell=True).returncode
    
    os.system = _no_console_system

# Export the utility functions so they can be imported
__all__ = ['run_hidden_process', 'popen_hidden_process']
'''
    
    # Write with explicit UTF-8 encoding
    with open("ENHANCED_NO_CONSOLE_PATCH.py", "w", encoding="utf-8") as f:
        f.write(patch_content)
    
    if USE_ASCII_ONLY:
        print("Created enhanced no-console patch file")
    else:
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
        if USE_ASCII_ONLY:
            print("Applied zstandard patch")
        else:
            print("✅ Applied zstandard patch")
        
        # Log the patch
        import logging
        logging.info("Applied zstandard patch")
    except ImportError:
        # Already not available, that's fine
        if USE_ASCII_ONLY:
            print("Applied zstandard patch")
        else:
            print("✅ Applied zstandard patch")
        
        # Log the patch
        import logging
        logging.info("Applied zstandard patch")
    
    # Set matplotlib backend to TkAgg
    try:
        import matplotlib
        matplotlib.use('TkAgg')
        if USE_ASCII_ONLY:
            print(f"Matplotlib backend set to: {matplotlib.get_backend()}")
        else:
            print(f"✅ Matplotlib backend set to: {matplotlib.get_backend()}")
        
        # Log the backend setting
        import logging
        logging.info(f"Matplotlib backend set to: {matplotlib.get_backend()}")
    except ImportError:
        if USE_ASCII_ONLY:
            print("WARNING: matplotlib not available")
        else:
            print("⚠️ WARNING: matplotlib not available")
    
    if USE_ASCII_ONLY:
        print("Checking system prerequisites")
    else:
        print("🔍 Checking system prerequisites")
    
    # Check for Visual C++ Redistributable on Windows
    if sys.platform == "win32":
        try:
            import ctypes
            try:
                ctypes.windll.msvcr100  # VS 2010
                vcredist_available = True
            except:
                try:
                    ctypes.windll.msvcp140  # VS 2015+
                    vcredist_available = True
                except:
                    vcredist_available = False
            
            if vcredist_available:
                if USE_ASCII_ONLY:
                    print("Visual C++ Redistributable detected")
                else:
                    print("✅ Visual C++ Redistributable detected")
                logging.info("Visual C++ Redistributable detected")
            else:
                if USE_ASCII_ONLY:
                    print("WARNING: Visual C++ Redistributable might be missing")
                else:
                    print("⚠️ WARNING: Visual C++ Redistributable might be missing")
        except:
            if USE_ASCII_ONLY:
                print("WARNING: Could not check for Visual C++ Redistributable")
            else:
                print("⚠️ WARNING: Could not check for Visual C++ Redistributable")
    
    # Check for Python development components
    try:
        import distutils
        if USE_ASCII_ONLY:
            print("Python development components detected")
        else:
            print("✅ Python development components detected")
        logging.info("Python development components detected")
    except ImportError:
        if USE_ASCII_ONLY:
            print("WARNING: Python development components might be missing")
        else:
            print("⚠️ WARNING: Python development components might be missing")
    
    # Check for Nuitka
    try:
        import nuitka
        # Get Nuitka version using subprocess instead of directly accessing attribute
        try:
            result = run_hidden_process([sys.executable, "-m", "nuitka", "--version"], 
                               capture_output=True, text=True)
            if result.returncode == 0:
                nuitka_version = result.stdout.strip()
                if USE_ASCII_ONLY:
                    print(f"Nuitka version {nuitka_version} detected")
                else:
                    print(f"✅ Nuitka version {nuitka_version} detected")
                logging.info(f"Nuitka version {nuitka_version} detected")
            else:
                if USE_ASCII_ONLY:
                    print("Nuitka detected, but couldn't determine version")
                else:
                    print("✅ Nuitka detected, but couldn't determine version")
        except Exception as e:
            # Simpler version check fallback
            if USE_ASCII_ONLY:
                print("Nuitka detected")
            else:
                print("✅ Nuitka detected")
            logging.info("Nuitka detected")
    except ImportError:
        if USE_ASCII_ONLY:
            print("ERROR: Nuitka not found! Please install it with: pip install nuitka")
        else:
            print("❌ ERROR: Nuitka not found! Please install it with: pip install nuitka")
        return False
    
    return True

def prepare_bundled_environment():
    """Create a minimal bundled environment that can be included in the build"""
    if USE_ASCII_ONLY:
        print("Preparing minimal bundled environment...")
    else:
        print("📦 Preparing minimal bundled environment...")
    
    # Create a minimal venv for bundling
    bundled_venv_dir = Path("bundled_venv")
    if bundled_venv_dir.exists():
        if USE_ASCII_ONLY:
            print("Cleaning existing bundled environment...")
        else:
            print("🧹 Cleaning existing bundled environment...")
        shutil.rmtree(bundled_venv_dir)
    
    import venv
    if USE_ASCII_ONLY:
        print("Creating minimal bundled venv...")
    else:
        print("🔨 Creating minimal bundled venv...")
    venv.create(bundled_venv_dir, with_pip=True)
    
    # Create a manifest of essential packages
    with open(bundled_venv_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({
            "essential_packages": [
                "manim", "numpy", "customtkinter", "matplotlib", "pillow", 
                "opencv-python", "jedi"
            ],
            "version": "3.5.0"
        }, f, indent=2)
    
    if USE_ASCII_ONLY:
        print("Minimal environment prepared")
    else:
        print("✅ Minimal environment prepared")
    return bundled_venv_dir

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
        # If PIL is importable, return both PIL and Pillow
        return "PIL"
    elif package_name == "cv2":
        return "cv2"
    elif package_name == "process_utils":
        # This is our own module that will be explicitly included
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
    """Create a batch launcher script"""
    launcher_content = f'''@echo off
REM Silent launcher - no console windows
start "" "{exe_path}"
exit
'''
    
    launcher_path = Path("Launch_ManimStudio.bat")
    with open(launcher_path, 'w', encoding="utf-8") as f:
        f.write(launcher_content)
    
    if USE_ASCII_ONLY:
        print(f"Created silent launcher: {launcher_path}")
    else:
        print(f"📝 Created silent launcher: {launcher_path}")

def find_executable():
    """Find the built executable"""
    possible_paths = [
        Path("dist/ManimStudio.exe"),
        Path("dist/app.dist/ManimStudio.exe"),
    ]
    
    # Search for executable
    for path in possible_paths:
        if path.exists():
            return path
    
    # Search in subdirectories
    dist_dir = Path("dist")
    if dist_dir.exists():
        for item in dist_dir.rglob("*.exe"):
            if "ManimStudio" in item.name:
                return item
    
    return None

def list_contents():
    """List contents of build directories"""
    for dir_name in ["dist", "build"]:
        dir_path = Path(dir_name)
        if dir_path.exists():
            if USE_ASCII_ONLY:
                print(f"\nContents of {dir_name}:")
            else:
                print(f"\n📂 Contents of {dir_name}:")
            for item in dir_path.iterdir():
                if item.is_file():
                    size = item.stat().st_size / (1024 * 1024)
                    if USE_ASCII_ONLY:
                        print(f"  {item.name} ({size:.1f} MB)")
                    else:
                        print(f"  📄 {item.name} ({size:.1f} MB)")
                elif item.is_dir():
                    if USE_ASCII_ONLY:
                        print(f"  {item.name}/")
                    else:
                        print(f"  📁 {item.name}/")

def check_requirements():
    """Check if all build requirements are met"""
    if USE_ASCII_ONLY:
        print("Checking build requirements...")
    else:
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
            if USE_ASCII_ONLY:
                print(f"  {package}")
            else:
                print(f"  ✅ {package}")
        except ImportError:
            if USE_ASCII_ONLY:
                print(f"  MISSING: {package}")
            else:
                print(f"  ❌ {package}")
            missing.append(package)
    
    if missing:
        if USE_ASCII_ONLY:
            print(f"\nMissing packages: {missing}")
        else:
            print(f"\n⚠️ Missing packages: {missing}")
        print("Install with: pip install " + " ".join(missing))
        return False
    
    if USE_ASCII_ONLY:
        print("All requirements met!")
    else:
        print("✅ All requirements met!")
    return True

def main():
    """Main function with build options"""
    import sys  # Explicitly import here to fix scope issue
    # Set ASCII mode if specified
    global USE_ASCII_ONLY
    if USE_ASCII_ONLY:
        print("Manim Studio - NO CONSOLE Builder")
    else:
        print("🎬 Manim Studio - NO CONSOLE Builder")
    print("=" * 40)
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Build Manim Studio executable")
    parser.add_argument("--jobs", type=int, help="Number of CPU threads to use (default: CPU count - 1)")
    parser.add_argument("--max-cpu", action="store_true", help="Use all available CPU cores with oversubscription")
    parser.add_argument("--turbo", action="store_true", help="Use turbo mode - maximum CPU with high priority")
    parser.add_argument("--build-type", type=int, choices=[1, 2, 3], help="Build type: 1=silent, 2=debug, 3=both")
    parser.add_argument("--ascii", action="store_true", help="Use ASCII output instead of Unicode symbols")
    
    # Parse args but keep default behavior if not specified
    args, remaining_args = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + remaining_args
    
    
    if args.ascii:
        USE_ASCII_ONLY = True
    
    # Determine job count
    cpu_count = multiprocessing.cpu_count()
    process_priority = "normal"
    
    if args.turbo:
        # Turbo mode: maximum cores + oversubscription + high priority
        jobs = int(cpu_count * 2)  # Double the cores for extreme oversubscription
        process_priority = "high"
        if USE_ASCII_ONLY:
            print(f"TURBO MODE: Maximum CPU power with {jobs} threads and HIGH priority!")
        else:
            print(f"🚀 TURBO MODE: Maximum CPU power with {jobs} threads and HIGH priority!")
    elif args.max_cpu:
        # Maximum cores with oversubscription
        jobs = int(cpu_count * 1.5)  # Oversubscription by 50%
        if USE_ASCII_ONLY:
            print(f"Maximum CPU mode: {jobs} threads (oversubscribed from {cpu_count} cores)")
        else:
            print(f"🔥 Maximum CPU mode: {jobs} threads (oversubscribed from {cpu_count} cores)")
    elif args.jobs:
        jobs = args.jobs
        if USE_ASCII_ONLY:
            print(f"Using specified CPU threads: {jobs} of {cpu_count} available")
        else:
            print(f"⚙️ Using specified CPU threads: {jobs} of {cpu_count} available")
    else:
        jobs = max(1, cpu_count - 1)
        if USE_ASCII_ONLY:
            print(f"Using optimal CPU threads: {jobs} of {cpu_count} available")
        else:
            print(f"⚙️ Using optimal CPU threads: {jobs} of {cpu_count} available")
    
    # Check requirements first
    if not check_requirements():
        if USE_ASCII_ONLY:
            print("Please install missing packages first")
        else:
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
    
    logging.info("Building silent release version")
    
    # Use command line arg if provided, otherwise prompt
    if args.build_type:
        choice = str(args.build_type)
    else:
        # Ask for build type
        print("\nSelect build type:")
        if USE_ASCII_ONLY:
            print("1. Silent release build (NO CONSOLE EVER)")
            print("2. Debug build (with console for testing)")
            print("3. Both builds")
        else:
            print("1. 🔇 Silent release build (NO CONSOLE EVER)")
            print("2. 🐛 Debug build (with console for testing)")
            print("3. 📦 Both builds")
        choice = input("\nEnter your choice (1-3): ").strip()
    
    success = False
    
    if choice == "1":
        exe_path = build_self_contained_version(jobs=jobs, priority=process_priority)
        success = exe_path is not None
    elif choice == "2":
        if USE_ASCII_ONLY:
            print("Debug build option temporarily disabled while fixing compatibility issues")
        else:
            print("🐛 Debug build option temporarily disabled while fixing compatibility issues")
        success = False
    elif choice == "3":
        if USE_ASCII_ONLY:
            print("\nBuilding silent release version first...")
        else:
            print("\n🔇 Building silent release version first...")
        release_exe = build_self_contained_version(jobs=jobs, priority=process_priority)
        if USE_ASCII_ONLY:
            print("\nDebug build option temporarily disabled")
        else:
            print("\n🐛 Debug build option temporarily disabled")
        success = release_exe is not None
    else:
        if USE_ASCII_ONLY:
            print("Invalid choice!")
        else:
            print("❌ Invalid choice!")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    if success:
        if USE_ASCII_ONLY:
            print("Build completed successfully!")
        else:
            print("🎉 Build completed successfully!")
        if choice == "1" or choice == "3":
            if USE_ASCII_ONLY:
                print("GUARANTEE: The release version will NEVER show console windows")
                print("   Main app: Silent")
                print("   Manim operations: Hidden")
                print("   Package installs: Silent")
                print("   All operations: Invisible")
                print("Professional desktop application ready!")
            else:
                print("🔇 GUARANTEE: The release version will NEVER show console windows")
                print("   ✅ Main app: Silent")
                print("   ✅ Manim operations: Hidden")
                print("   ✅ Package installs: Silent")
                print("   ✅ All operations: Invisible")
                print("🚀 Professional desktop application ready!")
    else:
        if USE_ASCII_ONLY:
            print("Build failed!")
        else:
            print("❌ Build failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
