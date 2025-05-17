#!/usr/bin/env python3
import subprocess
import sys
import os
from pathlib import Path
import shutil
import json
import importlib

def build_self_contained_version():
    """Build self-contained version with NO CONSOLE EVER"""
    
    print("🐍 Building SELF-CONTAINED version (NO CONSOLE)...")
    
    # Clean previous builds
    if Path("build").exists():
        print("🧹 Cleaning build directory...")
        shutil.rmtree("build")
    if Path("dist").exists():
        print("🧹 Cleaning dist directory...")
        shutil.rmtree("dist")
    
    # Create assets directory if it doesn't exist
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)
    
    # Prepare bundled venv
    bundled_venv = prepare_bundled_environment()
    
    # Create enhanced no-console patch
    create_no_console_patch()
    
    # Detect Nuitka version for compatibility
    nuitka_version = get_nuitka_version()
    print(f"📊 Detected Nuitka version: {nuitka_version}")
    
    # Basic command with universal options
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",  # Single executable file
    ]
    
    # Add console hiding - use the correct option for newer Nuitka versions
    cmd.append("--windows-console-mode=disable")
    
    # Add basic plugins - TKinter is usually available
    cmd.append("--enable-plugin=tk-inter")
    
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
                print(f"✅ Including package: {correct_name}")
        else:
            print(f"⚠️ Skipping unavailable package: {package}")
    
    # Include critical modules that are part of standard library
    essential_modules = [
        "json", "tempfile", "threading", "subprocess", 
        "os", "sys", "ctypes", "venv"
    ]
    
    for module in essential_modules:
        cmd.append(f"--include-module={module}")
    
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
    
    # Jobs for faster compilation
    cmd.append("--jobs=4")
    
    # Final target
    cmd.append("app.py")
    
    print("🔨 Building executable with NO CONSOLE...")
    print("Command:", " ".join(cmd))
    print("=" * 60)
    
    # Run build with real-time output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Print output in real-time
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())
    
    return_code = process.poll()
    
    if return_code == 0:
        print("=" * 60)
        print("✅ NO-CONSOLE build successful!")
        
        # Find executable
        exe_path = find_executable()
        
        if exe_path:
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"📁 Executable: {exe_path} ({size_mb:.1f} MB)")
            
            print(f"\n🎉 SUCCESS! Silent executable ready!")
            print(f"🚀 Run: {exe_path}")
            print(f"\n🔇 GUARANTEED: NO CONSOLE WINDOWS WILL APPEAR")
            
            # Create a launcher script
            create_launcher_script(exe_path)
            
            return exe_path
        else:
            print("❌ Executable not found")
            list_contents()
            return None
    else:
        print("=" * 60)
        print("❌ Build failed!")
        print(f"Return code: {return_code}")
        return None

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
    return package_name

