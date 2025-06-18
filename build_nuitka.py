#!/usr/bin/env python3
"""
Enhanced Nuitka Build Script for Manim Studio
Builds onefile executable with comprehensive package inclusion and optimization
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
import glob

# Global flag for ASCII-only output
USE_ASCII_ONLY = False

def check_requirements():
    """Check if all required packages are available"""
    required = ["nuitka", "customtkinter", "PIL", "numpy", "cv2", "matplotlib"]
    missing = []
    
    for package in required:
        try:
            if package == "PIL":
                import PIL
            elif package == "cv2":
                import cv2
            else:
                __import__(package)
            print(f"✅ {package} - OK")
        except ImportError:
            missing.append(package)
            print(f"❌ {package} - Missing")
    
    if missing:
        print(f"\n❌ Missing packages: {', '.join(missing)}")
        print("Please install missing packages first:")
        for pkg in missing:
            install_name = "Pillow" if pkg == "PIL" else "opencv-python" if pkg == "cv2" else pkg
            print(f"  pip install {install_name}")
        return False
    
    print("✅ All required packages available")
    return True

def get_nuitka_version():
    """Get Nuitka version"""
    try:
        result = subprocess.run([sys.executable, "-m", "nuitka", "--version"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return "Unknown"

def check_system_prerequisites():
    """Check system prerequisites"""
    print("🔍 Checking system prerequisites...")
    
    # Check Python version
    if sys.version_info < (3, 8):
        print(f"❌ Python 3.8+ required, found {sys.version}")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    
    # Check if we're on Windows
    if sys.platform != "win32":
        print("⚠️ This script is optimized for Windows")
    
    return True

def is_package_importable(package_name):
    """Check if a package can be imported"""
    try:
        if package_name == "PIL":
            import PIL
        elif package_name == "cv2":
            import cv2
        else:
            __import__(package_name)
        return True
    except ImportError:
        return False

def get_correct_package_name(package):
    """Get the correct package name for inclusion"""
    package_mapping = {
        "PIL": "PIL",
        "cv2": "cv2", 
        "sklearn": "sklearn",
        "yaml": "yaml",
    }
    return package_mapping.get(package, package)

def create_subprocess_helper():
    """Create subprocess helper module for onefile compatibility"""
    subprocess_helper_content = '''# process_utils.py - Enhanced subprocess utilities for onefile builds
import subprocess
import sys
import os

# Store original functions
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
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        # Set creation flags to hide console
        creationflags = subprocess.CREATE_NO_WINDOW
        
        kwargs['startupinfo'] = startupinfo
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
    
    # Use the original run function with our modifications
    return _original_run(command, **kwargs)

def popen_hidden_process(command, **kwargs):
    """Popen with hidden console window"""
    startupinfo = None
    creationflags = 0
    
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        creationflags = subprocess.CREATE_NO_WINDOW
        
        kwargs['startupinfo'] = startupinfo
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
    
    return _original_popen(command, **kwargs)

def call_hidden_process(*args, **kwargs):
    """subprocess.call() replacement with hidden console window"""
    result = run_hidden_process(*args, **kwargs)
    
    if result.returncode != 0:
        cmd = args[0] if args else kwargs.get('args')
        raise subprocess.CalledProcessError(result.returncode, cmd)
    
    return 0

def check_output_hidden_process(*args, **kwargs):
    """subprocess.check_output() replacement with hidden console window"""
    kwargs['capture_output'] = True
    result = run_hidden_process(*args, **kwargs)
    
    if result.returncode != 0:
        cmd = args[0] if args else kwargs.get('args')
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    
    return result.stdout

def check_call_hidden_process(*args, **kwargs):
    """subprocess.check_call() replacement with hidden console window"""
    result = run_hidden_process(*args, **kwargs)
    
    if result.returncode != 0:
        cmd = args[0] if args else kwargs.get('args')
        raise subprocess.CalledProcessError(result.returncode, cmd)
    
    return 0

# Safe system replacement
def system_hidden_process(command):
    """os.system() replacement with hidden console window"""
    return run_hidden_process(command, shell=True).returncode

# Add direct access to original functions
run_original = _original_run
popen_original = _original_popen
call_original = _original_call
check_output_original = _original_check_output
check_call_original = _original_check_call

# Export all functions
__all__ = [
    'run_hidden_process', 
    'popen_hidden_process',
    'call_hidden_process',
    'check_output_hidden_process',
    'check_call_hidden_process',
    'system_hidden_process',
    'run_original',
    'popen_original',
    'call_original',
    'check_output_original',
    'check_call_original'
]'''
    
    with open("process_utils.py", "w", encoding="utf-8") as f:
        f.write(subprocess_helper_content)
    
    print("📄 Created process utilities module")

def create_fixes_module():
    """Create the fixes module to handle runtime issues"""
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
        # Check if already patched to prevent infinite recursion
        if hasattr(subprocess, '_manimstudio_patched'):
            return True
        
        # Define safe wrappers that check arguments
        def safe_run_wrapper(*args, **kwargs):
            # For safety, use original if this looks like a direct call
            if len(args) == 1 and isinstance(args[0], list):
                return run_hidden_process(args[0], **kwargs)
            # Call with hidden console
            return run_hidden_process(*args, **kwargs)
        
        def safe_popen_wrapper(*args, **kwargs):
            # For safety, use original if this looks like a direct call  
            if len(args) == 1 and isinstance(args[0], list):
                return popen_hidden_process(args[0], **kwargs)
            # Call directly
            return popen_original(*args, **kwargs)
        
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
            creationflags = CREATE_NO_WINDOW
            
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
        
        # Use the original run function with our modifications
        return _original_run(command, **kwargs)

    def popen_hidden_process(command, **kwargs):
        """Popen with hidden console window"""
        startupinfo = None
        creationflags = 0
        
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = SW_HIDE
            
            creationflags = CREATE_NO_WINDOW
            
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
        
        return _original_popen(command, **kwargs)

    # Replace subprocess functions with our hidden versions
    subprocess.run = run_hidden_process
    subprocess.Popen = popen_hidden_process
    
    # Mark as patched
    subprocess._manimstudio_patched = True
    
    print("✅ Aggressive no-console patch applied successfully")
'''
    
    with open("no_console_patch.py", "w", encoding="utf-8") as f:
        f.write(patch_content)
    
    print("📄 Created aggressive no-console patch")

def find_standalone_executable():
    """Find the built standalone executable"""
    dist_dir = Path("dist")
    if not dist_dir.exists():
        return None
    
    # Look for .exe files
    for exe_file in dist_dir.glob("*.exe"):
        return exe_file.absolute()
    
    return None

def create_launcher_script(exe_path):
    """Create a launcher script for the executable"""
    launcher_content = f'''@echo off
REM Launcher script for Manim Studio
echo Starting Manim Studio...
"{exe_path}"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%
    pause
)
'''
    
    launcher_path = exe_path.parent / "launch_manim_studio.bat"
    with open(launcher_path, "w") as f:
        f.write(launcher_content)
    
    print(f"📄 Created launcher script: {launcher_path}")

def list_contents():
    """List the contents of the dist directory"""
    dist_dir = Path("dist")
    if dist_dir.exists():
        print("\n📁 Contents of dist directory:")
        for item in dist_dir.iterdir():
            size = item.stat().st_size if item.is_file() else 0
            size_mb = size / (1024 * 1024)
            print(f"  📄 {item.name} ({size_mb:.1f} MB)")
    else:
        print("❌ dist directory not found")

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

    # CRITICAL: Enhanced command for onefile with subprocess support
    cmd = [
        sys.executable, "-m", "nuitka",
        "--onefile",
        # CRITICAL: Use a predictable unpack directory
        "--onefile-tempdir-spec={PROGRAM_DIR}/manim_studio_runtime",
        "--onefile-cache-mode=cached",
        # Console settings
        "--windows-console-mode=disable",
        "--windows-disable-console",
        # Core plugins and settings
        "--enable-plugin=tk-inter",
        "--enable-plugin=numpy",
        "--lto=no",
        "--show-progress",
        "--remove-output",
        "--assume-yes-for-downloads",
        "--mingw64",
        "--disable-ccache",
        "--show-memory",
        # Force stdout/stderr to work properly
        "--windows-force-stdout-spec={PROGRAM_DIR}/stdout.log",
        "--windows-force-stderr-spec={PROGRAM_DIR}/stderr.log",
    ]

    # MINIMAL exclusions - only exclude test modules to avoid subprocess issues
    minimal_exclusions = [
        "*.tests.*", "*.test_*", "test.*",
        "pytest.*", "*.benchmarks.*",
        # Only exclude known problematic modules
        "zstandard.*", "setuptools.*", "_distutils_hack.*",
    ]

    for module in minimal_exclusions:
        cmd.append(f"--nofollow-import-to={module}")

    # CRITICAL: Include ALL external packages (not built-in modules)
    external_packages = [
        "customtkinter", "PIL", "numpy", "cv2",
        "matplotlib", "jedi", "psutil", "manim", "tkinter"
    ]

    # CRITICAL: Built-in modules that should use --include-module (not --include-package)  
    builtin_modules = [
        "subprocess", "threading", "multiprocessing", 
        "queue", "json", "tempfile", "os", "sys", 
        "shutil", "pathlib", "signal", "atexit", "logging", 
        "glob", "re", "time", "datetime", "uuid", "base64", 
        "io", "codecs", "platform", "getpass", "math", "random", 
        "collections", "itertools", "functools", "operator", "copy",
        "ctypes", "venv", "asyncio", "concurrent.futures"
    ]

    # Include external packages
    included_packages = []
    for package in external_packages:
        if is_package_importable(package):
            correct_name = get_correct_package_name(package)
            if correct_name:
                included_packages.append(correct_name)
                cmd.append(f"--include-package={correct_name}")
                # Only add package data for packages that actually need it
                if correct_name in ["matplotlib", "numpy", "manim", "tkinter"]:
                    cmd.append(f"--include-package-data={correct_name}")
                print(f"📦 Including external package: {correct_name}")

    # Include built-in modules (using --include-module)
    for module in builtin_modules:
        cmd.append(f"--include-module={module}")
        print(f"🔧 Including built-in module: {module}")

    # CRITICAL: Include SymPy with minimal exclusions
    if is_package_importable("sympy"):
        cmd.append("--include-package=sympy")
        cmd.append("--include-package-data=sympy")
        
        # Only exclude the absolute minimum to avoid build failures
        sympy_critical_exclusions = [
            "sympy.polys.benchmarks.bench_solvers",
            "sympy.physics.quantum.tests.test_spin", 
            "sympy.solvers.ode.tests.test_systems",
            "sympy.polys.polyquinticconst",
        ]
        
        for exclusion in sympy_critical_exclusions:
            cmd.append(f"--nofollow-import-to={exclusion}")
        
        included_packages.append("sympy")
        print("🧮 Including SymPy with subprocess compatibility")
    if is_package_importable("sympy"):
        cmd.append("--include-package=sympy")
        cmd.append("--include-package-data=sympy")
        
        # Only exclude the absolute minimum to avoid build failures
        sympy_critical_exclusions = [
            "sympy.polys.benchmarks.bench_solvers",
            "sympy.physics.quantum.tests.test_spin", 
            "sympy.solvers.ode.tests.test_systems",
            "sympy.polys.polyquinticconst",
        ]
        
        for exclusion in sympy_critical_exclusions:
            cmd.append(f"--nofollow-import-to={exclusion}")
        
        included_packages.append("sympy")
        print("🧮 Including SymPy with subprocess compatibility")

    # CRITICAL: Include comprehensive system modules for subprocess support
    critical_system_modules = [
        "json", "tempfile", "threading", "subprocess", "multiprocessing",
        "os", "sys", "ctypes", "venv", "psutil", "signal", "atexit",
        "logging", "pathlib", "shutil", "glob", "re", "time", 
        "datetime", "uuid", "base64", "io", "codecs", "platform", 
        "getpass", "queue", "math", "random", "collections",
        "itertools", "functools", "operator", "copy", "concurrent",
        "concurrent.futures", "asyncio"
    ]

    for module in critical_system_modules:
        cmd.append(f"--include-module={module}")

    # CRITICAL: Include additional data for packages that need it (avoid duplicates)
    additional_data_packages = ["sympy"]  # manim, matplotlib, numpy already handled above
    for package in additional_data_packages:
        if is_package_importable(package) and package not in [p.lower() for p in included_packages]:
            cmd.append(f"--include-package-data={package}")
            print(f"📊 Including additional data for: {package}")

    # Output configuration
    cmd.extend([
        "--output-dir=dist",
        f"--jobs={jobs}",
    ])

    # Icon if available
    if Path("assets/icon.ico").exists():
        cmd.append("--windows-icon-from-ico=assets/icon.ico")

    # CRITICAL: Include all data directories
    data_dirs = ["assets=assets"]
    
    # Include matplotlib data if available
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

    print("Building onefile executable with subprocess support...")
    print("Command:", " ".join(cmd))
    print("=" * 60)

    # CRITICAL: Environment setup for build
    env = os.environ.copy()
    env.update({
        "GCC_LTO": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "NUITKA_CACHE_MODE": "cached"
    })

    # Set process priority
    process_priority = 0
    if priority == "high" and sys.platform == "win32":
        print("🔥 Setting HIGH process priority for maximum CPU utilization")
        process_priority = 0x00000080

    try:
        print("🚀 Starting build process...")
        
        # Run the build command
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
        print(f"📦 Included {len(included_packages)} external packages")
        print(f"🔧 Included {len(builtin_modules)} built-in modules")

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
                print("  ✅ Unpacks to manim_studio_runtime folder next to .exe")
                print("  ✅ Smart caching system")
                print("  ✅ No console windows")
                print("  ✅ Complete functionality included")
                print("  ✅ Subprocess compatibility fixed")

                return str(exe_path)
            else:
                print("❌ Executable not found")
                list_contents()
                return None
        else:
            print("=" * 60)
            print("❌ Build failed!")
            print(f"Return code: {return_code}")
            return None
            
    except subprocess.TimeoutExpired:
        print("❌ Build timed out")
        return None
    except Exception as e:
        print(f"❌ Build error: {e}")
        return None

def main():
    """Main function - Enhanced onefile build with proper parameter handling"""
    print("🚀 Manim Studio - Enhanced Onefile Builder")
    print("=" * 50)
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Build Manim Studio as onefile executable")
    parser.add_argument("--jobs", type=int, help="Number of CPU threads to use (default: CPU count - 1)")
    parser.add_argument("--max-cpu", action="store_true", help="Use all available CPU cores with oversubscription")
    parser.add_argument("--turbo", action="store_true", help="Use turbo mode - maximum CPU with high priority")
    parser.add_argument("--ascii", action="store_true", help="Use ASCII output instead of Unicode symbols")
    
    # Parse args
    args = parser.parse_args()
    
    global USE_ASCII_ONLY
    if args.ascii:
        USE_ASCII_ONLY = True
    
    # Determine job count and priority
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
    print("\n🎯 Building ENHANCED ONEFILE executable...")
    print("📋 This build includes:")
    print("  ✅ Single file executable")
    print("  ✅ Unpacks to stable folder next to .exe")
    print("  ✅ Smart caching system")
    print("  ✅ Complete functionality")
    print("  ✅ No console windows")
    print("  ✅ Subprocess compatibility fixes")
    print("  ✅ Latest Nuitka onefile features")
    
    # Confirmation
    confirm = input(f"\n🚀 Proceed with production onefile build using {jobs} threads? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("❌ Build cancelled by user")
        sys.exit(0)
    
    # Execute the build - FIXED: Remove debug_mode parameter
    print(f"\n🚀 Starting enhanced onefile build process...")
    exe_path = build_onefile_executable(jobs=jobs, priority=process_priority)
    success = exe_path is not None
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Build completed successfully!")
        print("🚀 ENHANCED ONEFILE BUILD: Single file executable ready!")
        print("   🆕 FEATURES:")
        print("   ✅ Single file executable")
        print("   ✅ Unpacks to manim_studio_runtime folder next to .exe")
        print("   ✅ Smart caching for better performance")
        print("   ✅ Latest Nuitka onefile technology")
        print("   ✅ Complete functionality included")
        print("   ✅ No console windows")
        print("   ✅ Subprocess compatibility fixed")
        print("   🎯 OPTIMIZED: Best onefile integration with subprocess fixes!")
        print("🚀 Professional desktop application ready!")
        
        # Show usage instructions
        print("\n📋 USAGE INSTRUCTIONS:")
        print(f"   📁 Executable location: {exe_path}")
        print("   🚀 Run the .exe file to start the application")
        print("   📂 App will unpack to 'manim_studio_runtime' folder next to .exe")
        print("   ✅ Complete functionality ready out of the box")
        print("   ✅ Subprocess calls work properly in onefile mode")
        
    else:
        print("❌ Build failed!")
        print("💡 Check the logs above for error details.")
        print("   📄 Check build.log for detailed error information")
        sys.exit(1)

if __name__ == "__main__":
    main()
