#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import multiprocessing
import importlib
import shutil
from pathlib import Path
import logging
import tempfile

# Configure logging
logging.basicConfig(
    filename='build.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

USE_ASCII_ONLY = False

def run_hidden_process(command, **kwargs):
    """Run a process with hidden console window on Windows"""
    # Configure for Windows console hiding
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        creationflags = subprocess.CREATE_NO_WINDOW
        
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
        print("❌ ERROR: Nuitka not found!")
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

def build_onefile():
    """Build onefile executable with optimized settings and manim data files"""
    print("🚀 Building Onefile Executable")
    print("=" * 50)
    
    # Determine CPU usage
    cpu_count = multiprocessing.cpu_count()
    jobs = max(1, cpu_count - 1)  # Leave one core for system
    
    # Base command - FIXED: Use complete path resolution
    cmd = [
        sys.executable, "-m", "nuitka",
        "--onefile",
        "--standalone",
        os.path.abspath("app.py"),  # Use absolute path
        "--output-filename=ManimStudio.exe",
        f"--jobs={jobs}",
        "--assume-yes-for-downloads",
        "--disable-console",
        "--enable-plugin=tk-inter",
        "--report=compilation-report.xml",
        # CRITICAL FIX: Configure onefile for persistent cache
        "--onefile-cache-mode=auto",  # Enable persistent caching 
        "--onefile-tempdir-spec={PROGRAM_DIR}/.manim_studio_cache",  # Cache next to exe
    ]
    
    # Add Windows-specific options
    if sys.platform == "win32":
        cmd.extend([
            "--mingw64",
            "--windows-icon-from-ico=icon.ico" if Path("icon.ico").exists() else "",
        ])
        # Filter empty strings
        cmd = [c for c in cmd if c]
    
    # CRITICAL MANIM FIX: Ensure manim data files are included
    manim_fixes = [
        "--include-package=manim",
        "--include-package-data=manim",  # Include ALL manim data files
        "--include-data-dir=manim=manim",  # Force include manim directory
        "--follow-import-to=manim",
    ]
    cmd.extend(manim_fixes)
    
    # Minimal exclusions to avoid build issues
    minimal_exclusions = [
        "*.tests", "*.test", "test_*", "*.test_*", "test.*",
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

    # Include ALL packages with data files
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
                # CRITICAL: Include package data for complete functionality
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
            "sympy.*.tests.*",
            "sympy.*.benchmarks.*",
        ]
        
        for exclusion in sympy_test_exclusions:
            cmd.append(f"--nofollow-import-to={exclusion}")
        
        included_packages.append("sympy")
        print("📦 Including SymPy with selective exclusions")

    # Set environment variables for better builds
    env = os.environ.copy()
    
    # Disable LTO to reduce memory usage and linking issues
    env["NUITKA_DISABLE_LTO"] = "1"
    env["GCC_COMPILE_ARGS"] = "-fno-lto"

    # Set process priority
    process_priority = 0
    priority = "normal"  # Default priority
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
    print(f"🎯 Manim data files: ENABLED")
    print(f"💾 Persistent cache: {'{PROGRAM_DIR}/.manim_studio_cache'}")

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
            print("  ✅ Persistent cache next to executable")
            print("  ✅ Smart caching system - unpacks only once")
            print("  ✅ No console windows")
            print("  ✅ Complete Manim functionality included")
            print("  ✅ All package data files included")

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
    
    print("🚀 Manim Studio - Advanced Onefile Builder")
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
        # Max CPU mode: use all cores with some oversubscription
        jobs = int(cpu_count * 1.5)
        print(f"🔥 MAX CPU MODE: Using {jobs} threads for maximum performance!")
    elif args.jobs:
        jobs = args.jobs
        print(f"⚙️ CUSTOM MODE: Using {jobs} threads as specified")
    else:
        jobs = max(1, cpu_count - 1)  # Conservative default
        print(f"🔧 STANDARD MODE: Using {jobs} threads (leaving 1 core for system)")
    
    # Prerequisites check
    if not check_system_prerequisites():
        sys.exit(1)
    
    # Requirements check 
    if not check_requirements():
        print("\n❌ Missing requirements! Please install them first.")
        sys.exit(1)
    
    # Build
    exe_path = build_onefile()
    
    if exe_path:
        print("\n" + "=" * 60)
        print("🎉 BUILD COMPLETED SUCCESSFULLY!")
        print("🚀 Professional desktop application ready!")
        
        # Show usage instructions
        print("\n📋 USAGE INSTRUCTIONS:")
        print(f"   📁 Executable location: {exe_path}")
        print("   🚀 Run the .exe file to start the application")
        print("   📂 App will cache to '.manim_studio_cache' folder next to .exe")
        print("   ✅ Complete Manim functionality ready out of the box")
        print("   🔄 Subsequent runs will be faster (no re-unpacking)")
        
    else:
        print("❌ Build failed!")
        print("💡 Check the logs above for error details.")
        print("   📄 Check build.log for detailed error information")
        sys.exit(1)

if __name__ == "__main__":
    main()