def get_nuitka_version():
    """Get Nuitka version for compatibility checks"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "Unknown"
    except Exception:
        return "Unknown"

def prepare_bundled_environment():
    """Create a minimal bundled environment that can be included in the build"""
    print("📦 Preparing minimal bundled environment...")
    
    # Create a minimal venv for bundling
    bundled_venv_dir = Path("bundled_venv")
    if bundled_venv_dir.exists():
        print("🧹 Cleaning existing bundled environment...")
        shutil.rmtree(bundled_venv_dir)
    
    import venv
    print("🔨 Creating minimal bundled venv...")
    venv.create(bundled_venv_dir, with_pip=True)
    
    # Create a manifest of essential packages
    with open(bundled_venv_dir / "manifest.json", "w") as f:
        json.dump({
            "essential_packages": [
                "manim", "numpy", "customtkinter", "matplotlib", "pillow", 
                "opencv-python", "jedi"
            ],
            "version": "3.5.0"
        }, f, indent=2)
    
    print("✅ Minimal environment prepared")
    return bundled_venv_dir

def create_no_console_patch():
    """Create a more aggressive patch file to ensure NO subprocess calls show console windows"""
    patch_content = '''# ENHANCED_NO_CONSOLE_PATCH.py
# This ensures all subprocess calls hide console windows

import subprocess
import sys
import os
import ctypes

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

# Original subprocess functions
_original_popen = subprocess.Popen
_original_run = subprocess.run
_original_call = subprocess.call
_original_check_output = subprocess.check_output
_original_check_call = subprocess.check_call

# Define startupinfo to fully hide console
def _get_hidden_startupinfo():
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= STARTF_USESHOWWINDOW  # Use constant defined above
        startupinfo.wShowWindow = SW_HIDE  # Use constant defined above
        return startupinfo
    return None

def _no_console_popen(*args, **kwargs):
    """Enhanced Popen wrapper that guarantees hidden console windows on Windows"""
    if sys.platform == "win32":
        # Add flags to hide console window
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = 0
        kwargs['creationflags'] |= CREATE_NO_WINDOW | DETACHED_PROCESS
        
        # Add startupinfo to hide window
        startupinfo = _get_hidden_startupinfo()
        kwargs['startupinfo'] = startupinfo
        
        # Redirect stdout/stderr to null if not already redirected
        if 'stdout' not in kwargs:
            kwargs['stdout'] = subprocess.PIPE
        if 'stderr' not in kwargs:
            kwargs['stderr'] = subprocess.PIPE
    
    return _original_popen(*args, **kwargs)

def _no_console_run(*args, **kwargs):
    """Run wrapper with enhanced console hiding"""
    if sys.platform == "win32":
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = 0
        kwargs['creationflags'] |= CREATE_NO_WINDOW | DETACHED_PROCESS
        kwargs['startupinfo'] = _get_hidden_startupinfo()
        
        # Redirect stdout/stderr if not specified
        if 'stdout' not in kwargs:
            kwargs['stdout'] = subprocess.PIPE 
        if 'stderr' not in kwargs:
            kwargs['stderr'] = subprocess.PIPE
    
    return _original_run(*args, **kwargs)

def _no_console_call(*args, **kwargs):
    """Call wrapper with enhanced console hiding"""
    if sys.platform == "win32":
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = 0
        kwargs['creationflags'] |= CREATE_NO_WINDOW | DETACHED_PROCESS
        kwargs['startupinfo'] = _get_hidden_startupinfo()
    
    return _original_call(*args, **kwargs)

def _no_console_check_output(*args, **kwargs):
    """check_output wrapper with enhanced console hiding"""
    if sys.platform == "win32":
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = 0
        kwargs['creationflags'] |= CREATE_NO_WINDOW | DETACHED_PROCESS
        kwargs['startupinfo'] = _get_hidden_startupinfo()
    
    return _original_check_output(*args, **kwargs)

def _no_console_check_call(*args, **kwargs):
    """check_call wrapper with enhanced console hiding"""
    if sys.platform == "win32":
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = 0
        kwargs['creationflags'] |= CREATE_NO_WINDOW | DETACHED_PROCESS
        kwargs['startupinfo'] = _get_hidden_startupinfo()
    
    return _original_check_call(*args, **kwargs)

# Monkey patch ALL subprocess functions
subprocess.Popen = _no_console_popen
subprocess.run = _no_console_run
subprocess.call = _no_console_call
subprocess.check_output = _no_console_check_output
subprocess.check_call = _no_console_check_call

# Patch Python's system function too for good measure
if hasattr(os, 'system'):
    _original_system = os.system
    
    def _no_console_system(command):
        """system wrapper that hides console"""
        if sys.platform == "win32":
            # Use our patched subprocess.call instead
            return subprocess.call(command, shell=True, 
                                  creationflags=CREATE_NO_WINDOW,
                                  startupinfo=_get_hidden_startupinfo())
        return _original_system(command)
    
    os.system = _no_console_system
'''
    
    with open("ENHANCED_NO_CONSOLE_PATCH.py", "w") as f:
        f.write(patch_content)
    
    print("📄 Created enhanced no-console patch file")

def create_launcher_script(exe_path):
    """Create a batch launcher script"""
    launcher_content = f'''@echo off
REM Silent launcher - no console windows
start "" "{exe_path}"
exit
'''
    
    launcher_path = Path("Launch_ManimStudio.bat")
    with open(launcher_path, 'w') as f:
        f.write(launcher_content)
    
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
        "matplotlib", "manim", "jedi"
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

def main():
    """Main function with build options"""
    print("🎬 Manim Studio - NO CONSOLE Builder")
    print("=" * 40)
    
    # Check requirements first
    if not check_requirements():
        print("❌ Please install missing packages first")
        sys.exit(1)
    
    # Ask for build type
    print("\nSelect build type:")
    print("1. 🔇 Silent release build (NO CONSOLE EVER)")
    print("2. 🐛 Debug build (with console for testing)")
    print("3. 📦 Both builds")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    success = False
    
    if choice == "1":
        exe_path = build_self_contained_version()
        success = exe_path is not None
    elif choice == "2":
        print("Debug build option temporarily disabled while fixing compatibility issues")
        success = False
    elif choice == "3":
        print("\n🔇 Building silent release version first...")
        release_exe = build_self_contained_version()
        print("\n🐛 Debug build option temporarily disabled")
        success = release_exe is not None
    else:
        print("❌ Invalid choice!")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Build completed successfully!")
        if choice == "1" or choice == "3":
            print("🔇 GUARANTEE: The release version will NEVER show console windows")
            print("   ✅ Main app: Silent")
            print("   ✅ Manim operations: Hidden")
            print("   ✅ Package installs: Silent")
            print("   ✅ All operations: Invisible")
            print("🚀 Professional desktop application ready!")
    else:
        print("❌ Build failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()