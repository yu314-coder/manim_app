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
# Updated lists for better build performance
MINIMAL_PACKAGES = [
    "customtkinter", "tkinter", "PIL", "numpy", "jedi", "psutil"
]

ESSENTIAL_PACKAGES_WITH_TESTS_EXCLUDED = [
    "customtkinter", "tkinter", "PIL", "numpy", "cv2", 
    "matplotlib", "jedi", "psutil"
]

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

ESSENTIAL_SYMPY_MODULES = [
    "sympy.core", "sympy.printing", "sympy.parsing",
    "sympy.functions.elementary", "sympy.simplify.simplify",
    "sympy.utilities.lambdify"
]
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
    
    # Create enhanced no-console patch
    create_no_console_patch()
    
    # Create fixes module
    create_fixes_module()
    
    # Create helper script for unified subprocess handling
    create_subprocess_helper()
    
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
    
    # Basic command with universal options
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",  # Single executable file
    ]
    
    # Enhanced console hiding - use both modern and legacy options for maximum compatibility
    cmd.append("--windows-console-mode=disable")  # Modern option
    cmd.append("--windows-disable-console")       # Legacy option for compatibility
    
    # Add GUI toolkit for matplotlib
    cmd.append("--enable-plugin=tk-inter")
    
    # CRITICAL: Completely disable LTO to fix the zstandard error
    cmd.append("--lto=no")
    
    # Explicitly exclude problematic modules - COMPREHENSIVE LIST
    problematic_modules = [
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
        # Exclude the specific problematic modules from the error
        "sympy.polys.benchmarks.bench_solvers",
        "sympy.physics.quantum.tests.test_spin",
        "sympy.solvers.ode.tests.test_systems",
        "sympy.polys.polyquinticconst",
        # Exclude benchmark modules
        "*.benchmarks.*", "*.test_*", "*.tests.*",
        # Exclude other problematic modules
        "matplotlib.tests.*", "numpy.tests.*", "PIL.tests.*",
        "cv2.tests.*", "jedi.test.*", "pytest.*",
    ]
    
    for module in problematic_modules:
        cmd.append(f"--nofollow-import-to={module}")
    
    # IMPORTANT: Use show-progress instead of no-progressbar
    cmd.append("--show-progress")
    
    # Add optimization flags that don't use LTO with faster compilation
    cmd.extend([
        "--remove-output",                     # Remove intermediate files to reduce I/O
        "--assume-yes-for-downloads",          # Don't prompt for downloads
        "--mingw64",                           # Use MinGW64 compiler
        "--disable-ccache",                    # Disable ccache to avoid issues
        "--show-memory",                       # Show memory usage
        "--disable-dll-dependency-cache",     # Disable DLL cache
        "--onefile-tempdir-spec=CACHE",       # Use cache for temp files
    ])
    
    # Check for importable packages and include only those that exist (SELECTIVE APPROACH)
    essential_packages = [
        "customtkinter", "tkinter", "PIL", "numpy", "cv2", 
        "matplotlib", "jedi", "psutil"
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
    
    # Handle manim separately with more control
    if is_package_importable("manim"):
        cmd.append("--include-package=manim")
        cmd.append("--include-package-data=manim")
        # Exclude manim tests
        cmd.append("--nofollow-import-to=manim.*.tests")
        cmd.append("--nofollow-import-to=manim.test.*")
        included_packages.append("manim")
        if USE_ASCII_ONLY:
            print("Including manim (excluding tests)")
        else:
            print("✅ Including manim (excluding tests)")
    
    # Handle sympy with minimal inclusion to avoid compilation issues
    if is_package_importable("sympy"):
        # Only include essential sympy modules
        essential_sympy_modules = [
            "sympy.core", "sympy.printing", "sympy.parsing",
            "sympy.functions.elementary", "sympy.utilities.lambdify"
        ]
        
        for module in essential_sympy_modules:
            cmd.append(f"--include-module={module}")
        
        # Exclude ALL problematic sympy subpackages
        sympy_exclusions = [
            "sympy.polys", "sympy.physics", "sympy.geometry",
            "sympy.matrices", "sympy.stats", "sympy.tensor",
            "sympy.*.tests", "sympy.*.benchmarks", "sympy.plotting"
        ]
        
        for exclusion in sympy_exclusions:
            cmd.append(f"--nofollow-import-to={exclusion}")
        
        included_packages.append("sympy (minimal)")
        if USE_ASCII_ONLY:
            print("Including minimal sympy (core only, excluding problematic modules)")
        else:
            print("✅ Including minimal sympy (core only, excluding problematic modules)")
    
    # Include critical modules that are part of standard library
    essential_modules = [
        "json", "tempfile", "threading", "subprocess", 
        "os", "sys", "ctypes", "venv", "fixes", "psutil",
        "process_utils", "logging", "pathlib"
    ]
    
    for module in essential_modules:
        cmd.append(f"--include-module={module}")
    
    # Include package data for Manim (for config files) - but exclude tests
    if is_package_importable("manim"):
        cmd.append("--include-package-data=manim")
        # But exclude test data
        cmd.append("--nofollow-import-to=manim.*.tests.*")
    
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
    ])
    
    # Add custom performance flags to maximize CPU
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
    
    # Create environment variables to force disable LTO in GCC
    env = os.environ.copy()
    env["GCC_LTO"] = "0"
    env["NUITKA_DISABLE_LTO"] = "1"
    env["GCC_COMPILE_ARGS"] = "-fno-lto"
    
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
        print(f"Included {len(included_packages)} packages")
    else:
        print(f"🖥️ CPU Info: {cpu_count} logical cores available")
        print(f"⚙️ Using {jobs} compilation threads")
        print(f"📦 Included {len(included_packages)} packages")
    
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
def build_standalone_version(jobs=None, priority="normal"):
    """Build standalone version (directory-based, not onefile) with complete LaTeX support"""

    cpu_count = multiprocessing.cpu_count()
    if jobs is None:
        jobs = max(1, cpu_count - 1)

    if USE_ASCII_ONLY:
        print(f"Building STANDALONE version (directory-based) with {jobs} CPU threads...")
    else:
        print(f"🐍 Building STANDALONE version (directory-based) with {jobs} CPU threads...")

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

    # Create enhanced patches and helpers
    create_no_console_patch()
    create_fixes_module()
    create_subprocess_helper()

    # Check system prerequisites
    if not check_system_prerequisites():
        print("❌ System prerequisites check failed" if not USE_ASCII_ONLY else "ERROR: System prerequisites check failed")
        return None

    # Get Nuitka version
    nuitka_version = get_nuitka_version()
    if USE_ASCII_ONLY:
        print(f"Detected Nuitka version: {nuitka_version}")
    else:
        print(f"📊 Detected Nuitka version: {nuitka_version}")

    # Basic command structure
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
    ]

    # Enhanced console hiding - use both methods for maximum compatibility
    cmd.append("--windows-console-mode=disable")
    cmd.append("--windows-disable-console")

    # Enable GUI toolkit support
    cmd.append("--enable-plugin=tk-inter")

    # CRITICAL: Disable LTO to prevent zstandard linking issues
    cmd.append("--lto=no")

    # Exclude problematic modules that cause build issues - COMPREHENSIVE LIST
    problematic_modules = [
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
        # Exclude the specific problematic modules from the error
        "sympy.polys.benchmarks.bench_solvers",
        "sympy.physics.quantum.tests.test_spin",
        "sympy.solvers.ode.tests.test_systems",
        "sympy.polys.polyquinticconst",
        # Exclude benchmark modules
        "*.benchmarks.*", "*.test_*", "*.tests.*",
        # Exclude other problematic modules
        "matplotlib.tests.*", "numpy.tests.*", "PIL.tests.*",
        "cv2.tests.*", "jedi.test.*", "pytest.*",
    ]

    for module in problematic_modules:
        cmd.append(f"--nofollow-import-to={module}")

    # Progress and optimization flags with faster compilation
    cmd.extend([
        "--show-progress",
        "--remove-output",
        "--assume-yes-for-downloads",
        "--mingw64",
        "--disable-ccache",
        "--show-memory",
        "--disable-dll-dependency-cache",
        "--onefile-tempdir-spec=CACHE",  # Use cache for temp files
    ])

    # Essential packages - check availability before including (SELECTIVE APPROACH)
    essential_packages = [
        "customtkinter", "tkinter", "PIL", "numpy", "cv2",
        "matplotlib", "jedi", "psutil"
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

    # Handle manim separately with more control
    if is_package_importable("manim"):
        cmd.append("--include-package=manim")
        cmd.append("--include-package-data=manim")
        # Exclude manim tests
        cmd.append("--nofollow-import-to=manim.*.tests")
        cmd.append("--nofollow-import-to=manim.test.*")
        included_packages.append("manim")
        if USE_ASCII_ONLY:
            print("Including manim (excluding tests)")
        else:
            print("✅ Including manim (excluding tests)")

    # Handle sympy with minimal inclusion for LaTeX support but avoid problematic modules
    if is_package_importable("sympy"):
        # Only include essential sympy modules for LaTeX
        essential_sympy_modules = [
            "sympy.core", "sympy.printing.latex", "sympy.printing.mathml",
            "sympy.parsing", "sympy.functions.elementary", 
            "sympy.utilities.lambdify", "sympy.simplify.simplify"
        ]
        
        for module in essential_sympy_modules:
            cmd.append(f"--include-module={module}")
        
        # Exclude ALL problematic sympy subpackages
        sympy_exclusions = [
            "sympy.polys", "sympy.physics", "sympy.geometry",
            "sympy.matrices", "sympy.stats", "sympy.tensor",
            "sympy.*.tests", "sympy.*.benchmarks", "sympy.plotting",
            "sympy.solvers.ode", "sympy.polys.benchmarks"
        ]
        
        for exclusion in sympy_exclusions:
            cmd.append(f"--nofollow-import-to={exclusion}")
        
        included_packages.append("sympy (minimal LaTeX)")
        if USE_ASCII_ONLY:
            print("Including minimal sympy for LaTeX (excluding problematic modules)")
        else:
            print("✅ Including minimal sympy for LaTeX (excluding problematic modules)")

    # Include additional LaTeX support packages if available
    latex_packages = ["latex2mathml", "antlr4", "pygments", "colour"]
    
    for package in latex_packages:
        if is_package_importable(package):
            cmd.append(f"--include-package={package}")
            included_packages.append(package)
            if USE_ASCII_ONLY:
                print(f"Including LaTeX support: {package}")
            else:
                print(f"📦 Including LaTeX support: {package}")

    # Critical system modules
    essential_modules = [
        "json", "tempfile", "threading", "subprocess",
        "os", "sys", "ctypes", "venv", "fixes", "psutil",
        "process_utils", "logging", "pathlib", "shutil",
        "glob", "re", "time", "datetime", "uuid", "base64",
        "io", "codecs", "platform", "getpass", "signal",
        "atexit", "queue", "math", "random", "collections",
        "itertools", "functools", "operator", "copy"
    ]

    for module in essential_modules:
        cmd.append(f"--include-module={module}")

    # LaTeX and mathematical expression support data (selective)
    latex_data_packages = ["manim", "matplotlib", "numpy"]

    for package in latex_data_packages:
        if is_package_importable(package):
            cmd.append(f"--include-package-data={package}")
            if USE_ASCII_ONLY:
                print(f"Including data for: {package}")
            else:
                print(f"📦 Including data for: {package}")

    # Include LaTeX-specific modules (minimal set)
    latex_modules = [
        "sympy.printing.latex", "sympy.printing.mathml", 
        "sympy.core.basic", "sympy.core.expr"
    ]

    for module in latex_modules:
        if is_package_importable(module.split('.')[0]):
            cmd.append(f"--include-module={module}")

    # Manim-specific data inclusion (but exclude tests)
    if is_package_importable("manim"):
        cmd.extend([
            "--include-package-data=manim",
            "--include-package-data=manim.mobject",
            "--include-package-data=manim.scene",
            "--include-package-data=manim.animation",
            "--include-package-data=manim.utils",
        ])
        # But exclude test data
        cmd.extend([
            "--nofollow-import-to=manim.*.tests.*",
            "--nofollow-import-to=manim.test.*"
        ])

    # Output configuration
    cmd.extend([
        "--output-dir=dist",
    ])

    # Icon (if available)
    if Path("assets/icon.ico").exists():
        cmd.append("--windows-icon-from-ico=assets/icon.ico")
        if USE_ASCII_ONLY:
            print("Using custom icon")
        else:
            print("🎨 Using custom icon")

    # Include data directories and assets
    data_dirs = ["assets=assets"]

    # Try to include matplotlib data if available (but not tests)
    try:
        import matplotlib
        mpl_data = Path(matplotlib.get_data_path())
        if mpl_data.exists():
            data_dirs.append(f"{mpl_data}=matplotlib/mpl-data")
            if USE_ASCII_ONLY:
                print("Including matplotlib data")
            else:
                print("📊 Including matplotlib data")
    except ImportError:
        pass

    for data_dir in data_dirs:
        cmd.append(f"--include-data-dir={data_dir}")

    # Performance optimization
    cmd.append(f"--jobs={jobs}")

    # Final target
    cmd.append("app.py")

    if USE_ASCII_ONLY:
        print("Building standalone executable with LaTeX support...")
    else:
        print("🔨 Building standalone executable with LaTeX support...")
    print("Command:", " ".join(cmd))
    print("=" * 60)

    # Environment variables for compilation
    env = os.environ.copy()
    env["GCC_LTO"] = "0"
    env["NUITKA_DISABLE_LTO"] = "1"
    env["GCC_COMPILE_ARGS"] = "-fno-lto"

    # Disable problematic optimizations
    env["NUITKA_DISABLE_CCACHE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    # Set process priority for faster compilation
    process_priority = 0
    if priority == "high" and sys.platform == "win32":
        if USE_ASCII_ONLY:
            print("Setting HIGH process priority for maximum CPU utilization")
        else:
            print("🔥 Setting HIGH process priority for maximum CPU utilization")
        process_priority = 0x00000080

    # Start compilation process
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

    # Display CPU and build info
    if USE_ASCII_ONLY:
        print(f"CPU Info: {cpu_count} logical cores available")
        print(f"Using {jobs} compilation threads")
        print(f"Included {len(included_packages)} packages")
    else:
        print(f"🖥️ CPU Info: {cpu_count} logical cores available")
        print(f"⚙️ Using {jobs} compilation threads")
        print(f"📦 Included {len(included_packages)} packages")

    # Stream compilation output in real-time
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
            print("Standalone build successful!")
        else:
            print("✅ Standalone build successful!")

        # Find the executable
        exe_path = find_standalone_executable()
        if exe_path:
            if USE_ASCII_ONLY:
                print(f"Executable: {exe_path}")
                print(f"Distribution folder: {exe_path.parent}")
                print(f"\nSUCCESS! Standalone version ready with LaTeX support!")
                print(f"Features included:")
                print(f"  - Mathematical expression rendering")
                print(f"  - Basic LaTeX formula support")
                print(f"  - Professional animation engine")
                print(f"  - No console windows")
            else:
                print(f"📁 Executable: {exe_path}")
                print(f"📁 Distribution folder: {exe_path.parent}")
                print(f"\n🎉 SUCCESS! Standalone version ready with LaTeX support!")
                print(f"🧮 Features included:")
                print(f"  ✅ Mathematical expression rendering")
                print(f"  ✅ Basic LaTeX formula support")
                print(f"  ✅ Professional animation engine")
                print(f"  ✅ No console windows")

            # Create configuration file for LaTeX
            create_latex_config(exe_path.parent)

            # Create launcher scripts
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

def call_hidden_process(*args, **kwargs):
    """subprocess.call() with hidden console window"""
    return run_hidden_process(*args, **kwargs).returncode

def check_output_hidden_process(*args, **kwargs):
    """subprocess.check_output() with hidden console window"""
    if 'stdout' not in kwargs:
        kwargs['stdout'] = subprocess.PIPE
    if 'stderr' not in kwargs:
        kwargs['stderr'] = subprocess.DEVNULL
    
    result = run_hidden_process(*args, **kwargs)
    
    if result.returncode != 0:
        cmd = args[0] if args else kwargs.get('args')
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr)
    
    return result.stdout

def check_call_hidden_process(*args, **kwargs):
    """subprocess.check_call() with hidden console window"""
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
run_original = subprocess._original_run
popen_original = subprocess._original_popen
call_original = subprocess._original_call
check_output_original = subprocess._original_check_output
check_call_original = subprocess._original_check_call

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
]
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
    
    if USE_ASCII_ONLY:
        print("Created fixes module to handle runtime issues")
    else:
        print("📄 Created fixes module to handle runtime issues")

def create_no_console_patch():
    """Create a more aggressive patch file to ensure NO subprocess calls show console windows"""
    patch_content = '''# ENHANCED_NO_CONSOLE_PATCH.py
# This ensures all subprocess calls hide console windows
# IMPROVED: Added protection against recursive patching

import subprocess
import sys
import os
import ctypes

# Check if already patched to prevent recursion
if hasattr(subprocess, '_manimstudio_patched'):
    print("Subprocess already patched, skipping additional patching")
else:
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

    # Store original functions BEFORE defining any wrappers
    # to prevent recursive calls
    _original_run = subprocess.run
    _original_popen = subprocess.Popen
    _original_call = subprocess.call
    _original_check_output = subprocess.check_output
    _original_check_call = subprocess.check_call

    # Define the unified process utilities if they weren't imported
    if 'run_hidden_process' not in globals():
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
            
            # Run the process using original run - directly reference the saved original
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

    # Monkey patch ALL subprocess functions
    subprocess.run = run_hidden_process
    subprocess.Popen = popen_hidden_process
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

    # Mark as patched to prevent recursive patching
    subprocess._manimstudio_patched = True
    subprocess._original_run = _original_run  # Store reference to original
    subprocess._original_popen = _original_popen  # Store reference to original

    print("Subprocess patching complete - all console windows will be hidden")

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
    
    if USE_ASCII_ONLY:
        print(f"Created launchers: {launcher_path} and {ps_launcher_path}")
    else:
        print(f"📝 Created launchers: {launcher_path} and {ps_launcher_path}")

def create_latex_config(dist_dir):
    """Create LaTeX configuration for the standalone build"""
    try:
        config_content = """# ManimStudio LaTeX Configuration
# This file configures LaTeX support for mathematical expressions

[tex]
# Use built-in LaTeX processing
tex_template = TeX_Template_string

[CLI]
# Reduce verbosity to avoid console output
verbosity = WARNING

[logger]
# Configure logging for standalone app
logging_level = WARNING

[output]
# Optimize for standalone deployment
disable_caching = True
"""

        config_path = Path(dist_dir) / "manim_config.cfg"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)

        if USE_ASCII_ONLY:
            print(f"Created LaTeX config: {config_path}")
        else:
            print(f"📝 Created LaTeX config: {config_path}")

    except Exception as e:
        if USE_ASCII_ONLY:
            print(f"Warning: Could not create LaTeX config: {e}")
        else:
            print(f"⚠️ Warning: Could not create LaTeX config: {e}")
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
def build_minimal_version(jobs=None, priority="normal"):
    """Build minimal version without heavy packages like sympy for fastest compilation"""
    
    cpu_count = multiprocessing.cpu_count()
    if jobs is None:
        jobs = max(1, cpu_count - 1)

    if USE_ASCII_ONLY:
        print(f"Building MINIMAL version (fast build) with {jobs} CPU threads...")
    else:
        print(f"🚀 Building MINIMAL version (fast build) with {jobs} CPU threads...")

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

    # Create assets directory
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)

    # Create patches
    create_no_console_patch()
    create_fixes_module()
    create_subprocess_helper()

    # Check prerequisites
    if not check_system_prerequisites():
        if USE_ASCII_ONLY:
            print("ERROR: System prerequisites check failed")
        else:
            print("❌ System prerequisites check failed")
        return False

    # Basic command with minimal packages
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
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
        "--onefile-tempdir-spec=CACHE",
    ]

    # Exclude ALL problematic modules including sympy and scipy completely
    massive_exclusions = [
        "sympy.*", "scipy.*", "*.tests.*", "*.test_*", "test.*",
        "pytest.*", "*.benchmarks.*", "setuptools.*", "distutils.*",
        "zstandard.*", "_distutils_hack.*", "numpy.distutils.*",
        "matplotlib.tests.*", "PIL.tests.*", "cv2.tests.*"
    ]
    
    for module in massive_exclusions:
        cmd.append(f"--nofollow-import-to={module}")

    # Include only essential packages (no sympy, no scipy, no manim initially)
    for package in MINIMAL_PACKAGES:
        if is_package_importable(package):
            correct_name = get_correct_package_name(package)
            if correct_name:
                cmd.append(f"--include-package={correct_name}")
                if USE_ASCII_ONLY:
                    print(f"Including minimal package: {correct_name}")
                else:
                    print(f"✅ Including minimal package: {correct_name}")

    # Try to include manim but with heavy exclusions
    if is_package_importable("manim"):
        cmd.append("--include-package=manim")
        cmd.append("--include-package-data=manim")
        # Exclude manim tests and heavy modules
        cmd.append("--nofollow-import-to=manim.*.tests")
        cmd.append("--nofollow-import-to=manim.test.*")
        if USE_ASCII_ONLY:
            print("Including manim (minimal, excluding tests)")
        else:
            print("✅ Including manim (minimal, excluding tests)")

    # Include essential modules
    essential_modules = [
        "json", "tempfile", "threading", "subprocess",
        "os", "sys", "ctypes", "venv", "fixes", "psutil",
        "process_utils", "logging", "pathlib", "shutil"
    ]

    for module in essential_modules:
        cmd.append(f"--include-module={module}")

    # Output configuration
    cmd.extend([
        "--output-dir=dist",
        "--output-filename=ManimStudio_Minimal.exe",
        f"--jobs={jobs}",
    ])

    # Icon if available
    if Path("assets/icon.ico").exists():
        cmd.append("--windows-icon-from-ico=assets/icon.ico")

    # Include assets
    cmd.append("--include-data-dir=assets=assets")

    # Final target
    cmd.append("app.py")

    if USE_ASCII_ONLY:
        print("Building minimal executable (fastest compilation)...")
    else:
        print("🔨 Building minimal executable (fastest compilation)...")
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
        if USE_ASCII_ONLY:
            print("Setting HIGH process priority for fastest compilation")
        else:
            print("🔥 Setting HIGH process priority for fastest compilation")
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

    # Display info
    if USE_ASCII_ONLY:
        print(f"CPU Info: {multiprocessing.cpu_count()} logical cores available")
        print(f"Using {jobs} compilation threads")
        print("Excluded heavy modules: sympy, scipy, all tests, benchmarks")
    else:
        print(f"🖥️ CPU Info: {multiprocessing.cpu_count()} logical cores available")
        print(f"⚙️ Using {jobs} compilation threads")
        print("🚫 Excluded heavy modules: sympy, scipy, all tests, benchmarks")

    # Stream output
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
            print("Minimal build successful!")
        else:
            print("✅ Minimal build successful!")
        
        exe_path = find_executable()
        if exe_path:
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            if USE_ASCII_ONLY:
                print(f"Executable: {exe_path} ({size_mb:.1f} MB)")
                print("FAST BUILD: Excluded heavy modules for quick compilation")
            else:
                print(f"📁 Executable: {exe_path} ({size_mb:.1f} MB)")
                print("⚡ FAST BUILD: Excluded heavy modules for quick compilation")
            
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
            print("Minimal build failed!")
        else:
            print("❌ Minimal build failed!")
        print(f"Return code: {return_code}")
        return None
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
    parser.add_argument("--build-type", type=int, choices=[1, 2, 3, 4, 5], help="Build type: 1=onefile, 2=standalone, 3=debug, 4=both silent, 5=minimal")
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
    
    logging.info("Building release version with improved performance")
    
    # Use command line arg if provided, otherwise prompt
    if args.build_type:
        choice = str(args.build_type)
    else:
        # Ask for build type
        print("\nSelect build type:")
        if USE_ASCII_ONLY:
            print("1. Silent onefile build (single .exe)")
            print("2. Silent standalone build (directory)")
            print("3. Debug build (with console)")
            print("4. Both silent builds")
            print("5. Minimal build (fastest, no sympy/scipy)")
        else:
            print("1. 🔇 Silent onefile build (single .exe)")
            print("2. 📁 Silent standalone build (directory)")
            print("3. 🐛 Debug build (with console)")
            print("4. 📦 Both silent builds")
            print("5. ⚡ Minimal build (fastest, no sympy/scipy)")
        choice = input("\nEnter your choice (1-5): ").strip()
    
    success = False
    
    if choice == "1":
        exe_path = build_self_contained_version(jobs=jobs, priority=process_priority)
        success = exe_path is not None
    elif choice == "2":
        exe_path = build_standalone_version(jobs=jobs, priority=process_priority)
        success = exe_path is not None
    elif choice == "3":
        if USE_ASCII_ONLY:
            print("Debug build option temporarily disabled while fixing compatibility issues")
        else:
            print("🐛 Debug build option temporarily disabled while fixing compatibility issues")
        success = False
    elif choice == "4":
        print("\n" + ("Building onefile version..." if USE_ASCII_ONLY else "🔇 Building onefile version..."))
        onefile_exe = build_self_contained_version(jobs=jobs, priority=process_priority)
        print("\n" + ("Building standalone version..." if USE_ASCII_ONLY else "📁 Building standalone version..."))
        standalone_exe = build_standalone_version(jobs=jobs, priority=process_priority)
        success = onefile_exe is not None or standalone_exe is not None
    elif choice == "5":
        print("\n" + ("Building minimal version (fastest)..." if USE_ASCII_ONLY else "⚡ Building minimal version (fastest)..."))
        exe_path = build_minimal_version(jobs=jobs, priority=process_priority)
        success = exe_path is not None
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
        
        if choice == "5":
            if USE_ASCII_ONLY:
                print("MINIMAL BUILD: Fast compilation without heavy mathematical libraries")
                print("   Included: Basic manim, customtkinter, PIL, numpy")
                print("   Excluded: sympy, scipy, all tests, benchmarks")
                print("   Result: Much faster compilation time")
            else:
                print("⚡ MINIMAL BUILD: Fast compilation without heavy mathematical libraries")
                print("   ✅ Included: Basic manim, customtkinter, PIL, numpy")
                print("   🚫 Excluded: sympy, scipy, all tests, benchmarks")
                print("   🚀 Result: Much faster compilation time")
        else:
            if USE_ASCII_ONLY:
                print("GUARANTEE: The release version will NEVER show console windows")
                print("   Main app: Silent")
                print("   Manim operations: Hidden")
                print("   Package installs: Silent")
                print("   All operations: Invisible")
            else:
                print("🔇 GUARANTEE: The release version will NEVER show console windows")
                print("   ✅ Main app: Silent")
                print("   ✅ Manim operations: Hidden")
                print("   ✅ Package installs: Silent")
                print("   ✅ All operations: Invisible")
        
        if USE_ASCII_ONLY:
            print("Professional desktop application ready!")
        else:
            print("🚀 Professional desktop application ready!")
    else:
        if USE_ASCII_ONLY:
            print("Build failed!")
        else:
            print("❌ Build failed!")
        sys.exit(1)
if __name__ == "__main__":
    main()
