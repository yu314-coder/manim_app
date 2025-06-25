# app.py - Manim Animation Studio - Professional Edition with Integrated Environment Manager
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import tempfile
import os
import ctypes
import logging
import json
import subprocess
import getpass
import platform
import shlex
try:
    from process_utils import popen_original, run_original
except Exception:
    popen_original = subprocess.Popen
    run_original = subprocess.run
import sys
import time
import threading
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
import re
import webbrowser
from PIL import Image, ImageTk
import cv2
import math
import requests
from dataclasses import dataclass
from typing import List, Optional
import psutil
import signal
import glob
import queue
import atexit
import multiprocessing
import importlib.util
import importlib 
try:
    from fixes import ensure_ascii_path
except Exception:
    def ensure_ascii_path(path: str) -> str:
        return path
from queue import Queue, Empty
import threading
import time
# Determine base directory of the running script or executable
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Encoding setup
# Force UTF-8 for all file operations and standard streams. This helps avoid
# Unicode related crashes especially on Windows.
import locale

try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except Exception:
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except Exception:
        pass

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = '0'
# Add this to the top of app.py after the imports section
# ADD THIS RIGHT AFTER YOUR IMPORTS
try:
    import bundled_env_loader
    print("📦 Using bundled environment")
    USING_BUNDLED_ENV = True
except ImportError:
    print("🐍 Using standard environment")
    USING_BUNDLED_ENV = False
def get_executable_directory():
    """Get the directory where the executable is located"""
    if getattr(sys, 'frozen', False):
        # Running as executable
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))
# Add this near the top of your app.py, after BASE_DIR is defined

def setup_portable_logging():
    """Set up logging to go next to the app.exe for portability"""
    
    # Determine where to put logs - next to executable for portability
    if getattr(sys, 'frozen', False):
        # Running as executable - logs next to app.exe
        log_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        # Running as script - logs next to script
        log_dir = BASE_DIR
    
    # Create logs directory next to executable
    logs_dir = os.path.join(log_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Set up log file paths
    main_log = os.path.join(logs_dir, "manim_studio.log")
    debug_log = os.path.join(logs_dir, "debug.log")
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(main_log, encoding='utf-8'),
            logging.FileHandler(debug_log, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Log the setup
    logger = logging.getLogger(__name__)
    logger.info(f"📁 Portable logging initialized")
    logger.info(f"   Log directory: {logs_dir}")
    logger.info(f"   Main log: {main_log}")
    logger.info(f"   Debug log: {debug_log}")
    
    return logs_dir

# Call this early in your app initialization
LOGS_DIR = setup_portable_logging()
def run_subprocess_safe(command, **kwargs):
    """Enhanced subprocess runner for onefile executables"""
    if getattr(sys, 'frozen', False):
        # Running as onefile executable - need special handling
        
        # Fix PATH to include the unpacked directory
        env = kwargs.get('env', os.environ.copy())
        
        # Add the executable directory to PATH
        exe_dir = get_executable_directory()
        if 'PATH' in env:
            env['PATH'] = f"{exe_dir};{env['PATH']}"
        else:
            env['PATH'] = exe_dir
            
        # Use system temp directory instead of onefile temp
        system_temp = os.environ.get('TEMP', tempfile.gettempdir())
        env.update({
            'TEMP': system_temp,
            'TMP': system_temp,
            'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONUNBUFFERED': '1'
        })
        
        kwargs['env'] = env
        
        # Force shell=False for onefile to avoid shell interpretation issues
        kwargs['shell'] = False
        
        # Set working directory to a stable location
        if 'cwd' not in kwargs:
            kwargs['cwd'] = system_temp
    
    try:
        return subprocess.run(command, **kwargs)
    except Exception as e:
        print(f"Subprocess error: {e}")
        print(f"Command: {command}")
        raise

def run_subprocess_async_safe(command, callback, **kwargs):
    """Safe async subprocess runner for onefile executables"""
    def run_in_thread():
        try:
            # Use the safe subprocess runner
            result = run_subprocess_safe(command, **kwargs)
            success = result.returncode == 0
            callback(success, result.returncode)
        except Exception as e:
            print(f"Async subprocess error: {e}")
            callback(False, -1)
    
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    return thread

# ---------------------------------------------------------------------------
# Logging utilities
class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that ignores encoding errors"""

    def emit(self, record):
        try:
            msg = self.format(record)
            try:
                self.stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                encoding = getattr(self.stream, "encoding", "utf-8")
                safe_msg = msg.encode(encoding, errors="replace").decode(encoding)
                self.stream.write(safe_msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)
def check_dll_dependencies():
        """Check if required DLLs are available at startup"""
        if getattr(sys, 'frozen', False):
            try:
                import mapbox_earcut  # noqa: F401
                print("✅ mapbox_earcut loaded successfully")
                return True
            except ImportError as e:
                print(f"❌ mapbox_earcut import failed: {e}")
                
                # Try to provide helpful error message
                if "DLL load failed" in str(e):
                    messagebox.showerror(
                        "Missing Dependencies",
                        "The application requires Visual C++ Redistributable.\n\n"
                        "Please install Microsoft Visual C++ 2015-2022 Redistributable (x64)\n"
                        "from the Microsoft website and restart the application.\n\n"
                        "Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe"
                    )
                return False
        return True
# Helper to convert Windows short paths to long form
def get_long_path(path: str) -> str:
    """Return the long form of a Windows path if possible."""
    if os.name == "nt":
        GetLongPathNameW = ctypes.windll.kernel32.GetLongPathNameW
        GetLongPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        buffer = ctypes.create_unicode_buffer(260)
        result = GetLongPathNameW(path, buffer, len(buffer))
        if result:
            return buffer.value
    return path

# Global media directory
#
# Some TeX distributions on Windows fail when paths contain spaces or
# non-ASCII characters.  When the application is located in such a
# directory the generated TeX files may end up with short (8.3) paths
# which causes ``pdflatex`` to stop with an "Emergency stop" error.
# To avoid this we place the media directory inside the system's
# temporary directory where ASCII paths are guaranteed. We convert the
# resulting path to its long form on Windows to avoid 8.3 short paths.
MEDIA_DIR = get_long_path(
    os.path.join(ensure_ascii_path(tempfile.gettempdir()), "manim_media")
)
os.makedirs(MEDIA_DIR, exist_ok=True)
# Try to import Jedi for IntelliSense
try:
    import jedi
    JEDI_AVAILABLE = True
except ImportError:
    JEDI_AVAILABLE = False
    print("Jedi not available. IntelliSense will be limited.")

# Try to import other optional dependencies
try:
    from idlelib.colorizer import ColorDelegator, color_config  # noqa: F401
    from idlelib.percolator import Percolator  # noqa: F401
    from idlelib.undo import UndoDelegator  # noqa: F401
    IDLE_AVAILABLE = True
except ImportError:
    IDLE_AVAILABLE = False

try:
    from pygments import highlight  # noqa: F401
    from pygments.lexers import PythonLexer  # noqa: F401
    from pygments.formatters import TerminalFormatter  # noqa: F401
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False
# Early load of fixes module to handle runtime issues
try:
    import fixes
    if hasattr(fixes, "apply_fixes"):
        fixes.apply_fixes()
    elif hasattr(fixes, "apply_all_fixes"):
        fixes.apply_all_fixes()
    else:
        print("Warning: apply_fixes function not found in fixes module")
except (ImportError, AttributeError) as e:
    print(f"Warning: fixes module issue: {e}")
except Exception as e:
    print(f"Warning: Error applying fixes: {e}")

# Force matplotlib backend to TkAgg
try:
    import matplotlib
    matplotlib.use('TkAgg')
except ImportError:
    print("Warning: matplotlib not available")
    pass
# Configure CustomTkinter with modern appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('manim_studio.log', encoding='utf-8'),
        SafeStreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Application constants
APP_NAME = "Manim Animation Studio"
APP_VERSION = "3.5.0"
APP_AUTHOR = "Manim Studio Team"
APP_EMAIL = "euler.yu@gmail.com"

# Essential packages for ManimStudio - UPDATED VERSION
ESSENTIAL_PACKAGES = [
    # Core animation and math (minimal for basic functionality)
    "numpy>=1.22.0",
    "matplotlib>=3.5.0", 
    "scipy>=1.8.0",
    
    # UI and development tools (essential)
    "customtkinter>=5.0.0",
    "jedi>=0.18.0",  # IntelliSense
    "Pillow>=9.0.0",
    
    # Manim dependencies (installed separately to avoid DLL issues)
    "mapbox-earcut>=0.12.0",
    "manimpango>=0.4.0",
    "moderngl>=5.6.0",
    "moderngl-window>=2.3.0",
    "colour>=0.1.5",
    "decorator>=4.4.2",
    "isosurfaces>=0.1.0",
    
    # Image/Video processing
    "opencv-python>=4.6.0",
    "imageio>=2.19.0",
    "moviepy>=1.0.3",
    "imageio-ffmpeg",
    
    # System utilities
    "psutil>=5.8.0",
    "requests>=2.25.0",
    "colorama>=0.4.4",
    "rich>=10.0.0",
    "click>=8.0.0",
    
    # Remove aiohttp - not needed for basic functionality
    # "aiohttp>=3.8.5",  # REMOVED - causes unnecessary dependencies
]

# Minimal packages for initial setup (to avoid DLL conflicts)
MINIMAL_PACKAGES = [
    "numpy>=1.22.0",
    "customtkinter>=5.0.0", 
    "Pillow>=9.0.0",
    "jedi>=0.18.0",
]

# Windows-specific package fixes
WINDOWS_FIX_PACKAGES = [
    "mapbox-earcut>=0.12.0",
    "manimpango>=0.4.0",
    "moderngl>=5.6.0",
]

# Optional packages
OPTIONAL_PACKAGES = [
    "jupyter>=1.0.0",
    "ipython>=8.0.0",
    "notebook>=6.4.0",
    "beautifulsoup4>=4.11.0",
    "lxml>=4.9.0",
    "sympy>=1.11.0",
    "networkx>=2.8.0",
]
# Add this to the settings variables
CPU_USAGE_PRESETS = {
    "Low": {"cores": 1, "description": "Use 1 core (minimal CPU usage)"},
    "Medium": {"cores": None, "description": "Use half available cores (balanced)"},
    "High": {"cores": -1, "description": "Use all available cores (fastest)"},
    "Custom": {"cores": 2, "description": "Use custom number of cores"}
}
QUALITY_PRESETS = {
    "480p": {"resolution": "854x480", "fps": "30", "flag": "-ql"},
    "720p": {"resolution": "1280x720", "fps": "30", "flag": "-qm"},
    "1080p": {"resolution": "1920x1080", "fps": "60", "flag": "-qh"},
    "4K": {"resolution": "3840x2160", "fps": "60", "flag": "-qk"},
    "8K": {"resolution": "7680x4320", "fps": "60", "flag": "-qp"},
    "Custom": {"resolution": "1920x1080", "fps": "30", "flag": "-qh"}  # Default values for custom
}

PREVIEW_QUALITIES = {
    "Low": {"resolution": "640x360", "fps": "15", "flag": "-ql"},
    "Medium": {"resolution": "854x480", "fps": "24", "flag": "-ql"},
    "High": {"resolution": "1280x720", "fps": "30", "flag": "-qm"}
}

EXPORT_FORMATS = {
    "MP4 Video": "mp4",
    "GIF Animation": "gif",
    "WebM Video": "webm",
    "PNG Sequence": "png"
}

# Enhanced Professional VSCode color schemes
THEME_SCHEMES = {
    "Dark+": {
        "primary": "#007ACC",
        "primary_hover": "#005A9E",
        "secondary": "#6366f1",
        "accent": "#0E7490",
        "success": "#16A085",
        "warning": "#F39C12",
        "error": "#E74C3C",
        "info": "#3498DB",
        "surface": "#252526",
        "surface_light": "#2D2D30",
        "surface_lighter": "#383838",
        "background": "#1E1E1E",
        "text": "#CCCCCC",
        "text_secondary": "#858585",
        "text_bright": "#FFFFFF",
        "border": "#464647",
        "selection": "#264F78",
        "current_line": "#2A2D2E",
        "line_numbers": "#858585",
        "line_numbers_bg": "#252526",
        "bracket_match": "#49483E",
        "find_match": "#515C6A",
        "find_current": "#007ACC",
    },
    "Light+": {
        "primary": "#0066CC",
        "primary_hover": "#004499",
        "secondary": "#5A51D8",
        "accent": "#0E7490",
        "success": "#16A085",
        "warning": "#F39C12",
        "error": "#E74C3C",
        "info": "#3498DB",
        "surface": "#F3F3F3",
        "surface_light": "#FFFFFF",
        "surface_lighter": "#F8F8F8",
        "background": "#FFFFFF",
        "text": "#333333",
        "text_secondary": "#666666",
        "text_bright": "#000000",
        "border": "#E5E5E5",
        "selection": "#ADD6FF",
        "current_line": "#F0F0F0",
        "line_numbers": "#237893",
        "line_numbers_bg": "#F3F3F3",
        "bracket_match": "#E7E7E7",
        "find_match": "#FFE792",
        "find_current": "#A8CCF0",
    },
    "Monokai": {
        "primary": "#F92672",
        "primary_hover": "#DC2566",
        "secondary": "#AE81FF",
        "accent": "#66D9EF",
        "success": "#A6E22E",
        "warning": "#FD971F",
        "error": "#F92672",
        "info": "#66D9EF",
        "surface": "#272822",
        "surface_light": "#3E3D32",
        "surface_lighter": "#49483E",
        "background": "#272822",
        "text": "#F8F8F2",
        "text_secondary": "#75715E",
        "text_bright": "#FFFFFF",
        "border": "#49483E",
        "selection": "#49483E",
        "current_line": "#3E3D32",
        "line_numbers": "#90908A",
        "line_numbers_bg": "#272822",
        "bracket_match": "#49483E",
        "find_match": "#FFE792",
        "find_current": "#F92672",
    },
    "Solarized Dark": {
        "primary": "#268BD2",
        "primary_hover": "#2076C2",
        "secondary": "#6C71C4",
        "accent": "#2AA198",
        "success": "#859900",
        "warning": "#B58900",
        "error": "#DC322F",
        "info": "#268BD2",
        "surface": "#002B36",
        "surface_light": "#073642",
        "surface_lighter": "#586E75",
        "background": "#002B36",
        "text": "#839496",
        "text_secondary": "#586E75",
        "text_bright": "#FDF6E3",
        "border": "#073642",
        "selection": "#073642",
        "current_line": "#073642",
        "line_numbers": "#586E75",
        "line_numbers_bg": "#002B36",
        "bracket_match": "#586E75",
        "find_match": "#FFE792",
        "find_current": "#268BD2",
    },
    "Custom": {
        "primary": "#007ACC",
        "primary_hover": "#005A9E",
        "secondary": "#6366f1",
        "accent": "#0E7490",
        "success": "#16A085",
        "warning": "#F39C12",
        "error": "#E74C3C",
        "info": "#3498DB",
        "surface": "#252526",
        "surface_light": "#2D2D30",
        "surface_lighter": "#383838",
        "background": "#1E1E1E",
        "text": "#CCCCCC",
        "text_secondary": "#858585",
        "text_bright": "#FFFFFF",
        "border": "#464647",
        "selection": "#264F78",
        "current_line": "#2A2D2E",
        "line_numbers": "#858585",
        "line_numbers_bg": "#252526",
        "bracket_match": "#49483E",
        "find_match": "#515C6A",
        "find_current": "#007ACC",
    }
}
# VSCode-style colors (adjust these to match your existing color scheme)
# Ensure VSCODE_COLORS has all required keys
VSCODE_COLORS = {
    "background": "#1e1e1e",
    "surface": "#252526",
    "surface_light": "#2d2d30", 
    "surface_lighter": "#3e3e42",
    "text": "#cccccc",
    "text_bright": "#ffffff",
    "text_secondary": "#969696",
    "selection": "#264f78",
    "primary": "#007acc",
    "primary_hover": "#005a9e",
    "success": "#16A085",
    "error": "#E74C3C",
    "warning": "#F39C12",
    "info": "#3498DB",
    "accent": "#FF6B35",
    "current_line": "#2a2a2a",
    "line_numbers": "#858585",
    "line_numbers_bg": "#1e1e1e",
    "bracket_match": "#0064001a",
    "find_match": "#515c6a",
    "find_current": "#f2cc60"
}
# Global color scheme
# Global color scheme - explicitly ensure critical keys exist
VSCODE_COLORS = THEME_SCHEMES["Dark+"].copy()
VSCODE_COLORS["success"] = "#16A085"  # Explicitly ensure success exists
VSCODE_COLORS["error"] = "#E74C3C"    # Explicitly ensure error exists 
VSCODE_COLORS["warning"] = "#F39C12"  # Explicitly ensure warning exists
VSCODE_COLORS["info"] = "#3498DB"     # Explicitly ensure info exists


# Enhanced Python syntax highlighting colors (like VSCode Dark+)
SYNTAX_COLORS = {
    "keyword": "#569CD6",          # Blue - Keywords like def, class, if
    "string": "#CE9178",           # Orange - String literals
    "comment": "#6A9955",          # Green - Comments
    "number": "#B5CEA8",           # Light green - Numbers
    "function": "#DCDCAA",         # Yellow - Function names
    "class": "#4EC9B0",            # Cyan - Class names
    "builtin": "#569CD6",          # Blue - Built-in functions
    "operator": "#D4D4D4",         # White - Operators
    "variable": "#9CDCFE",         # Light blue - Variables
    "constant": "#569CD6",         # Blue - Constants
    "decorator": "#569CD6",        # Blue - Decorators like @property
    "import": "#C586C0",           # Purple - Import statements
    "exception": "#569CD6",        # Blue - Exception classes
    "magic": "#DCDCAA",           # Yellow - Magic methods like __init__
    "self": "#569CD6",            # Blue - self keyword
    "parameter": "#9CDCFE",       # Light blue - Function parameters
}
# Runtime check for LaTeX availability
def check_latex_installation() -> Optional[str]:
    """Return the path to a working LaTeX executable, or ``None`` if not found.

    The detected LaTeX directory is prepended to ``PATH`` so bundled
    environments can access the system installation."""

    latex_path = shutil.which("latex") or shutil.which("pdflatex")
    if not latex_path:
        warning_lines = [
            "LaTeX was not found on this system.",
            "Please install a LaTeX distribution and ensure the 'latex'",
            "or 'pdflatex' command is available in your PATH.",
            "",
            "Windows: install MiKTeX from https://miktex.org/",
            "macOS: install MacTeX from https://www.tug.org/mactex/",
            "Linux: install TeX Live using your package manager, e.g.",
            "  sudo apt install texlive-full",
            "After installation restart the application."
        ]
        warning = "\n".join(warning_lines)
        logging.warning(warning)
        try:
            from tkinter import messagebox
            messagebox.showwarning("LaTeX not found", warning)
        except Exception:
            print(warning)
        return None

    try:
        subprocess.run(
            [latex_path, "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        logging.warning("LaTeX check failed: %s", exc)
        print(f"LaTeX found at {latex_path} but running it failed: {exc}")
        return None

    latex_dir = os.path.dirname(latex_path)
    current_path = os.environ.get("PATH", "")
    if latex_dir not in current_path.split(os.pathsep):
        os.environ["PATH"] = latex_dir + os.pathsep + current_path

    logging.info("LaTeX found: %s", latex_path)
    print(f"LaTeX found: {latex_path}")
    return latex_path

@dataclass
class PackageInfo:
    """Data class for package information"""
    name: str
    version: str
    description: str
    author: str
    license: str
    homepage: str
    download_url: str
    size: Optional[int] = None
    last_updated: Optional[str] = None
    dependencies: List[str] = None
    category: str = "General"
    stars: int = 0
    downloads: int = 0
    is_installed: bool = False
    installed_version: Optional[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
class PackageInstallationProgressDialog(ctk.CTkToplevel):
    """Advanced progress dialog for Python package installation with real-time feedback"""
    
    def install_packages_worker(self):
        """Worker thread for installing packages"""
        try:
            self.log_message("Starting package installation...")
            
            # Check if we have a valid Python environment
            if not self.venv_manager.python_path:
                self.log_message("ERROR: No valid Python environment found!")
                self.installation_failed("No Python environment available")
                return
            
            # First upgrade pip and setuptools
            self.log_message("Upgrading pip and setuptools...")
            self.update_overall_progress(0.05, "Upgrading pip...")
            pip_upgrade_cmd = self.venv_manager.get_pip_command()
            pip_upgrade_cmd.extend(["install", "--upgrade", "pip", "setuptools", "wheel"])
            
            subprocess.run(
                pip_upgrade_cmd,
                capture_output=True,
                text=True,
                timeout=180,
                cwd=tempfile.gettempdir()
            )
            
            # Install each package
            for i, package in enumerate(self.packages):
                if self.installation_cancelled:
                    self.log_message("Installation cancelled by user")
                    return
                
                self.current_package_index = i
                overall_progress = 0.1 + (i / self.total_packages * 0.8)  # 10% for pip upgrade, 80% for packages
                
                # Update UI
                self.update_overall_progress(
                    overall_progress,
                    f"Installing package {i+1} of {self.total_packages}"
                )
                
                self.update_package_progress(0, f"Installing {package}...")
                self.log_message(f"Installing {package}...")
                
                # Install the package
                success = self.install_single_package(package)
                
                if not success and not self.installation_cancelled:
                    self.log_message(f"ERROR: Failed to install {package}")
                    # Don't fail completely for single package failures
                    self.log_message("Continuing with remaining packages...")
                
                # Update progress
                self.update_package_progress(1.0, f"✓ {package} processed")
                self.log_message(f"✓ Processed {package}")
            
            # CRITICAL FIX: Handle mapbox_earcut DLL issues
            self.log_message("Checking for DLL issues...")
            self.update_overall_progress(0.9, "Fixing DLL dependencies...")
            
            # Test manim import
            test_cmd = [
                self.venv_manager.python_path, "-c", 
                "import manim; print('Manim import successful')"
            ]
            
            test_result = subprocess.run(
                test_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tempfile.gettempdir()
            )
            
            if test_result.returncode != 0 and "mapbox_earcut" in test_result.stderr:
                self.log_message("Detected mapbox_earcut DLL issue, applying fix...")
                fix_success = self.venv_manager.fix_mapbox_earcut_issue()
                if fix_success:
                    self.log_message("✓ Fixed mapbox_earcut DLL issues")
                else:
                    self.log_message("⚠️ Could not fix mapbox_earcut, but continuing...")
            
            # Installation completed
            if not self.installation_cancelled:
                self.update_overall_progress(1.0, "Installation completed!")
                self.log_message("🎉 Package installation process completed!")
                self.installation_completed()
                
        except Exception as e:
            self.log_message(f"ERROR: Installation failed with exception: {e}")
            self.installation_failed(str(e))

    def install_single_package(self, package):
        """Install a single package using pip with enhanced progress monitoring"""
        try:
            # Get the proper pip command
            pip_cmd = self.venv_manager.get_pip_command()
            pip_cmd.extend(["install", package, "--no-warn-script-location", "--progress-bar", "off"])
            
            # Run pip install with progress monitoring
            process = subprocess.Popen(
                pip_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True,
                cwd=tempfile.gettempdir()
            )
            
            # Monitor output for progress with better parsing
            output_lines = []
            while True:
                if self.installation_cancelled:
                    process.terminate()
                    return False
                
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                
                if line:
                    line = line.strip()
                    output_lines.append(line)
                    
                    # Enhanced progress tracking
                    if "Collecting" in line:
                        self.update_package_progress(0.1, f"Collecting {package}...")
                    elif "Downloading" in line:
                        self.update_package_progress(0.3, f"Downloading {package}...")
                    elif "Installing" in line or "Running setup.py" in line:
                        self.update_package_progress(0.7, f"Installing {package}...")
                    elif "Successfully installed" in line:
                        self.update_package_progress(1.0, f"✓ {package} installed")
                    
                    # Log important messages
                    if any(keyword in line.lower() for keyword in ["error", "warning", "successfully", "failed"]):
                        self.log_message(f"  {line}")
            
            return_code = process.poll()
            
            if return_code == 0:
                return True
            else:
                self.log_message(f"Package {package} installation had issues (code {return_code})")
                return False
                
        except Exception as e:
            self.log_message(f"Exception during {package} installation: {e}")
            return False
# Terminal emulation in Tkinter
class TkTerminal(tk.Text):
    """A Tkinter-based terminal emulator widget with realistic appearance"""

    def __init__(self, parent, app=None, **kwargs):
        # Terminal-like appearance
        kwargs.setdefault('background', '#0C0C0C')  # Windows Terminal dark background
        kwargs.setdefault('foreground', '#CCCCCC')  # Light gray text
        kwargs.setdefault('insertbackground', '#FFFFFF')  # White cursor
        kwargs.setdefault('selectbackground', '#264F78')  # VSCode selection color
        kwargs.setdefault('highlightthickness', 0)
        kwargs.setdefault('relief', 'flat')
        kwargs.setdefault('font', ('Cascadia Code', 11))  # Modern terminal font
        kwargs.setdefault('padx', 10)
        kwargs.setdefault('pady', 8)
        super().__init__(parent, **kwargs)

        self.app = app
        self.process = None
        self.command_running = False

        # History management
        history_dir = os.path.join(BASE_DIR, "history")
        os.makedirs(history_dir, exist_ok=True)
        self.history_file = os.path.join(history_dir, "terminal_history.txt")

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                self.command_history = [line.rstrip("\n") for line in f]
        except FileNotFoundError:
            self.command_history = []

        self.history_index = len(self.command_history)
        self.command_buffer = ""
        self.input_start = "1.0"

        # Track working directory and environment
        self.cwd = BASE_DIR
        self.env = os.environ.copy()

        # Configure enhanced tags with realistic terminal colors
        self.tag_configure("output", foreground="#CCCCCC")
        self.tag_configure("error", foreground="#FF6B6B")
        self.tag_configure("warning", foreground="#FFD93D")
        self.tag_configure("success", foreground="#6BCF7F")
        self.tag_configure("prompt", foreground="#61DAFB", font=('Cascadia Code', 11, 'bold'))
        self.tag_configure("directory", foreground="#4FC3F7")
        self.tag_configure("executable", foreground="#81C784")
        self.tag_configure("command", foreground="#FFB74D")
        self.tag_configure("info", foreground="#64B5F6")
        
        # Initialize with terminal banner
        self.show_terminal_banner()
        
        # Initialize prompt
        self.show_prompt()
        
        # Bind events
        self.bind("<Return>", self.on_enter)
        self.bind("<BackSpace>", self.on_backspace)
        self.bind("<Up>", self.on_up)
        self.bind("<Down>", self.on_down)
        self.bind("<Tab>", self.on_tab)
        self.bind("<Control-c>", self.on_ctrl_c)
        self.bind("<Control-l>", lambda e: self.clear_terminal())
        self.bind("<Key>", self.on_key)
        
    def show_terminal_banner(self):
        """Show terminal startup banner"""
        banner = f"""Manim Studio Terminal v{APP_VERSION}
Copyright (c) 2025 ManimStudio. All rights reserved.

Type 'help' for available commands.
Working directory: {self.cwd}

"""
        self.insert("end", banner, "info")
        
    def show_prompt(self):
        """Show command prompt with enhanced styling"""
        if self.command_running:
            return
            
        if os.name == "nt":
            # Windows-style prompt
            prompt_parts = [
                ("PS ", "prompt"),
                (f"{self.cwd}", "directory"),
                ("> ", "prompt")
            ]
        else:
            # Unix-style prompt
            user = getpass.getuser()
            host = platform.node().split(".")[0]
            prompt_parts = [
                (f"{user}@{host}", "success"),
                (":", "prompt"),
                (f"{self.cwd}", "directory"),
                ("$ ", "prompt")
            ]

        # Insert prompt with proper styling
        for text, tag in prompt_parts:
            self.insert("end", text, tag)
            
        self.input_start = self.index("end-1c")
        self.see("end")
        
    def on_enter(self, event):
        """Handle Enter key press"""
        command = self.get(self.input_start, "end-1c")
        self.insert("end", "\n")

        # Execute command
        if command.strip():
            self.command_history.append(command)
            self.history_index = len(self.command_history)
            try:
                with open(self.history_file, "a", encoding="utf-8") as f:
                    f.write(command + "\n")
            except Exception:
                pass

            self.execute_command(command)
        else:
            self.show_prompt()
            
        return "break"
        
    def on_backspace(self, event):
        """Handle Backspace key press"""
        if self.index("insert") <= self.input_start:
            return "break"
        return None
        
    def on_up(self, event):
        """Navigate command history up"""
        if self.command_history and self.history_index > 0:
            # Save current command if at the end of history
            if self.history_index == len(self.command_history):
                self.command_buffer = self.get(self.input_start, "end-1c")
                
            self.history_index -= 1
            self.delete(self.input_start, "end-1c")
            self.insert(self.input_start, self.command_history[self.history_index])
            
        return "break"
        
    def on_down(self, event):
        """Navigate command history down"""
        if self.history_index < len(self.command_history):
            self.history_index += 1
            self.delete(self.input_start, "end-1c")
            
            if self.history_index == len(self.command_history):
                self.insert(self.input_start, self.command_buffer)
            else:
                self.insert(self.input_start, self.command_history[self.history_index])
                
        return "break"
        
    def on_key(self, event):
        """Handle key press"""
        if self.index("insert") < self.input_start:
            self.mark_set("insert", "end")

    def on_tab(self, event):
        """Simple tab completion for files and directories"""
        current = self.get(self.input_start, "insert")
        tokens = current.split()
        if not tokens:
            return "break"

        prefix = tokens[-1]
        base = os.path.join(self.cwd, prefix)
        matches = glob.glob(base + "*")
        if len(matches) == 1:
            completion = os.path.basename(matches[0])
            new_line = " ".join(tokens[:-1] + [completion])
            self.delete(self.input_start, "end-1c")
            self.insert(self.input_start, new_line)
        elif len(matches) > 1:
            self.insert("end", "\n" + "  ".join(os.path.basename(m) for m in matches) + "\n", "output")
            self.show_prompt()
            self.insert(self.input_start, current)
        return "break"

    def on_ctrl_c(self, event):
        """Send interrupt signal to running process"""
        if self.process and self.process.poll() is None:
            try:
                if os.name == "nt":
                    self.process.terminate()
                else:
                    self.process.send_signal(signal.SIGINT)
            except Exception as e:
                self.insert("end", f"Error sending interrupt: {e}\n", "error")
        return "break"
            
    def execute_command(self, command):
        """Execute command with enhanced output formatting"""
        cmd = command.strip()
        
        # Show command in terminal style
        self.insert("end", "\n")
        
        # Handle built-in commands
        if self.handle_builtin_command(cmd):
            return
            
        # Handle special manim studio commands
        if self.handle_studio_command(cmd):
            return

        # Execute external command
        self.command_running = True
        try:
            # Show executing indicator
            self.insert("end", f"Executing: {cmd}\n", "command")
            
            process = subprocess.Popen(  # Use subprocess.Popen instead of popen_original
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                env=self.env,
                encoding='utf-8',          # ADD THIS
                errors='replace',          # ADD THIS
                universal_newlines=True
            )

            self.process = process

            def read_output():
                try:
                    for line in process.stdout:
                        if line:
                            # Color code output based on content
                            if "error" in line.lower() or "failed" in line.lower():
                                tag = "error"
                            elif "warning" in line.lower():
                                tag = "warning"
                            elif "success" in line.lower() or "completed" in line.lower():
                                tag = "success"
                            else:
                                tag = "output"
                                
                            self.insert("end", line, tag)
                            self.see("end")

                    return_code = process.wait()
                    
                    # Show completion status
                    if return_code == 0:
                        self.insert("end", "\n[Process completed successfully]\n", "success")
                    else:
                        self.insert("end", f"\n[Process exited with code {return_code}]\n", "error")
                        
                except Exception as e:
                    self.insert("end", f"\nError reading output: {str(e)}\n", "error")
                finally:
                    self.process = None
                    self.command_running = False
                    self.show_prompt()

            threading.Thread(target=read_output, daemon=True).start()

        except Exception as e:
            self.insert("end", f"Error: {str(e)}\n", "error")
            self.command_running = False
            self.show_prompt()
    
    def handle_builtin_command(self, cmd):
        """Handle built-in terminal commands"""
        if cmd.startswith("cd"):
            target = cmd[2:].strip() or os.path.expanduser("~")
            if not os.path.isabs(target):
                target = os.path.join(self.cwd, target)
            if os.path.isdir(target):
                self.cwd = os.path.abspath(target)
                self.insert("end", f"Changed directory to: {self.cwd}\n", "success")
            else:
                self.insert("end", f"Directory not found: {target}\n", "error")
            self.show_prompt()
            return True

        elif cmd in ("clear", "cls"):
            self.clear_terminal()
            return True

        elif cmd == "pwd":
            self.insert("end", f"{self.cwd}\n", "directory")
            self.show_prompt()
            return True
            
        elif cmd == "help":
            self.show_help()
            return True
            
        elif cmd.startswith("ls") or cmd.startswith("dir"):
            self.list_directory(cmd)
            return True
            
        return False
    
    def handle_studio_command(self, cmd):
        """Handle ManimStudio-specific commands"""
        if cmd.startswith("activate ") and self.app:
            env_name = cmd.split(None, 1)[1]
            if self.app.venv_manager.activate_venv(env_name):
                venv_path = os.path.join(self.app.venv_manager.venv_dir, env_name)
                bin_dir = "Scripts" if os.name == "nt" else "bin"
                bin_path = os.path.join(venv_path, bin_dir)
                self.env = os.environ.copy()
                self.env["PATH"] = bin_path + os.pathsep + self.env.get("PATH", "")
                self.env["VIRTUAL_ENV"] = venv_path
                self.insert("end", f"✓ Activated environment: {env_name}\n", "success")
            else:
                self.insert("end", f"✗ Failed to activate: {env_name}\n", "error")
            self.show_prompt()
            return True

        elif cmd == "deactivate" and self.app:
            if hasattr(self.app.venv_manager, "deactivate_venv"):
                self.app.venv_manager.deactivate_venv()
            self.env = os.environ.copy()
            self.insert("end", "✓ Environment deactivated\n", "success")
            self.show_prompt()
            return True
            
        elif cmd == "envs" and self.app:
            envs = self.app.venv_manager.list_venvs()
            self.insert("end", "Available environments:\n", "info")
            for env in envs:
                status = " (active)" if env == self.app.venv_manager.current_venv else ""
                self.insert("end", f"  • {env}{status}\n", "output")
            self.show_prompt()
            return True
            
        return False
        
    def show_help(self):
        """Show help information"""
        help_text = """
ManimStudio Terminal Commands:

Built-in Commands:
  help              Show this help message
  clear, cls        Clear the terminal
  cd <path>         Change directory
  pwd               Show current directory
  ls, dir           List directory contents

Environment Commands:
  envs              List available environments
  activate <name>   Activate virtual environment
  deactivate        Deactivate current environment

System Commands:
  Any system command (python, pip, git, etc.)

Keyboard Shortcuts:
  Ctrl+C            Interrupt running process
  Ctrl+L            Clear terminal
  Up/Down Arrow     Navigate command history
  Tab               Auto-complete paths

"""
        self.insert("end", help_text, "info")
        self.show_prompt()
        
    def list_directory(self, cmd):
        """Enhanced directory listing"""
        parts = shlex.split(cmd) if cmd else []
        show_all = "-a" in parts or "/a" in parts
        long_format = "-l" in parts or "/l" in parts
        
        # Determine target directory
        target = self.cwd
        for p in parts[1:]:
            if not p.startswith("-") and not p.startswith("/"):
                target = os.path.join(self.cwd, p) if not os.path.isabs(p) else p

        try:
            entries = os.listdir(target)
        except Exception as e:
            self.insert("end", f"Error: {e}\n", "error")
            self.show_prompt()
            return

        if not show_all:
            entries = [e for e in entries if not e.startswith('.')]
        entries.sort()

        if long_format:
            # Detailed listing
            total_size = 0
            for e in entries:
                full_path = os.path.join(target, e)
                try:
                    stat = os.stat(full_path)
                    size = stat.st_size
                    total_size += size
                    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    
                    if os.path.isdir(full_path):
                        self.insert("end", f"d {mtime} {size:>10} ", "info")
                        self.insert("end", f"{e}/\n", "directory")
                    elif os.access(full_path, os.X_OK):
                        self.insert("end", f"- {mtime} {size:>10} ", "info")
                        self.insert("end", f"{e}*\n", "executable")
                    else:
                        self.insert("end", f"- {mtime} {size:>10} {e}\n", "output")
                except:
                    self.insert("end", f"- ??? ??? {e}\n", "output")
                    
            self.insert("end", f"\nTotal: {len(entries)} items, {total_size} bytes\n", "info")
        else:
            # Grid listing
            cols = 4
            col_width = 20
            for i, e in enumerate(entries):
                full_path = os.path.join(target, e)
                if os.path.isdir(full_path):
                    self.insert("end", (e + "/").ljust(col_width), "directory")
                elif os.access(full_path, os.X_OK):
                    self.insert("end", (e + "*").ljust(col_width), "executable")
                else:
                    self.insert("end", e.ljust(col_width), "output")
                    
                if (i + 1) % cols == 0:
                    self.insert("end", "\n")
                    
            if len(entries) % cols != 0:
                self.insert("end", "\n")

        self.show_prompt()
        
    def clear_terminal(self):
        """Clear terminal and show banner"""
        self.delete("1.0", "end")
        self.show_terminal_banner()
        self.show_prompt()
        
    def run_command_redirected(self, command, on_complete=None, env=None):
        """Run command with improved file handling"""
        if isinstance(command, list):
            cmd_str = ' '.join(f'"{arg}"' if ' ' in str(arg) else str(arg) for arg in command)
        else:
            cmd_str = command

        # Show command being executed
        self.insert("end", f"\n$ {cmd_str}\n", "command")

        def execute_with_retry():
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if isinstance(command, list) and len(command) > 2:
                        potential_file = command[2]
                        if potential_file.endswith('.py') and not os.path.exists(potential_file):
                            if attempt < max_retries - 1:
                                self.insert("end", f"⚠️ File not found, retrying in 0.2s... (attempt {attempt + 1})\n", "warning")
                                time.sleep(0.2)
                                continue
                            else:
                                raise FileNotFoundError(f"Scene file not found after {max_retries} attempts: {potential_file}")

                    env_vars = self.env.copy()
                    if env:
                        env_vars.update(env)

                    process = popen_original(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        universal_newlines=True,
                        env=env_vars,
                        cwd=self.cwd,
                        bufsize=1
                    )

                    self.process = process
                    self.command_running = True

                    for line in process.stdout:
                        if line:
                            line_lower = line.lower()
                            if any(word in line_lower for word in ["error", "failed", "exception", "traceback"]):
                                tag = "error"
                            elif any(word in line_lower for word in ["warning", "warn"]):
                                tag = "warning"
                            elif any(word in line_lower for word in ["success", "complete", "done"]):
                                tag = "success"
                            else:
                                tag = "output"
                            self.insert("end", line, tag)
                            self.see("end")

                    return_code = process.wait()
                    if on_complete:
                        on_complete(return_code == 0, return_code)
                    return return_code == 0

                except FileNotFoundError as e:
                    if attempt == max_retries - 1:
                        self.insert("end", f"\n❌ File not found: {str(e)}\n", "error")
                        if on_complete:
                            on_complete(False, -1)
                        return False
                except Exception as e:
                    if attempt == max_retries - 1:
                        self.insert("end", f"\n❌ Command failed: {str(e)}\n", "error")
                        if on_complete:
                            on_complete(False, -1)
                        return False
                finally:
                    self.process = None
                    self.command_running = False
                    self.show_prompt()

        threading.Thread(target=execute_with_retry, daemon=True).start()

@dataclass
class PackageCategory:
    """Package category definition"""
    name: str
    icon: str
    description: str
    packages: List[str]

# Comprehensive package categories with many more options
PACKAGE_CATEGORIES = [
    PackageCategory("Machine Learning & AI", "🤖", "Machine learning, deep learning, and AI frameworks", 
                   ["tensorflow", "pytorch", "sklearn", "transformers", "huggingface", "opencv-python", 
                    "keras", "xgboost", "lightgbm", "catboost", "mlflow", "wandb", "optuna", "ray",
                    "gymnasium", "stable-baselines3", "tensorboard", "onnx", "torchvision", "torchaudio"]),
    
    PackageCategory("Data Science & Analytics", "📊", "Data analysis, visualization, and processing", 
                   ["pandas", "numpy", "matplotlib", "seaborn", "plotly", "scipy", "statsmodels",
                    "jupyter", "ipython", "notebook", "dask", "polars", "pyarrow", "h5py",
                    "openpyxl", "xlsxwriter", "bokeh", "altair", "streamlit", "dash", "gradio"]),
    
    PackageCategory("Web Development", "🌐", "Web frameworks, APIs, and web tools", 
                   ["django", "flask", "fastapi", "tornado", "pyramid", "bottle", "cherrypy",
                    "requests", "aiohttp", "httpx", "urllib3", "beautifulsoup4", "scrapy",
                    "selenium", "playwright", "lxml", "html5lib", "werkzeug", "jinja2"]),
    
    PackageCategory("GUI & Desktop Development", "🖥️", "Desktop application frameworks and GUI tools", 
                   ["tkinter", "customtkinter", "pyqt5", "pyqt6", "pyside2", "pyside6", "kivy",
                    "kivymd", "wxpython", "flet", "dear-pygui", "arcade", "ursina", "moderngl",
                    "glfw", "imgui", "toga", "beeware"]),
    
    PackageCategory("Animation & Graphics", "🎨", "Animation, 3D graphics, and visual processing", 
                   ["manim", "pygame", "pyglet", "panda3d", "blender", "moderngl", "vispy",
                    "mayavi", "vtk", "open3d", "trimesh", "pyopengl", "arcade", "imageio",
                    "pillow", "wand", "cairo-python", "aggdraw", "skimage"]),
    
    PackageCategory("Scientific Computing", "🔬", "Scientific libraries and numerical computing", 
                   ["numpy", "scipy", "sympy", "networkx", "scikit-image", "astropy", "biopython",
                    "chempy", "mendeleev", "pymc", "stan", "pystan", "emcee", "corner",
                    "uncertainties", "pint", "quantities", "fenics", "firedrake"]),
    
    PackageCategory("Development Tools", "🛠️", "Developer utilities, testing, and code quality", 
                   ["pytest", "unittest", "black", "isort", "flake8", "pylint", "mypy", "bandit",
                    "pre-commit", "tox", "poetry", "pipenv", "setuptools", "wheel", "twine",
                    "coverage", "hypothesis", "faker", "factory-boy", "mock"]),
    
    PackageCategory("System & Networking", "⚙️", "System utilities, networking, and DevOps", 
                   ["psutil", "paramiko", "fabric", "pexpect", "click", "typer", "rich", "textual",
                    "docker", "kubernetes", "ansible", "saltstack", "supervisor", "celery",
                    "redis", "pymongo", "psycopg2", "mysql-connector-python", "sqlalchemy"]),
    
    PackageCategory("Security & Cryptography", "🔒", "Security tools and cryptographic libraries", 
                   ["cryptography", "pycrypto", "bcrypt", "passlib", "oauthlib", "pyjwt",
                    "keyring", "gnupg", "pyotp", "qrcode", "python-decouple", "hashlib",
                    "secrets", "ssl", "certifi", "urllib3"]),
    
    PackageCategory("Audio & Video Processing", "🎵", "Audio and video manipulation libraries", 
                   ["moviepy", "opencv-python", "imageio", "pyaudio", "pydub", "librosa",
                    "ffmpeg-python", "audioread", "soundfile", "wave", "mutagen", "eyed3",
                    "pillow-simd", "av", "decord", "youtube-dl"]),
    
    PackageCategory("Database & ORM", "🗄️", "Database connectors and Object-Relational Mapping", 
                   ["sqlalchemy", "django-orm", "peewee", "tortoise-orm", "databases", "alembic",
                    "psycopg2", "pymongo", "redis", "cassandra-driver", "neo4j", "elasticsearch",
                    "pymysql", "cx-oracle", "pyodbc", "sqlite3"]),
    
    PackageCategory("Cloud & Infrastructure", "☁️", "Cloud services and infrastructure tools", 
                   ["boto3", "azure-storage", "google-cloud", "kubernetes", "docker", "terraform",
                    "pulumi", "cloudformation", "serverless", "zappa", "chalice", "sls",
                    "aws-sam-cli", "azure-cli", "gcloud"]),
    
    PackageCategory("Text Processing & NLP", "📝", "Natural language processing and text analysis", 
                   ["nltk", "spacy", "textblob", "gensim", "transformers", "datasets", "tokenizers",
                    "langchain", "openai", "anthropic", "cohere", "sentence-transformers", "flair",
                    "stanza", "allennlp", "polyglot", "textstat", "pyspellchecker"]),
    
    PackageCategory("Game Development", "🎮", "Game engines and development frameworks", 
                   ["pygame", "arcade", "panda3d", "ursina", "pyglet", "cocos2d", "kivy",
                    "moderngl", "pyopengl", "pybullet", "pymunk", "pybox2d", "noise",
                    "perlin-noise", "python-tcod"]),
    
    PackageCategory("Finance & Trading", "💰", "Financial analysis and trading tools", 
                   ["yfinance", "pandas-datareader", "quantlib", "zipline", "backtrader", "pyfolio",
                    "empyrical", "ta-lib", "finta", "stockstats", "alpha-vantage", "quandl",
                    "ccxt", "freqtrade", "vnpy"]),
    
    PackageCategory("Education & Research", "🎓", "Educational tools and research utilities", 
                   ["jupyter", "nbconvert", "nbformat", "ipywidgets", "voila", "binder",
                    "papermill", "scooby", "sphinx", "mkdocs", "gitpython", "nbstripout",
                    "jupyter-book", "myst-parser", "rise"]),
    
    PackageCategory("IoT & Hardware", "🔌", "Internet of Things and hardware interfaces", 
                   ["raspberry-pi", "adafruit", "circuitpython", "micropython", "pyserial",
                    "pyfirmata", "bleak", "bluepy", "pybluez", "gpiozero", "rpi-gpio",
                    "spidev", "i2c", "smbus", "w1thermsensor"]),
    
    PackageCategory("Image Processing", "🖼️", "Image manipulation and computer vision", 
                   ["pillow", "opencv-python", "scikit-image", "imageio", "wand", "pyqr",
                    "qrcode", "python-barcode", "face-recognition", "dlib", "mediapipe",
                    "albumentations", "imgaug", "kornia", "torchvision"]),
    
    PackageCategory("Utilities & Helpers", "🔧", "General utilities and helper libraries", 
                   ["python-dateutil", "pytz", "arrow", "pendulum", "humanize", "tqdm",
                    "colorama", "termcolor", "click", "argparse", "configparser", "python-dotenv",
                    "pathlib", "shutil", "glob", "fnmatch", "itertools", "functools"]),
]

# Popular packages for quick installation
POPULAR_PACKAGES = [
    # Core Data Science
    "numpy", "pandas", "matplotlib", "seaborn", "scipy", "scikit-learn",
    "jupyter", "ipython", "notebook", "plotly", "bokeh",
    
    # Machine Learning & AI
    "tensorflow", "pytorch", "keras", "transformers", "opencv-python",
    "scikit-image", "pillow", "huggingface-hub", "datasets",
    
    # Web Development
    "django", "flask", "fastapi", "requests", "beautifulsoup4",
    "selenium", "scrapy", "aiohttp", "httpx",
    
    # GUI Development
    "customtkinter", "pyqt5", "kivy", "tkinter", "flet",
    "dear-pygui", "pygame", "arcade",
    
    # Development Tools
    "pytest", "black", "flake8", "mypy", "isort", "poetry",
    "pre-commit", "tox", "coverage", "click", "typer",
    
    # Animation & Graphics
    "manim", "pygame", "pyglet", "panda3d", "moderngl",
    "imageio", "moviepy", "cairo-python",
    
    # Database & Storage
    "sqlalchemy", "pymongo", "redis", "psycopg2", "mysql-connector-python",
    
    # Cloud & APIs
    "boto3", "azure-storage", "google-cloud", "docker", "kubernetes",
    
    # Scientific Computing
    "sympy", "networkx", "astropy", "biopython", "pymc",
    
    # Text Processing
    "nltk", "spacy", "textblob", "gensim", "openai",
    
    # System utilities
    "psutil", "paramiko", "rich", "typer", "click", "celery",
    
    # Security
    "cryptography", "bcrypt", "pyjwt", "oauthlib", "passlib",
    
    # Audio/Video
    "moviepy", "pydub", "librosa", "pyaudio", "ffmpeg-python",
    
    # Finance
    "yfinance", "pandas-datareader", "quantlib", "backtrader",
    
    # IoT
    "pyserial", "adafruit", "gpiozero", "bleak",
    
    # Utilities
    "python-dateutil", "arrow", "tqdm", "colorama", "python-dotenv"
]
class SystemTerminalManager:
    """System Terminal Integration Manager"""
    
    def __init__(self, parent_app):
        self.parent_app = parent_app
        self.cwd = BASE_DIR
        self.env = os.environ.copy()
        self.command_history = []
        self.output_queue = queue.Queue()
        self.process_thread = None
        
        # Load command history
        history_dir = os.path.join(BASE_DIR, "history")
        os.makedirs(history_dir, exist_ok=True)
        self.history_file = os.path.join(history_dir, "terminal_history.txt")
        self.load_history()
        
        # Detect system terminal
        self.detect_system_terminal()

    def safe_after(self, delay, callback=None):
        """Safely schedule a callback on the main Tk loop."""
        try:
            self.parent_app.root.after(delay, callback)
        except RuntimeError:
            pass
    # Essential packages for ManimStudio - Windows-optimized
        self.essential_packages = [
            # Core animation (with specific versions that work on Windows)
            "manim>=0.17.0",
            "numpy>=1.22.0",
            "matplotlib>=3.5.0",
            "scipy>=1.8.0",
            "matplotlib>=3.5.0",  # Ensure matplotlib is compatible
            # Critical dependencies
            "pycairo>=1.20.0",  # Specify minimum working version
            "ManimPango>=0.4.0",  # ManimPango with capital M
            "Cython>=0.29.0",   # Often needed for ManimPango
            
            # Image/Video processing
            "Pillow>=9.0.0",
            "opencv-python>=4.6.0",
            "imageio>=2.19.0",
            "moviepy>=1.0.3",
            "imageio-ffmpeg",
            
            # Development tools
            "jedi>=0.18.0",
            "customtkinter>=5.0.0",
            
            # Additional useful packages
            "requests",
            "rich",
            "tqdm",
            "colour",
            "moderngl",
            "moderngl-window"
        ]
    def detect_system_terminal(self):
        """Detect the best system terminal to use"""
        system = platform.system().lower()
        
        if system == "windows":
            # Windows - prefer PowerShell, fallback to cmd
            if shutil.which("powershell"):
                self.terminal_cmd = ["powershell", "-NoExit", "-Command"]
                self.shell_type = "powershell"
            else:
                self.terminal_cmd = ["cmd", "/k"]
                self.shell_type = "cmd"
        elif system == "darwin":
            # macOS - use Terminal.app
            self.terminal_cmd = ["open", "-a", "Terminal"]
            self.shell_type = "terminal"
        else:
            # Linux - try different terminals
            terminals = ["gnome-terminal", "konsole", "xterm", "terminator"]
            for term in terminals:
                if shutil.which(term):
                    if term == "gnome-terminal":
                        self.terminal_cmd = ["gnome-terminal", "--"]
                    elif term == "konsole":
                        self.terminal_cmd = ["konsole", "-e"]
                    else:
                        self.terminal_cmd = [term, "-e"]
                    self.shell_type = term
                    break
            else:
                # Fallback to xterm
                self.terminal_cmd = ["xterm", "-e"]
                self.shell_type = "xterm"
    
    def load_history(self):
        """Load command history from file"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.command_history = [line.rstrip("\n") for line in f]
        except Exception as e:
            print(f"Error loading history: {e}")
    
    def save_history(self):
        """Save command history to file"""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                for cmd in self.command_history[-100:]:  # Keep last 100 commands
                    f.write(cmd + "\n")
        except Exception as e:
            print(f"Error saving history: {e}")
    
    def open_terminal_here(self):
        """Open system terminal in current working directory"""
        try:
            system = platform.system().lower()
            
            if system == "windows":
                if self.shell_type == "powershell":
                    subprocess.Popen(
                        ["powershell", "-NoExit", "-Command", f"cd '{self.cwd}'"],
                        cwd=self.cwd,
                        env=self.env
                    )
                else:
                    subprocess.Popen(
                        ["cmd", "/k", f"cd /d {self.cwd}"],
                        cwd=self.cwd,
                        env=self.env
                    )
            elif system == "darwin":
                # macOS Terminal.app
                script = f'tell application "Terminal" to do script "cd {self.cwd}"'
                subprocess.Popen(["osascript", "-e", script])
            else:
                # Linux terminals
                if self.shell_type == "gnome-terminal":
                    subprocess.Popen(
                        ["gnome-terminal", "--working-directory", self.cwd],
                        env=self.env
                    )
                elif self.shell_type == "konsole":
                    subprocess.Popen(
                        ["konsole", "--workdir", self.cwd],
                        env=self.env
                    )
                else:
                    subprocess.Popen(
                        [self.shell_type, "-e", "bash"],
                        cwd=self.cwd,
                        env=self.env
                    )
                    
            return True
        except Exception as e:
            print(f"Error opening terminal: {e}")
            return False
    
    def execute_command(self, command, capture_output=True, on_complete=None):
        """Execute command in system terminal with output capture"""
        try:
            self.command_history.append(command)
            self.save_history()
            
            if capture_output:
                # Execute with output capture
                def run_command():
                    try:
                        # Use system's shell to execute command
                        if platform.system().lower() == "windows":
                            shell_cmd = ["cmd", "/c", command]
                        else:
                            shell_cmd = ["bash", "-c", command]
                        
                        process = subprocess.Popen(
                            shell_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            cwd=self.cwd,
                            env=self.env,
                            universal_newlines=True
                        )
                        
                        # Read output line by line
                        output_lines = []
                        for line in process.stdout:
                            output_lines.append(line)
                            # Send to output display
                            if hasattr(self.parent_app, 'append_terminal_output'):
                                self.safe_after(0, lambda l=line: self.parent_app.append_terminal_output(l))
                        
                        process.wait()
                        
                        if on_complete:
                            success = process.returncode == 0
                            self.safe_after(0, lambda: on_complete(success, process.returncode))
                            
                    except Exception as e:
                        error_msg = f"Error executing command: {str(e)}\n"
                        if hasattr(self.parent_app, 'append_terminal_output'):
                            self.safe_after(0, lambda: self.parent_app.append_terminal_output(error_msg))
                        if on_complete:
                            self.safe_after(0, lambda: on_complete(False, -1))
                
                # Run in background thread
                thread = threading.Thread(target=run_command, daemon=True)
                thread.start()
                
            else:
                # Execute without capture (open in new terminal)
                self.execute_in_new_terminal(command)
                
            return True
            
        except Exception as e:
            print(f"Error executing command: {e}")
            return False
    
    def execute_in_new_terminal(self, command):
        """Execute command in a new terminal window"""
        try:
            system = platform.system().lower()
            
            if system == "windows":
                if self.shell_type == "powershell":
                    subprocess.Popen([
                        "powershell", "-NoExit", "-Command", 
                        f"cd '{self.cwd}'; {command}"
                    ])
                else:
                    subprocess.Popen([
                        "cmd", "/k", f"cd /d {self.cwd} && {command}"
                    ])
            elif system == "darwin":
                script = f'''tell application "Terminal"
                    do script "cd {self.cwd} && {command}"
                end tell'''
                subprocess.Popen(["osascript", "-e", script])
            else:
                # Linux
                if self.shell_type == "gnome-terminal":
                    subprocess.Popen([
                        "gnome-terminal", "--working-directory", self.cwd,
                        "--", "bash", "-c", f"{command}; bash"
                    ])
                elif self.shell_type == "konsole":
                    subprocess.Popen([
                        "konsole", "--workdir", self.cwd,
                        "-e", "bash", "-c", f"{command}; bash"
                    ])
                else:
                    subprocess.Popen([
                        self.shell_type, "-e", "bash", "-c", 
                        f"cd {self.cwd} && {command}; bash"
                    ])
                    
        except Exception as e:
            print(f"Error opening new terminal: {e}")
    
    def run_command_redirected(self, command, on_complete=None, env=None):
        """Run command with output redirection (compatibility method)"""
        if env:
            old_env = self.env.copy()
            self.env.update(env)
        
        # Convert command list to string if needed
        if isinstance(command, list):
            command_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command)
        else:
            command_str = command
            
        result = self.execute_command(command_str, capture_output=True, on_complete=on_complete)
        
        if env:
            self.env = old_env
            
        return result
      

class EnvironmentSetupDialog(ctk.CTkToplevel):
    """Professional dialog for setting up the default environment on first run"""
    
    def __init__(self, parent, venv_manager):
        super().__init__(parent)
        
        self.parent_window = parent  # Store reference to parent window
        self.venv_manager = venv_manager
        self.setup_complete = False
        
        self.title("ManimStudio - Environment Setup")
        self.geometry("750x780")
        self.transient(parent)
        self.grab_set()
        
        # Center the dialog
        self.geometry("+%d+%d" % (
            parent.winfo_rootx() + 100,
            parent.winfo_rooty() + 50
        ))
        
        # Prevent closing during setup
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Initialize queue-based logging
        import queue
        self._log_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._start_log_processor()
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the environment setup dialog UI"""
        # Safety check: Ensure VSCODE_COLORS has required keys
        global VSCODE_COLORS
        if "success" not in VSCODE_COLORS:
            VSCODE_COLORS["success"] = "#16A085"
        if "error" not in VSCODE_COLORS:
            VSCODE_COLORS["error"] = "#E74C3C"
        if "warning" not in VSCODE_COLORS:
            VSCODE_COLORS["warning"] = "#F39C12"
        if "surface" not in VSCODE_COLORS:
            VSCODE_COLORS["surface"] = "#252526"
        if "text" not in VSCODE_COLORS:
            VSCODE_COLORS["text"] = "#CCCCCC"
        if "text_secondary" not in VSCODE_COLORS:
            VSCODE_COLORS["text_secondary"] = "#858585"
        # Main frame
        main_frame = ctk.CTkFrame(self, fg_color=VSCODE_COLORS["surface"])
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header with logo
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))
        
        # App icon
        icon_label = ctk.CTkLabel(
            header_frame,
            text="🎬",
            font=ctk.CTkFont(size=48)
        )
        icon_label.pack(pady=10)
        
        # Welcome text
        title_label = ctk.CTkLabel(
            header_frame,
            text="Welcome to ManimStudio!",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        title_label.pack(pady=(0, 10))
        
        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Set up your Python environment for animation creation",
            font=ctk.CTkFont(size=14),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        subtitle_label.pack()
        
        # Package selection frame
        package_frame = ctk.CTkFrame(main_frame)
        package_frame.pack(fill="x", pady=(0, 15))
        
        package_title = ctk.CTkLabel(
            package_frame,
            text="📦 Select Packages to Install",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        package_title.pack(pady=(15, 10))
        
        # Package checkboxes in grid
        checkbox_frame = ctk.CTkFrame(package_frame, fg_color="transparent")
        checkbox_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        # Essential packages (always selected)essential_frame = ctk.CTkFrame(checkbox_frame, fg_color=VSCODE_COLORS["input"])
        essential_frame = ctk.CTkFrame(checkbox_frame, fg_color=VSCODE_COLORS["surface_light"])
        essential_frame.pack(fill="x", pady=(0, 10))
        
        essential_label = ctk.CTkLabel(
            essential_frame,
            text="✅ Essential Packages (Required)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=VSCODE_COLORS["success"]
        )
        essential_label.pack(pady=10)
        
        essential_desc = ctk.CTkLabel(
            essential_frame,
            text="manim, numpy, matplotlib, customtkinter, jedi, pillow",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        essential_desc.pack(pady=(0, 10))
        
        # Optional packages
        optional_packages = {
            "Video Processing": ["opencv-python", "moviepy", "imageio"],
            "Scientific Computing": ["scipy", "sympy"],
            "Audio Processing": ["pydub"],
            "Enhanced Graphics": ["moderngl", "colour"],
            "Utilities": ["requests", "rich", "tqdm"]
        }
        
        self.package_vars = {}
        
        for category, packages in optional_packages.items():
            cat_frame = ctk.CTkFrame(checkbox_frame, fg_color="transparent")
            cat_frame.pack(fill="x", pady=2)
            
            cat_label = ctk.CTkLabel(
                cat_frame,
                text=f"📁 {category}",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=VSCODE_COLORS["text"]
            )
            cat_label.pack(anchor="w")
            
            pkg_grid = ctk.CTkFrame(cat_frame, fg_color="transparent")
            pkg_grid.pack(fill="x", padx=20)
            
            for i, pkg in enumerate(packages):
                var = ctk.BooleanVar(value=True)  # Default to selected
                self.package_vars[pkg] = var
                
                checkbox = ctk.CTkCheckBox(
                    pkg_grid,
                    text=pkg,
                    variable=var,
                    text_color=VSCODE_COLORS["text"],
                    font=ctk.CTkFont(size=12)
                )
                checkbox.grid(row=i//2, column=i%2, sticky="w", padx=10, pady=2)
        
        # CPU Usage setting
        cpu_frame = ctk.CTkFrame(main_frame)
        cpu_frame.pack(fill="x", pady=(0, 15))
        
        cpu_title = ctk.CTkLabel(
            cpu_frame,
            text="⚙️ CPU Usage",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        cpu_title.pack(pady=(15, 10))
        
        self.cpu_var = ctk.StringVar(value="Medium")
        cpu_options = ["Low (1 core)", "Medium (Half cores)", "High (All cores)"]
        
        cpu_menu = ctk.CTkOptionMenu(
            cpu_frame,
            variable=self.cpu_var,
            values=cpu_options,
            font=ctk.CTkFont(size=12)
        )
        cpu_menu.pack(pady=(0, 15))
        
        # Progress section
        progress_frame = ctk.CTkFrame(main_frame)
        progress_frame.pack(fill="x", pady=(0, 15))
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=20)
        self.progress_bar.pack(fill="x", padx=20, pady=(15, 10))
        self.progress_bar.set(0)
        
        # Status labels
        self.step_label = ctk.CTkLabel(
            progress_frame,
            text="Ready to begin setup",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        self.step_label.pack(pady=(0, 5))
        
        self.detail_label = ctk.CTkLabel(
            progress_frame,
            text="Click 'Start Setup' to begin environment configuration",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.detail_label.pack(pady=(0, 15))
        
        # Log frame
        log_frame = ctk.CTkFrame(main_frame)
        log_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        log_title = ctk.CTkLabel(
            log_frame,
            text="📋 Setup Log",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        log_title.pack(pady=(10, 5))
        
        # Log text widget
        self.log_text = ctk.CTkTextbox(
            log_frame,
            height=200,
            font=ctk.CTkFont(size=11, family="Consolas"),
            text_color=VSCODE_COLORS["text"],
            fg_color=VSCODE_COLORS["surface_light"]
        )
        self.log_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Button frame
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(0, 10))
        
        # Start button
        self.start_button = ctk.CTkButton(
            button_frame,
            text="🚀 Start Setup",
            command=self.start_setup,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=VSCODE_COLORS["primary"],
            hover_color=VSCODE_COLORS["primary_hover"]
        )
        self.start_button.pack(side="left")
        
        # Skip button
        self.skip_button = ctk.CTkButton(
            button_frame,
            text="⏭️ Skip",
            command=self.skip_setup,
            height=40,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            border_width=2,
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.skip_button.pack(side="left", padx=(10, 0))
        
        # Continue button (initially disabled)
        self.close_button = ctk.CTkButton(
            button_frame,
            text="✅ Continue",
            command=self.continue_to_app,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=VSCODE_COLORS["primary"],
            state="disabled"
        )
        self.close_button.pack(side="right")
        
    def log_message(self, message):
        """Add message to log"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.update_idletasks()
        
    def log_message_threadsafe(self, message):
        """Thread-safe log message method using queue"""
        if hasattr(self, '_log_queue'):
            self._log_queue.put(message)
    
    def _start_log_processor(self):
        """Start the log processor that runs on main thread"""
        def process_logs():
            if not hasattr(self, '_log_queue'):
                return
                
            try:
                while True:
                    message = self._log_queue.get_nowait()
                    self.log_message(message)
            except:
                pass  # Queue empty
            
            # Schedule next check
            try:
                self.after(100, process_logs)
            except:
                pass  # Widget destroyed
        
        self.after(100, process_logs)
        
    def update_progress(self, value, step_text="", detail_text=""):
        """Update progress bar and status"""
        self.progress_bar.set(value)
        if step_text:
            self.step_label.configure(text=step_text)
        if detail_text:
            self.detail_label.configure(text=detail_text)
        self.update_idletasks()
        
    def start_setup(self):
        """Start the environment setup process"""
        self.start_button.configure(state="disabled")
        self.skip_button.configure(state="disabled")
        
        self.log_message("Starting ManimStudio environment setup...")
        self.update_progress(0.05, "Preparing...", "Initializing environment creation")
        
        # Use the VirtualEnvironmentManager's essential packages instead of UI selection
        selected_packages = self.venv_manager.essential_packages.copy()
        
        self.log_message(f"Installing {len(selected_packages)} essential packages...")
        self.log_message(f"Packages: {', '.join(selected_packages[:5])}{'...' if len(selected_packages) > 5 else ''}")
        
        # Start the setup process on main thread with after() calls
        self.after(100, lambda: self.run_setup_step_by_step(selected_packages, 0))

    def run_setup_step_by_step(self, packages, step):
        """Run setup process step by step on main thread"""
        try:
            if step == 0:
                # Step 1: Create virtual environment
                self.update_progress(0.1, "Creating virtual environment...", "Setting up isolated Python environment")
                self.log_message("Creating virtual environment...")
                
                # Run environment creation in background and schedule next step
                def create_env():
                    success = self.venv_manager.create_virtual_environment()
                    # Use queue to communicate result back to main thread
                    self._result_queue.put(('env_created', success))
                
                threading.Thread(target=create_env, daemon=True).start()
                # Schedule checking for result
                self.after(500, lambda: self.check_for_results(packages, 1))
                
            elif step == 1:
                # Step 2: Activate environment
                self.update_progress(0.2, "Activating environment...", "Configuring environment")
                self.log_message("Activating environment...")
                self.after(500, lambda: self.run_setup_step_by_step(packages, 2))
                
            elif step == 2:
                # Step 3: Upgrade pip
                self.update_progress(0.25, "Upgrading pip...", "Ensuring latest package manager")
                self.log_message("Upgrading pip...")
                
                def upgrade_pip():
                    success = self.venv_manager.upgrade_pip_in_existing_env(self.log_message_threadsafe)
                    if not success:
                        self.log_message_threadsafe("WARNING: Could not upgrade pip")
                    # Use queue to communicate result back to main thread
                    self._result_queue.put(('pip_upgraded', True))
                
                threading.Thread(target=upgrade_pip, daemon=True).start()
                # Schedule checking for result
                self.after(500, lambda: self.check_for_results(packages, 3))
                
            elif step == 3:
                # Step 4: Install packages using VirtualEnvironmentManager's method
                self.update_progress(0.3, "Installing packages...", "Installing essential packages")
                self.log_message("Installing essential packages...")
                
                def install_packages():
                    # Use the VirtualEnvironmentManager's install_all_packages method
                    success = self.venv_manager.install_all_packages(self.log_message_threadsafe)
                    # Use queue to communicate result back to main thread
                    self._result_queue.put(('packages_installed', success))
                
                threading.Thread(target=install_packages, daemon=True).start()
                # Schedule checking for result
                self.after(500, lambda: self.check_for_results(packages, 4))
                    
            elif step == 5:
                # Step 5: Verify installation
                self.update_progress(0.95, "Verifying installation...", "Testing all components")
                self.log_message("Verifying installation...")
                
                def verify():
                    success = self.venv_manager.verify_complete_installation(self.log_message_threadsafe)
                    # Use queue to communicate result back to main thread
                    self._result_queue.put(('verification_done', success))
                
                threading.Thread(target=verify, daemon=True).start()
                # Schedule checking for result
                self.after(500, lambda: self.check_for_results(packages, 5))
                
            elif step == 6:
                # Success
                self.update_progress(1.0, "Setup complete!", "All components ready")
                self.log_message("✅ Environment setup completed successfully!")
                self.setup_complete_ui()
                
            elif step == 7:
                # Verification failed but continue
                self.log_message("WARNING: Installation verification failed")
                self.show_warning("Setup completed with warnings")
                
            elif step == -1:
                # Error occurred
                self.log_message("ERROR: Failed to create virtual environment")
                self.show_error("Failed to create virtual environment")
                
        except Exception as e:
            error_msg = f"Setup failed with error: {str(e)}"
            self.log_message(f"ERROR: {error_msg}")
            self.show_error(error_msg)

    
    def check_for_results(self, packages, next_step):
        """Check for results from background threads"""
        try:
            action, result = self._result_queue.get_nowait()
            
            if action == 'env_created':
                self.run_setup_step_by_step(packages, next_step if result else -1)
            elif action == 'pip_upgraded':
                self.run_setup_step_by_step(packages, next_step)
            elif action == 'packages_installed':
                self.run_setup_step_by_step(packages, 5 if result else 7)  # Go to verification
            elif action == 'verification_done':
                self.run_setup_step_by_step(packages, 6 if result else 7)
                
        except:
            # No result yet, check again later
            self.after(500, lambda: self.check_for_results(packages, next_step))

    def check_for_package_results(self, packages, current_package_index):
        """Check for package installation results"""
        try:
            action, result = self._result_queue.get_nowait()
            
            if action == 'package_installed':
                self.install_packages_step_by_step(packages, result)
                
        except:
            # No result yet, check again later
            self.after(500, lambda: self.check_for_package_results(packages, current_package_index))
        
    def setup_complete_ui(self):
        """Update UI when setup is complete"""
        self.setup_complete = True
        self.progress_bar.set(1.0)
        self.step_label.configure(text="✅ Setup Complete!")
        self.detail_label.configure(text="Environment is ready to use")
        
        # Enable the continue button
        self.close_button.configure(state="normal", text="✅ Continue to App")
        
        # Update button colors to indicate success
        self.close_button.configure(
            fg_color="#28a745",  # Green color for success
            hover_color="#218838"
        )
        
    def skip_setup(self):
        """Skip environment setup"""
        from tkinter import messagebox
        if messagebox.askyesno(
            "Skip Setup",
            "Are you sure you want to skip environment setup?\n\n"
            "You can set up the environment later from the Tools menu.",
            parent=self
        ):
            self.venv_manager.needs_setup = False
            # Ensure main window is shown before destroying dialog
            if hasattr(self, 'parent_window') and self.parent_window:
                self.parent_window.after(10, lambda: self.parent_window.deiconify())
            self.destroy()
            
    def continue_to_app(self):
        """Continue to main application"""
        if self.setup_complete:
            self.venv_manager.needs_setup = False
            # Ensure main window is shown before destroying dialog
            if hasattr(self, 'parent_window') and self.parent_window:
                self.parent_window.after(10, lambda: self.parent_window.deiconify())
            self.destroy()
        else:
            from tkinter import messagebox
            messagebox.showwarning(
                "Setup Not Complete",
                "Please complete the environment setup first, or skip setup to continue.",
                parent=self
            )

    def on_closing(self):
        """Handle application closing"""
        try:
            if hasattr(self, 'logger'):
                self.logger.info("Application closing...")
            
            # Stop any running processes
            self.stop_process()
            
            # Save settings
            self.save_settings()
            
            # Destroy the window
            if self.root and self.root.winfo_exists():
                self.root.quit()
                self.root.destroy()
                
        except Exception as e:
            # Ignore errors during shutdown
            pass
        
    def show_error(self, message):
        """Show error message"""
        from tkinter import messagebox
        messagebox.showerror("Setup Error", message, parent=self)
        self.start_button.configure(state="normal")
        self.skip_button.configure(state="normal")
            
    def show_warning(self, message):
        """Show warning message"""
        from tkinter import messagebox
        messagebox.showwarning("Setup Warning", message, parent=self)
        self.setup_complete_ui()
class EnhancedVenvManagerDialog(ctk.CTkToplevel):
    """Enhanced dialog for manual virtual environment management"""
    
    def __init__(self, parent, venv_manager):
        super().__init__(parent)

        self.parent = parent
        self.venv_manager = venv_manager
        self.package_queue = queue.Queue()
        self.title("Virtual Environment Manager")
        
        # Dynamic sizing so dialog fits on smaller screens
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(900, screen_w - 100)
        height = min(800, screen_h - 100)
        self.geometry(f"{width}x{height}")
        self.minsize(min(850, width), min(700, height))
        self.resizable(True, True)
        
        self.transient(parent)
        self.grab_set()
        
        # FIXED: Better centering on parent window
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        
        x = parent_x + (parent_width - 900) // 2
        y = parent_y + (parent_height - 700) // 2
        
        self.geometry(f"+{x}+{y}")
        
        self.create_ui()
        self.load_environments()
        
    def create_ui(self):
        """Create the enhanced UI with manual controls"""
        self.columnconfigure(0, weight=0)  # Left panel
        self.columnconfigure(1, weight=1)  # Right panel
        self.rowconfigure(0, weight=1)
        
        # Left panel - Environment list
        left_panel = ctk.CTkFrame(self, width=250, corner_radius=0)
        left_panel.grid(row=0, column=0, sticky="nsew")
        left_panel.grid_propagate(False)
        
        # Environments header
        env_header = ctk.CTkFrame(left_panel, height=50, fg_color=VSCODE_COLORS["surface_light"])
        env_header.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            env_header, 
            text="Python Environments",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left", padx=15, pady=15)
        
        # Environment list with scrollbar
        list_frame = ctk.CTkFrame(left_panel)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.env_listbox = tk.Listbox(
            list_frame,
            bg=VSCODE_COLORS["surface"],
            fg=VSCODE_COLORS["text"],
            selectbackground=VSCODE_COLORS["primary"],
            selectforeground=VSCODE_COLORS["text_bright"],
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 11)
        )
        self.env_listbox.pack(side="left", fill="both", expand=True)
        self.env_listbox.bind("<<ListboxSelect>>", self.on_env_select)
        
        scrollbar = ctk.CTkScrollbar(list_frame, command=self.env_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.env_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Action buttons
        btn_frame = ctk.CTkFrame(left_panel)
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(
            btn_frame,
            text="Create New",
            command=self.create_new_env,
            height=32
        ).pack(side="left", padx=5, fill="x", expand=True)
        
        ctk.CTkButton(
            btn_frame,
            text="Refresh",
            command=self.load_environments,
            height=32
        ).pack(side="right", padx=5, fill="x", expand=True)
        
        # Right panel - Environment details and actions
        right_panel = ctk.CTkFrame(self)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 0))
        
        # Details header
        self.details_header = ctk.CTkFrame(right_panel, height=50, fg_color=VSCODE_COLORS["surface_light"])
        self.details_header.pack(fill="x")
        
        self.header_label = ctk.CTkLabel(
            self.details_header,
            text="Environment Details",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.header_label.pack(side="left", padx=20, pady=15)
        
        # Main content area
        self.content_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=30, pady=20)
        
        # Environment info section
        self.info_frame = ctk.CTkFrame(self.content_frame, fg_color=VSCODE_COLORS["surface_light"])
        self.info_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            self.info_frame,
            text="Environment Information",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Info grid
        info_grid = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        info_grid.pack(fill="x", padx=15, pady=(0, 15))
        info_grid.columnconfigure(1, weight=1)
        
        # Row 1: Path
        ctk.CTkLabel(
            info_grid, 
            text="Path:",
            font=ctk.CTkFont(weight="bold"),
            width=100
        ).grid(row=0, column=0, sticky="w", pady=3)
        
        self.path_label = ctk.CTkLabel(info_grid, text="")
        self.path_label.grid(row=0, column=1, sticky="w", pady=3)
        
        # Row 2: Python Version
        ctk.CTkLabel(
            info_grid, 
            text="Python:",
            font=ctk.CTkFont(weight="bold"),
            width=100
        ).grid(row=1, column=0, sticky="w", pady=3)
        
        self.python_label = ctk.CTkLabel(info_grid, text="")
        self.python_label.grid(row=1, column=1, sticky="w", pady=3)
        
        # Row 3: Packages
        ctk.CTkLabel(
            info_grid, 
            text="Packages:",
            font=ctk.CTkFont(weight="bold"),
            width=100
        ).grid(row=2, column=0, sticky="w", pady=3)
        
        self.packages_label = ctk.CTkLabel(info_grid, text="")
        self.packages_label.grid(row=2, column=1, sticky="w", pady=3)
        
        # Row 4: Size
        ctk.CTkLabel(
            info_grid, 
            text="Size:",
            font=ctk.CTkFont(weight="bold"),
            width=100
        ).grid(row=3, column=0, sticky="w", pady=3)
        
        self.size_label = ctk.CTkLabel(info_grid, text="")
        self.size_label.grid(row=3, column=1, sticky="w", pady=3)
        
        # Row 5: Status
        ctk.CTkLabel(
            info_grid, 
            text="Status:",
            font=ctk.CTkFont(weight="bold"),
            width=100
        ).grid(row=4, column=0, sticky="w", pady=3)
        
        self.status_label = ctk.CTkLabel(info_grid, text="")
        self.status_label.grid(row=4, column=1, sticky="w", pady=3)
        
        # Package management section
        self.package_frame = ctk.CTkFrame(self.content_frame, fg_color=VSCODE_COLORS["surface_light"])
        self.package_frame.pack(fill="both", expand=True)
        
        ctk.CTkLabel(
            self.package_frame,
            text="Package Management",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Package action buttons
        pkg_action_frame = ctk.CTkFrame(self.package_frame, fg_color="transparent")
        pkg_action_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        self.pkg_entry = ctk.CTkEntry(
            pkg_action_frame, 
            placeholder_text="Package name (e.g., numpy==1.21.0)",
            height=35
        )
        self.pkg_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.install_btn = ctk.CTkButton(
            pkg_action_frame,
            text="Install",
            command=self.install_package,
            width=100,
            height=35,
            fg_color=VSCODE_COLORS["success"]
        )
        self.install_btn.pack(side="left", padx=(0, 5))
        
        self.uninstall_btn = ctk.CTkButton(
            pkg_action_frame,
            text="Uninstall",
            command=self.uninstall_package,
            width=100,
            height=35,
            fg_color=VSCODE_COLORS["error"]
        )
        self.uninstall_btn.pack(side="left")

        self.verify_btn = ctk.CTkButton(
            pkg_action_frame,
            text="Verify Packages",
            command=self.verify_packages,
            width=130,
            height=35,
            fg_color=VSCODE_COLORS["primary"]
        )
        self.verify_btn.pack(side="left", padx=(5, 0))
        
        # Package list
        pkg_list_frame = ctk.CTkFrame(self.package_frame, fg_color="transparent")
        pkg_list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Package list with scrollbar
        self.pkg_listbox = tk.Listbox(
            pkg_list_frame,
            bg=VSCODE_COLORS["background"],
            fg=VSCODE_COLORS["text"],
            selectbackground=VSCODE_COLORS["selection"],
            selectforeground=VSCODE_COLORS["text_bright"],
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10)
        )
        self.pkg_listbox.pack(side="left", fill="both", expand=True)
        
        pkg_scrollbar = ctk.CTkScrollbar(pkg_list_frame, command=self.pkg_listbox.yview)
        pkg_scrollbar.pack(side="right", fill="y")
        self.pkg_listbox.configure(yscrollcommand=pkg_scrollbar.set)
        
        # Bottom buttons - FIXED: Made more visible with increased height and better positioning
        btn_bottom_frame = ctk.CTkFrame(right_panel, height=70, fg_color=VSCODE_COLORS["surface"])
        btn_bottom_frame.pack(fill="x")
        
        self.activate_btn = ctk.CTkButton(
            btn_bottom_frame,
            text="Activate Environment",
            command=self.activate_environment,
            height=40,  # Increased height
            width=180,
            fg_color=VSCODE_COLORS["primary"]
        )
        self.activate_btn.pack(side="left", padx=20, pady=15)  # Increased padding
        
        self.delete_btn = ctk.CTkButton(
            btn_bottom_frame,
            text="Delete Environment",
            command=self.delete_environment,
            height=40,  # Increased height
            width=150,
            fg_color=VSCODE_COLORS["error"]
        )
        self.delete_btn.pack(side="left", padx=5, pady=15)  # Increased padding
        
        ctk.CTkButton(
            btn_bottom_frame,
            text="Close",
            command=self.destroy,
            height=40,  # Increased height
            width=100
        ).pack(side="right", padx=20, pady=15)  # Increased padding
        
        # Initially disable environment-specific buttons
        self.set_controls_state("disabled")
        
    def load_environments(self):
        """Load all available environments"""
        # Clear listbox
        self.env_listbox.delete(0, tk.END)
        
        # Get environments
        environments = self.venv_manager.list_venvs()
        
        # Add to listbox
        for env in environments:
            # Mark active environment
            display_name = env
            if env == self.venv_manager.current_venv:
                display_name = f"✓ {env} (Active)"
                
            self.env_listbox.insert(tk.END, display_name)
            
        # Select active environment if available
        if self.venv_manager.current_venv in environments:
            index = environments.index(self.venv_manager.current_venv)
            self.env_listbox.selection_set(index)
            self.env_listbox.see(index)
            self.on_env_select()
        
    def on_env_select(self, event=None):
        """Handle environment selection"""
        # Get selected environment
        selection = self.env_listbox.curselection()
        if not selection:
            self.clear_env_details()
            return
            
        # Get environment name
        env_name = self.env_listbox.get(selection[0])
        if " (Active)" in env_name:
            env_name = env_name.split(" (Active)")[0][2:]  # Remove checkmark and (Active)
        else:
            env_name = env_name
            
        # Update header
        self.header_label.configure(text=f"Environment: {env_name}")
        
        # Get environment info
        env_info = self.venv_manager.get_venv_info(env_name)
        
        # Update info display
        self.path_label.configure(text=env_info['path'])
        self.python_label.configure(text=env_info['python_version'] or "Unknown")
        self.packages_label.configure(text=f"{env_info['packages_count']} packages")
        
        # Format size
        size_mb = env_info['size'] / (1024 * 1024)
        if size_mb > 1000:
            size_str = f"{size_mb/1024:.1f} GB"
        else:
            size_str = f"{size_mb:.1f} MB"
        self.size_label.configure(text=size_str)
        
        # Status
        status = "Active" if env_info['is_active'] else "Inactive"
        self.status_label.configure(
            text=status,
            text_color=VSCODE_COLORS["success"] if env_info['is_active'] else VSCODE_COLORS["text_secondary"]
        )
        
        # Enable controls
        self.set_controls_state("normal")
        
        # Update activate button
        if env_info['is_active']:
            self.activate_btn.configure(
                text="✓ Currently Active",
                state="disabled"
            )
        else:
            self.activate_btn.configure(
                text="Activate Environment",
                state="normal"
            )
            
        # Load packages
        self.load_packages(env_name)
        
    def load_packages(self, env_name):
        """Load packages for the selected environment"""
        # Clear package listbox
        self.pkg_listbox.delete(0, tk.END)
        
        # Add "Loading..." indicator
        self.pkg_listbox.insert(tk.END, "Loading packages...")
        
        # Get packages in background thread
        def get_packages_thread():
            success, result = self.venv_manager.list_packages()
            if success:
                self.package_queue.put((True, result, None))
            else:
                self.package_queue.put((False, [], result))

        threading.Thread(target=get_packages_thread, daemon=True).start()
        self.after(100, self.check_packages_queue)

    def check_packages_queue(self):
        try:
            success, packages, error = self.package_queue.get_nowait()
        except queue.Empty:
            self.after(100, self.check_packages_queue)
            return
        self.on_packages_loaded(success, packages, error)
        
    def on_packages_loaded(self, success, packages, error):
        """Handle package list loading"""
        # Clear package listbox
        self.pkg_listbox.delete(0, tk.END)
        
        if not success:
            self.pkg_listbox.insert(tk.END, f"Error: {error}")
            return
            
        # Sort packages by name
        packages.sort(key=lambda p: p['name'].lower())
        
        # Add packages to listbox
        for package in packages:
            self.pkg_listbox.insert(tk.END, f"{package['name']} ({package['version']})")
            
        # Add info line
        self.pkg_listbox.insert(tk.END, f"Total: {len(packages)} packages")
        
    def clear_env_details(self):
        """Clear environment details"""
        self.header_label.configure(text="Environment Details")
        self.path_label.configure(text="")
        self.python_label.configure(text="")
        self.packages_label.configure(text="")
        self.size_label.configure(text="")
        self.status_label.configure(text="")
        self.pkg_listbox.delete(0, tk.END)
        
        # Disable controls
        self.set_controls_state("disabled")
        
    def set_controls_state(self, state):
        """Set state of all controls"""
        self.activate_btn.configure(state=state)
        self.delete_btn.configure(state=state)
        self.install_btn.configure(state=state)
        self.uninstall_btn.configure(state=state)
        self.verify_btn.configure(state=state)
        self.pkg_entry.configure(state=state)
        
    def create_new_env(self):
        """Create a new environment"""
        # Show dialog
        dialog = NewEnvironmentDialog(self, self.venv_manager)
        self.wait_window(dialog)
        
        # Reload environments
        self.load_environments()
        
    def activate_environment(self):
        """Activate the selected environment"""
        # Get selected environment
        selection = self.env_listbox.curselection()
        if not selection:
            return
            
        # Get environment name
        env_name = self.env_listbox.get(selection[0])
        if " (Active)" in env_name:
            env_name = env_name.split(" (Active)")[0][2:]
            
        # Activate environment
        success = self.venv_manager.activate_venv(env_name)
        
        if success:
            # Show success message
            messagebox.showinfo(
                "Environment Activated",
                f"Environment '{env_name}' activated successfully.",
                parent=self
            )
            
            # Reload environments
            self.load_environments()
        else:
            messagebox.showerror(
                "Activation Failed",
                f"Failed to activate environment '{env_name}'.",
                parent=self
            )
            
    def delete_environment(self):
        """Delete the selected environment"""
        # Get selected environment
        selection = self.env_listbox.curselection()
        if not selection:
            return
            
        # Get environment name
        env_name = self.env_listbox.get(selection[0])
        if " (Active)" in env_name:
            env_name = env_name.split(" (Active)")[0][2:]
            
        # Confirm deletion
        if not messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete environment '{env_name}'?\n\n"
            "This action cannot be undone.",
            icon="warning",
            parent=self
        ):
            return
            
        # Check if environment is active
        if env_name == self.venv_manager.current_venv:
            messagebox.showerror(
                "Cannot Delete Active Environment",
                "You cannot delete the currently active environment.\n"
                "Please activate a different environment first.",
                parent=self
            )
            return
            
        # Delete environment
        try:
            # Get environment path
            env_info = self.venv_manager.get_venv_info(env_name)
            env_path = env_info['path']
            
            # Delete directory
            shutil.rmtree(env_path)
            
            # Show success message
            messagebox.showinfo(
                "Environment Deleted",
                f"Environment '{env_name}' deleted successfully.",
                parent=self
            )
            
            # Reload environments
            self.load_environments()
            
        except Exception as e:
            messagebox.showerror(
                "Deletion Failed",
                f"Failed to delete environment '{env_name}':\n{str(e)}",
                parent=self
            )
            
    def install_package(self):
        """Install a package in the selected environment"""
        # Get package name
        package_name = self.pkg_entry.get().strip()
        if not package_name:
            messagebox.showwarning(
                "Package Name Required",
                "Please enter a package name to install.",
                parent=self
            )
            return
            
        # Get selected environment
        selection = self.env_listbox.curselection()
        if not selection:
            return
            
        # Get environment name
        env_name = self.env_listbox.get(selection[0])
        if " (Active)" in env_name:
            env_name = env_name.split(" (Active)")[0][2:]
            
        # Show confirmation
        if not messagebox.askyesno(
            "Confirm Installation",
            f"Install package '{package_name}' in environment '{env_name}'?",
            parent=self
        ):
            return
            
        # Disable controls during installation
        self.install_btn.configure(text="Installing...", state="disabled")
        self.pkg_entry.configure(state="disabled")
        
        # Install package
        def on_install_complete(success, stdout, stderr):
            self.install_btn.configure(text="Install", state="normal")
            self.pkg_entry.configure(state="normal")
            
            if success:
                messagebox.showinfo(
                    "Installation Complete",
                    f"Package '{package_name}' installed successfully.",
                    parent=self
                )
                self.pkg_entry.delete(0, tk.END)
                self.load_packages(env_name)
            else:
                messagebox.showerror(
                    "Installation Failed",
                    f"Failed to install package '{package_name}':\n{stderr}",
                    parent=self
                )
        
        # Start installation
        self.venv_manager.install_package(package_name, on_install_complete)
        
    def uninstall_package(self):
        """Uninstall a package from the selected environment"""
        # Get selected package
        selection = self.pkg_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "No Package Selected",
                "Please select a package to uninstall.",
                parent=self
            )
            return
            
        # Get package name
        package_info = self.pkg_listbox.get(selection[0])
        if "Total:" in package_info:
            return
            
        package_name = package_info.split(" (")[0]
        
        # Get selected environment
        env_selection = self.env_listbox.curselection()
        if not env_selection:
            return
            
        # Get environment name
        env_name = self.env_listbox.get(env_selection[0])
        if " (Active)" in env_name:
            env_name = env_name.split(" (Active)")[0][2:]
            
        # Show confirmation
        if not messagebox.askyesno(
            "Confirm Uninstallation",
            f"Uninstall package '{package_name}' from environment '{env_name}'?\n\n"
            "This may break dependencies in your environment.",
            icon="warning",
            parent=self
        ):
            return
            
        # Disable controls during uninstallation
        self.uninstall_btn.configure(text="Uninstalling...", state="disabled")
        
        # Uninstall package
        def on_uninstall_complete(success, stdout, stderr):
            self.uninstall_btn.configure(text="Uninstall", state="normal")
            
            if success:
                messagebox.showinfo(
                    "Uninstallation Complete",
                    f"Package '{package_name}' uninstalled successfully.",
                    parent=self
                )
                self.load_packages(env_name)
            else:
                messagebox.showerror(
                    "Uninstallation Failed",
                    f"Failed to uninstall package '{package_name}':\n{stderr}",
                    parent=self
                )
        
        # Start uninstallation
        self.venv_manager.uninstall_package(package_name, on_uninstall_complete)

    def verify_packages(self):
        """Verify essential packages in the selected environment"""
        selection = self.env_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "No Environment Selected",
                "Please select an environment to verify.",
                parent=self
            )
            return

        env_name = self.env_listbox.get(selection[0])
        if " (Active)" in env_name:
            env_name = env_name.split(" (Active)")[0][2:]

        env_info = self.venv_manager.get_venv_info(env_name)
        env_path = env_info["path"]

        self.verify_btn.configure(text="Verifying...", state="disabled")

        def run_verify():
            success = self.venv_manager.verify_environment_packages(env_path)
            msg = (
                f"Packages verified for {env_name}" if success else
                f"Package verification failed for {env_name}"
            )
            log_widget = getattr(
                self.venv_manager.parent_app, "log_display", None
            )
            if log_widget:
                log_widget.insert("end", msg + "\n")
                log_widget.see("end")
            if success:
                messagebox.showinfo("Verification Complete", msg, parent=self)
            else:
                messagebox.showerror("Verification Failed", msg, parent=self)
            self.verify_btn.configure(text="Verify Packages", state="normal")

        threading.Thread(target=run_verify, daemon=True).start()
        
class NewEnvironmentDialog(ctk.CTkToplevel):
    """Dialog for creating a new environment"""
    
    def __init__(self, parent, venv_manager):
        super().__init__(parent)
        
        self.parent = parent
        self.venv_manager = venv_manager
        
        self.title("Create New Environment")

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(600, screen_w - 100)
        height = min(700, screen_h - 100)
        self.geometry(f"{width}x{height}")
        self.minsize(500, 500)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        
        # Center the dialog
        self.geometry("+%d+%d" % (
            parent.winfo_rootx() + 150,
            parent.winfo_rooty() + 100
        ))
        
        self.create_ui()
        
    def create_ui(self):
        """Create dialog UI"""
        # Main frame
        main_frame = ctk.CTkFrame(self, fg_color=VSCODE_COLORS["surface"])
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        ctk.CTkLabel(
            main_frame,
            text="Create New Virtual Environment",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(0, 20))
        
        # Environment settings
        settings_frame = ctk.CTkFrame(main_frame, fg_color=VSCODE_COLORS["surface_light"])
        settings_frame.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(
            settings_frame,
            text="Environment Settings",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Environment name
        name_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        name_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        ctk.CTkLabel(
            name_frame,
            text="Name:",
            width=100
        ).pack(side="left")
        
        self.name_entry = ctk.CTkEntry(
            name_frame,
            placeholder_text="e.g., manim_project"
        )
        self.name_entry.pack(side="left", fill="x", expand=True)
        
        # Python interpreter (if multiple are available)
        python_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        python_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        ctk.CTkLabel(
            python_frame,
            text="Python:",
            width=100
        ).pack(side="left")
        
        self.python_var = ctk.StringVar(value=sys.executable)
        
        # Python interpreters dropdown
        interpreters = self.find_python_interpreters()
        self.python_dropdown = ctk.CTkComboBox(
            python_frame,
            values=interpreters,
            variable=self.python_var,
            state="readonly"
        )
        self.python_dropdown.pack(side="left", fill="x", expand=True)
        
        # Location option
        location_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        location_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkLabel(
            location_frame,
            text="Location:",
            width=100
        ).pack(side="left")
        
        # Default location under the user's application directory
        default_location = self.venv_manager.venv_dir
        self.location_var = ctk.StringVar(value=default_location)
        
        location_entry = ctk.CTkEntry(
            location_frame,
            textvariable=self.location_var,
            state="readonly"
        )
        location_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        browse_btn = ctk.CTkButton(
            location_frame,
            text="...",
            width=30,
            command=self.browse_location
        )
        browse_btn.pack(side="left")
        
        # Package selection
        packages_frame = ctk.CTkFrame(main_frame, fg_color=VSCODE_COLORS["surface_light"])
        packages_frame.pack(fill="both", expand=True, pady=(0, 20))
        
        ctk.CTkLabel(
            packages_frame,
            text="Select Packages to Install",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Essential packages
        essential_frame = ctk.CTkFrame(packages_frame, fg_color="transparent")
        essential_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        self.essential_var = ctk.BooleanVar(value=True)
        essential_check = ctk.CTkCheckBox(
            essential_frame,
            text="Essential Packages",
            variable=self.essential_var,
            onvalue=True,
            offvalue=False
        )
        essential_check.pack(anchor="w")
        
        ctk.CTkLabel(
            essential_frame,
            text="(manim, numpy, matplotlib, jedi, etc.)",
            font=ctk.CTkFont(size=10),
            text_color=VSCODE_COLORS["text_secondary"]
        ).pack(anchor="w", padx=(25, 0))
        
        # Common packages - create scrollable area
        pkg_scroll = ctk.CTkScrollableFrame(
            packages_frame,
            label_text="Additional Packages",
            fg_color="transparent"
        )
        pkg_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Common packages
        common_packages = [
            ("PIL", "Image processing"),
            ("opencv-python", "Computer vision"),
            ("scipy", "Scientific computing"),
            ("ipython", "Enhanced interactive console"),
            ("pandas", "Data analysis"),
            ("seaborn", "Statistical visualization"),
            ("sympy", "Symbolic mathematics"),
            ("jupyter", "Interactive notebooks"),
            ("tqdm", "Progress bars")
        ]
        
        self.package_vars = {}
        for pkg, desc in common_packages:
            var = ctk.BooleanVar(value=False)
            self.package_vars[pkg] = var
            
            pkg_frame = ctk.CTkFrame(pkg_scroll, fg_color="transparent")
            pkg_frame.pack(fill="x", pady=2)
            
            check = ctk.CTkCheckBox(
                pkg_frame,
                text=pkg,
                variable=var,
                onvalue=True,
                offvalue=False
            )
            check.pack(side="left")
            
            ctk.CTkLabel(
                pkg_frame,
                text=f"({desc})",
                font=ctk.CTkFont(size=10),
                text_color=VSCODE_COLORS["text_secondary"]
            ).pack(side="left", padx=(10, 0))
            
        # Custom package
        custom_frame = ctk.CTkFrame(packages_frame, fg_color="transparent")
        custom_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkLabel(
            custom_frame,
            text="Custom Packages:"
        ).pack(anchor="w", pady=(0, 5))
        
        self.custom_packages = ctk.CTkTextbox(
            custom_frame,
            height=60,
            font=ctk.CTkFont(size=12)
        )
        self.custom_packages.pack(fill="x")
        
        ctk.CTkLabel(
            custom_frame,
            text="Enter package names, one per line. You can include version specifiers (e.g., numpy==1.21.0)",
            font=ctk.CTkFont(size=10),
            text_color=VSCODE_COLORS["text_secondary"],
            wraplength=400
        ).pack(anchor="w", pady=(5, 0))
        
        # Buttons
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 0))
        
        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            command=self.destroy,
            width=100
        ).pack(side="left")
        
        ctk.CTkButton(
            btn_frame,
            text="Create Environment",
            command=self.create_environment,
            width=150,
            fg_color=VSCODE_COLORS["success"]
        ).pack(side="right")
        
    def find_python_interpreters(self):
        """Find available Python interpreters"""
        interpreters = [sys.executable]
        
        # Try to find other Python installations
        if sys.platform == "win32":
            # Check common Python installation paths on Windows
            common_paths = [
                os.path.join(os.environ.get("ProgramFiles", ""), "Python*"),
                os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Python*"),
                os.path.join(os.environ.get("LocalAppData", ""), "Programs", "Python", "Python*")
            ]
            
            for path_pattern in common_paths:
                for path in glob.glob(path_pattern):
                    python_exe = os.path.join(path, "python.exe")
                    if os.path.exists(python_exe) and python_exe not in interpreters:
                        interpreters.append(python_exe)
        else:
            # On Unix, check PATH for python executables
            for path in os.environ.get("PATH", "").split(os.pathsep):
                for name in ["python3", "python"]:
                    python_exe = os.path.join(path, name)
                    if os.path.exists(python_exe) and os.access(python_exe, os.X_OK) and python_exe not in interpreters:
                        interpreters.append(python_exe)
                        
        return interpreters
        
    def browse_location(self):
        """Browse for environment location"""
        location = filedialog.askdirectory(
            title="Select Environment Location",
            initialdir=self.location_var.get()
        )
        
        if location:
            self.location_var.set(location)
            
    def create_environment(self):
        """Create the new environment"""
        # Get settings
        name = self.name_entry.get().strip()
        location = self.location_var.get()
        python_exe = self.python_var.get()
        
        # Validate name
        if not name:
            messagebox.showerror(
                "Invalid Name",
                "Please enter a name for the environment.",
                parent=self
            )
            return
            
        # Check if name contains invalid characters
        if not re.match(r'^[a-zA-Z0-9_.-]+$', name):
            messagebox.showerror(
                "Invalid Name",
                "Environment name can only contain letters, numbers, underscores, dots, and hyphens.",
                parent=self
            )
            return
            
        # Check if environment already exists
        env_path = os.path.join(location, name)
        if os.path.exists(env_path):
            if not messagebox.askyesno(
                "Environment Exists",
                f"An environment with the name '{name}' already exists.\n"
                "Do you want to remove it and create a new one?",
                icon="warning",
                parent=self
            ):
                return
                
            # Remove existing environment
            try:
                shutil.rmtree(env_path)
            except Exception as e:
                messagebox.showerror(
                    "Removal Failed",
                    f"Failed to remove existing environment:\n{str(e)}",
                    parent=self
                )
                return
                
        # Create progress dialog
        progress_dialog = EnvCreationProgressDialog(self, name, location, python_exe, self.get_packages())
        self.wait_window(progress_dialog)
        
        # Close dialog
        self.destroy()
        
    def get_packages(self):
        """Get selected packages"""
        packages = []
        
        # Add essential packages
        if self.essential_var.get():
            packages.extend([
                "manim",
                "numpy",
                "matplotlib",
                "jedi",
                "customtkinter",
                "pillow"
            ])
            
        # Add selected common packages
        for pkg, var in self.package_vars.items():
            if var.get():
                packages.append(pkg)
                
        # Add custom packages
        custom = self.custom_packages.get("1.0", tk.END).strip()
        if custom:
            for line in custom.split("\n"):
                line = line.strip()
                if line:
                    packages.append(line)
                    
        return packages

class EnvCreationProgressDialog(ctk.CTkToplevel):
    """Dialog showing environment creation progress"""
    
    def __init__(self, parent, env_name, location, python_exe, packages):
        super().__init__(parent)
        
        self.parent = parent
        self.env_name = env_name
        self.location = location
        self.python_exe = python_exe
        self.packages = packages
        
        self.title("Creating Environment")

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(500, screen_w - 100)
        height = min(900, screen_h - 100)
        self.geometry(f"{width}x{height}")
        self.minsize(450, 400)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        
        # Prevent closing
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Center the dialog
        self.geometry("+%d+%d" % (
            parent.winfo_rootx() + 150,
            parent.winfo_rooty() + 150
        ))
        
        self.create_ui()
        self.start_creation()
        
    def create_ui(self):
        """Create dialog UI"""
        # Main frame
        main_frame = ctk.CTkFrame(self, fg_color=VSCODE_COLORS["surface"])
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        ctk.CTkLabel(
            main_frame,
            text=f"Creating Environment: {self.env_name}",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(0, 20))
        
        # Status
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Initializing...",
            font=ctk.CTkFont(size=14)
        )
        self.status_label.pack(pady=(0, 10))
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(main_frame)
        self.progress_bar.pack(fill="x", pady=(0, 10))
        self.progress_bar.set(0)
        
        # Details
        self.details_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.details_label.pack(pady=(0, 10))
        
        # Log
        log_frame = ctk.CTkFrame(main_frame, fg_color=VSCODE_COLORS["background"])
        log_frame.pack(fill="both", expand=True, pady=(0, 20))
        
        # Log with scrollbar
        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(size=11, family="Consolas"),
            fg_color=VSCODE_COLORS["background"],
            text_color="#CCCCCC"
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Buttons
        self.btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.btn_frame.pack(fill="x")
        
        self.cancel_btn = ctk.CTkButton(
            self.btn_frame,
            text="Cancel",
            command=self.cancel_creation,
            width=100
        )
        self.cancel_btn.pack(side="left")
        
        self.done_btn = ctk.CTkButton(
            self.btn_frame,
            text="Done",
            command=self.destroy,
            width=100,
            state="disabled"
        )
        self.done_btn.pack(side="right")
        
    def start_creation(self):
        """Start environment creation process"""
        # Log environment details
        self.log(f"Creating environment: {self.env_name}")
        self.log(f"Location: {self.location}")
        self.log(f"Python: {self.python_exe}")
        self.log(f"Packages: {', '.join(self.packages)}")
        self.log("")
        
        # Start creation in background thread
        self.creation_thread = threading.Thread(target=self.create_environment, daemon=True)
        self.creation_thread.start()
        
    def create_environment(self):
        """Create the environment"""
        try:
            # Update status
            self.update_status("Creating virtual environment...", 0.1)
            
            # Create environment directory
            env_path = os.path.join(self.location, self.env_name)
            os.makedirs(self.location, exist_ok=True)
            
            # Create virtual environment
            self.log("Creating virtual environment...")
            import venv
            venv.create(env_path, with_pip=True)
            
            # Get Python and pip paths
            if sys.platform == "win32":
                python_path = get_long_path(ensure_ascii_path(os.path.join(env_path, "Scripts", "python.exe")))
                pip_path = get_long_path(ensure_ascii_path(os.path.join(env_path, "Scripts", "pip.exe")))
            else:
                python_path = get_long_path(ensure_ascii_path(os.path.join(env_path, "bin", "python")))
                pip_path = get_long_path(ensure_ascii_path(os.path.join(env_path, "bin", "pip")))
                
            # Verify paths
            if not os.path.exists(python_path) or not os.path.exists(pip_path):
                self.log(f"ERROR: Python or pip executable not found in created environment")
                self.log(f"Python path: {python_path}, exists: {os.path.exists(python_path)}")
                self.log(f"Pip path: {pip_path}, exists: {os.path.exists(pip_path)}")
                self.update_status("Creation failed!", 0)
                self.finish(success=False)
                return
                
            # Upgrade pip
            self.update_status("Upgrading pip...", 0.15)
            self.log("Upgrading pip...")
            
            result = self.run_command([pip_path, "install", "--upgrade", "pip"])
            if result.returncode != 0:
                self.log(f"WARNING: Failed to upgrade pip: {result.stderr}")
            else:
                self.log("Pip upgraded successfully")
                
            # Install packages
            if self.packages:
                self.update_status("Installing packages...", 0.2)
                self.log("\nInstalling packages...")
                
                for i, package in enumerate(self.packages):
                    progress = 0.2 + (i / len(self.packages) * 0.7)
                    self.update_status(f"Installing {package}...", progress)
                    
                    self.log(f"Installing {package}...")
                    result = self.run_command([pip_path, "install", package])
                    
                    if result.returncode == 0:
                        self.log(f"✓ Successfully installed {package}")
                    else:
                        self.log(f"✗ Failed to install {package}: {result.stderr}")
                        
            # Finish
            self.update_status("Environment created successfully!", 1.0)
            self.log("\n✅ Environment created successfully!")
            self.finish(success=True)
            
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
            self.update_status("Creation failed!", 0)
            self.finish(success=False)
            
    def run_command(self, command):
        """Run command with hidden console"""
        startupinfo = None
        creationflags = 0
        
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
            
        return run_original(
            command,
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        
    def update_status(self, status, progress):
        """Update status and progress bar"""
        self.after(0, lambda: self.status_label.configure(text=status))
        self.after(0, lambda: self.progress_bar.set(progress))
        self.after(0, lambda: self.details_label.configure(text=f"Progress: {int(progress * 100)}%"))
        
    def log(self, message):
        """Add message to log"""
        self.after(0, lambda: self.log_text.insert("end", f"{message}\n"))
        self.after(0, lambda: self.log_text.see("end"))
        
    def finish(self, success):
        """Finish creation process"""
        self.after(0, lambda: self.done_btn.configure(state="normal"))
        self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
        
        if success:
            self.after(0, lambda: messagebox.showinfo(
                "Environment Created",
                f"Environment '{self.env_name}' created successfully!",
                parent=self
            ))
        else:
            self.after(0, lambda: messagebox.showerror(
                "Creation Failed",
                f"Failed to create environment '{self.env_name}'.\nCheck the log for details.",
                parent=self
            ))
            
    def cancel_creation(self):
        """Cancel environment creation"""
        if messagebox.askyesno(
            "Cancel Creation",
            "Are you sure you want to cancel environment creation?",
            parent=self
        ):
            self.destroy()
            
    def on_close(self):
        """Handle window close attempt"""
        # Ignore if creation is in progress
        pass


# Essential packages for ManimStudio

class VirtualEnvironmentManager:
    """
    Complete virtual environment manager for Manim Studio
    Handles creation, activation, package management, and verification of Python environments
    """
    
    def __init__(self, parent_app=None):
        self.parent_app = parent_app
        self.logger = logging.getLogger(__name__)
        
        # Check for bundled environment first
        if USING_BUNDLED_ENV:
            print("📦 Detected bundled environment")
            self.setup_bundled_environment()
            return  # Exit early, don't do normal setup
        
        # Normal initialization for non-bundled environments
        print("🐍 Using standard environment setup")
        # Environment paths and configuration
        self.base_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
        self.app_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")
        self.venv_dir = os.path.join(self.app_dir, "venvs")
        self.bundled_dir = os.path.join(self.base_dir, "bundled")
        
        # Create necessary directories
        os.makedirs(self.venv_dir, exist_ok=True)
        os.makedirs(self.app_dir, exist_ok=True)
        
        # Current environment state
        self.current_venv = None
        self.python_path = sys.executable
        self.pip_path = "pip"
        self.needs_setup = True
        self.using_fallback = False
        self.is_frozen = self._detect_if_frozen()
        
        # Bundled environment detection
        self.bundled_venv_dir = None
        self.bundled_available = False
        self._detect_bundled_environment()
        
        # Essential packages for ManimStudio - COMPLETE LIST
        self.essential_packages = [
            # Core animation
            "manim>=0.17.0",
            "numpy>=1.22.0",
            "matplotlib>=3.5.0",
            "scipy>=1.8.0",
            
            # Critical dependencies
            "pycairo>=1.20.0",
            "ManimPango>=0.4.0",
            
            # Image/Video processing
            "Pillow>=9.0.0",
            "opencv-python>=4.6.0",
            "imageio>=2.19.0",
            "moviepy>=1.0.3",
            "imageio-ffmpeg",
            
            # Development tools
            "jedi>=0.18.0",
            "customtkinter>=5.0.0",
            
            # Additional useful packages
            "requests",
            "rich",
            "tqdm",
            "colour",
            "moderngl",
            "moderngl-window"
        ]
        
        # Auto-detect existing environment (this will be called by ManimStudioApp)
        # Don't auto-detect here to avoid conflicts with app-level detection
    def safe_after(self, delay, callback=None):
        """Safely schedule a callback on the main Tk root."""
        if self.parent_app and hasattr(self.parent_app, 'root'):
            try:
                self.parent_app.root.after(delay, callback)
            except RuntimeError:
                pass
        
        # Essential packages for ManimStudio - COMPLETE LIST
        # Essential packages for ManimStudio - Complete list
        self.essential_packages = [
            # Core animation
            "manim>=0.17.0",
            "numpy>=1.22.0", 
            "matplotlib>=3.5.0",
            "scipy>=1.8.0",
            
            # Critical dependencies
            "pycairo>=1.20.0",
            "ManimPango>=0.4.0",
            
            # Image/Video processing
            "Pillow>=9.0.0",
            "opencv-python>=4.6.0",
            "imageio>=2.19.0",
            "moviepy>=1.0.3",
            "imageio-ffmpeg",
            
            # Development tools
            "jedi>=0.18.0",
            "customtkinter>=5.0.0",
            
            # Additional useful packages
            "requests",
            "rich",
            "tqdm",
            "colour",
            "moderngl",
            "moderngl-window"
        ]
        
        # Initialize environment detection
        self._initialize_environment()

    def fix_mapbox_earcut_issue(self):
        """Attempt to reinstall mapbox_earcut to resolve DLL problems."""
        try:
            pip_cmd = self.get_pip_command()
            # force reinstall of known good version
            cmd = pip_cmd + ["install", "--force-reinstall", "mapbox-earcut"]
            result = self.run_hidden_subprocess_nuitka_safe(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode == 0:
                return True
        except Exception as e:
            self.logger.error(f"Error fixing mapbox_earcut: {e}")
        return False

    def get_venv_info(self, venv_name):
        """Get detailed information about a virtual environment (portable version)"""
        # Handle bundled environment case (portable mode)
        if USING_BUNDLED_ENV and venv_name == "manim_studio_default":
            # In portable mode, environment is next to app.exe
            if getattr(sys, 'frozen', False):
                app_dir = Path(sys.executable).parent
            else:
                app_dir = Path(__file__).parent
            
            venv_path = app_dir / "manim_studio_default"
            
            info = {
                'name': venv_name,
                'path': str(venv_path),
                'python_version': "Bundled Python",
                'is_active': self.current_venv == venv_name,
                'packages_count': 0,
                'size': 0,
                'is_bundled': True,  # Mark as bundled
                'is_portable': True  # Mark as portable
            }
            
            # Get Python version if available
            python_exe = venv_path / "Scripts" / "python.exe" if os.name == 'nt' else venv_path / "bin" / "python"
            if python_exe.exists():
                try:
                    result = subprocess.run([str(python_exe), "--version"], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        info['python_version'] = result.stdout.strip() + " (Portable)"
                except:
                    pass
            
            # Count packages
            try:
                if os.name == 'nt':
                    site_packages = venv_path / "Lib" / "site-packages"
                else:
                    # Find site-packages directory
                    lib_dirs = list((venv_path / "lib").glob("python*"))
                    site_packages = lib_dirs[0] / "site-packages" if lib_dirs else None
                
                if site_packages and site_packages.exists():
                    packages = [item for item in site_packages.iterdir() 
                              if item.is_dir() and not item.name.startswith('.') 
                              and not item.name.endswith('.dist-info')]
                    info['packages_count'] = f"{len(packages)} (bundled)"
            except:
                info['packages_count'] = "Many (bundled)"
            
            # Get directory size
            try:
                total_size = sum(f.stat().st_size for f in venv_path.rglob('*') if f.is_file())
                info['size'] = total_size
            except:
                info['size'] = 0
            
            return info
        
        # Normal environment handling (existing code)
        info = {
            'name': venv_name,
            'path': '',
            'python_version': '',
            'is_active': self.current_venv == venv_name,
            'packages_count': 0,
            'size': 0,
            'is_bundled': False,
            'is_portable': False
        }
        
        # Handle special environments
        if venv_name.startswith("system_"):
            info['path'] = "System Python"
            info['python_version'] = sys.version.split()[0]
            return info
        elif venv_name.startswith("current_"):
            info['path'] = "Current Python"
            info['python_version'] = sys.version.split()[0]
            return info
        
        # Regular virtual environment
        venv_path = os.path.join(self.venv_dir, venv_name)
        info['path'] = venv_path
        
        if not os.path.exists(venv_path):
            return info
        
        try:
            # Get Python version
            if os.name == 'nt':
                python_exe = os.path.join(venv_path, "Scripts", "python.exe")
                site_packages = os.path.join(venv_path, "Lib", "site-packages")
            else:
                python_exe = os.path.join(venv_path, "bin", "python")
                site_packages = os.path.join(venv_path, "lib", "python*/site-packages")
            
            if os.path.exists(python_exe):
                result = subprocess.run([python_exe, "--version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    info['python_version'] = result.stdout.strip()
            
            # Count packages
            if os.name == 'nt' and os.path.exists(site_packages):
                info['packages_count'] = len([item for item in os.listdir(site_packages) if not item.startswith('.') and not item.endswith('.dist-info')])
            else:
                import glob
                site_dirs = glob.glob(os.path.join(venv_path, "lib", "python*", "site-packages"))
                if site_dirs:
                    info['packages_count'] = len([item for item in os.listdir(site_dirs[0]) if not item.startswith('.') and not item.endswith('.dist-info')])
            
            # Get directory size
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(venv_path):
                for fname in filenames:
                    fpath = os.path.join(dirpath, fname)
                    try:
                        total_size += os.path.getsize(fpath)
                    except OSError:
                        pass
            info['size'] = total_size
        except Exception as e:
            self.logger.error(f"Error getting venv info for {venv_name}: {e}")
        return info


    def show_setup_dialog(self):
        """Show environment setup dialog"""
        if self.parent_app is None:
            return
        dialog = EnvironmentSetupDialog(self.parent_app.root, self)
        self.parent_app.root.wait_window(dialog)
        
        # After dialog closes, ensure main window is visible
        self.parent_app.root.after(10, lambda: self.parent_app.root.deiconify())

    def is_environment_ready(self):
        """Enhanced environment readiness check with error handling"""
        if self.needs_setup:
            return False
        
        # Quick validation with repair attempt
        if not self.validate_and_repair_environment():
            # If validation fails, try to auto-repair once
            try:
                self.logger.info("Environment validation failed, attempting auto-repair...")
                default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
                
                if os.path.exists(default_venv_path):
                    if self.repair_corrupted_environment(default_venv_path):
                        self.activate_default_environment()
                        self.needs_setup = False
                        return True
                
                # If repair fails, mark as needs setup
                self.needs_setup = True
                return False
                
            except Exception as e:
                self.logger.error(f"Auto-repair failed: {e}")
                self.needs_setup = True
                return False
        
        return True
        
    def _detect_if_frozen(self):
        """Enhanced detection of frozen executable"""
        # Standard PyInstaller detection
        if getattr(sys, 'frozen', False):
            return True
        
        # Additional checks for our specific case
        exe_path = os.path.abspath(sys.executable)
        exe_name = os.path.basename(exe_path).lower()
        
        # Check if executable name suggests it's our app
        app_names = ["manimstudio", "manim_studio", "app", "main"]
        if any(name in exe_name for name in app_names):
            return True
        
        # Check if executable is in a 'dist' directory (common for PyInstaller)
        if "dist" in exe_path.lower():
            return True
        
        # Check for Nuitka onefile indicators
        if "onefile" in exe_path or "temp" in exe_path:
            return True
        
        return False
    
    def _detect_bundled_environment(self):
        """Detect if there's a bundled virtual environment"""
        bundled_paths = [
            os.path.join(self.base_dir, "venv.zip"),
            os.path.join(self.base_dir, "bundled", "venv.zip"),
            os.path.join(self.base_dir, "resources", "venv.zip")
        ]
        
        for path in bundled_paths:
            if os.path.exists(path):
                self.bundled_venv_dir = Path(path).parent
                self.bundled_available = True
                self.logger.info(f"Found bundled environment: {path}")
                break
    
    def _initialize_environment(self):
        """Initialize and detect current environment"""
        self.logger.info("Initializing environment detection...")
        
        # First check for manim_studio_default specifically
        default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
        if os.path.exists(default_venv_path) and self.is_valid_venv(default_venv_path):
            self.logger.info("Found manim_studio_default environment")
            if os.name == 'nt':
                self.python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
                self.pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
            else:
                self.python_path = os.path.join(default_venv_path, "bin", "python")
                self.pip_path = os.path.join(default_venv_path, "bin", "pip")
                
            # Verify manim is available
            if self.check_manim_availability():
                self.current_venv = "manim_studio_default"
                self.needs_setup = False
                return True
            else:
                self.logger.warning("manim_studio_default exists but manim not available")

        # Check for local environment alongside the application
        if self.check_local_directory_venv():
            return True

        # CRITICAL: Don't check current virtual environment when frozen
        # because sys.executable points to our .exe file
        if not self.is_frozen:
            # Only check if we're in a virtual environment when running as script
            if hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix:
                venv_name = os.path.basename(sys.prefix)
                self.current_venv = f"current_{venv_name}"
                self.python_path = sys.executable
                self.pip_path = os.path.join(os.path.dirname(sys.executable), "pip")
                
                # Check if this environment has essential packages
                if self.verify_current_environment():
                    self.logger.info(f"Using current virtual environment: {venv_name}")
                    self.needs_setup = False
                    return True
            
            # Check system Python for Manim (only when not frozen)
            if self.check_system_python():
                self.needs_setup = False
                return True
        else:
            self.logger.info("Running as executable - skipping current environment detection")
        
        # Check for bundled environment
        if self.check_bundled_environment():
            self.logger.info("Found bundled environment, will extract when needed")
            return False  # Still need setup, but we have backup
            
        return False
    def setup_environment(self, log_callback=None):
        """Main setup method - handle bundled vs normal environment"""
        if USING_BUNDLED_ENV:
            if log_callback:
                log_callback("📦 Using bundled environment - no setup needed!")
            return True
        
        # Original setup logic for non-bundled environments
        self.logger.info("Starting environment setup...")
        
        default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
        
        # Step 1: Check for existing environment
        if os.path.exists(default_venv_path) and self.is_valid_venv(default_venv_path):
            self.logger.info("Found existing environment, checking what's missing...")
            
            # Set up paths for existing environment
            if os.name == 'nt':
                self.python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
                self.pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
            else:
                self.python_path = os.path.join(default_venv_path, "bin", "python")
                self.pip_path = os.path.join(default_venv_path, "bin", "pip")
            
            # Validate Python installation
            if not self.validate_python_installation(self.python_path):
                self.logger.warning("Invalid Python installation in existing environment")
                # Fall through to recreate
            else:
                # Check what packages are missing
                missing_packages = self.check_missing_packages()
                
                if not missing_packages:
                    self.logger.info("✅ All packages already installed!")
                    self.activate_default_environment()
                    self.needs_setup = False
                    return True
                else:
                    self.logger.info(f"Missing packages: {missing_packages}")
                    
                    # Upgrade pip first in existing environment
                    self.upgrade_pip_in_existing_env(log_callback)
                    
                    # Try to install missing packages
                    if self.install_missing_packages(missing_packages, log_callback):
                        self.logger.info("✅ Successfully installed missing packages!")
                        self.activate_default_environment()
                        self.needs_setup = False
                        return True
                    else:
                        self.logger.warning("Failed to install some packages, will recreate environment...")
                        # Fall through to recreate environment
        
        # Step 2: Try bundled environment if available
        if self.bundled_available:
            self.logger.info("Attempting to extract bundled environment...")
            if self.extract_bundled_environment():
                self.logger.info("✅ Bundled environment extracted successfully!")
                self.activate_default_environment()
                self.needs_setup = False
                return True
        
        # Step 3: Create new environment (if no existing or repair failed)
        if os.path.exists(default_venv_path):
            self.logger.info("Removing problematic environment for fresh install...")
            try:
                shutil.rmtree(default_venv_path)
                time.sleep(1)  # Wait for cleanup
            except Exception as e:
                self.logger.warning(f"Could not remove existing environment: {e}")
                return False
        
        # Step 4: Create new environment
        if not self.create_virtual_environment():
            return False
            
        # Step 5: Install all packages
        if not self.install_all_packages(log_callback):
            return False

        # Step 6: Verify installation
        if not self.verify_complete_installation(log_callback):
            return False
            
        # Step 7: Activate environment
        self.activate_default_environment()
        
        self.logger.info("✅ Environment setup completed successfully!")
        self.needs_setup = False
        return True
    def check_missing_packages(self):
        """Check which essential packages are missing from the current environment"""
        missing = []
        
        # Create a script to check all packages at once
        check_script = f"""
import sys
import importlib

packages_to_check = {self.essential_packages}
missing_packages = []

for package_spec in packages_to_check:
    # Extract package name (remove version specifiers)
    package_name = package_spec.split('>=')[0].split('==')[0].split('<')[0].split('>')[0]
    
    try:
        if package_name == "opencv-python":
            import cv2  # opencv-python imports as cv2
        elif package_name == "Pillow":
            import PIL  # Pillow imports as PIL
        elif package_name == "imageio-ffmpeg":
            import imageio_ffmpeg
        elif package_name == "moderngl-window":
            import moderngl_window
        else:
            importlib.import_module(package_name)
    except ImportError:
        missing_packages.append(package_spec)

if missing_packages:
    print("MISSING:" + ",".join(missing_packages))
else:
    print("ALL_INSTALLED")
"""
        
        try:
            result = self.run_hidden_subprocess_nuitka_safe(
                [self.python_path, "-c", check_script],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                if output.startswith("MISSING:"):
                    missing = output.replace("MISSING:", "").split(",")
                    missing = [pkg.strip() for pkg in missing if pkg.strip()]
                
            return missing
            
        except Exception as e:
            self.logger.error(f"Error checking packages: {e}")
            # If we can't check, assume all are missing
            return self.essential_packages.copy()
    def run_manim_command_safe(self, command, **kwargs):
        """Safe manim command runner with proper encoding"""
        # Set default encoding for manim commands
        kwargs.setdefault('encoding', 'utf-8')
        kwargs.setdefault('errors', 'replace')
        
        return self.run_hidden_subprocess_nuitka_safe(command, **kwargs)
    def install_missing_packages(self, missing_packages, log_callback=None):
        """Install only the missing packages"""
        if not missing_packages:
            return True

        self.logger.info(f"Installing {len(missing_packages)} missing packages...")
        if log_callback:
            log_callback(f"Installing {len(missing_packages)} missing packages...")

        success_count = 0
        total_packages = len(missing_packages)

        for i, package in enumerate(missing_packages):
            self.logger.info(f"Installing missing package: {package} ({i+1}/{total_packages})...")
            if log_callback:
                log_callback(f"Installing missing package: {package} ({i+1}/{total_packages})...")

            if log_callback:
                ok = self.install_single_package_with_logging(package, log_callback)
            else:
                ok = self.install_single_package(package)

            if ok:
                success_count += 1
                self.logger.info(f"✅ {package} installed successfully")
            else:
                self.logger.error(f"❌ Failed to install {package}")

        self.logger.info(f"Missing packages installation: {success_count}/{total_packages} successful")
        if log_callback:
            log_callback(f"Missing packages installation: {success_count}/{total_packages} successful")
        
        # Consider it successful if at least 80% of packages installed
        success_rate = success_count / total_packages if total_packages > 0 else 0
        return success_rate >= 0.8
    
    def upgrade_pip_in_existing_env(self, log_callback=None):
        """Upgrade pip in the existing environment"""
        try:
            self.logger.info("Upgrading pip in existing environment...")
            if log_callback:
                log_callback("Upgrading pip in existing environment...")
            result = self.run_hidden_subprocess_nuitka_safe(
                [self.python_path, "-m", "pip", "install", "--upgrade", "pip"],
                capture_output=True,
                text=True,
                timeout=120
            )

            if log_callback and result.stdout:
                for line in result.stdout.splitlines():
                    log_callback(line)
            if log_callback and result.stderr:
                for line in result.stderr.splitlines():
                    log_callback(line)

            if result.returncode == 0:
                self.logger.info("✅ Pip upgraded successfully")
                if log_callback:
                    log_callback("✅ Pip upgraded successfully")
            else:
                self.logger.warning(f"Pip upgrade warning: {result.stderr}")
                if log_callback:
                    log_callback(f"Pip upgrade warning: {result.stderr}")

        except Exception as e:
            self.logger.warning(f"Could not upgrade pip: {e}")
            if log_callback:
                log_callback(f"Could not upgrade pip: {e}")

    def install_all_packages(self, log_callback=None):
        """Install all essential packages one by one"""
        self.logger.info("Installing all essential packages...")
        if log_callback:
            log_callback("Installing all essential packages...")
            log_callback(f"Total packages to install: {len(self.essential_packages)}")
            log_callback(f"Packages: {', '.join(self.essential_packages)}")

        success_count = 0
        total_packages = len(self.essential_packages)

        for i, package in enumerate(self.essential_packages):
            self.logger.info(f"Installing {package} ({i+1}/{total_packages})...")
            if log_callback:
                log_callback(f"Installing {package} ({i+1}/{total_packages})...")

            if log_callback:
                ok = self.install_single_package_with_logging(package, log_callback)
            else:
                ok = self.install_single_package(package)

            if ok:
                success_count += 1
                self.logger.info(f"✅ {package} installed successfully")
                if log_callback:
                    log_callback(f"✅ {package} installed successfully")
            else:
                self.logger.error(f"❌ Failed to install {package}")
                if log_callback:
                    log_callback(f"❌ Failed to install {package}")
                
        self.logger.info(f"Installation complete: {success_count}/{total_packages} packages installed")
        if log_callback:
            log_callback(f"Installation complete: {success_count}/{total_packages} packages installed")
        
        # Consider it successful if at least the core packages are installed
        if success_count >= (total_packages * 0.7):  # At least 70% success rate
            return True
        else:
            self.logger.error("Too many package installations failed")
            return False
    def install_single_package(self, package):
        """Install a single package with retries and better error handling"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Try different installation strategies with Windows compatibility
                install_strategies = self._get_install_strategies(package, attempt)
                
                # Use appropriate strategy based on attempt
                strategy_index = min(attempt, len(install_strategies) - 1)
                install_cmd = install_strategies[strategy_index]
                
                self.logger.info(f"Attempt {attempt+1}: Installing {package}")
                self.logger.debug(f"Command: {' '.join(install_cmd)}")
                
                result = self.run_hidden_subprocess_nuitka_safe(
                    install_cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10 minutes per package max
                    env=self.get_clean_environment()
                )
                
                if result.returncode == 0:
                    # Verify the package actually imported correctly
                    if self.verify_single_package(package):
                        return True
                    else:
                        self.logger.warning(f"{package} installed but cannot import")
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                else:
                    self.logger.warning(f"Attempt {attempt+1} failed for {package}")
                    self.logger.debug(f"Error output: {result.stderr}")
                    if attempt < max_retries - 1:
                        time.sleep(2)  # Wait before retry
                        
            except subprocess.TimeoutExpired:
                self.logger.warning(f"Timeout installing {package} (attempt {attempt+1})")
                if attempt < max_retries - 1:
                    time.sleep(5)
            except Exception as e:
                self.logger.warning(f"Error installing {package} (attempt {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    
        return False
    
    def _get_install_strategies(self, package, attempt):
        """Get installation strategies with Windows 64-bit compatibility"""
        base_cmd = [self.python_path, "-m", "pip", "install"]
        
        # Common flags for all strategies
        common_flags = ["--no-cache-dir", "--timeout", "300"]
        
        # Windows-specific flags for 64-bit compatibility
        windows_flags = []
        if os.name == 'nt':
            # Force 64-bit wheels when available
            arch = platform.machine().lower()
            if arch in ['amd64', 'x86_64']:
                windows_flags.extend([
                    "--only-binary=:all:",  # Prefer wheels over source
                    "--platform", "win_amd64",  # Force 64-bit platform
                ])
        
        strategies = [
            # Strategy 1: Basic install with Windows compatibility
            base_cmd + [package] + common_flags + windows_flags,
            
            # Strategy 2: With upgrade flag
            base_cmd + [package, "--upgrade"] + common_flags + windows_flags,
            
            # Strategy 3: Force reinstall with pre-compiled wheels only
            base_cmd + [package, "--force-reinstall", "--only-binary=:all:"] + common_flags
        ]
        
        # For specific problematic packages on Windows, use special handling
        if os.name == 'nt' and any(pkg in package.lower() for pkg in ['opencv', 'numpy', 'scipy', 'pillow']):
            # Add strategy for pre-compiled wheels from reliable sources
            strategies.insert(0, base_cmd + [package, "--only-binary=:all:", "--find-links", "https://download.pytorch.org/whl/torch_stable.html"] + common_flags)
        
        return strategies
    
    def verify_single_package(self, package_spec):
        """Verify that a single package can be imported"""
        # Extract package name (remove version specifiers)
        package_name = package_spec.split('>=')[0].split('==')[0].split('<')[0].split('>')[0]
        
        verify_script = f"""
try:
    if "{package_name}" == "opencv-python":
        import cv2
    elif "{package_name}" == "Pillow":
        import PIL
    elif "{package_name}" == "imageio-ffmpeg":
        import imageio_ffmpeg
    elif "{package_name}" == "moderngl-window":
        import moderngl_window
    else:
        import {package_name}
    print("OK")
except ImportError as e:
    print(f"FAIL: {{e}}")
    exit(1)
"""
        
        try:
            result = self.run_hidden_subprocess_nuitka_safe(
                [self.python_path, "-c", verify_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0 and "OK" in result.stdout
        except Exception:
            return False
    
    def create_virtual_environment(self):
        """Create the virtual environment"""
        env_path = os.path.join(self.venv_dir, "manim_studio_default")
        
        self.logger.info(f"Creating virtual environment at: {env_path}")
        
        try:
            # Find system Python
            python_exe = self.find_system_python()
            if not python_exe:
                self.logger.error("No Python installation found!")
                return False
                
            # Create virtual environment
            create_cmd = [python_exe, "-m", "venv", env_path, "--clear"]
            result = self.run_hidden_subprocess_nuitka_safe(
                create_cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=os.path.expanduser("~")
            )
            
            if result.returncode != 0:
                self.logger.error(f"Failed to create virtual environment: {result.stderr}")
                return False
                
            # Set up paths
            if os.name == 'nt':
                self.python_path = os.path.join(env_path, "Scripts", "python.exe")
                self.pip_path = os.path.join(env_path, "Scripts", "pip.exe")
            else:
                self.python_path = os.path.join(env_path, "bin", "python")
                self.pip_path = os.path.join(env_path, "bin", "pip")
                
            # Verify executables exist
            if not os.path.exists(self.python_path):
                self.logger.error(f"Python executable not found: {self.python_path}")
                return False
                
            # Install/upgrade pip first
            self.logger.info("Upgrading pip...")
            pip_upgrade_cmd = [self.python_path, "-m", "pip", "install", "--upgrade", "pip"]
            result = self.run_hidden_subprocess_nuitka_safe(pip_upgrade_cmd, capture_output=True, text=True, timeout=180)
            
            if result.returncode == 0:
                self.logger.info("✅ Pip upgraded successfully")
            else:
                self.logger.warning(f"Pip upgrade warning: {result.stderr}")
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating virtual environment: {e}")
            return False
    
    def verify_complete_installation(self, log_callback=None):
        """Simple verification that doesn't trigger 3221225477 errors"""
        if log_callback:
            log_callback("🔍 Performing simple installation check...")
        
        # Just check if key files exist rather than importing
        required_paths = [
            self.python_path,
            self.pip_path,
        ]
        
        for path in required_paths:
            if not os.path.exists(path):
                if log_callback:
                    log_callback(f"❌ Missing: {path}")
                return False
        
        # Check if site-packages directory exists and has some packages
        if os.name == 'nt':
            site_packages = os.path.join(os.path.dirname(self.python_path), "..", "Lib", "site-packages")
        else:
            site_packages = os.path.join(os.path.dirname(self.python_path), "..", "lib", "python*", "site-packages")
        
        site_packages = os.path.normpath(site_packages)
        if os.path.exists(site_packages):
            # Check if we have some packages installed
            packages = os.listdir(site_packages)
            if len([p for p in packages if not p.startswith('.')] ) > 5:  # Basic threshold
                if log_callback:
                    log_callback("✅ Installation appears valid")
                return True
        
        if log_callback:
            log_callback("⚠️ Installation may be incomplete")
        return True  # Don't fail - let the user try to use it
   
    def activate_default_environment(self):
        """Activate the default environment"""
        self.current_venv = "manim_studio_default"
        env_path = os.path.join(self.venv_dir, "manim_studio_default")
        
        if os.name == 'nt':
            self.python_path = os.path.join(env_path, "Scripts", "python.exe")
            self.pip_path = os.path.join(env_path, "Scripts", "pip.exe")
        else:
            self.python_path = os.path.join(env_path, "bin", "python")
            self.pip_path = os.path.join(env_path, "bin", "pip")
            
        self.logger.info(f"Activated environment: {self.current_venv}")
        return True
    
    def find_system_python(self):
        """Find the best system Python installation with 64-bit preference"""
        candidates = []
        
        if os.name == 'nt':
            # Windows candidates - prioritize 64-bit installations
            if not self.is_frozen:
                candidates.append(sys.executable)
            candidates.extend([
                "python",
                "python3"
            ])
            
            # Force 64-bit Python paths first
            for version in ['3.12', '3.11', '3.10', '3.9']:
                # 64-bit installations in Program Files
                candidates.append(rf"C:\Program Files\Python{version.replace('.', '')}\python.exe")
                # 64-bit installations in AppData
                appdata = os.environ.get('LOCALAPPDATA', '')
                if appdata:
                    candidates.append(os.path.join(appdata, 'Programs', 'Python', f'Python{version.replace(".", "")}', 'python.exe'))
            
            # Fallback to any Python (32-bit) only if no 64-bit found
            for version in ['3.12', '3.11', '3.10', '3.9']:
                candidates.append(rf"C:\Python{version.replace('.', '')}\python.exe")
                
        else:
            # Unix-like candidates
            if not self.is_frozen:
                candidates.append(sys.executable)
            candidates.extend([
                "python3",
                "python",
                "/usr/bin/python3",
                "/usr/local/bin/python3",
                "/opt/python3/bin/python3"
            ])
        
        for candidate in candidates:
            try:
                python_path = None
                if os.path.isfile(candidate):
                    python_path = candidate
                elif shutil.which(candidate):
                    python_path = shutil.which(candidate)
                else:
                    continue

                if self.is_frozen and os.path.samefile(python_path, sys.executable):
                    self.logger.debug("Skipping frozen executable candidate")
                    continue
                
                # Check Python version
                result = subprocess.run([python_path, "--version"], capture_output=True, text=True, timeout=10)
                if result.returncode != 0 or "Python 3." not in result.stdout:
                    continue
                
                # Check architecture (64-bit preferred on Windows)
                if os.name == 'nt':
                    arch_result = subprocess.run([python_path, "-c", "import platform; print(platform.machine())"], 
                                                capture_output=True, text=True, timeout=10)
                    if arch_result.returncode == 0:
                        arch = arch_result.stdout.strip()
                        self.logger.info(f"Found Python: {python_path} - {result.stdout.strip()} - Architecture: {arch}")
                        
                        # Prefer 64-bit on 64-bit systems
                        if platform.machine().endswith('64') and not arch.endswith('64'):
                            self.logger.info(f"Skipping 32-bit Python on 64-bit system: {python_path}")
                            continue
                            
                        return python_path
                else:
                    self.logger.info(f"Found Python: {python_path} - {result.stdout.strip()}")
                    return python_path
                    
            except Exception as e:
                self.logger.debug(f"Error checking Python candidate {candidate}: {e}")
                continue
                
        return None
    
    def get_clean_environment(self):
        """Get a clean environment for subprocess calls with 64-bit focus"""
        env = os.environ.copy()
        
        # Remove any existing virtual environment variables
        env.pop('VIRTUAL_ENV', None)
        env.pop('VIRTUAL_ENV_PROMPT', None)
        
        # Set clean Python environment
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['PYTHONUNBUFFERED'] = '1'
        
        # Set temp directory to system temp to avoid path issues
        system_temp = tempfile.gettempdir()
        env['TEMP'] = system_temp
        env['TMP'] = system_temp
        
        # Windows-specific PATH cleaning for 64-bit compatibility
        if os.name == 'nt':
            # Clean PATH to avoid 16-bit legacy tools
            path_dirs = env.get('PATH', '').split(os.pathsep)
            clean_path_dirs = []
            
            # Prioritize 64-bit system directories
            system_paths = [
                os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32'),
                os.path.join(os.environ.get('SystemRoot', 'C:\\Windows')),
                os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32', 'WindowsPowerShell', 'v1.0'),
                os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'Git', 'bin'),
                os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'Microsoft VS Code', 'bin')
            ]
            
            # Add system paths first
            for sys_path in system_paths:
                if os.path.exists(sys_path) and sys_path not in clean_path_dirs:
                    clean_path_dirs.append(sys_path)
            
            # Filter existing PATH, avoiding problematic directories
            problematic_dirs = [
                'SysWOW64',  # 32-bit compatibility layer
                'System',    # 16-bit legacy
                'C:\\Windows\\System',  # 16-bit legacy
            ]
            
            for path_dir in path_dirs:
                if path_dir and os.path.exists(path_dir):
                    # Skip problematic directories
                    if any(prob in path_dir for prob in problematic_dirs):
                        self.logger.debug(f"Skipping problematic PATH entry: {path_dir}")
                        continue
                    
                    # Skip duplicate entries
                    if path_dir not in clean_path_dirs:
                        clean_path_dirs.append(path_dir)
            
            env['PATH'] = os.pathsep.join(clean_path_dirs)
            
            # Force 64-bit architecture preference
            env['PROCESSOR_ARCHITECTURE'] = 'AMD64'
            if 'PROCESSOR_ARCHITEW6432' in env:
                del env['PROCESSOR_ARCHITEW6432']
        
        return env
    
    def run_hidden_subprocess_nuitka_safe(self, command, capture_output=False, text=True, 
                                         timeout=None, cwd=None, env=None, encoding='utf-8', errors='replace'):
        """Run subprocess with proper encoding handling for Windows"""
        startupinfo = None
        creationflags = 0
        
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        
        try:
            if text and encoding:
                # Handle text with explicit encoding
                result = subprocess.run(
                    command,
                    capture_output=capture_output,
                    text=text,
                    timeout=timeout,
                    cwd=cwd,
                    env=env,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    encoding=encoding,
                    errors=errors
                )
            else:
                # Fallback to original behavior
                result = subprocess.run(
                    command,
                    capture_output=capture_output,
                    text=text,
                    timeout=timeout,
                    cwd=cwd,
                    env=env,
                    startupinfo=startupinfo,
                    creationflags=creationflags
                )
            return result
        except subprocess.TimeoutExpired:
            self.logger.error(f"Command timed out after {timeout} seconds: {' '.join(command)}")
            raise
        except Exception as e:
            self.logger.error(f"Error running command {' '.join(command)}: {e}")
            raise
    def check_local_directory_venv(self):
        """Check for a virtual environment in the application directory"""
        candidates = ["venv", "env"]
        for name in candidates:
            venv_path = os.path.join(self.base_dir, name)
            if os.path.isdir(venv_path) and self.is_valid_venv(venv_path):
                self.logger.info(f"Found local environment: {venv_path}")
                if self.verify_environment_packages(venv_path):
                    self.logger.info("Local environment verified")
                    self.activate_venv_path(venv_path)
                    return True
                else:
                    self.logger.warning("Local environment missing required packages")
        return False
    
    def check_system_python(self):
        """Check if system Python has Manim installed (only when not frozen)"""
        # Don't use system Python when running as executable
        if self.is_frozen:
            self.logger.info("Running as executable - skipping system Python check")
            return False
            
        try:
            import manim
            # Manim is available in system Python
            self.current_venv = "system_python"
            self.python_path = sys.executable
            self.pip_path = "pip"
            self.logger.info("Using system Python with Manim")
            return True
        except ImportError:
            return False
    
    def check_bundled_environment(self):
        """Check for bundled environment"""
        if self.bundled_available:
            self.logger.info("Bundled environment is available")
            return True
        return False
    
    def extract_bundled_environment(self):
        """Extract bundled environment to the venvs directory"""
        if not self.bundled_available:
            return False
            
        try:
            venv_zip_path = os.path.join(self.bundled_venv_dir, "venv.zip")
            extract_path = os.path.join(self.venv_dir, "manim_studio_default")
            
            self.logger.info(f"Extracting bundled environment to: {extract_path}")
            
            # Remove existing directory if it exists
            if os.path.exists(extract_path):
                shutil.rmtree(extract_path)
            
            # Extract the zip file
            with zipfile.ZipFile(venv_zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            
            # Set up paths
            if os.name == 'nt':
                self.python_path = os.path.join(extract_path, "Scripts", "python.exe")
                self.pip_path = os.path.join(extract_path, "Scripts", "pip.exe")
            else:
                self.python_path = os.path.join(extract_path, "bin", "python")
                self.pip_path = os.path.join(extract_path, "bin", "pip")
            
            # Verify extraction
            if not os.path.exists(self.python_path):
                self.logger.error("Python executable not found after extraction")
                return False
            
            # Set permissions on Unix-like systems
            if os.name != 'nt':
                os.chmod(self.python_path, 0o755)
                if os.path.exists(self.pip_path):
                    os.chmod(self.pip_path, 0o755)
            
            # Read manifest and install any missing packages if needed
            manifest_path = os.path.join(self.bundled_venv_dir, "manifest.json")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, 'r') as f:
                        manifest = json.load(f)
                        essential_packages = manifest.get('essential_packages', [])
                        
                        # Install missing packages if any
                        missing = self.check_missing_packages()
                        if missing:
                            self.install_missing_packages(missing)
                            
                except Exception as e:
                    self.logger.error(f"Error reading or processing manifest: {e}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error extracting bundled environment: {e}")
            return False
    
    def verify_current_environment(self):
        """Verify that current environment has essential packages"""
        try:
            # Test essential packages
            essential_test = ["manim", "numpy", "customtkinter"]
            for package in essential_test:
                try:
                    __import__(package)
                except ImportError:
                    self.logger.info(f"Missing package {package} in current environment")
                    return False
            return True
        except Exception as e:
            self.logger.error(f"Error verifying current environment: {e}")
            return False
    
    def verify_environment_packages(self, venv_path):
        """Verify that environment has essential packages"""
        try:
            # Get python path
            if os.name == 'nt':
                python_exe = os.path.join(venv_path, "Scripts", "python.exe")
            else:
                python_exe = os.path.join(venv_path, "bin", "python")
            
            if not os.path.exists(python_exe):
                self.logger.error(f"Python executable not found: {python_exe}")
                return False
            
            # Validate that this is not our own executable
            if not self.validate_python_installation(python_exe):
                return False
                
            # Test essential packages directly without temporary files
            essential_packages = ["manim", "numpy", "customtkinter", "PIL"]
            
            # Create a single test command
            test_code = f"""
import sys
missing = []
packages = {essential_packages}
for pkg in packages:
    try:
        if pkg == 'PIL':
            import PIL
        else:
            __import__(pkg)
        print(f'[OK] {{pkg}}')
    except ImportError:
        missing.append(pkg)
        print(f'[FAIL] {{pkg}}')

if missing:
    print(f'MISSING:{{",".join(missing)}}')
    sys.exit(1)
else:
    print('ALL_OK')
    sys.exit(0)
"""
            
            # Execute directly without temporary file
            result = self.run_hidden_subprocess_nuitka_safe(
                [python_exe, "-c", test_code],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 and "ALL_OK" in result.stdout:
                self.logger.info("All essential packages verified")
                return True
            else:
                self.logger.warning(f"Package verification failed: {result.stdout}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error verifying environment packages: {e}")
            return False
    
    def validate_python_installation(self, python_exe):
        """Validate that Python installation is proper and 64-bit compatible"""
        try:
            # Don't validate our own executable as Python
            if self.is_frozen and os.path.samefile(python_exe, sys.executable):
                self.logger.debug("Skipping validation of frozen executable")
                return False
                
            # Check if it's actually Python
            result = self.run_hidden_subprocess_nuitka_safe(
                [python_exe, "--version"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0 or "Python" not in result.stdout:
                return False
            
            # Check architecture compatibility on Windows
            if os.name == 'nt':
                arch_script = """
import platform
import sys
print(f"Architecture: {platform.machine()}")
print(f"Platform: {platform.platform()}")
print(f"64bit: {platform.architecture()[0]}")
print(f"Pointer size: {sys.maxsize > 2**32}")
"""
                
                arch_result = self.run_hidden_subprocess_nuitka_safe(
                    [python_exe, "-c", arch_script],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if arch_result.returncode == 0:
                    output = arch_result.stdout
                    self.logger.info(f"Python architecture info:\n{output}")
                    
                    # Check for 64-bit compatibility
                    system_arch = platform.machine()
                    if system_arch.endswith('64'):
                        # On 64-bit system, prefer 64-bit Python
                        if '64bit' not in output or 'Pointer size: False' in output:
                            self.logger.warning(f"32-bit Python on 64-bit system: {python_exe}")
                            # Still allow it, but log the warning
                        else:
                            self.logger.info(f"64-bit Python confirmed: {python_exe}")
                    
                    return True
                else:
                    self.logger.warning(f"Could not determine Python architecture: {python_exe}")
                    return True  # Allow it anyway
            
            return True
            
        except Exception as e:
            self.logger.debug(f"Python validation failed: {e}")
            return False
    
    def use_system_python_fallback(self):
        """Use system Python as fallback when environment setup fails"""
        self.logger.info("Using system Python as fallback")
        try:
            # Try to import manim - might work if it's installed system-wide
            __import__("manim")
            self.current_venv = "system_python_fallback"
            self.python_path = sys.executable
            self.pip_path = "pip"
            self.needs_setup = False
            self.using_fallback = True
            self.logger.info("System Python fallback activated with manim available")
            return True
        except ImportError:
            # Manim not available in system Python
            self.logger.warning("Cannot use system Python as fallback - manim not available")
            # Still mark as using fallback to avoid repeated failures
            self.using_fallback = True
            return False
    
    def create_default_environment(self, log_callback=None):
        """Create the default virtual environment with enhanced logging and error handling"""
        env_name = "manim_studio_default"
        env_path = os.path.join(self.venv_dir, env_name)
        
        try:
            if log_callback:
                log_callback(f"Creating virtual environment: {env_name}")
                log_callback(f"Location: {env_path}")
            
            # Remove existing environment if it exists
            if os.path.exists(env_path):
                if log_callback:
                    log_callback("Removing existing environment...")
                shutil.rmtree(env_path, ignore_errors=True)
            
            # Find the best Python executable
            python_exe = self._find_best_python()
            if not python_exe:
                if log_callback:
                    log_callback("❌ No suitable Python installation found")
                return False
            
            if log_callback:
                log_callback(f"Using Python: {python_exe}")
            
            # Create virtual environment with proper subprocess handling
            create_cmd = [python_exe, "-m", "venv", env_path]
            
            if log_callback:
                log_callback("Creating virtual environment...")
            
            # Use proper subprocess configuration
            startupinfo = None
            creationflags = 0
            
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
            
            result = subprocess.run(
                create_cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            
            if result.returncode != 0:
                error_msg = f"Failed to create virtual environment: {result.stderr}"
                if log_callback:
                    log_callback(f"❌ {error_msg}")
                self.logger.error(error_msg)
                return False
            
            # Verify creation
            if not os.path.exists(env_path):
                if log_callback:
                    log_callback("❌ Environment directory not created")
                return False
            
            # Activate the environment
            if self.activate_venv(env_name):
                if log_callback:
                    log_callback("✅ Virtual environment created and activated successfully")
                return True
            else:
                if log_callback:
                    log_callback("❌ Failed to activate environment")
                return False

        except Exception as e:
            error_msg = f"Environment creation failed: {str(e)}"
            if log_callback:
                log_callback(f"❌ {error_msg}")
            self.logger.error(error_msg)
            return False
    def create_environment_unified(self, name, location, packages=None, log_callback=None):
        """Unified environment creation method"""
        if packages is None:
            packages = self.essential_packages[:10]  # Core packages only
            
        env_path = os.path.join(location, name)

        if log_callback:
            log_callback(f"Creating virtual environment: {name}")
            log_callback(f"Location: {env_path}")

        try:
            # Find the best Python installation
            if log_callback:
                log_callback("Searching for Python installations...")
                
            python_exe = self.find_system_python()
            if not python_exe:
                error_msg = "❌ CRITICAL: No Python installation found!\n\n"
                error_msg += "Please install Python from https://python.org and restart the application."
                if log_callback:
                    log_callback(error_msg)
                return False

            # Create virtual environment
            if log_callback:
                log_callback(f"Creating environment with Python: {python_exe}")
                
            create_cmd = [python_exe, "-m", "venv", env_path, "--clear"]
            result = self.run_hidden_subprocess_nuitka_safe(
                create_cmd,
                capture_output=True,
                text=True,
                timeout=180,
                cwd=os.path.expanduser("~")
            )

            if result.returncode != 0:
                if log_callback:
                    log_callback(f"Failed to create environment: {result.stderr}")
                return False

            # Set up environment paths
            if not self._setup_environment_after_creation(env_path):
                return False
                
            # Install packages
            if packages:
                if log_callback:
                    log_callback(f"Installing {len(packages)} packages...")
                    
                for i, package in enumerate(packages):
                    if log_callback:
                        log_callback(f"Installing {package} ({i+1}/{len(packages)})...")
                    
                    if not self.install_single_package_with_logging(package, log_callback):
                        if log_callback:
                            log_callback(f"Warning: Failed to install {package}")

            # Verify installation
            if self.verify_environment_packages(env_path):
                if log_callback:
                    log_callback("Environment setup complete and verified")
                self.needs_setup = False
                return True
            else:
                if log_callback:
                    log_callback("Environment verification failed after setup")
                return self.use_system_python_fallback()
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error during environment creation: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return self.use_system_python_fallback()
    
    def check_environment_status(self, log_callback=None):
        """Check environment status - bundled or virtual"""
        
        if USING_BUNDLED_ENV:
            if log_callback:
                log_callback("✅ Using bundled environment - ready to go!")
            return True
        else:
            # Use existing check_environment_status logic
            return self.original_check_environment_status(log_callback)

    def original_check_environment_status(self, log_callback=None):
        """Check virtual environment status without strict manim testing"""
        default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
        
        if not os.path.exists(default_venv_path):
            if log_callback:
                log_callback("❌ Default environment not found")
            return False
        
        # Check for basic structure
        if not self.is_valid_venv(default_venv_path):
            if log_callback:
                log_callback("❌ Environment structure invalid, attempting repair...")
            return self.repair_corrupted_environment(default_venv_path, log_callback)
        
        # REMOVED: Test if Python executable works (catches 3221225477 errors)
        # Just check if Python executable exists instead of running it
        if not os.path.exists(self.python_path):
            if log_callback:
                log_callback(f"❌ Python executable not found: {self.python_path}")
            return self.repair_corrupted_environment(default_venv_path, log_callback)
        
        # REMOVED: Test manim import specifically - this was causing 3221225477 errors
        # Instead, just verify the virtual environment structure is valid
        if log_callback:
            log_callback("✅ Environment validation successful (skipped import tests)")
        return True

    def setup_bundled_environment(self):
        """Set up bundled environment - Extract next to app.exe for portability"""
        print("🔧 Setting up portable bundled environment...")
        
        if getattr(sys, 'frozen', False):
            # Running as executable - extract next to app.exe
            app_dir = Path(sys.executable).parent
        else:
            # Running as script - extract next to script
            app_dir = Path(__file__).parent
        
        venv_bundle = app_dir / "venv_bundle"
        
        if not venv_bundle.exists():
            print("❌ venv_bundle not found, falling back to normal setup")
            self._initialize_environment()
            return
        
        # Target location: NEXT TO APP.EXE (portable setup)
        target_venv = app_dir / "manim_studio_default"
        
        print(f"📁 Extracting bundled environment to: {target_venv}")
        print(f"🚀 Portable mode: Everything stays with app.exe")
        
        # Remove existing environment if it exists
        if target_venv.exists():
            print("🗑️ Removing existing environment...")
            shutil.rmtree(target_venv, ignore_errors=True)
        
        # Copy bundled environment to target location
        try:
            print("📦 Copying bundled environment...")
            shutil.copytree(venv_bundle, target_venv, dirs_exist_ok=True)
            print("✅ Bundled environment extracted successfully!")
        except Exception as e:
            print(f"❌ Failed to extract bundled environment: {e}")
            self._initialize_environment()
            return
        
        # Set up paths to the extracted environment
        if os.name == 'nt':
            self.python_path = str(target_venv / "Scripts" / "python.exe")
            self.pip_path = str(target_venv / "Scripts" / "pip.exe")
        else:
            self.python_path = str(target_venv / "bin" / "python")
            self.pip_path = str(target_venv / "bin" / "pip")
        
        # Verify extraction worked
        if not os.path.exists(self.python_path):
            print(f"❌ Python executable not found at: {self.python_path}")
            self._initialize_environment()
            return
        
        # Set up all paths for PORTABLE MODE - everything next to exe
        self.app_dir = str(app_dir)  # Next to app.exe
        self.venv_dir = str(app_dir)  # Environments next to app.exe
        self.base_dir = str(app_dir)
        
        # Set up state
        self.current_venv = "manim_studio_default"
        self.needs_setup = False  # No setup needed - everything is bundled!
        self.using_fallback = False
        self.is_frozen = True
        self.bundled_venv_dir = None
        self.bundled_available = False
        
        # Essential packages list (empty since everything is bundled)
        self.essential_packages = []
        
        # Set up logging if not already done
        if not hasattr(self, 'logger'):
            self.logger = logging.getLogger(__name__)
        
        print(f"✅ Portable bundled environment ready!")
        print(f"   📁 App directory: {self.app_dir}")
        print(f"   🐍 Python: {self.python_path}")
        print(f"   📦 Environment: {target_venv}")
        print("🚀 Ready to use - no package installation needed!")
        print("📁 Everything is portable - copy the whole folder to move the app!")
    
    def _setup_environment_after_creation(self, venv_path):
        """Set up environment after creation"""
        if os.name == 'nt':
            python_exe = os.path.join(venv_path, "Scripts", "python.exe")
            pip_exe = os.path.join(venv_path, "Scripts", "pip.exe")
        else:
            python_exe = os.path.join(venv_path, "bin", "python")
            pip_exe = os.path.join(venv_path, "bin", "pip")
            
        self.logger.info(f"Python path: {python_exe}, exists: {os.path.exists(python_exe)}")
        self.logger.info(f"Pip path: {pip_exe}, exists: {os.path.exists(pip_exe)}")
        
        if not os.path.exists(python_exe):
            self.logger.error("Python executable not found in created environment")
            return self.use_system_python_fallback()
            
        # Ensure pip is available
        if not os.path.exists(pip_exe):
            self.logger.info("Pip not found, installing...")
            try:
                # Try to install pip using ensurepip
                result = self.run_hidden_subprocess_nuitka_safe(
                    [python_exe, "-m", "ensurepip", "--upgrade"],
                    capture_output=True, 
                    text=True, 
                    timeout=60
                )
                if result.returncode != 0:
                    self.logger.error("Failed to install pip with ensurepip")
                    return self.use_system_python_fallback()
            except Exception as e:
                self.logger.error(f"Error installing pip: {e}")
                return self.use_system_python_fallback()
            
        # Activate it for further operations
        self.python_path = python_exe
        self.pip_path = pip_exe
        self.current_venv = "manim_studio_default"
        
        return True
    
    def install_single_package_with_logging(self, package, log_callback):
        """Install a single package with logging to callback"""
        try:
            # Get number of cores for CPU control
            cores = min(4, multiprocessing.cpu_count())
            
            # Create environment variables for CPU control
            env = self.get_clean_environment()
            env.update({
                "OMP_NUM_THREADS": str(cores),
                "OPENBLAS_NUM_THREADS": str(cores),
                "MKL_NUM_THREADS": str(cores),
                "NUMEXPR_NUM_THREADS": str(cores)
            })
            
            # Use the platform-appropriate startupinfo to hide console
            startupinfo = None
            creationflags = 0
            
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
                
            # Execute pip install with CPU control and stream output
            env["PYTHONUNBUFFERED"] = "1"  # ensure real-time pip output
            process = subprocess.Popen(
                [self.python_path, "-m", "pip", "install", package, "--no-cache-dir"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )

            # Stream pip output line by line to the logger
            for line in process.stdout:
                if line and log_callback:
                    log_callback(line.rstrip())
            exit_code = process.wait()

            if exit_code == 0:
                if log_callback:
                    log_callback(f"Successfully installed {package}")
                return True
            else:
                if log_callback:
                    log_callback(f"Failed to install {package}")
                return False
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error installing {package}: {str(e)}")
            return False
    
    def list_venvs(self):
        """List all available virtual environments (portable version)"""
        venvs = []
        
        # Add current environment if it's special
        if self.current_venv and self.current_venv.startswith(("system_", "current_")):
            venvs.append(self.current_venv)
        
        # Handle bundled/portable environment
        if USING_BUNDLED_ENV:
            # In portable mode, check for environment next to app.exe
            if getattr(sys, 'frozen', False):
                app_dir = Path(sys.executable).parent
            else:
                app_dir = Path(__file__).parent
            
            bundled_env = app_dir / "manim_studio_default"
            if bundled_env.exists() and self.is_valid_venv(str(bundled_env)):
                venvs.append("manim_studio_default")
            
            # Don't look in the standard venv_dir for bundled apps
            return sorted(venvs)
        
        # Regular virtual environments (non-bundled mode)
        if hasattr(self, 'venv_dir') and os.path.exists(self.venv_dir):
            for item in os.listdir(self.venv_dir):
                venv_path = os.path.join(self.venv_dir, item)
                if os.path.isdir(venv_path) and self.is_valid_venv(venv_path):
                    venvs.append(item)
                    
        return sorted(venvs)
        
    def is_valid_venv(self, venv_path):
        """Check if a directory is a valid virtual environment"""
        if os.name == 'nt':
            return (os.path.exists(os.path.join(venv_path, "Scripts", "python.exe")) and
                    os.path.exists(os.path.join(venv_path, "Scripts", "pip.exe")))
        else:
            return (os.path.exists(os.path.join(venv_path, "bin", "python")) and
                    os.path.exists(os.path.join(venv_path, "bin", "pip")))
        
    def activate_venv(self, name):
        """Activate a virtual environment"""
        if name.startswith(("system_", "current_")):
            return True
            
        if name in self.list_venvs():
            self.current_venv = name
            venv_path = os.path.join(self.venv_dir, name)
            
            if os.name == 'nt':
                scripts_path = os.path.join(venv_path, "Scripts")
                self.python_path = os.path.join(scripts_path, "python.exe")
                self.pip_path = os.path.join(scripts_path, "pip.exe")
            else:
                bin_path = os.path.join(venv_path, "bin")
                self.python_path = os.path.join(bin_path, "python")
                self.pip_path = os.path.join(bin_path, "pip")
                
            return True
        return False
    def activate_default_environment(self):
        """Activate the manim_studio_default environment (portable version)"""
        
        # Handle bundled/portable environment
        if USING_BUNDLED_ENV:
            # In portable mode, environment is next to app.exe
            if getattr(sys, 'frozen', False):
                app_dir = Path(sys.executable).parent
            else:
                app_dir = Path(__file__).parent
            
            default_venv_path = app_dir / "manim_studio_default"
        else:
            # Regular mode - environment in standard location
            default_venv_path = Path(self.venv_dir) / "manim_studio_default"
        
        if not default_venv_path.exists():
            self.logger.error(f"manim_studio_default environment not found at: {default_venv_path}")
            return False
            
        if not self.is_valid_venv(str(default_venv_path)):
            self.logger.error("manim_studio_default environment is invalid")
            return False
        
        # Set up paths
        if os.name == 'nt':
            self.python_path = str(default_venv_path / "Scripts" / "python.exe")
            self.pip_path = str(default_venv_path / "Scripts" / "pip.exe")
        else:
            self.python_path = str(default_venv_path / "bin" / "python")
            self.pip_path = str(default_venv_path / "bin" / "pip")
        
        self.current_venv = "manim_studio_default"
        self.needs_setup = False
        
        if USING_BUNDLED_ENV:
            self.logger.info(f"✅ Activated portable bundled environment: {default_venv_path}")
        else:
            self.logger.info(f"✅ Activated manim_studio_default environment: {default_venv_path}")
        return True
    def deactivate_venv(self):
        """Deactivate the current virtual environment"""
        self.current_venv = None
        self.python_path = sys.executable
        self.pip_path = "pip"
        return True

    def activate_venv_path(self, venv_path):
        """Activate a virtual environment located at an arbitrary path"""
        if not self.is_valid_venv(venv_path):
            return False

        if os.name == 'nt':
            self.python_path = os.path.join(venv_path, "Scripts", "python.exe")
            self.pip_path = os.path.join(venv_path, "Scripts", "pip.exe")
        else:
            self.python_path = os.path.join(venv_path, "bin", "python")
            self.pip_path = os.path.join(venv_path, "bin", "pip")

        self.current_venv = f"external_{os.path.basename(venv_path)}"
        return True
    
    def install_package(self, package_name, callback=None):
        """Install a package using system terminal"""
        if not self.current_venv:
            if callback:
                callback(False, "", "No virtual environment active")
            return False, "No virtual environment active"
        
        def on_install_complete(success, return_code):
            stdout = "Installation completed" if success else ""
            stderr = "" if success else f"Installation failed with code {return_code}"
            if callback:
                callback(success, stdout, stderr)
        
        # Use threading-safe command execution
        try:
            self.run_command_with_threading_fix(
                [self.pip_path, "install", package_name],
                on_complete=on_install_complete
            )
            return True, "Installation started"
        except Exception as e:
            if callback:
                callback(False, "", str(e))
            return False, str(e)
    
    def run_command_with_threading_fix(self, command, on_complete=None):
        """Execute command with proper threading for UI integration"""
        if not hasattr(self, 'parent_app') or not self.parent_app:
            # Direct execution without UI integration
            try:
                result = self.run_hidden_subprocess_nuitka_safe(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if on_complete:
                    on_complete(result.returncode == 0, result.returncode)
                return result.returncode == 0
            except Exception as e:
                if on_complete:
                    on_complete(False, -1)
                return False
        
        def run_in_thread():
            try:
                # Execute command and capture output
                result = self.run_hidden_subprocess_nuitka_safe(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=self.get_clean_environment()
                )
                
                # Stream output to parent app if available
                if hasattr(self.parent_app, 'append_terminal_output'):
                    if result.stdout:
                        self.safe_after(0, lambda: self.parent_app.append_terminal_output(result.stdout))
                    if result.stderr:
                        self.safe_after(0, lambda: self.parent_app.append_terminal_output(result.stderr))

                if on_complete:
                    self.safe_after(0, lambda: on_complete(result.returncode == 0, result.returncode))
                        
            except Exception as e:
                error_msg = f"Command execution error: {e}\n"
                self.logger.error(error_msg)
                if hasattr(self.parent_app, 'append_terminal_output'):
                    self.safe_after(0, lambda: self.parent_app.append_terminal_output(error_msg))
                if on_complete:
                    self.safe_after(0, lambda: on_complete(False, -1))
        
        # Run in background thread
        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def upgrade_pip(self, log_callback=None):
        """Upgrade pip in the current environment using system terminal"""
        if not self.current_venv:
            if log_callback:
                log_callback("No virtual environment active")
            return False
            
        try:
            if log_callback:
                log_callback("Upgrading pip...")
            
            # Create environment with proper subprocess handling
            startupinfo = None
            creationflags = 0
            
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
            
            process = subprocess.Popen(
                [self.python_path, "-m", "pip", "install", "--upgrade", "pip"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            
            # Stream output
            for line in process.stdout:
                if line and log_callback:
                    log_callback(line.rstrip())
            
            exit_code = process.wait()
            
            if exit_code == 0:
                if log_callback:
                    log_callback("Pip upgraded successfully")
                return True
            else:
                if log_callback:
                    log_callback(f"Warning: Failed to upgrade pip (exit code {exit_code})")
                return False
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error upgrading pip: {str(e)}")
            return False
    def verify_installation(self, log_callback=None):
        """Verify that the installation is working correctly using direct subprocess"""
        test_packages = ["manim", "numpy", "matplotlib", "customtkinter", "jedi"]
        
        if log_callback:
            log_callback("Verifying installation...")
        
        # Test packages directly without temporary files
        test_code = f"""
import sys
test_packages = {test_packages}
failed = []

for package in test_packages:
    try:
        __import__(package)
        print(f"✓ {{package}} - OK")
    except ImportError as e:
        print(f"✗ {{package}} - FAILED: {{e}}")
        failed.append(package)

if failed:
    print(f"Failed packages: {{failed}}")
    sys.exit(1)
else:
    print("All packages verified successfully!")
    sys.exit(0)
"""
        
        try:
            # Execute verification in the virtual environment
            startupinfo = None
            creationflags = 0
            
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
            
            process = subprocess.Popen(
                [self.python_path, "-c", test_code],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            
            # Stream output if callback provided
            if log_callback:
                for line in process.stdout:
                    if line.strip():
                        log_callback(line.strip())
            
            exit_code = process.wait()
            
            if exit_code == 0:
                if log_callback:
                    log_callback("✅ Installation verification completed successfully")
                return True
            else:
                if log_callback:
                    log_callback("❌ Installation verification failed")
                return False
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error during verification: {str(e)}")
            return False
    def check_manim_availability(self, log_callback=None):
        """Safe manim check that doesn't cause 3221225477 errors"""
        if log_callback:
            log_callback(f"Checking manim availability (safe mode)")
        
        # Instead of importing, just check if manim package exists in site-packages
        if os.name == 'nt':
            site_packages = os.path.join(os.path.dirname(self.python_path), "..", "Lib", "site-packages")
        else:
            site_packages = os.path.join(os.path.dirname(self.python_path), "..", "lib", "python*", "site-packages")
        
        site_packages = os.path.normpath(site_packages)
        
        # Look for manim directory or manim-*.dist-info
        manim_found = False
        if os.path.exists(site_packages):
            for item in os.listdir(site_packages):
                if item.startswith('manim') and (os.path.isdir(os.path.join(site_packages, item)) or 'dist-info' in item):
                    manim_found = True
                    break
        
        if manim_found:
            if log_callback:
                log_callback("✅ Manim package found in site-packages")
        else:
            if log_callback:
                log_callback("⚠️ Manim package not found - may need installation")
        
        return manim_found
    
    
    def repair_environment(self):
        """Force repair of the environment by checking and installing all missing packages"""
        self.logger.info("🔧 Repairing environment...")
        
        default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
        
        if not os.path.exists(default_venv_path) or not self.is_valid_venv(default_venv_path):
            self.logger.info("Environment doesn't exist, creating new one...")
            return self.setup_environment()
        
        # Set up paths
        if os.name == 'nt':
            self.python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
            self.pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
        else:
            self.python_path = os.path.join(default_venv_path, "bin", "python")
            self.pip_path = os.path.join(default_venv_path, "bin", "pip")
        
        # Upgrade pip first
        self.upgrade_pip_in_existing_env()
        
        # Check and install all missing packages
        missing = self.check_missing_packages()
        if missing:
            self.logger.info(f"Found {len(missing)} missing packages, installing...")
            success = self.install_missing_packages(missing)
            if success:
                self.activate_default_environment()
                self.needs_setup = False
            return success
        else:
            self.logger.info("✅ Environment is already complete!")
            self.activate_default_environment()
            self.needs_setup = False
            return True
    
    def get_environment_info(self):
        """Get detailed information about the current environment"""
        info = {
            'current_venv': self.current_venv,
            'python_path': self.python_path,
            'pip_path': self.pip_path,
            'needs_setup': self.needs_setup,
            'manim_available': self.check_manim_availability(),
            'environment_valid': False,
            'missing_packages': [],
            'bundled_available': self.bundled_available,
            'is_frozen': self.is_frozen
        }
        
        if self.current_venv:
            default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
            info['environment_valid'] = self.is_valid_venv(default_venv_path)
            
            if info['environment_valid']:
                info['missing_packages'] = self.check_missing_packages()
        
        return info
    
    def export_requirements(self, filepath):
        """Export current environment requirements to a file"""
        if not self.current_venv:
            return False
            
        try:
            result = self.run_hidden_subprocess_nuitka_safe(
                [self.pip_path, "freeze"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                with open(filepath, 'w') as f:
                    f.write(result.stdout)
                return True
            else:
                return False
                
        except Exception as e:
            self.logger.error(f"Error exporting requirements: {e}")
            return False
    
    def import_requirements(self, filepath, log_callback=None):
        """Install packages from a requirements file"""
        if not self.current_venv:
            return False
            
        if not os.path.exists(filepath):
            return False
            
        try:
            if log_callback:
                log_callback(f"Installing packages from {filepath}...")
                
            def on_install_complete(success, return_code):
                if log_callback:
                    if success:
                        log_callback("Requirements installed successfully")
                    else:
                        log_callback(f"Requirements installation failed (exit code {return_code})")
            
            self.run_command_with_threading_fix(
                [self.pip_path, "install", "-r", filepath],
                on_complete=on_install_complete
            )
            return True
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error installing requirements: {str(e)}")
            return False

    def list_packages(self, env_name=None):
        """List installed packages for the given or current environment."""
        if env_name and not env_name.startswith(("system_", "current_")):
            venv_path = os.path.join(self.venv_dir, env_name)
            if os.name == "nt":
                python_exe = os.path.join(venv_path, "Scripts", "python.exe")
            else:
                python_exe = os.path.join(venv_path, "bin", "python")
        else:
            python_exe = self.python_path

        try:
            result = self.run_hidden_subprocess_nuitka_safe(
                [python_exe, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                packages = json.loads(result.stdout)
                return True, packages
            else:
                return False, result.stderr

        except Exception as e:
            return False, str(e)

    def cleanup_old_environments(self, keep_current=True):
        """Clean up old virtual environments to save disk space"""
        cleaned = []
        
        if not os.path.exists(self.venv_dir):
            return cleaned
    
    def diagnose_architecture_issues(self):
        """Diagnose and report architecture-related issues"""
        diagnosis = {
            'system_arch': platform.machine(),
            'system_platform': platform.platform(),
            'python_arch': platform.architecture(),
            'is_64bit_system': platform.machine().endswith('64'),
            'current_python_64bit': sys.maxsize > 2**32,
            'issues': [],
            'recommendations': []
        }
        
        # Check for common issues
        if os.name == 'nt':
            if diagnosis['is_64bit_system'] and not diagnosis['current_python_64bit']:
                diagnosis['issues'].append("32-bit Python on 64-bit Windows system")
                diagnosis['recommendations'].append("Install 64-bit Python from python.org")
            
            # Check PATH for problematic entries
            path_dirs = os.environ.get('PATH', '').split(os.pathsep)
            problematic_paths = []
            for path_dir in path_dirs:
                if any(prob in path_dir.lower() for prob in ['syswow64', 'system32\\wbem']):
                    problematic_paths.append(path_dir)
            
            if problematic_paths:
                diagnosis['issues'].append(f"Problematic PATH entries: {problematic_paths}")
                diagnosis['recommendations'].append("Clean PATH to prioritize 64-bit directories")
        
        # Test current Python
        if self.python_path:
            try:
                result = self.run_hidden_subprocess_nuitka_safe(
                    [self.python_path, "-c", "import platform; print(f'{platform.machine()}-{platform.architecture()[0]}')"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    diagnosis['current_python_details'] = result.stdout.strip()
                else:
                    diagnosis['issues'].append("Cannot determine current Python architecture")
            except Exception as e:
                diagnosis['issues'].append(f"Error testing current Python: {e}")
        
        return diagnosis
    
    def fix_architecture_issues(self):
        """Attempt to fix common architecture issues"""
        diagnosis = self.diagnose_architecture_issues()
        fixes_applied = []
        
        if os.name == 'nt' and diagnosis['is_64bit_system']:
            # Try to find and use 64-bit Python
            python_64 = self.find_system_python()
            if python_64:
                # Validate it's actually 64-bit
                try:
                    result = self.run_hidden_subprocess_nuitka_safe(
                        [python_64, "-c", "import sys; print(sys.maxsize > 2**32)"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0 and "True" in result.stdout:
                        self.logger.info(f"Found 64-bit Python: {python_64}")
                        fixes_applied.append(f"Using 64-bit Python: {python_64}")
                        return python_64, fixes_applied
                except Exception as e:
                    self.logger.warning(f"Error validating 64-bit Python: {e}")
        
        return None, fixes_applied
            
        current_env_path = None
        if keep_current and self.current_venv:
            current_env_path = os.path.join(self.venv_dir, self.current_venv)
            
        for item in os.listdir(self.venv_dir):
            env_path = os.path.join(self.venv_dir, item)
            
            if os.path.isdir(env_path):
                # Don't delete current environment if keep_current is True
                if keep_current and current_env_path and os.path.samefile(env_path, current_env_path):
                    continue
                    
                # Check if it's an old environment (simple heuristic)
                if item.startswith("temp_") or "backup" in item.lower():
                    try:
                        shutil.rmtree(env_path)
                        cleaned.append(item)
                        self.logger.info(f"Cleaned up old environment: {item}")
                    except Exception as e:
                        self.logger.warning(f"Could not clean up {item}: {e}")
                        
        return cleaned
    def create_thread_safe_log_callback(self, original_callback):
        """Create a thread-safe version of a log callback"""
        import queue
        import threading
        
        if not hasattr(self, '_log_queue'):
            self._log_queue = queue.Queue()
            self._setup_log_queue_processor(original_callback)
        
        def thread_safe_callback(message):
            self._log_queue.put(message)
        
        return thread_safe_callback
    
    def _setup_log_queue_processor(self, original_callback):
        """Setup queue processor on main thread"""
        def process_queue():
            try:
                while True:
                    message = self._log_queue.get_nowait()
                    # Call original callback on main thread
                    if hasattr(self.parent_app, 'after'):
                        self.parent_app.after(0, lambda m=message: original_callback(m))
                    else:
                        original_callback(message)
            except:
                pass  # Queue empty
            
            # Schedule next check
            if hasattr(self.parent_app, 'after'):
                self.parent_app.after(100, process_queue)
        
        if hasattr(self.parent_app, 'after'):
            self.parent_app.after(100, process_queue)
    def _find_best_python(self):
        """Find the best Python executable available on the system"""
        try:
            # First try the current Python executable when not frozen
            current_python = sys.executable
            if not self.is_frozen and current_python and os.path.exists(current_python):
                self.logger.info(f"Using current Python executable: {current_python}")
                return current_python
            
            # Common Python executable names to search for
            python_names = []
            
            if os.name == 'nt':  # Windows
                python_names = [
                    "python.exe", "python3.exe", 
                    "python3.11.exe", "python3.10.exe", "python3.9.exe", "python3.8.exe"
                ]
            else:  # Unix/Linux/macOS
                python_names = [
                    "python3", "python", 
                    "python3.11", "python3.10", "python3.9", "python3.8"
                ]
            
            # Search in PATH
            for python_name in python_names:
                python_path = shutil.which(python_name)
                if python_path and os.path.exists(python_path):
                    # Skip our own executable when frozen
                    if self.is_frozen:
                        try:
                            if os.path.samefile(python_path, sys.executable):
                                self.logger.debug("Skipping frozen executable candidate")
                                continue
                        except Exception:
                            if os.path.abspath(python_path) == os.path.abspath(sys.executable):
                                continue

                    # Verify it's a working Python installation
                    try:
                        result = subprocess.run(
                            [python_path, "--version"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode == 0:
                            self.logger.info(f"Found Python: {python_path} - {result.stdout.strip()}")
                            return python_path
                    except Exception as e:
                        self.logger.warning(f"Failed to verify Python {python_path}: {e}")
                        continue
            
            # If still not found, try common installation paths
            common_paths = []
            
            if os.name == 'nt':  # Windows
                # Check common Windows Python installation paths
                for version in ['311', '310', '39', '38']:
                    common_paths.extend([
                        f"C:\\Python{version}\\python.exe",
                        f"C:\\Program Files\\Python {version[0]}.{version[1:]}\\python.exe",
                        f"C:\\Program Files (x86)\\Python {version[0]}.{version[1:]}\\python.exe",
                        os.path.expanduser(f"~\\AppData\\Local\\Programs\\Python\\Python{version}\\python.exe")
                    ])
            else:  # Unix/Linux/macOS
                common_paths = [
                    "/usr/bin/python3", "/usr/bin/python",
                    "/usr/local/bin/python3", "/usr/local/bin/python",
                    "/opt/python3/bin/python3", "/opt/python/bin/python"
                ]
            
            for path in common_paths:
                if os.path.exists(path):
                    # Skip our own executable when frozen
                    if self.is_frozen:
                        try:
                            if os.path.samefile(path, sys.executable):
                                self.logger.debug("Skipping frozen executable candidate")
                                continue
                        except Exception:
                            if os.path.abspath(path) == os.path.abspath(sys.executable):
                                continue

                    try:
                        result = subprocess.run(
                            [path, "--version"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode == 0:
                            self.logger.info(f"Found Python at common path: {path} - {result.stdout.strip()}")
                            return path
                    except Exception as e:
                        continue
            
            # Last resort: try 'python' command directly
            try:
                result = subprocess.run(
                    ["python", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    python_path = shutil.which("python")
                    if python_path:
                        if self.is_frozen:
                            try:
                                if os.path.samefile(python_path, sys.executable):
                                    self.logger.debug("Skipping frozen executable candidate")
                                    python_path = None
                            except Exception:
                                if os.path.abspath(python_path) == os.path.abspath(sys.executable):
                                    python_path = None
                        if python_path:
                            self.logger.info(f"Using 'python' command: {python_path}")
                            return python_path
            except Exception:
                pass
            
            self.logger.error("No suitable Python installation found")
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding Python executable: {e}")
            return None
    def get_pip_command(self):
        """Get pip command for current environment"""
        if not self.current_venv:
            return ["pip"]
        
        # Return list for subprocess
        return [self.pip_path]
    def _auto_detect_environment(self):
        """Auto-detect and activate existing manim_studio_default environment"""
        default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
        
        if os.path.exists(default_venv_path) and self.is_valid_venv(default_venv_path):
            self.logger.info(f"Found existing manim_studio_default environment")
            
            # Set up paths
            if os.name == 'nt':
                self.python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
                self.pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
            else:
                self.python_path = os.path.join(default_venv_path, "bin", "python")
                self.pip_path = os.path.join(default_venv_path, "bin", "pip")
            
            # Verify executables exist
            if os.path.exists(self.python_path) and os.path.exists(self.pip_path):
                # Check if manim is available and working
                if self.check_manim_availability():
                    self.logger.info("✅ manim_studio_default environment is ready")
                    self.current_venv = "manim_studio_default"
                    self.needs_setup = False
                else:
                    self.logger.info("manim_studio_default exists but manim needs repair/installation")
                    self.current_venv = "manim_studio_default"
                    # needs_setup stays True to trigger repair
            else:
                self.logger.warning("manim_studio_default environment has missing executables")
    def fix_pycairo_installation(self, log_callback=None):
        """Attempt to fix pycairo installation issues"""
        try:
            if log_callback:
                log_callback("Reinstalling pycairo...")
            
            # Try reinstalling pycairo
            cmd = [self.python_path, "-m", "pip", "install", "--force-reinstall", "--no-cache-dir", "pycairo"]
            result = self.run_hidden_subprocess_nuitka_safe(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                if log_callback:
                    log_callback("✅ pycairo reinstalled successfully")
                return True
            else:
                if log_callback:
                    log_callback("⚠️ pycairo reinstallation had issues")
                return False
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error fixing pycairo: {e}")
            return False
    
    def fix_manimpango_installation(self, log_callback=None):
        """Attempt to fix ManimPango installation issues"""
        try:
            if log_callback:
                log_callback("Reinstalling ManimPango...")
            
            # Try installing Cython first (common fix)
            cython_cmd = [self.python_path, "-m", "pip", "install", "Cython"]
            cython_result = self.run_hidden_subprocess_nuitka_safe(
                cython_cmd,
                capture_output=True,
                text=True,
                timeout=120,
                encoding='utf-8',
                errors='replace'
            )
            
            # Then reinstall ManimPango
            cmd = [self.python_path, "-m", "pip", "install", "--force-reinstall", "--no-cache-dir", "ManimPango"]
            result = self.run_hidden_subprocess_nuitka_safe(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                if log_callback:
                    log_callback("✅ ManimPango reinstalled successfully")
                return True
            else:
                if log_callback:
                    log_callback("⚠️ ManimPango reinstallation had issues")
                return False
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error fixing ManimPango: {e}")
            return False
    def _get_config_file_path(self):
        """Get path to environment config file"""
        return os.path.join(self.app_dir, "environment_config.json")
    
    def _get_environment_hash(self, env_path):
        """Generate a hash of the environment to detect changes"""
        import hashlib
        
        # Create hash based on environment directory modification time and critical files
        hash_input = ""
        
        try:
            # Add environment directory modification time
            if os.path.exists(env_path):
                hash_input += str(os.path.getmtime(env_path))
            
            # Add Python executable modification time
            python_exe = os.path.join(env_path, "Scripts" if os.name == 'nt' else "bin", "python.exe" if os.name == 'nt' else "python")
            if os.path.exists(python_exe):
                hash_input += str(os.path.getmtime(python_exe))
            
            # Add site-packages directory modification time (where packages are installed)
            site_packages = os.path.join(env_path, "Lib", "site-packages" if os.name == 'nt' else "lib/python*/site-packages")
            if os.name != 'nt':
                # For Unix, we need to find the actual python version directory
                lib_dir = os.path.join(env_path, "lib")
                if os.path.exists(lib_dir):
                    for item in os.listdir(lib_dir):
                        if item.startswith("python") and os.path.isdir(os.path.join(lib_dir, item)):
                            site_packages = os.path.join(lib_dir, item, "site-packages")
                            break
            
            if os.path.exists(site_packages):
                hash_input += str(os.path.getmtime(site_packages))
            
            return hashlib.md5(hash_input.encode()).hexdigest()
        except Exception as e:
            self.logger.warning(f"Error generating environment hash: {e}")
            return ""
    
    def _load_environment_config(self):
        """Load environment configuration from file"""
        config_file = self._get_config_file_path()
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Error loading environment config: {e}")
        
        return {}
    
    def _save_environment_config(self, config):
        """Save environment configuration to file"""
        config_file = self._get_config_file_path()
        
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving environment config: {e}")
    
    def _is_environment_validated(self, env_name):
        """Check if environment has been validated recently and hasn't changed"""
        config = self._load_environment_config()
        env_config = config.get(env_name, {})
        
        if not env_config:
            return False
        
        # Check if we have validation info
        last_validated = env_config.get('last_validated')
        last_hash = env_config.get('environment_hash')
        manim_working = env_config.get('manim_working', False)
        
        if not all([last_validated, last_hash]):
            return False
        
        # Check if environment has changed since last validation
        env_path = os.path.join(self.venv_dir, env_name)
        current_hash = self._get_environment_hash(env_path)
        
        if current_hash != last_hash:
            self.logger.info(f"Environment {env_name} has changed since last validation")
            return False
        
        # Check if validation is recent (within last 24 hours) and manim was working
        import time
        if time.time() - last_validated < 86400 and manim_working:  # 24 hours
            self.logger.info(f"✅ Environment {env_name} validated from cache (manim working)")
            return True
        
        return False
    
    def _mark_environment_validated(self, env_name, manim_working):
        """Mark environment as validated with current status"""
        config = self._load_environment_config()
        
        env_path = os.path.join(self.venv_dir, env_name)
        current_hash = self._get_environment_hash(env_path)
        
        import time
        config[env_name] = {
            'last_validated': time.time(),
            'environment_hash': current_hash,
            'manim_working': manim_working,
            'validation_version': '1.0'  # For future compatibility
        }
        
        self._save_environment_config(config)
        self.logger.info(f"Marked environment {env_name} as validated (manim: {'working' if manim_working else 'not working'})")
    def validate_and_repair_environment(self, log_callback=None):
        """Enhanced validation with automatic repair for corrupted environments"""
        default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
        
        if not os.path.exists(default_venv_path):
            if log_callback:
                log_callback("❌ Default environment not found")
            return False
        
        # Check for basic structure
        if not self.is_valid_venv(default_venv_path):
            if log_callback:
                log_callback("❌ Environment structure invalid, attempting repair...")
            return self.repair_corrupted_environment(default_venv_path, log_callback)
        
        # Test if Python executable works (catches 3221225477 errors)
        try:
            test_result = self.run_hidden_subprocess_nuitka_safe(
                [self.python_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if test_result.returncode != 0:
                if log_callback:
                    log_callback(f"❌ Python executable test failed: {test_result.stderr}")
                return self.repair_corrupted_environment(default_venv_path, log_callback)
                
        except Exception as e:
            if log_callback:
                log_callback(f"❌ Critical error testing Python: {str(e)}")
            return self.repair_corrupted_environment(default_venv_path, log_callback)
        
        # Test manim import specifically (main cause of environment issues)
        try:
            manim_test = self.run_hidden_subprocess_nuitka_safe(
                [self.python_path, "-c", "import manim; print('MANIM_OK')"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if manim_test.returncode != 0 or "MANIM_OK" not in manim_test.stdout:
                if log_callback:
                    log_callback("❌ Manim import failed, repairing environment...")
                # Force reinstall manim and dependencies
                self.force_reinstall_manim(log_callback)
                
        except Exception as e:
            if log_callback:
                log_callback(f"❌ Manim test failed: {str(e)}")
            return False
        
        if log_callback:
            log_callback("✅ Environment validation successful")
        return True
    def repair_corrupted_environment(self, env_path, log_callback=None):
        """Repair corrupted environment by recreating critical components"""
        try:
            if log_callback:
                log_callback("🔧 Attempting environment repair...")
            
            # Step 1: Backup and clear problematic cache files
            cache_dirs = [
                os.path.join(env_path, "Lib", "site-packages", "__pycache__"),
                os.path.join(env_path, "Scripts", "__pycache__"),
                os.path.join(env_path, "pyvenv.cfg.bak")
            ]
            
            for cache_dir in cache_dirs:
                if os.path.exists(cache_dir):
                    try:
                        if os.path.isdir(cache_dir):
                            shutil.rmtree(cache_dir, ignore_errors=True)
                        else:
                            os.remove(cache_dir)
                    except Exception as e:
                        if log_callback:
                            log_callback(f"Warning: Could not clear {cache_dir}: {e}")
            
            # Step 2: Regenerate pyvenv.cfg if corrupted
            pyvenv_cfg = os.path.join(env_path, "pyvenv.cfg")
            if os.path.exists(pyvenv_cfg):
                try:
                    with open(pyvenv_cfg, 'r') as f:
                        content = f.read()
                    if len(content.strip()) < 10:  # Corrupted file
                        os.remove(pyvenv_cfg)
                        self.regenerate_pyvenv_cfg(env_path)
                except Exception:
                    os.remove(pyvenv_cfg)
                    self.regenerate_pyvenv_cfg(env_path)
            
            # Step 3: Fix permissions (Windows specific)
            if os.name == 'nt':
                try:
                    import stat
                    scripts_dir = os.path.join(env_path, "Scripts")
                    for file in os.listdir(scripts_dir):
                        file_path = os.path.join(scripts_dir, file)
                        if file.endswith('.exe'):
                            os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                except Exception as e:
                    if log_callback:
                        log_callback(f"Warning: Permission fix failed: {e}")
            
            # Step 4: Test repair
            if self.is_valid_venv(env_path):
                if log_callback:
                    log_callback("✅ Environment repair successful")
                return True
            else:
                if log_callback:
                    log_callback("❌ Repair failed, environment needs recreation")
                return False
                
        except Exception as e:
            if log_callback:
                log_callback(f"❌ Repair process failed: {str(e)}")
            return False
    def force_reinstall_manim(self, log_callback=None):
        """Force reinstall manim and related packages to fix DLL issues"""
        try:
            if log_callback:
                log_callback("🔄 Force reinstalling manim and dependencies...")
            
            # Critical packages that often cause 3221225477 errors
            critical_packages = [
                "manim",
                "numpy",
                "opencv-python", 
                "Pillow",
                "moderngl",
                "pycairo",
                "manimpango",
                "mapbox-earcut"  # Common cause of DLL errors
            ]
            
            pip_cmd = [self.pip_path, "install", "--force-reinstall", "--no-cache-dir"]
            
            for package in critical_packages:
                try:
                    cmd = pip_cmd + [package]
                    result = self.run_hidden_subprocess_nuitka_safe(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    
                    if result.returncode == 0:
                        if log_callback:
                            log_callback(f"✅ Reinstalled {package}")
                    else:
                        if log_callback:
                            log_callback(f"⚠️ Failed to reinstall {package}: {result.stderr}")
                            
                except Exception as e:
                    if log_callback:
                        log_callback(f"❌ Error reinstalling {package}: {str(e)}")
            
            return True
            
        except Exception as e:
            if log_callback:
                log_callback(f"❌ Force reinstall failed: {str(e)}")
            return False
    def regenerate_pyvenv_cfg(self, env_path):
        """Regenerate pyvenv.cfg file for corrupted environments"""
        try:
            python_exe = self.find_system_python()
            if not python_exe:
                return False
            
            # Get Python version info
            version_result = self.run_hidden_subprocess_nuitka_safe(
                [python_exe, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True,
                text=True
            )
            
            if version_result.returncode != 0:
                return False
            
            version = version_result.stdout.strip()
            python_home = os.path.dirname(os.path.dirname(python_exe))
            
            pyvenv_content = f"""home = {python_home}
include-system-site-packages = false
version = {version}
executable = {python_exe}
command = {python_exe} -m venv {env_path}
"""
            
            pyvenv_cfg = os.path.join(env_path, "pyvenv.cfg")
            with open(pyvenv_cfg, 'w') as f:
                f.write(pyvenv_content)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to regenerate pyvenv.cfg: {e}")
            return False
    def get_python_command(self):
        """Get the Python command as a list for subprocess execution"""
        return [self.python_path]

    def get_pip_command(self):
        """Get the pip command as a list for subprocess execution"""  
        return [self.pip_path]
    def run_with_streaming_output(self, command, log_callback=None, on_complete=None, timeout=None, env=None):
        """Run subprocess with line-buffered streaming output"""
        
        def enqueue_output(pipe, queue, stream_name):
            """Put complete lines from pipe into queue"""
            try:
                line_buffer = ""
                while True:
                    char = pipe.read(1)
                    if not char:
                        # End of stream - flush any remaining buffer
                        if line_buffer.strip():
                            queue.put((stream_name, line_buffer.strip()))
                        break
                    
                    line_buffer += char
                    
                    # When we hit a newline, send the complete line
                    if char == '\n':
                        if line_buffer.strip():  # Only send non-empty lines
                            queue.put((stream_name, line_buffer.strip()))
                        line_buffer = ""
                        
                pipe.close()
            except Exception as e:
                queue.put((stream_name, f"Stream error: {e}"))

        # Configure for Windows console hiding
        startupinfo = None
        creationflags = 0
        
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        
        try:
            # Start the process
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,  # Unbuffered for character-by-character reading
                universal_newlines=True,
                encoding='utf-8',           # FIXED: Explicit UTF-8 encoding
                errors='replace',           # FIXED: Replace problematic characters
                startupinfo=startupinfo,
                creationflags=creationflags,
                env=env
            )
            
            # Create queues for stdout and stderr
            stdout_queue = Queue()
            stderr_queue = Queue()
            
            # Start threads to read output
            stdout_thread = threading.Thread(
                target=enqueue_output, 
                args=(process.stdout, stdout_queue, 'stdout'),
                daemon=True
            )
            stderr_thread = threading.Thread(
                target=enqueue_output, 
                args=(process.stderr, stderr_queue, 'stderr'),
                daemon=True
            )
            
            stdout_thread.start()
            stderr_thread.start()
            
            # Monitor output in real-time
            start_time = time.time()
            all_output = []
            
            while True:
                # Check if process is done
                return_code = process.poll()
                
                # Check for timeout
                if timeout and (time.time() - start_time) > timeout:
                    process.terminate()
                    if log_callback:
                        log_callback("⚠️ Process timed out", "warning")
                    break
                
                # Read available output
                output_received = False
                
                # Check stdout
                try:
                    while True:
                        stream_name, line = stdout_queue.get_nowait()
                        if log_callback and line.strip():  # Only send non-empty lines
                            # Determine message type
                            if "error" in line.lower() or "failed" in line.lower():
                                log_callback(line, "error")
                            elif "✅" in line or "success" in line.lower() or "File ready" in line:
                                log_callback(line, "success")
                            elif "INFO" in line:
                                log_callback(line, "info")
                            else:
                                log_callback(line)
                        all_output.append(('stdout', line))
                        output_received = True
                except Empty:
                    pass
                
                # Check stderr
                try:
                    while True:
                        stream_name, line = stderr_queue.get_nowait()
                        if log_callback and line.strip():  # Only send non-empty lines
                            # Clean up stderr formatting
                            clean_line = line.replace("STDERR: ", "")
                            if clean_line.strip():
                                log_callback(clean_line, "error")
                        all_output.append(('stderr', line))
                        output_received = True
                except Empty:
                    pass
                
                # If process is done and no more output, break
                if return_code is not None and not output_received:
                    time.sleep(0.1)
                    # Try once more for remaining output
                    try:
                        while True:
                            stream_name, line = stdout_queue.get_nowait()
                            if log_callback and line.strip():
                                log_callback(line)
                            all_output.append(('stdout', line))
                    except Empty:
                        pass
                    try:
                        while True:
                            stream_name, line = stderr_queue.get_nowait()
                            if log_callback and line.strip():
                                clean_line = line.replace("STDERR: ", "")
                                if clean_line.strip():
                                    log_callback(clean_line, "error")
                            all_output.append(('stderr', line))
                    except Empty:
                        pass
                    break
                
                # Small delay to prevent busy waiting
                time.sleep(0.01)
            
            # Wait for process to complete
            final_return_code = process.wait()
            
            # Wait for threads to finish
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            
            # Call completion callback
            if on_complete:
                success = final_return_code == 0
                on_complete(success, final_return_code)
            
            return final_return_code, all_output
            
        except Exception as e:
            if log_callback:
                log_callback(f"❌ Process execution error: {e}", "error")
            if on_complete:
                on_complete(False, -1)
            return -1, [('error', str(e))]
    def run_command_streaming(self, command, log_callback=None, on_complete=None, timeout=300):
        """Execute command with real-time output streaming"""
        if not self.current_venv:
            if log_callback:
                log_callback("No virtual environment active", "warning")
            if on_complete:
                on_complete(False, -1)
            return False
        
        env = self.get_clean_environment()
        
        def run_in_thread():
            return_code, output = self.run_with_streaming_output(
                command,
                log_callback=log_callback,
                timeout=timeout,
                env=env
            )
            
            if on_complete:
                on_complete(return_code == 0, return_code)
        
        # Run in background thread
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        return True
    def run_command_streaming(self, command, log_callback=None, on_complete=None, timeout=300):
        """Execute command with real-time output streaming"""
        if not self.current_venv:
            if log_callback:
                log_callback("No virtual environment active")
            if on_complete:
                on_complete(False, -1)
            return False
        
        env = self.get_clean_environment()
        
        def run_in_thread():
            return_code, output = self.run_with_streaming_output(
                command,
                log_callback=log_callback,
                timeout=timeout,
                env=env
            )
            
            if on_complete:
                on_complete(return_code == 0, return_code)
        
        # Run in background thread to prevent UI blocking
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        return True
class CallbackHandler(logging.Handler):
    """Custom logging handler that calls a callback function"""
    
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        
    def emit(self, record):
        if self.callback:
            try:
                self.callback(self.format(record))
            except Exception:
                pass
            
class IntelliSenseEngine:
    """Advanced IntelliSense engine using Jedi for Python autocompletion"""
    
    def __init__(self, editor):
        self.editor = editor
        self.completions = []
        
        if JEDI_AVAILABLE:
            try:
                # Try to create Jedi environment
                self.environment = jedi.create_environment()
            except:
                self.environment = None
        else:
            self.environment = None
            
        # Fallback completion lists
        self.python_keywords = [
            'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
            'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
            'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
            'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return',
            'try', 'while', 'with', 'yield'
        ]
        
        self.python_builtins = [
            'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray', 'bytes',
            'callable', 'chr', 'classmethod', 'compile', 'complex', 'delattr',
            'dict', 'dir', 'divmod', 'enumerate', 'eval', 'exec', 'filter',
            'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr',
            'hash', 'help', 'hex', 'id', 'input', 'int', 'isinstance',
            'issubclass', 'iter', 'len', 'list', 'locals', 'map', 'max',
            'memoryview', 'min', 'next', 'object', 'oct', 'open', 'ord',
            'pow', 'print', 'property', 'range', 'repr', 'reversed', 'round',
            'set', 'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum',
            'super', 'tuple', 'type', 'vars', 'zip'
        ]
        
        self.manim_completions = [
            'Scene', 'ThreeDScene', 'MovingCameraScene', 'ZoomedScene',
            'Mobject', 'VMobject', 'Group', 'VGroup',
            'Circle', 'Square', 'Rectangle', 'Triangle', 'Polygon',
            'Text', 'Tex', 'MathTex', 'Title',
            'Line', 'Arrow', 'Vector', 'DoubleArrow',
            'NumberPlane', 'Axes', 'ThreeDAxes',
            'Create', 'Write', 'DrawBorderThenFill', 'FadeIn', 'FadeOut',
            'Transform', 'ReplacementTransform', 'TransformFromCopy',
            'ShowCreation', 'ShowIncreasingSubsets', 'ShowSubmobjectsOneByOne',
            'UP', 'DOWN', 'LEFT', 'RIGHT', 'ORIGIN',
            'RED', 'BLUE', 'GREEN', 'YELLOW', 'ORANGE', 'PURPLE', 'WHITE', 'BLACK'
        ]
        
    def get_completions(self, code, line, column, prefix=""):
        """Get completions for the current cursor position"""
        if JEDI_AVAILABLE and self.environment:
            try:
                script = jedi.Script(
                    code=code,
                    line=line + 1,  # Jedi uses 1-based line numbers
                    column=column,
                    environment=self.environment
                )
                completions = script.completions()
                
                # Convert Jedi completions to our format
                result = []
                for comp in completions:
                    result.append({
                        'name': comp.name,
                        'type': comp.type,
                        'description': comp.docstring() if hasattr(comp, 'docstring') else "",
                        'detail': f"{comp.type}" if comp.type else ""
                    })
                return result
            except Exception as e:
                logger.error(f"Jedi completion error: {e}")
                
        # Fallback to simple prefix matching
        return self.get_fallback_completions(prefix)
        
    def get_fallback_completions(self, prefix):
        """Fallback completions when Jedi is not available"""
        prefix_lower = prefix.lower()
        completions = []
        
        # Add Python keywords and builtins
        for word in self.python_keywords + self.python_builtins + self.manim_completions:
            if word.lower().startswith(prefix_lower):
                completions.append({
                    'name': word,
                    'type': 'keyword' if word in self.python_keywords else 'builtin',
                    'description': f"Python {word}",
                    'detail': ''
                })
                
        return completions
    
    def get_signature_help(self, code, line, column):
        """Get function signature help"""
        if JEDI_AVAILABLE and self.environment:
            try:
                script = jedi.Script(
                    code=code,
                    line=line + 1,
                    column=column,
                    environment=self.environment
                )
                signatures = script.get_signatures()
                
                if signatures:
                    sig = signatures[0]
                    return {
                        'label': str(sig),
                        'documentation': sig.docstring() if hasattr(sig, 'docstring') else ""
                    }
            except Exception as e:
                logger.error(f"Signature help error: {e}")
        return None


class AutocompletePopup(tk.Toplevel):
    """Professional autocomplete popup window"""
    
    def __init__(self, parent, editor):
        super().__init__(parent)
        self.editor = editor
        self.overrideredirect(True)
        self.configure(bg=VSCODE_COLORS["surface"])
        self.lift()
        self.withdraw()  # Start hidden
        
        # Create frame with border
        self.frame = tk.Frame(
            self,
            bg=VSCODE_COLORS["surface"],
            relief="solid",
            borderwidth=1
        )
        self.frame.pack(fill="both", expand=True)
        
        # Create listbox for completions
        self.listbox = tk.Listbox(
            self.frame,
            height=8,
            font=("Consolas", 11),
            bg=VSCODE_COLORS["surface"],
            fg=VSCODE_COLORS["text"],
            selectbackground=VSCODE_COLORS["primary"],
            selectforeground=VSCODE_COLORS["text_bright"],
            borderwidth=0,
            highlightthickness=0,
            activestyle="none"
        )
        
        # Scrollbar
        self.scrollbar = tk.Scrollbar(self.frame, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=self.scrollbar.set)
        
        self.listbox.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Store completions
        self.completions = []
        self.selected_index = 0
        
        # Bind events
        self.listbox.bind("<Double-Button-1>", self.on_select)
        self.listbox.bind("<Return>", self.on_select)
        self.listbox.bind("<Tab>", self.on_select)
        self.bind("<Escape>", self.hide)
        
    def show_completions(self, completions, x, y, prefix=""):
        """Show completions at specified position"""
        self.completions = completions
        self.listbox.delete(0, tk.END)
        
        if not completions:
            self.hide()
            return False
            
        # Filter and sort completions by prefix
        if prefix:
            filtered = [c for c in completions if c['name'].lower().startswith(prefix.lower())]
            completions = filtered
            
        for comp in completions:
            # Format completion with type information
            display_text = comp['name']
            if comp.get('type'):
                display_text += f" ({comp['type']})"
            self.listbox.insert(tk.END, display_text)
            
        if completions:
            self.listbox.selection_set(0)
            self.selected_index = 0
            
            # Calculate popup size and position
            height = min(len(completions) * 20 + 10, 170)
            width = 400
            
            # Ensure popup stays on screen
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            
            if x + width > screen_width:
                x = screen_width - width - 10
            if y + height > screen_height:
                y = y - height - 25
                
            self.geometry(f"{width}x{height}+{x}+{y}")
            self.deiconify()
            self.lift()
            return True
        return False
    
    def navigate(self, direction):
        """Navigate through completion list"""
        if not self.completions:
            return
            
        current = self.listbox.curselection()
        if current:
            index = current[0] + direction
        else:
            index = 0 if direction > 0 else len(self.completions) - 1
            
        # Wrap around
        if index < 0:
            index = len(self.completions) - 1
        elif index >= len(self.completions):
            index = 0
            
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(index)
        self.listbox.see(index)
        self.selected_index = index
    
    def on_select(self, event=None):
        """Handle completion selection"""
        if self.completions and self.selected_index < len(self.completions):
            completion = self.completions[self.selected_index]
            self.editor.insert_completion(completion['name'])
        self.hide()
        
    def hide(self, event=None):
        """Hide the autocomplete popup"""
        self.withdraw()
        
    def get_selected_completion(self):
        """Get currently selected completion"""
        if self.completions and self.selected_index < len(self.completions):
            return self.completions[self.selected_index]
        return None


class SignatureHelpPopup(tk.Toplevel):
    """Function signature help popup"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=VSCODE_COLORS["surface_light"])
        self.withdraw()
        
        # Create frame with border
        self.frame = tk.Frame(
            self,
            bg=VSCODE_COLORS["surface_light"],
            relief="solid",
            borderwidth=1
        )
        self.frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        self.label = tk.Label(
            self.frame,
            font=("Consolas", 10),
            bg=VSCODE_COLORS["surface_light"],
            fg=VSCODE_COLORS["text"],
            padx=10,
            pady=5,
            anchor="w",
            justify="left"
        )
        self.label.pack(fill="both", expand=True)
        
    def show_signature(self, signature_info, x, y):
        """Show function signature at position"""
        if signature_info:
            text = signature_info['label']
            self.label.configure(text=text)
            
            # Calculate size
            self.update_idletasks()
            width = self.label.winfo_reqwidth() + 20
            height = self.label.winfo_reqheight() + 10
            
            # Ensure stays on screen
            screen_width = self.winfo_screenwidth()
            if x + width > screen_width:
                x = screen_width - width - 10
                
            self.geometry(f"{width}x{height}+{x}+{y-height-5}")
            self.deiconify()
            self.lift()
            
    def hide(self):
        """Hide signature popup"""
        self.withdraw()


class EnhancedPythonEditor(tk.Text):
    """Enhanced Python editor with advanced IntelliSense and features"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        # Initialize editor state
        self.parent_app = None
        self.syntax_timer = None
        self.last_content = ""
        self.line_count = 1
        
        # Configure editor appearance
        self.configure(
            bg=VSCODE_COLORS["background"],
            fg=VSCODE_COLORS["text"],
            insertbackground=VSCODE_COLORS["text"],
            selectbackground=VSCODE_COLORS["selection"],
            selectforeground=VSCODE_COLORS["text_bright"],
            bd=0,
            highlightthickness=0,
            wrap="none",
            undo=True,
            maxundo=50,
            tabs="4",
            padx=10,
            pady=10
        )
        
        # Initialize IntelliSense
        self.intellisense = IntelliSenseEngine(self)
        self.autocomplete_popup = AutocompletePopup(self.master, self)
        self.signature_popup = SignatureHelpPopup(self.master)
        
        # Completion state
        self.completion_start_pos = None
        self.completion_prefix = ""
        self.is_completing = False
        self.auto_completion_enabled = True
        
        # Auto-completion delay
        self.autocomplete_delay = 500  # ms
        self.autocomplete_timer = None
        
        # Setup syntax highlighting
        self.setup_syntax_highlighting()
        
        # Configure tags for syntax highlighting
        self.configure_tags()
        
        # Bind events
        self.bind_events()
        
        # Initialize features
        self.setup_features()
        
    def setup_syntax_highlighting(self):
        """Setup advanced syntax highlighting patterns"""
        self.syntax_patterns = [
            # Comments (must be first to avoid conflicts)
            (r'#.*$', 'comment'),
            
            # Strings (various types)
            (r'"""([^"\\]|\\.)*"""', 'string'),
            (r"'''([^'\\]|\\.)*'''", 'string'),
            (r'"([^"\\]|\\.)*"', 'string'),
            (r"'([^'\\]|\\.)*'", 'string'),
            (r'r"[^"]*"', 'string'),
            (r"r'[^']*'", 'string'),
            (r'f"[^"]*"', 'string'),
            (r"f'[^']*'", 'string'),
            
            # Numbers
            (r'\b\d+\.?\d*([eE][+-]?\d+)?\b', 'number'),
            (r'\b0[xX][0-9a-fA-F]+\b', 'number'),
            (r'\b0[oO][0-7]+\b', 'number'),
            (r'\b0[bB][01]+\b', 'number'),
            
            # Keywords
            (r'\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b', 'keyword'),
            
            # Built-in functions and types
            (r'\b(abs|all|any|ascii|bin|bool|bytearray|bytes|callable|chr|classmethod|compile|complex|delattr|dict|dir|divmod|enumerate|eval|exec|filter|float|format|frozenset|getattr|globals|hasattr|hash|help|hex|id|input|int|isinstance|issubclass|iter|len|list|locals|map|max|memoryview|min|next|object|oct|open|ord|pow|print|property|range|repr|reversed|round|set|setattr|slice|sorted|staticmethod|str|sum|super|tuple|type|vars|zip)\b', 'builtin'),
            
            # Exception classes
            (r'\b(ArithmeticError|AssertionError|AttributeError|BaseException|BlockingIOError|BrokenPipeError|BufferError|BytesWarning|ChildProcessError|ConnectionAbortedError|ConnectionError|ConnectionRefusedError|ConnectionResetError|DeprecationWarning|EOFError|Ellipsis|EnvironmentError|Exception|FileExistsError|FileNotFoundError|FloatingPointError|FutureWarning|GeneratorExit|IOError|ImportError|ImportWarning|IndentationError|IndexError|InterruptedError|IsADirectoryError|KeyError|KeyboardInterrupt|LookupError|MemoryError|ModuleNotFoundError|NameError|NotADirectoryError|NotImplemented|NotImplementedError|OSError|OverflowError|PendingDeprecationWarning|PermissionError|ProcessLookupError|RecursionError|ReferenceError|ResourceWarning|RuntimeError|RuntimeWarning|StopAsyncIteration|StopIteration|SyntaxError|SyntaxWarning|SystemError|SystemExit|TabError|TimeoutError|TypeError|UnboundLocalError|UnicodeDecodeError|UnicodeEncodeError|UnicodeError|UnicodeTranslateError|UnicodeWarning|UserWarning|ValueError|Warning|WindowsError|ZeroDivisionError)\b', 'exception'),
            
            # Decorators
            (r'@\w+', 'decorator'),
            
            # Import statements
            (r'\b(import|from)\b', 'import'),
            
            # Class definitions
            (r'\bclass\s+([a-zA-Z_]\w*)', 'class'),
            
            # Function definitions
            (r'\bdef\s+([a-zA-Z_]\w*)', 'function'),
            
            # Magic methods
            (r'\b__\w+__\b', 'magic'),
            
            # Self keyword
            (r'\bself\b', 'self'),
            
            # Constants (uppercase variables)
            (r'\b[A-Z_][A-Z0-9_]*\b', 'constant'),
            
            # Operators
            (r'[+\-*/%=<>!&|^~@]', 'operator'),
            (r'\b(and|or|not|in|is)\b', 'operator'),
        ]
        
    def configure_tags(self):
        """Configure text tags for syntax highlighting"""
        # Configure syntax highlighting tags
        for name, color in SYNTAX_COLORS.items():
            self.tag_configure(name, foreground=color)
            
        # Configure special tags
        self.tag_configure("current_line", background=VSCODE_COLORS["current_line"])
        self.tag_configure("bracket_match", background=VSCODE_COLORS["bracket_match"])
        self.tag_configure("find_match", background=VSCODE_COLORS["find_match"])
        self.tag_configure("find_current", background=VSCODE_COLORS["find_current"])
        
    def bind_events(self):
        """Bind events for editor functionality"""
        # Text editing events
        self.bind('<KeyRelease>', self.on_text_change)
        self.bind('<Button-1>', self.on_click)
        self.bind('<ButtonRelease-1>', self.on_click)
        
        # IntelliSense events
        self.bind('<Control-space>', self.trigger_autocomplete)
        self.bind('<KeyPress>', self.on_key_press)
        
        # Special key combinations
        self.bind('<Control-f>', self.show_find_dialog)
        self.bind('<Control-h>', self.show_replace_dialog)
        self.bind('<Control-d>', self.duplicate_line)
        self.bind('<Control-l>', self.select_line)
        self.bind('<Control-slash>', self.toggle_comment)
        self.bind('<Control-bracketright>', self.indent_selection)
        self.bind('<Control-bracketleft>', self.unindent_selection)
        self.bind('<Control-k>', self.delete_line)
        self.bind('<Alt-Up>', self.move_line_up)
        self.bind('<Alt-Down>', self.move_line_down)
        
        # Tab and return handling
        self.bind('<Tab>', self.handle_tab)
        self.bind('<Shift-Tab>', self.handle_shift_tab)
        self.bind('<Return>', self.handle_return)
        self.bind('<BackSpace>', self.handle_backspace)
        
        # Bracket matching
        self.bind('<KeyPress>', self.check_bracket_match, add=True)
        
    def setup_features(self):
        """Setup advanced editor features"""
        # Bracket pairs
        self.bracket_pairs = {
            '(': ')',
            '[': ']',
            '{': '}',
            '"': '"',
            "'": "'"
        }
        
        # Initialize current line highlighting
        self.highlight_current_line()
        
    def on_key_press(self, event):
        """Handle key press events for IntelliSense"""
        # Handle autocomplete navigation
        if self.autocomplete_popup.winfo_viewable():
            if event.keysym == "Down":
                self.autocomplete_popup.navigate(1)
                return "break"
            elif event.keysym == "Up":
                self.autocomplete_popup.navigate(-1)
                return "break"
            elif event.keysym in ("Return", "Tab"):
                self.autocomplete_popup.on_select()
                return "break"
            elif event.keysym == "Escape":
                self.autocomplete_popup.hide()
                return "break"
            elif event.char and event.char.isprintable():
                # Update completion list as user types
                self.after_idle(self.update_completion_list)
                
        # Check for function signature trigger
        if event.char == "(":
            self.after(50, self.show_signature_help)
        elif event.char == ")":
            self.signature_popup.hide()
            
        # Trigger autocomplete on dot notation
        if event.char == "." and self.auto_completion_enabled:
            self.after(100, self.trigger_autocomplete)
            
    def on_text_change(self, event=None):
        """Handle text changes with enhanced features"""
        # Cancel previous syntax highlighting timer
        if self.syntax_timer:
            self.after_cancel(self.syntax_timer)
            
        # Schedule syntax highlighting with debouncing
        self.syntax_timer = self.after(50, self.apply_syntax_highlighting)
        
        # Update line count
        self.update_line_count()
        
        # Highlight current line
        self.highlight_current_line()
        
        # Auto-trigger completion
        if (self.auto_completion_enabled and 
            event and hasattr(event, 'char') and 
            event.char and event.char.isalpha()):
            
            if self.autocomplete_timer:
                self.after_cancel(self.autocomplete_timer)
            self.autocomplete_timer = self.after(
                self.autocomplete_delay, 
                self.trigger_autocomplete_if_needed
            )
        
        # Notify parent of changes
        if self.parent_app and hasattr(self.parent_app, 'on_text_change'):
            self.parent_app.on_text_change(event)
            
    def trigger_autocomplete_if_needed(self):
        """Auto-trigger autocomplete if conditions are met"""
        # Get current context
        current_pos = self.index(tk.INSERT)
        line_start = self.index("insert linestart")
        current_line = self.get(line_start, current_pos)
        
        # Don't show in comments or strings
        if self.is_in_comment_or_string(current_line):
            return
            
        # Get current word
        words = re.findall(r'\w+', current_line)
        if words and len(words[-1]) >= 2:  # At least 2 characters
            self.trigger_autocomplete()
            
    def is_in_comment_or_string(self, line_text):
        """Check if cursor is in a comment or string"""
        # Simple heuristic - check if line starts with # or contains quotes
        stripped = line_text.strip()
        return stripped.startswith('#') or ('"' in line_text or "'" in line_text)
    
    def trigger_autocomplete(self, event=None):
        """Trigger autocomplete at current position"""
        try:
            # Get current position and text
            current_pos = self.index(tk.INSERT)
            line_num = int(current_pos.split('.')[0]) - 1
            column_num = int(current_pos.split('.')[1])
            
            # Get current word/prefix
            line_start = self.index("insert linestart")
            current_line = self.get(line_start, current_pos)
            
            # Find word boundary
            word_start = column_num
            while (word_start > 0 and 
                   (current_line[word_start - 1].isalnum() or 
                    current_line[word_start - 1] in ('_', '.'))):
                word_start -= 1
                
            self.completion_prefix = current_line[word_start:column_num]
            self.completion_start_pos = f"{line_num + 1}.{word_start}"
            
            # Get completions in background thread
            threading.Thread(
                target=self.get_completions_async,
                args=(line_num, column_num, self.completion_prefix),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f"Autocomplete error: {e}")
            
    def get_completions_async(self, line_num, column_num, prefix):
        """Get completions asynchronously"""
        try:
            code = self.get("1.0", "end-1c")
            completions = self.intellisense.get_completions(
                code, line_num, column_num, prefix
            )
            
            # Show completions in main thread
            self.after(0, lambda: self.show_completions(completions, prefix))
            
        except Exception as e:
            logger.error(f"Async completion error: {e}")
            
    def show_completions(self, completions, prefix):
        """Show completion popup"""
        if not completions:
            self.autocomplete_popup.hide()
            return
            
        # Get popup position
        try:
            x, y, _, _ = self.bbox(self.completion_start_pos)
            x += self.winfo_rootx()
            y += self.winfo_rooty() + 20
            
            # Show popup
            self.autocomplete_popup.show_completions(completions, x, y, prefix)
            self.is_completing = True
            
        except tk.TclError:
            # Position not visible, hide popup
            self.autocomplete_popup.hide()
            
    def update_completion_list(self):
        """Update completion list as user types"""
        if not self.is_completing:
            return
            
        try:
            # Get current prefix
            current_pos = self.index(tk.INSERT)
            line_start = self.index("insert linestart")
            current_line = self.get(line_start, current_pos)
            
            # Extract current word
            column_num = int(current_pos.split('.')[1])
            word_start = column_num
            while (word_start > 0 and 
                   (current_line[word_start - 1].isalnum() or 
                    current_line[word_start - 1] == '_')):
                word_start -= 1
                
            new_prefix = current_line[word_start:column_num]
            
            # Update completion list if prefix changed
            if new_prefix != self.completion_prefix:
                self.completion_prefix = new_prefix
                if new_prefix:
                    # Re-filter existing completions
                    filtered = [c for c in self.autocomplete_popup.completions 
                              if c['name'].lower().startswith(new_prefix.lower())]
                    
                    if filtered:
                        x, y, _, _ = self.bbox(self.completion_start_pos)
                        x += self.winfo_rootx()
                        y += self.winfo_rooty() + 20
                        self.autocomplete_popup.show_completions(filtered, x, y, new_prefix)
                    else:
                        self.autocomplete_popup.hide()
                        self.is_completing = False
                else:
                    self.autocomplete_popup.hide()
                    self.is_completing = False
                    
        except tk.TclError:
            self.autocomplete_popup.hide()
            self.is_completing = False
    
    def insert_completion(self, completion_text):
        """Insert selected completion"""
        try:
            # Delete the current prefix
            current_pos = self.index(tk.INSERT)
            self.delete(self.completion_start_pos, current_pos)
            
            # Insert completion
            self.insert(self.completion_start_pos, completion_text)
            
            # Reset completion state
            self.is_completing = False
            self.completion_prefix = ""
            
        except tk.TclError as e:
            logger.error(f"Completion insertion error: {e}")
            
    def show_signature_help(self):
        """Show function signature help"""
        try:
            current_pos = self.index(tk.INSERT)
            line_num = int(current_pos.split('.')[0]) - 1
            column_num = int(current_pos.split('.')[1])
            
            code = self.get("1.0", "end-1c")
            signature = self.intellisense.get_signature_help(code, line_num, column_num)
            
            if signature:
                # Get position for popup
                x, y, _, _ = self.bbox(current_pos)
                x += self.winfo_rootx()
                y += self.winfo_rooty()
                
                self.signature_popup.show_signature(signature, x, y)
                
        except Exception as e:
            logger.error(f"Signature help error: {e}")
    
    def on_click(self, event=None):
        """Handle mouse clicks"""
        # Hide autocomplete on click
        self.autocomplete_popup.hide()
        self.signature_popup.hide()
        self.is_completing = False
        
        # Highlight current line
        self.highlight_current_line()
        
        # Check for bracket matching
        self.check_bracket_match(event)
        
    def apply_syntax_highlighting(self):
        """Apply syntax highlighting to the text"""
        # Get current text
        content = self.get("1.0", "end-1c")
        
        # Only update if content changed
        if content == self.last_content:
            return
        self.last_content = content
        
        # Clear existing tags (except for special ones)
        for tag in SYNTAX_COLORS.keys():
            self.tag_remove(tag, "1.0", "end")
            
        # Apply syntax highlighting patterns
        for pattern, tag in self.syntax_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                start_idx = self.index_from_char_offset(match.start())
                end_idx = self.index_from_char_offset(match.end())
                
                # Handle special cases for function and class definitions
                if tag in ['function', 'class'] and match.groups():
                    # Highlight only the name, not the keyword
                    start_idx = self.index_from_char_offset(match.start(1))
                    end_idx = self.index_from_char_offset(match.end(1))
                    
                self.tag_add(tag, start_idx, end_idx)
                
    def index_from_char_offset(self, char_offset):
        """Convert character offset to tkinter text index"""
        return self.index(f"1.0 + {char_offset}c")
        
    def update_line_count(self):
        """Update line count for line numbers"""
        content = self.get("1.0", "end-1c")
        self.line_count = content.count('\n') + 1
        if hasattr(self.parent_app, 'update_line_numbers'):
            self.parent_app.update_line_numbers()
            
    def highlight_current_line(self):
        """Highlight the current line"""
        # Remove previous current line highlight
        self.tag_remove("current_line", "1.0", "end")
        
        # Get current line
        current_line = self.index(tk.INSERT).split('.')[0]
        line_start = f"{current_line}.0"
        line_end = f"{current_line}.end"
        
        # Apply current line highlight
        self.tag_add("current_line", line_start, line_end)
        
    def check_bracket_match(self, event=None):
        """Check and highlight matching brackets"""
        # Remove previous bracket highlights
        self.tag_remove("bracket_match", "1.0", "end")
        
        # Get current position
        pos = self.index(tk.INSERT)
        
        # Check character at cursor
        char = self.get(pos)
        if char in self.bracket_pairs:
            # Find matching bracket
            matching = self.find_matching_bracket(pos, char)
            if matching:
                # Highlight both brackets
                self.tag_add("bracket_match", pos)
                self.tag_add("bracket_match", matching)
                
    def find_matching_bracket(self, start_pos, bracket):
        """Find the matching bracket"""
        matching_bracket = self.bracket_pairs[bracket]
        content = self.get("1.0", "end-1c")
        start_offset = len(self.get("1.0", start_pos))
        
        if bracket in '([{':
            # Forward search
            count = 1
            for i in range(start_offset + 1, len(content)):
                if content[i] == bracket:
                    count += 1
                elif content[i] == matching_bracket:
                    count -= 1
                    if count == 0:
                        return self.index_from_char_offset(i)
        else:
            # Backward search (closing bracket)
            count = 1
            for i in range(start_offset - 1, -1, -1):
                if content[i] == bracket:
                    count += 1
                elif content[i] == matching_bracket:
                    count -= 1
                    if count == 0:
                        return self.index_from_char_offset(i)
        return None
        
    # Editor feature methods
    def handle_tab(self, event):
        """Handle tab key for smart indentation"""
        # Check if text is selected
        if self.tag_ranges("sel"):
            # Indent selection
            self.indent_selection()
        else:
            # Insert tab or spaces
            self.insert(tk.INSERT, "    ")
        return "break"
        
    def handle_shift_tab(self, event):
        """Handle shift+tab for unindenting"""
        self.unindent_selection()
        return "break"
        
    def handle_return(self, event):
        """Handle return key with smart indentation"""
        # Get current line
        current_pos = self.index(tk.INSERT)
        current_line = self.get(self.index("insert linestart"), current_pos)
        
        # Calculate indentation
        indent_level = 0
        for char in current_line:
            if char == ' ':
                indent_level += 1
            elif char == '\t':
                indent_level += 4
            else:
                break
                
        # Check if we need to increase indentation
        if current_line.rstrip().endswith(':'):
            indent_level += 4
            
        # Check for brackets
        if current_line.rstrip().endswith(('{', '[', '(')):
            indent_level += 4
            
        # Insert newline and indentation
        self.insert(tk.INSERT, '\n' + ' ' * indent_level)
        
        # Auto-close brackets
        if current_line.rstrip().endswith(('{', '[')):
            closing = '}' if current_line.rstrip().endswith('{') else ']'
            self.insert(tk.INSERT, f'\n{" " * (indent_level - 4)}{closing}')
            self.mark_set(tk.INSERT, f"{tk.INSERT} linestart")
            self.mark_set(tk.INSERT, f"{tk.INSERT} lineend")
            
        return "break"
        
    def handle_backspace(self, event):
        """Handle backspace with smart unindentation"""
        current_pos = self.index(tk.INSERT)
        line_start = self.index("insert linestart")
        
        # Check if we're at the beginning of indentation
        if current_pos != line_start:
            before_cursor = self.get(line_start, current_pos)
            if before_cursor and all(c == ' ' for c in before_cursor):
                # Remove up to 4 spaces
                spaces_to_remove = min(4, len(before_cursor))
                if spaces_to_remove > 1:
                    self.delete(f"{current_pos} -{spaces_to_remove}c", current_pos)
                    return "break"
        
        # Default backspace behavior
        return None
        
    def indent_selection(self, event=None):
        """Indent selected lines"""
        if not self.tag_ranges("sel"):
            return "break"
            
        start_line = int(self.index("sel.first").split('.')[0])
        end_line = int(self.index("sel.last").split('.')[0])
        
        for line_num in range(start_line, end_line + 1):
            line_start = f"{line_num}.0"
            self.insert(line_start, "    ")
            
        return "break"
        
    def unindent_selection(self, event=None):
        """Unindent selected lines"""
        if not self.tag_ranges("sel"):
            return "break"
            
        start_line = int(self.index("sel.first").split('.')[0])
        end_line = int(self.index("sel.last").split('.')[0])
        
        for line_num in range(start_line, end_line + 1):
            line_start = f"{line_num}.0"
            line_content = self.get(line_start, f"{line_num}.end")
            
            # Remove up to 4 leading spaces
            spaces_to_remove = 0
            for char in line_content[:4]:
                if char == ' ':
                    spaces_to_remove += 1
                else:
                    break
                    
            if spaces_to_remove > 0:
                self.delete(line_start, f"{line_start} +{spaces_to_remove}c")
                
        return "break"
        
    def toggle_comment(self, event=None):
        """Toggle comment on current line or selection"""
        if self.tag_ranges("sel"):
            # Comment/uncomment selection
            start_line = int(self.index("sel.first").split('.')[0])
            end_line = int(self.index("sel.last").split('.')[0])
        else:
            # Comment/uncomment current line
            current_line = int(self.index(tk.INSERT).split('.')[0])
            start_line = end_line = current_line
            
        # Check if all lines are commented
        all_commented = True
        for line_num in range(start_line, end_line + 1):
            line_content = self.get(f"{line_num}.0", f"{line_num}.end")
            if line_content.strip() and not line_content.lstrip().startswith('#'):
                all_commented = False
                break
                
        # Toggle comments
        for line_num in range(start_line, end_line + 1):
            line_start = f"{line_num}.0"
            line_content = self.get(line_start, f"{line_num}.end")
            
            if all_commented:
                # Uncomment
                if line_content.lstrip().startswith('#'):
                    # Find the # and remove it (and the space after if present)
                    stripped = line_content.lstrip()
                    indent = line_content[:len(line_content) - len(stripped)]
                    if stripped.startswith('# '):
                        new_content = indent + stripped[2:]
                    else:
                        new_content = indent + stripped[1:]
                    self.delete(line_start, f"{line_num}.end")
                    self.insert(line_start, new_content)
            else:
                # Comment
                if line_content.strip():
                    stripped = line_content.lstrip()
                    indent = line_content[:len(line_content) - len(stripped)]
                    new_content = indent + '# ' + stripped
                    self.delete(line_start, f"{line_num}.end")
                    self.insert(line_start, new_content)
                    
        return "break"
        
    def duplicate_line(self, event=None):
        """Duplicate the current line"""
        current_line_num = int(self.index(tk.INSERT).split('.')[0])
        line_start = f"{current_line_num}.0"
        line_end = f"{current_line_num}.end"
        line_content = self.get(line_start, line_end)
        
        self.insert(line_end, '\n' + line_content)
        return "break"
        
    def select_line(self, event=None):
        """Select the current line"""
        current_line_num = int(self.index(tk.INSERT).split('.')[0])
        line_start = f"{current_line_num}.0"
        line_end = f"{current_line_num}.end"
        
        self.tag_remove("sel", "1.0", "end")
        self.tag_add("sel", line_start, line_end)
        self.mark_set(tk.INSERT, line_start)
        return "break"
        
    def delete_line(self, event=None):
        """Delete the current line"""
        current_line_num = int(self.index(tk.INSERT).split('.')[0])
        line_start = f"{current_line_num}.0"
        
        # If not the last line, include the newline
        total_lines = int(self.index("end-1c").split('.')[0])
        if current_line_num < total_lines:
            line_end = f"{current_line_num + 1}.0"
        else:
            line_end = f"{current_line_num}.end"
            
        self.delete(line_start, line_end)
        return "break"
        
    def move_line_up(self, event=None):
        """Move current line up"""
        current_line_num = int(self.index(tk.INSERT).split('.')[0])
        if current_line_num <= 1:
            return "break"
            
        # Get current line content
        line_start = f"{current_line_num}.0"
        line_end = f"{current_line_num}.end"
        line_content = self.get(line_start, line_end)
        
        # Get previous line content
        prev_line_start = f"{current_line_num - 1}.0"
        prev_line_end = f"{current_line_num - 1}.end"
        prev_line_content = self.get(prev_line_start, prev_line_end)
        
        # Swap lines
        self.delete(prev_line_start, line_end)
        self.insert(prev_line_start, line_content + '\n' + prev_line_content)
        
        # Move cursor
        self.mark_set(tk.INSERT, f"{current_line_num - 1}.0")
        return "break"
        
    def move_line_down(self, event=None):
        """Move current line down"""
        current_line_num = int(self.index(tk.INSERT).split('.')[0])
        total_lines = int(self.index("end-1c").split('.')[0])
        
        if current_line_num >= total_lines:
            return "break"
            
        # Get current line content
        line_start = f"{current_line_num}.0"
        line_end = f"{current_line_num}.end"
        line_content = self.get(line_start, line_end)
        
        # Get next line content
        next_line_start = f"{current_line_num + 1}.0"
        next_line_end = f"{current_line_num + 1}.end"
        next_line_content = self.get(next_line_start, next_line_end)
        
        # Swap lines
        self.delete(line_start, next_line_end)
        self.insert(line_start, next_line_content + '\n' + line_content)
        
        # Move cursor
        self.mark_set(tk.INSERT, f"{current_line_num + 1}.0")
        return "break"
        
    def show_find_dialog(self, event=None):
        """Show find dialog"""
        if self.parent_app and hasattr(self.parent_app, 'show_find_dialog'):
            self.parent_app.show_find_dialog()
        return "break"
        
    def show_replace_dialog(self, event=None):
        """Show replace dialog"""  
        if self.parent_app and hasattr(self.parent_app, 'show_replace_dialog'):
            self.parent_app.show_replace_dialog()
        return "break"


class LineNumbers(tk.Text):
    """Line numbers widget that syncs with the main editor"""
    
    def __init__(self, parent, editor, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.editor = editor
        
        # Configure appearance
        self.configure(
            width=5,
            bg=VSCODE_COLORS["line_numbers_bg"],
            fg=VSCODE_COLORS["line_numbers"],
            bd=0,
            highlightthickness=0,
            state="disabled",
            wrap="none",
            cursor="arrow",
            takefocus=False,
            selectbackground=VSCODE_COLORS["line_numbers_bg"],
            inactiveselectbackground=VSCODE_COLORS["line_numbers_bg"]
        )
        
        # Bind scrolling to editor
        self.bind('<MouseWheel>', self._on_mousewheel)
        self.bind('<Button-4>', self._on_mousewheel)
        self.bind('<Button-5>', self._on_mousewheel)
        
    def _on_mousewheel(self, event):
        """Redirect mouse wheel events to editor"""
        return self.editor.event_generate('<MouseWheel>', delta=event.delta)
        
    def update_line_numbers(self, line_count):
        """Update line numbers display"""
        self.configure(state="normal")
        self.delete("1.0", "end")
        
        # Generate line numbers
        line_numbers = '\n'.join(str(i) for i in range(1, line_count + 1))
        self.insert("1.0", line_numbers)
        
        self.configure(state="disabled")
        
        # Sync scrolling with editor
        self.yview_moveto(self.editor.yview()[0])


class FindReplaceDialog(ctk.CTkToplevel):
    """Enhanced find and replace dialog with VSCode-like features"""
    
    def __init__(self, parent, text_widget):
        super().__init__(parent)
        
        self.text_widget = text_widget
        self.title("Find and Replace")

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(450, screen_w - 100)
        height = min(250, screen_h - 100)
        self.geometry(f"{width}x{height}")
        self.minsize(400, 200)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        
        # Center the dialog
        self.geometry("+%d+%d" % (
            parent.winfo_rootx() + 100,
            parent.winfo_rooty() + 100
        ))
        
        self.current_matches = []
        self.current_index = -1
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the enhanced find/replace UI"""
        # Main frame
        main_frame = ctk.CTkFrame(self, fg_color=VSCODE_COLORS["surface"])
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Find frame
        find_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        find_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(find_frame, text="Find:", width=60).pack(side="left")
        self.find_entry = ctk.CTkEntry(find_frame, placeholder_text="Enter text to find")
        self.find_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.find_entry.bind('<KeyRelease>', self.on_find_entry_change)
        
        # Replace frame
        replace_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        replace_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(replace_frame, text="Replace:", width=60).pack(side="left")
        self.replace_entry = ctk.CTkEntry(replace_frame, placeholder_text="Enter replacement text")
        self.replace_entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
        
        # Options frame
        options_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        options_frame.pack(fill="x", pady=10)
        
        self.case_sensitive = ctk.BooleanVar()
        self.whole_word = ctk.BooleanVar()
        self.regex_mode = ctk.BooleanVar()
        
        ctk.CTkCheckBox(options_frame, text="Case sensitive", variable=self.case_sensitive, command=self.update_search).pack(side="left")
        ctk.CTkCheckBox(options_frame, text="Whole word", variable=self.whole_word, command=self.update_search).pack(side="left", padx=(20, 0))
        ctk.CTkCheckBox(options_frame, text="Regex", variable=self.regex_mode, command=self.update_search).pack(side="left", padx=(20, 0))
        
        # Results frame
        results_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        results_frame.pack(fill="x", pady=5)
        
        self.results_label = ctk.CTkLabel(
            results_frame, 
            text="", 
            font=ctk.CTkFont(size=11),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.results_label.pack(side="left")
        
        # Button frame
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        
        # Navigation buttons
        ctk.CTkButton(button_frame, text="Previous", width=80, command=self.find_previous).pack(side="left", padx=2)
        ctk.CTkButton(button_frame, text="Next", width=80, command=self.find_next).pack(side="left", padx=2)
        
        # Action buttons
        ctk.CTkButton(button_frame, text="Replace", width=80, command=self.replace_current).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="Replace All", width=90, command=self.replace_all).pack(side="left", padx=2)
        
        # Close button
        ctk.CTkButton(button_frame, text="Close", width=80, command=self.destroy).pack(side="right", padx=5)
        
        # Focus on find entry
        self.find_entry.focus()
        
    def on_find_entry_change(self, event=None):
        """Handle changes in find entry"""
        self.update_search()
        
    def update_search(self):
        """Update search results"""
        search_text = self.find_entry.get()
        if not search_text:
            self.clear_highlights()
            self.results_label.configure(text="")
            return
            
        self.find_all_matches(search_text)
        
    def find_all_matches(self, search_text):
        """Find all matches in the text"""
        # Clear previous highlights
        self.clear_highlights()
        
        # Get text content
        content = self.text_widget.get("1.0", "end-1c")
        
        # Prepare search pattern
        if self.regex_mode.get():
            try:
                flags = 0 if self.case_sensitive.get() else re.IGNORECASE
                pattern = re.compile(search_text, flags)
            except re.error:
                self.results_label.configure(text="Invalid regex")
                return
        else:
            if self.whole_word.get():
                search_text = r'\b' + re.escape(search_text) + r'\b'
            else:
                search_text = re.escape(search_text)
            flags = 0 if self.case_sensitive.get() else re.IGNORECASE
            pattern = re.compile(search_text, flags)
            
        # Find all matches
        self.current_matches = []
        for match in pattern.finditer(content):
            start_idx = self.text_widget.index(f"1.0 + {match.start()}c")
            end_idx = self.text_widget.index(f"1.0 + {match.end()}c")
            self.current_matches.append((start_idx, end_idx))
            self.text_widget.tag_add("find_match", start_idx, end_idx)
            
        # Update results label
        if self.current_matches:
            self.results_label.configure(text=f"{len(self.current_matches)} matches")
            self.current_index = 0
            self.highlight_current_match()
        else:
            self.results_label.configure(text="No matches")
            self.current_index = -1
            
    def clear_highlights(self):
        """Clear all search highlights"""
        self.text_widget.tag_remove("find_match", "1.0", "end")
        self.text_widget.tag_remove("find_current", "1.0", "end")
        
    def highlight_current_match(self):
        """Highlight the current match"""
        if not self.current_matches or self.current_index < 0:
            return
            
        # Clear previous current highlight
        self.text_widget.tag_remove("find_current", "1.0", "end")
        
        # Highlight current match
        start_idx, end_idx = self.current_matches[self.current_index]
        self.text_widget.tag_add("find_current", start_idx, end_idx)
        
        # Scroll to current match
        self.text_widget.see(start_idx)
        
        # Update results label
        self.results_label.configure(
            text=f"{self.current_index + 1} of {len(self.current_matches)} matches"
        )
        
    def find_next(self):
        """Find next match"""
        if not self.current_matches:
            self.update_search()
            return
            
        self.current_index = (self.current_index + 1) % len(self.current_matches)
        self.highlight_current_match()
        
    def find_previous(self):
        """Find previous match"""
        if not self.current_matches:
            self.update_search()
            return
            
        self.current_index = (self.current_index - 1) % len(self.current_matches)
        self.highlight_current_match()
        
    def replace_current(self):
        """Replace current match"""
        if not self.current_matches or self.current_index < 0:
            return
            
        start_idx, end_idx = self.current_matches[self.current_index]
        replacement_text = self.replace_entry.get()
        
        # Replace text
        self.text_widget.delete(start_idx, end_idx)
        self.text_widget.insert(start_idx, replacement_text)
        
        # Update search to find new matches
        self.update_search()
        
    def replace_all(self):
        """Replace all matches"""
        if not self.current_matches:
            return
            
        replacement_text = self.replace_entry.get()
        
        # Replace from end to beginning to maintain indices
        for start_idx, end_idx in reversed(self.current_matches):
            self.text_widget.delete(start_idx, end_idx)
            self.text_widget.insert(start_idx, replacement_text)
            
        # Update search
        self.update_search()


class AssetCard(ctk.CTkFrame):
    """Visual card for displaying assets"""
    def __init__(self, parent, asset_path, asset_type, on_use_callback, on_remove_callback, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.asset_path = asset_path
        self.asset_type = asset_type  # 'image' or 'audio'
        self.on_use_callback = on_use_callback
        self.on_remove_callback = on_remove_callback
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the asset card UI"""
        self.grid_columnconfigure(0, weight=1)
        
        # Asset preview/icon
        preview_frame = ctk.CTkFrame(self, height=80)
        preview_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        preview_frame.grid_columnconfigure(0, weight=1)
        
        if self.asset_type == "image":
            self.create_image_preview(preview_frame)
        else:
            self.create_audio_preview(preview_frame)
            
        # Asset info
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=1, column=0, sticky="ew", padx=10)
        info_frame.grid_columnconfigure(0, weight=1)
        
        # File name
        filename = os.path.basename(self.asset_path)
        if len(filename) > 20:
            filename = filename[:17] + "..."
            
        name_label = ctk.CTkLabel(
            info_frame,
            text=filename,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        name_label.grid(row=0, column=0, sticky="w", pady=2)
        
        # File size
        try:
            size = os.path.getsize(self.asset_path)
            size_str = self.format_file_size(size)
        except:
            size_str = "Unknown size"
            
        size_label = ctk.CTkLabel(
            info_frame,
            text=size_str,
            font=ctk.CTkFont(size=9),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        size_label.grid(row=1, column=0, sticky="w")
        
        # Action buttons
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))
        
        use_btn = ctk.CTkButton(
            button_frame,
            text="Use",
            height=25,
            width=50,
            command=self.on_use,
            font=ctk.CTkFont(size=10),
            fg_color=VSCODE_COLORS["primary"],
            hover_color=VSCODE_COLORS["primary_hover"]
        )
        use_btn.pack(side="left", padx=(0, 5))
        
        remove_btn = ctk.CTkButton(
            button_frame,
            text="Remove",
            height=25,
            width=60,
            command=self.on_remove,
            font=ctk.CTkFont(size=10),
            fg_color=VSCODE_COLORS["error"],
            hover_color="#C0392B"
        )
        remove_btn.pack(side="right")
        
    def create_image_preview(self, parent):
        """Create image preview"""
        try:
            # Load and resize image
            image = Image.open(self.asset_path)
            image.thumbnail((100, 60), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # Display in label
            preview_label = ctk.CTkLabel(parent, image=photo, text="")
            preview_label.pack(expand=True)
            
            # Keep reference to prevent garbage collection
            preview_label.image = photo
            
        except Exception as e:
            # Fallback to icon
            icon_label = ctk.CTkLabel(
                parent,
                text="🖼️",
                font=ctk.CTkFont(size=24)
            )
            icon_label.pack(expand=True)
            
    def create_audio_preview(self, parent):
        """Create audio preview"""
        # Audio waveform icon
        icon_label = ctk.CTkLabel(
            parent,
            text="🎵",
            font=ctk.CTkFont(size=24)
        )
        icon_label.pack(expand=True)
        
        # Duration info (if available)
        try:
            # Try to get audio duration using ffprobe
            cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", 
                   "-of", "csv=p=0", self.asset_path]
            result = self.run_hidden_subprocess_nuitka_safe(
                cmd, capture_output=True, text=True
            )
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                duration_str = f"{int(duration//60)}:{int(duration%60):02d}"
                
                duration_label = ctk.CTkLabel(
                    parent,
                    text=duration_str,
                    font=ctk.CTkFont(size=9),
                    text_color=VSCODE_COLORS["text_secondary"]
                )
                duration_label.pack()
        except:
            pass
            
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB"]
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
        
    def on_use(self):
        """Handle use button click"""
        if self.on_use_callback:
            self.on_use_callback(self.asset_path, self.asset_type)
            
    def on_remove(self):
        """Handle remove button click"""
        if self.on_remove_callback:
            self.on_remove_callback(self.asset_path, self)



import tkinter as tk
import customtkinter as ctk
import cv2
import threading
import time
from PIL import Image, ImageTk
import os

# VSCode-style colors (adjust these to match your existing color scheme)
VSCODE_COLORS = {
    "surface": "#1e1e1e",
    "surface_light": "#2d2d30",
    "surface_lighter": "#3e3e42",
    "primary": "#0078d4",
    "primary_hover": "#106ebe",
    "text": "#cccccc",
    "text_bright": "#ffffff",
    "text_secondary": "#969696",
    "border": "#3e3e42",
    "bracket_match": "#3e3e42"
}

class FullscreenVideoPlayer(tk.Toplevel):
    """YouTube-style fullscreen video player with proper state management"""
    
    def __init__(self, parent, video_player):
        super().__init__(parent)
        
        self.video_player = video_player
        self.parent = parent
        
        # Fullscreen setup
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.configure(bg="black", cursor="none")
        
        # Control visibility
        self.controls_visible = True
        self.mouse_timer = None
        self.last_mouse_move = time.time()
        
        self.setup_fullscreen_ui()
        self.setup_bindings()
        
        # Start mouse tracking
        self.start_mouse_tracking()
        
        # Sync initial state
        self.sync_with_main_player()
        
    def sync_with_main_player(self):
        """Sync fullscreen player state with main player"""
        if self.video_player.cap:
            self.display_frame(self.video_player.current_frame)
            self.update_progress_bar()
            
            # Update play button state AND start playing if main player is playing
            if self.video_player.is_playing:
                self.play_btn.configure(text="⏸")
                # Start fullscreen playback loop if main player is playing
                self.start_fullscreen_playback()
            else:
                self.play_btn.configure(text="▶")
    
    def start_fullscreen_playback(self):
        """Start fullscreen playback synchronized with main player"""
        if not self.video_player.is_playing or not self.video_player.cap:
            return
        
        # Schedule regular updates to sync with main player
        self.sync_playback_with_main()
    
    def sync_playback_with_main(self):
        """Keep fullscreen player synchronized with main player"""
        if not self.video_player.is_playing or not self.video_player.cap or not self.winfo_exists():
            return
        
        # Update fullscreen display to match main player
        self.display_frame(self.video_player.current_frame)
        
        # Update controls if visible
        if self.controls_visible:
            self.update_progress_bar()
        
        # Calculate sync interval based on playback speed for smoother sync
        # Higher speeds need more frequent updates
        if self.video_player.playback_speed >= 4.0:
            sync_interval = 20  # 20ms for very high speeds
        elif self.video_player.playback_speed >= 2.0:
            sync_interval = 30  # 30ms for high speeds  
        else:
            sync_interval = 50  # 50ms for normal speeds
        
        # Schedule next sync
        self.after(sync_interval, self.sync_playback_with_main)
        
    def setup_fullscreen_ui(self):
        """Setup YouTube-style fullscreen interface"""
        # Main video area
        self.video_frame = tk.Frame(self, bg="black")
        self.video_frame.pack(fill="both", expand=True)
        
        # Video canvas
        self.canvas = tk.Canvas(
            self.video_frame,
            bg="black",
            highlightthickness=0,
            relief="flat"
        )
        self.canvas.pack(fill="both", expand=True)
        
        # YouTube-style overlay controls container
        self.overlay_frame = tk.Frame(self, bg="black")
        self.overlay_frame.pack(fill="x", side="bottom")
        
        # Gradient background for controls
        self.controls_bg = tk.Frame(
            self.overlay_frame,
            bg="#000000",
            height=120
        )
        self.controls_bg.pack(fill="x", padx=0, pady=0)
        
        # Create controls with YouTube-style layout
        self.create_youtube_controls()
        
        # Title overlay (top)
        self.title_frame = tk.Frame(self, bg="black")
        self.title_frame.pack(fill="x", side="top")
        
        self.title_bg = tk.Frame(
            self.title_frame,
            bg="#000000",
            height=60
        )
        self.title_bg.pack(fill="x")
        
        # Video title
        self.title_label = tk.Label(
            self.title_bg,
            text="Manim Animation Preview",
            font=("Arial", 18, "bold"),
            fg="white",
            bg="#000000"
        )
        self.title_label.pack(side="left", padx=20, pady=15)
        
        # Exit fullscreen button (top right)
        self.exit_btn = tk.Button(
            self.title_bg,
            text="⚬ ⚬ ⚬",
            font=("Arial", 16),
            fg="white",
            bg="#000000",
            relief="flat",
            cursor="hand2",
            command=self.exit_fullscreen
        )
        self.exit_btn.pack(side="right", padx=20, pady=15)
        
    def create_youtube_controls(self):
        """Create YouTube-style control layout"""
        # Progress bar (full width, top of controls)
        self.progress_frame = tk.Frame(self.controls_bg, bg="#000000", height=30)
        self.progress_frame.pack(fill="x", padx=20, pady=(10, 0))
        
        # Custom progress bar that looks like YouTube
        self.progress_canvas = tk.Canvas(
            self.progress_frame,
            height=8,
            bg="#000000",
            highlightthickness=0
        )
        self.progress_canvas.pack(fill="x", pady=10)
        self.progress_canvas.bind("<Button-1>", self.on_progress_click)
        
        # Main controls row
        self.main_controls = tk.Frame(self.controls_bg, bg="#000000", height=60)
        self.main_controls.pack(fill="x", padx=20, pady=(0, 10))
        
        # Left side controls
        self.left_controls = tk.Frame(self.main_controls, bg="#000000")
        self.left_controls.pack(side="left", fill="y")
        
        # Play/Pause button (YouTube style - only one button like YouTube)
        self.play_btn = tk.Button(
            self.left_controls,
            text="▶",
            font=("Arial", 24),
            fg="white",
            bg="#000000",
            relief="flat",
            cursor="hand2",
            command=self.toggle_playback
        )
        self.play_btn.pack(side="left", padx=(0, 15))
        
        # Volume button
        self.volume_btn = tk.Button(
            self.left_controls,
            text="🔊",
            font=("Arial", 16),
            fg="white",
            bg="#000000",
            relief="flat",
            cursor="hand2"
        )
        self.volume_btn.pack(side="left", padx=(0, 15))
        
        # Time display (YouTube style)
        self.time_label = tk.Label(
            self.left_controls,
            text="0:00 / 0:00",
            font=("Arial", 14),
            fg="white",
            bg="#000000"
        )
        self.time_label.pack(side="left", padx=(0, 15))
        
        # Right side controls
        self.right_controls = tk.Frame(self.main_controls, bg="#000000")
        self.right_controls.pack(side="right", fill="y")
        
        # Speed control
        self.speed_label = tk.Label(
            self.right_controls,
            text="1×",
            font=("Arial", 14),
            fg="white",
            bg="#000000"
        )
        self.speed_label.pack(side="right", padx=(15, 0))
        
        # Settings button
        self.settings_btn = tk.Button(
            self.right_controls,
            text="⚙️",
            font=("Arial", 16),
            fg="white",
            bg="#000000",
            relief="flat",
            cursor="hand2",
            command=self.show_speed_menu
        )
        self.settings_btn.pack(side="right", padx=(15, 0))
        
        # Fullscreen button
        self.fullscreen_btn = tk.Button(
            self.right_controls,
            text="⛶",
            font=("Arial", 16),
            fg="white",
            bg="#000000",
            relief="flat",
            cursor="hand2",
            command=self.exit_fullscreen
        )
        self.fullscreen_btn.pack(side="right", padx=(15, 0))
        
        # Speed menu (hidden by default)
        self.speed_menu = tk.Frame(self, bg="#1c1c1c")
        self.speed_menu_visible = False
        
        speeds = ["0.25", "0.5", "0.75", "Normal", "1.25", "1.5", "1.75", "2"]
        for speed in speeds:
            btn = tk.Button(
                self.speed_menu,
                text=speed,
                font=("Arial", 12),
                fg="white",
                bg="#1c1c1c",
                relief="flat",
                cursor="hand2",
                command=lambda s=speed: self.set_speed_from_menu(s)
            )
            btn.pack(fill="x", pady=1)
        
    def setup_bindings(self):
        """Setup keyboard and mouse bindings for fullscreen"""
        # Escape to exit fullscreen
        self.bind("<Escape>", lambda e: self.exit_fullscreen())
        self.bind("<F11>", lambda e: self.exit_fullscreen())
        self.bind("<f>", lambda e: self.exit_fullscreen())  # 'f' key like YouTube
        
        # Space for play/pause
        self.bind("<space>", lambda e: self.toggle_playback())
        
        # Arrow keys for seeking
        self.bind("<Left>", lambda e: self.seek_relative(-5))
        self.bind("<Right>", lambda e: self.seek_relative(5))
        self.bind("<Up>", lambda e: self.change_speed(0.25))
        self.bind("<Down>", lambda e: self.change_speed(-0.25))
        
        # Number keys for speed
        for i in range(1, 9):
            self.bind(f"<Key-{i}>", lambda e, speed=i*0.25: self.set_speed(speed))
        
        # Mouse tracking for control visibility
        self.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.bind("<Button-1>", self.on_mouse_click)
        self.canvas.bind("<Button-1>", self.on_mouse_click)
        
        # Focus handling
        self.focus_set()
        
    def start_mouse_tracking(self):
        """Start tracking mouse movement for control visibility"""
        def check_mouse_idle():
            current_time = time.time()
            if current_time - self.last_mouse_move > 3.0:  # 3 seconds idle
                if self.controls_visible:
                    self.hide_controls()
            
            # Schedule next check
            if self.winfo_exists():
                self.after(500, check_mouse_idle)
        
        check_mouse_idle()
        
    def on_mouse_move(self, event):
        """Handle mouse movement"""
        self.last_mouse_move = time.time()
        if not self.controls_visible:
            self.show_controls()
        
        # Show cursor
        self.configure(cursor="")
        
        # Hide cursor after delay
        if self.mouse_timer:
            self.after_cancel(self.mouse_timer)
        self.mouse_timer = self.after(3000, lambda: self.configure(cursor="none"))
        
    def on_mouse_click(self, event):
        """Handle mouse clicks"""
        self.last_mouse_move = time.time()
        if not self.controls_visible:
            self.show_controls()
        else:
            # Click on video area toggles play/pause (like YouTube)
            if event.widget == self.canvas:
                self.toggle_playback()
    
    def on_progress_click(self, event):
        """Handle progress bar clicks for seeking"""
        if not self.video_player.cap:
            return
        
        canvas_width = self.progress_canvas.winfo_width()
        if canvas_width > 0:
            click_position = event.x / canvas_width
            target_frame = int(click_position * self.video_player.total_frames)
            target_frame = max(0, min(target_frame, self.video_player.total_frames - 1))
            
            # Update both players
            self.video_player.seek_to_frame(target_frame)
            self.update_progress_bar()
        
    def show_controls(self):
        """Show controls with smooth animation"""
        if not self.controls_visible:
            self.controls_visible = True
            
            # Fade in effect (simplified)
            self.overlay_frame.pack(fill="x", side="bottom")
            self.title_frame.pack(fill="x", side="top")
            
            # Update progress bar
            self.update_progress_bar()
            
    def hide_controls(self):
        """Hide controls with smooth animation"""
        if self.controls_visible:
            self.controls_visible = False
            
            # Fade out effect (simplified)
            self.overlay_frame.pack_forget()
            self.title_frame.pack_forget()
            
            # Hide speed menu if visible
            if self.speed_menu_visible:
                self.hide_speed_menu()
        
    def update_progress_bar(self):
        """Update YouTube-style progress bar"""
        if not self.video_player.cap or not self.controls_visible:
            return
        
        # Clear previous progress
        self.progress_canvas.delete("all")
        
        # Get canvas dimensions
        canvas_width = self.progress_canvas.winfo_width()
        if canvas_width <= 1:
            return
        
        # Calculate progress
        progress = 0
        if self.video_player.total_frames > 0:
            progress = self.video_player.current_frame / self.video_player.total_frames
        
        # Draw progress bar background
        self.progress_canvas.create_rectangle(
            0, 2, canvas_width, 6,
            fill="#404040", outline=""
        )
        
        # Draw progress
        if progress > 0:
            self.progress_canvas.create_rectangle(
                0, 2, canvas_width * progress, 6,
                fill="#ff0000", outline=""  # YouTube red
            )
        
        # Draw scrubber circle
        if progress > 0:
            x = canvas_width * progress
            self.progress_canvas.create_oval(
                x-6, 0, x+6, 8,
                fill="#ff0000", outline="white", width=2
            )
        
        # Update time display
        if self.video_player.cap:
            current_seconds = self.video_player.current_frame / max(self.video_player.fps, 1)
            total_seconds = self.video_player.total_frames / max(self.video_player.fps, 1)
            
            current_time = f"{int(current_seconds // 60)}:{int(current_seconds % 60):02d}"
            total_time = f"{int(total_seconds // 60)}:{int(total_seconds % 60):02d}"
            
            self.time_label.configure(text=f"{current_time} / {total_time}")
        
    def toggle_playback(self):
        """Toggle video playback (synchronized with main player)"""
        if self.video_player.cap:
            # Handle replay scenario - if video ended, restart from beginning
            if not self.video_player.is_playing and self.video_player.current_frame >= self.video_player.total_frames - 1:
                self.video_player.current_frame = 0
                self.video_player.display_frame(0)
                self.video_player.update_time_display()
                self.video_player.update_frame_display()
                self.display_frame(0)  # Update fullscreen too
                if self.controls_visible:
                    self.update_progress_bar()
            
            # Now toggle playback normally
            self.video_player.toggle_playback()
            
            # Update button text and sync playback state
            if self.video_player.is_playing:
                self.play_btn.configure(text="⏸")
                # Start syncing fullscreen playback
                self.start_fullscreen_playback()
            else:
                self.play_btn.configure(text="▶")
                # Fullscreen will stop syncing automatically when main player stops
        
    def seek_relative(self, seconds):
        """Seek relative to current position"""
        if not self.video_player.cap:
            return
        
        target_frame = self.video_player.current_frame + (seconds * self.video_player.fps)
        target_frame = max(0, min(target_frame, self.video_player.total_frames - 1))
        
        self.video_player.seek_to_frame(int(target_frame))
        self.update_progress_bar()
        
    def change_speed(self, delta):
        """Change playback speed"""
        new_speed = max(0.25, min(8.0, self.video_player.playback_speed + delta))
        self.set_speed(new_speed)
        
    def set_speed(self, speed):
        """Set playback speed"""
        self.video_player.set_speed(speed)
        self.speed_label.configure(text=f"{speed}×")
        
    def show_speed_menu(self):
        """Show speed selection menu"""
        if not self.speed_menu_visible:
            self.speed_menu_visible = True
            
            # Position menu above settings button
            self.speed_menu.place(
                x=self.winfo_width() - 200,
                y=self.winfo_height() - 200
            )
        else:
            self.hide_speed_menu()
        
    def hide_speed_menu(self):
        """Hide speed selection menu"""
        if self.speed_menu_visible:
            self.speed_menu_visible = False
            self.speed_menu.place_forget()
        
    def set_speed_from_menu(self, speed_text):
        """Set speed from menu selection"""
        speed_map = {
            "0.25": 0.25, "0.5": 0.5, "0.75": 0.75, "Normal": 1.0,
            "1.25": 1.25, "1.5": 1.5, "1.75": 1.75, "2": 2.0
        }
        
        if speed_text in speed_map:
            self.set_speed(speed_map[speed_text])
        
        self.hide_speed_menu()
        
    def display_frame(self, frame_number):
        """Display video frame in fullscreen canvas"""
        if not self.video_player.cap or not self.winfo_exists():
            return
        
        try:
            self.video_player.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = self.video_player.cap.read()
            
            if not ret:
                return
                
            # Get screen dimensions
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            
            # Convert frame
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_height, frame_width = frame_rgb.shape[:2]
            
            # Calculate display size to maintain aspect ratio
            aspect_ratio = frame_width / frame_height
            
            if screen_width / screen_height > aspect_ratio:
                # Screen is wider than video
                display_height = screen_height
                display_width = int(display_height * aspect_ratio)
            else:
                # Screen is taller than video
                display_width = screen_width
                display_height = int(display_width / aspect_ratio)
            
            # Resize frame
            frame_resized = cv2.resize(frame_rgb, (display_width, display_height))
            
            # Convert to PhotoImage
            image = Image.fromarray(frame_resized)
            self.photo = ImageTk.PhotoImage(image)
            
            # Display centered
            self.canvas.delete("all")
            self.canvas.create_image(
                screen_width // 2,
                screen_height // 2,
                image=self.photo,
                anchor="center"
            )
            
            # Update progress if controls are visible
            if self.controls_visible:
                self.update_progress_bar()
                
        except Exception as e:
            print(f"Fullscreen display error: {e}")
            # Don't crash, just skip this frame
        
    def exit_fullscreen(self):
        """Exit fullscreen mode properly"""
        # Properly destroy and clear reference
        self.video_player.fullscreen_player = None
        self.destroy()

class VideoPlayerWidget(ctk.CTkFrame):
    """Professional video player with YouTube-like behavior and simple state management"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.video_path = None
        self.cap = None
        self.is_playing = False
        self.current_frame = 0
        self.total_frames = 0
        self.fps = 30
        self.playback_speed = 1.0
        self.parent_window = parent
        self.has_focus = False
        self.fullscreen_player = None
        
        # Simple playback control (YouTube-style)
        self.playback_timer = None
        self.frame_delay_ms = 33  # ~30 FPS default
        self.max_speed = 8.0
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the video player interface"""
        # Configure grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Video display area
        self.video_frame = ctk.CTkFrame(self, fg_color="black", corner_radius=8)
        self.video_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))
        
        # Video canvas
        self.canvas = tk.Canvas(
            self.video_frame,
            bg="black",
            highlightthickness=1,
            highlightcolor=VSCODE_COLORS["primary"],
            highlightbackground=VSCODE_COLORS["border"],
            relief="flat"
        )
        self.canvas.pack(fill="both", expand=True, padx=8, pady=8)
        
        # Canvas bindings
        self.canvas.configure(takefocus=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Double-Button-1>", self.enter_fullscreen)
        self.canvas.bind("<FocusIn>", self.on_focus_in)
        self.canvas.bind("<FocusOut>", self.on_focus_out)
        self.canvas.bind("<KeyPress>", self.on_key_press)
        
        # Show placeholder
        self.show_placeholder()
        
        # Enhanced controls frame
        self.controls_frame = ctk.CTkFrame(self, height=120, corner_radius=8)
        self.controls_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.controls_frame.grid_columnconfigure(2, weight=1)
        
        self.create_controls()
        
    def create_controls(self):
        """Create YouTube-style control layout (simplified like YouTube)"""
        # Left controls - Playback
        left_controls = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        left_controls.grid(row=0, column=0, sticky="w", padx=15, pady=10)
        
        # Play/Pause button (YouTube style - single button)
        self.play_button = ctk.CTkButton(
            left_controls,
            text="▶",
            width=55,
            height=45,
            font=ctk.CTkFont(size=24),
            command=self.toggle_playback,
            fg_color=VSCODE_COLORS["primary"],
            hover_color=VSCODE_COLORS["primary_hover"],
            corner_radius=25
        )
        self.play_button.pack(side="left", padx=(0, 15))
        
        # Fullscreen button
        self.fullscreen_button = ctk.CTkButton(
            left_controls,
            text="⛶",
            width=45,
            height=45,
            font=ctk.CTkFont(size=18),
            command=self.enter_fullscreen,
            fg_color=VSCODE_COLORS["surface_light"],
            hover_color=VSCODE_COLORS["primary"],
            corner_radius=22
        )
        self.fullscreen_button.pack(side="left", padx=(0, 15))
        
        # Time display
        time_frame = ctk.CTkFrame(left_controls, fg_color="transparent")
        time_frame.pack(side="left", padx=(0, 15))
        
        self.time_label = ctk.CTkLabel(
            time_frame,
            text="00:00 / 00:00",
            font=ctk.CTkFont(family="Monaco", size=16, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        self.time_label.pack()
        
        # Speed indicator
        self.speed_indicator = ctk.CTkLabel(
            time_frame,
            text="1.0×",
            font=ctk.CTkFont(size=11),
            text_color=VSCODE_COLORS["primary"]
        )
        self.speed_indicator.pack()
        
        # Center controls - Speed
        self.create_speed_controls()
        
        # Progress bar (right side)
        self.create_progress_controls()
        
    def create_speed_controls(self):
        """Create speed control section"""
        center_controls = ctk.CTkFrame(
            self.controls_frame,
            fg_color=VSCODE_COLORS["surface_light"],
            corner_radius=8,
        )
        center_controls.grid(row=0, column=1, sticky="ew", padx=15, pady=10)
        center_controls.grid_columnconfigure((0, 1, 2, 3), weight=1)
        center_controls.grid_rowconfigure(1, weight=1)

        # Speed section header
        speed_header = ctk.CTkLabel(
            center_controls,
            text="⚡ Playback Speed",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=VSCODE_COLORS["text"],
        )
        speed_header.grid(row=0, column=0, columnspan=4, pady=(8, 5))

        # Speed controls container
        speed_controls = ctk.CTkFrame(center_controls, fg_color="transparent")
        speed_controls.grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 8))
        
        # Speed preset buttons
        speed_presets = [
            ("0.25×", 0.25, "#ff6b6b"),
            ("0.5×", 0.5, "#ffa500"), 
            ("1×", 1.0, "#4ecdc4"),
            ("1.5×", 1.5, "#45b7d1"),
            ("2×", 2.0, "#96ceb4"),
            ("4×", 4.0, "#feca57"),
            ("8×", 8.0, "#ff9ff3")
        ]
        
        self.speed_buttons = {}
        for i, (text, speed, color) in enumerate(speed_presets):
            btn = ctk.CTkButton(
                speed_controls,
                text=text,
                width=45,
                height=30,
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda s=speed: self.set_speed(s),
                fg_color=color if speed == 1.0 else "transparent",
                hover_color=color,
                border_width=2,
                border_color=color,
                corner_radius=15,
            )
            row, col = divmod(i, 4)
            btn.grid(row=row, column=col, padx=2, pady=2, sticky="ew")
            self.speed_buttons[speed] = btn

        # Custom speed slider
        slider_frame = ctk.CTkFrame(center_controls, fg_color="transparent")
        slider_frame.grid(row=2, column=0, columnspan=4, pady=(5, 8))
        
        ctk.CTkLabel(
            slider_frame,
            text="Custom:",
            font=ctk.CTkFont(size=10),
            text_color=VSCODE_COLORS["text_secondary"]
        ).pack(side="left", padx=(5, 5))

        self.speed_slider = ctk.CTkSlider(
            slider_frame,
            from_=0.25,
            to=self.max_speed,
            number_of_steps=31,
            command=self.on_speed_slider_change,
            width=120,
            height=16
        )
        self.speed_slider.pack(side="left", padx=5)
        self.speed_slider.set(1.0)
            
    def create_progress_controls(self):
        """Create progress control section"""
        progress_frame = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        progress_frame.grid(row=0, column=2, sticky="ew", padx=15, pady=10)
        progress_frame.grid_columnconfigure(0, weight=1)
        
        # Progress label
        ctk.CTkLabel(
            progress_frame,
            text="Progress",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=VSCODE_COLORS["text_secondary"]
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        # Progress bar
        self.progress_var = ctk.DoubleVar()
        self.progress_slider = ctk.CTkSlider(
            progress_frame,
            from_=0,
            to=100,
            variable=self.progress_var,
            command=self.seek_to_position,
            height=24,
            progress_color=VSCODE_COLORS["primary"]
        )
        self.progress_slider.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        
        # Frame info
        info_frame = ctk.CTkFrame(progress_frame, fg_color="transparent")
        info_frame.grid(row=2, column=0, sticky="ew")
        info_frame.grid_columnconfigure(1, weight=1)
        
        self.frame_label = ctk.CTkLabel(
            info_frame,
            text="Frame: 0/0",
            font=ctk.CTkFont(size=10),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.frame_label.grid(row=0, column=0, sticky="w")
        
        # Focus indicator
        self.focus_indicator = ctk.CTkLabel(
            info_frame,
            text="",
            font=ctk.CTkFont(size=9),
            text_color=VSCODE_COLORS["primary"]
        )
        self.focus_indicator.grid(row=0, column=1, sticky="e")
        
    def load_video(self, video_path):
        """Load video file with accurate timing setup"""
        try:
            if self.cap:
                self.cap.release()
            
            self.cap = cv2.VideoCapture(video_path)
            if not self.cap.isOpened():
                self.show_error("Could not open video file")
                return False
            
            self.video_path = video_path
            self.current_frame = 0
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
            
            # Ensure FPS is reasonable (some videos report crazy values)
            if self.fps > 120 or self.fps < 1:
                self.fps = 30  # Default to 30 FPS for problematic videos
            
            # Calculate base frame delay for accurate timing
            self.frame_delay_ms = int(1000.0 / self.fps)
            
            self.display_frame(0)
            self.update_time_display()
            self.update_frame_display()
            
            return True
            
        except Exception as e:
            self.show_error(f"Error loading video: {str(e)}")
            return False
    
    def enter_fullscreen(self, event=None):
        """Enter YouTube-style fullscreen mode with proper management"""
        if not self.cap:
            return
            
        # Always create new fullscreen player (destroy old one if exists)
        if self.fullscreen_player:
            try:
                self.fullscreen_player.destroy()
            except:
                pass
            self.fullscreen_player = None
        
        try:
            self.fullscreen_player = FullscreenVideoPlayer(self.winfo_toplevel(), self)
            
            # Handle cleanup when fullscreen closes
            def on_fullscreen_close():
                self.fullscreen_player = None
            
            self.fullscreen_player.bind("<Destroy>", lambda e: on_fullscreen_close())
            
            # IMPORTANT: If main player is playing, ensure fullscreen starts playing too
            if self.is_playing:
                # The sync_with_main_player method in fullscreen will handle this automatically
                pass
            
        except Exception as e:
            print(f"Error creating fullscreen player: {e}")
            self.fullscreen_player = None
    
    def on_canvas_click(self, event):
        """Handle canvas click"""
        self.canvas.focus_set()
        
    def on_focus_in(self, event):
        """Handle canvas gaining focus"""
        self.has_focus = True
        self.focus_indicator.configure(text="🎯 Focused • ESC to release • F11 for fullscreen")
        self.canvas.configure(highlightthickness=2)
        
    def on_focus_out(self, event):
        """Handle canvas losing focus"""
        self.has_focus = False
        self.focus_indicator.configure(text="")
        self.canvas.configure(highlightthickness=1)
        
    def on_key_press(self, event):
        """Enhanced keyboard shortcuts"""
        if not self.has_focus:
            return
            
        handled = False
        
        # Fullscreen controls
        if event.keysym in ["F11", "f"]:
            self.enter_fullscreen()
            handled = True
        # Speed controls
        elif event.keysym in ["minus", "KP_Subtract"]:
            new_speed = max(0.25, self.playback_speed - 0.25)
            self.set_speed(new_speed)
            handled = True
        elif event.keysym in ["plus", "equal", "KP_Add"]:
            new_speed = min(self.max_speed, self.playback_speed + 0.25)
            self.set_speed(new_speed)
            handled = True
        elif event.char in "12345678":
            speeds = [0.25, 0.5, 1.0, 1.5, 2.0, 4.0, 6.0, 8.0]
            try:
                index = int(event.char) - 1
                if 0 <= index < len(speeds):
                    self.set_speed(speeds[index])
                    handled = True
            except:
                pass
        elif event.keysym == "space":
            self.toggle_playback()
            handled = True
        elif event.keysym == "Escape":
            self.canvas.master.focus_set()
            handled = True
        elif event.keysym == "BackSpace":
            self.set_speed(1.0)
            handled = True
            
        return "break" if handled else None
    
    def on_speed_slider_change(self, value):
        """Handle custom speed slider change"""
        # Round to nearest 0.25
        speed = round(value * 4) / 4
        self.set_speed(speed)
    
    def toggle_playback(self):
        """Toggle playback with proper position maintenance (YouTube-style)"""
        if not self.cap:
            return

        if self.is_playing:
            # Pause at current position (just like YouTube)
            self.is_playing = False
            self.play_button.configure(text="▶")
            if self.playback_timer:
                self.after_cancel(self.playback_timer)
                self.playback_timer = None
        else:
            # Check if we're at the end - if so, restart from beginning
            if self.current_frame >= self.total_frames - 1:
                self.current_frame = 0
                self.display_frame(0)
                self.update_time_display()
                self.update_frame_display()
            
            # Resume/start from current position (just like YouTube)
            self.is_playing = True
            self.play_button.configure(text="⏸")
            self.start_playback_loop()
    
    def start_playback_loop(self):
        """Start simple timer-based playback loop with accurate timing"""
        if not self.is_playing or not self.cap:
            return
        
        # Check if we've reached the end
        if self.current_frame >= self.total_frames - 1:
            self.is_playing = False
            self.play_button.configure(text="▶")
            if self.fullscreen_player:
                self.fullscreen_player.play_btn.configure(text="▶")
            # Don't reset frame here - let toggle_playback handle replay
            return
        
        # Advance to next frame
        self.current_frame += 1
        self.display_frame(self.current_frame)
        
        # Update UI periodically (every 5 frames for better responsiveness)
        if self.current_frame % 5 == 0:
            self.update_time_display()
            self.update_frame_display()
        
        # Calculate accurate frame delay based on actual video FPS and playback speed
        # Use milliseconds with decimal precision for accuracy
        base_frame_time = 1000.0 / self.fps  # milliseconds per frame
        adjusted_frame_time = base_frame_time / self.playback_speed
        
        # Ensure minimum delay for very high speeds to prevent UI freezing
        frame_delay = max(1, int(adjusted_frame_time))
        
        # Schedule next frame with accurate timing
        self.playback_timer = self.after(frame_delay, self.start_playback_loop)
    
    def seek_to_frame(self, frame_number):
        """Seek to specific frame and maintain state"""
        if not self.cap:
            return
        
        self.current_frame = max(0, min(frame_number, self.total_frames - 1))
        self.display_frame(self.current_frame)
        self.update_time_display()
        self.update_frame_display()
        
        # Update fullscreen player if it exists
        if self.fullscreen_player and self.fullscreen_player.winfo_exists():
            self.fullscreen_player.display_frame(self.current_frame)
            if self.fullscreen_player.controls_visible:
                self.fullscreen_player.update_progress_bar()
    
    def seek_to_position(self, value):
        """Seek to specific position"""
        if not self.cap:
            return
            
        frame_number = int((value / 100) * (self.total_frames - 1))
        self.seek_to_frame(frame_number)
    
    def set_speed(self, speed):
        """Set playback speed with accurate timing updates"""
        old_speed = self.playback_speed
        self.playback_speed = max(0.25, min(speed, self.max_speed))
        self.speed_indicator.configure(text=f"{self.playback_speed}×")
        self.speed_slider.set(self.playback_speed)
        
        # Update speed button styles
        for btn_speed, btn in self.speed_buttons.items():
            if btn_speed == self.playback_speed:
                btn.configure(fg_color=btn.cget("border_color"))
            else:
                btn.configure(fg_color="transparent")
        
        # If speed changed significantly and we're playing, restart the timer
        # with new timing to ensure accuracy
        if abs(self.playback_speed - old_speed) > 0.1 and self.is_playing:
            if self.playback_timer:
                self.after_cancel(self.playback_timer)
                self.playback_timer = None
            # Restart with new timing
            self.start_playback_loop()
    
    def display_frame(self, frame_number):
        """Display video frame with improved reliability"""
        if not self.cap:
            return
            
        try:
            # Ensure frame number is within valid range
            frame_number = max(0, min(frame_number, self.total_frames - 1))
            
            # Use OpenCV's built-in frame positioning (more reliable than manual tracking)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = self.cap.read()
            
            if not ret:
                return
                
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                self.after(100, lambda: self.display_frame(frame_number))
                return
                
            # Convert and resize frame
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_height, frame_width = frame_rgb.shape[:2]
            
            # Calculate display size maintaining aspect ratio
            aspect_ratio = frame_width / frame_height
            if canvas_width / canvas_height > aspect_ratio:
                display_height = canvas_height - 20
                display_width = int(display_height * aspect_ratio)
            else:
                display_width = canvas_width - 20
                display_height = int(display_width / aspect_ratio)
                
            interpolation = cv2.INTER_LINEAR if self.playback_speed <= 2.0 else cv2.INTER_NEAREST
            frame_resized = cv2.resize(frame_rgb, (display_width, display_height), interpolation=interpolation)
            
            # Convert and display
            image = Image.fromarray(frame_resized)
            self.photo = ImageTk.PhotoImage(image)
            
            self.canvas.delete("all")
            self.canvas.create_image(
                canvas_width // 2,
                canvas_height // 2,
                image=self.photo,
                anchor="center"
            )
            
            # Update progress
            progress = (frame_number / max(self.total_frames - 1, 1)) * 100
            self.progress_var.set(progress)
            
        except Exception as e:
            print(f"Frame display error: {e}")
            # Don't crash, just skip this frame
    
    def update_time_display(self):
        """Update time display"""
        if not self.cap:
            return
            
        current_seconds = self.current_frame / self.fps
        total_seconds = self.total_frames / self.fps
        
        current_time = f"{int(current_seconds // 60):02d}:{int(current_seconds % 60):02d}"
        total_time = f"{int(total_seconds // 60):02d}:{int(total_seconds % 60):02d}"
        
        self.time_label.configure(text=f"{current_time} / {total_time}")
        
    def update_frame_display(self):
        """Update frame counter"""
        self.frame_label.configure(text=f"Frame: {self.current_frame}/{self.total_frames}")
    
    def show_placeholder(self):
        """Show placeholder with YouTube-style instructions"""
        self.canvas.delete("all")
        canvas_width = self.canvas.winfo_width() or 400
        canvas_height = self.canvas.winfo_height() or 300
        
        self.canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill="black", outline="")
        
        self.canvas.create_text(
            canvas_width/2, canvas_height/2 - 40,
            text="🎬",
            font=("Arial", 56),
            fill="#4a5568"
        )
        
        self.canvas.create_text(
            canvas_width/2, canvas_height/2 + 10,
            text="Professional Video Player",
            font=("Arial", 18, "bold"),
            fill="#6b7280"
        )
        
        self.canvas.create_text(
            canvas_width/2, canvas_height/2 + 35,
            text="Click 'Quick Preview' to generate preview",
            font=("Arial", 12),
            fill="#9ca3af"
        )
        
        instructions = [
            "• Double-click or F11 for YouTube-style fullscreen",
            "• ▶ Play/Pause maintains position • Auto-replay when ended",
            "• 1-8 keys for speed presets • +/- for speed adjust",
            "• Click progress bar to seek • Accurate speed playback"
        ]
        
        for i, instruction in enumerate(instructions):
            self.canvas.create_text(
                canvas_width/2, canvas_height/2 + 65 + i*16,
                text=instruction,
                font=("Arial", 10),
                fill="#6b7280"
            )
    
    def show_error(self, message):
        """Show error message"""
        self.canvas.delete("all")
        canvas_width = self.canvas.winfo_width() or 400
        canvas_height = self.canvas.winfo_height() or 300
        
        self.canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill="#2d1b1b", outline="")
        
        self.canvas.create_text(
            canvas_width/2, canvas_height/2 - 30,
            text="⚠️",
            font=("Arial", 36),
            fill="#ef4444"
        )
        
        lines = message.split('\n')
        for i, line in enumerate(lines):
            self.canvas.create_text(
                canvas_width/2, canvas_height/2 + 20 + i*20,
                text=line,
                font=("Arial", 12),
                fill="#ef4444",
                width=canvas_width-40
            )
    
    def clear(self):
        """Clear video player"""
        # Stop playback first
        if self.is_playing:
            self.is_playing = False
            if self.playback_timer:
                self.after_cancel(self.playback_timer)
                self.playback_timer = None
        
        if self.cap:
            self.cap.release()
            self.cap = None
            
        # Close fullscreen if open
        if self.fullscreen_player:
            try:
                self.fullscreen_player.destroy()
            except:
                pass
            self.fullscreen_player = None
            
        self.video_path = None
        self.current_frame = 0
        self.total_frames = 0
        
        self.set_speed(1.0)
        self.has_focus = False
        self.focus_indicator.configure(text="")
        self.canvas.configure(highlightthickness=1)
        
        self.progress_var.set(0)
        self.time_label.configure(text="00:00 / 00:00")
        self.frame_label.configure(text="Frame: 0/0")
        self.play_button.configure(text="▶")
        
        self.show_placeholder()

class PyPISearchEngine:
    """Advanced PyPI search engine with modern features"""
    
    def __init__(self):
        self.base_url = "https://pypi.org"
        self.api_url = "https://pypi.org/pypi"
        self.search_url = "https://pypi.org/search"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': f'{APP_NAME}/{APP_VERSION} (Package Manager)'
        })
        
        # Cache for search results
        self.search_cache = {}
        self.package_cache = {}
        
    async def search_packages(self, query: str, max_results: int = 50) -> List[PackageInfo]:
        """Search for packages asynchronously"""
        try:
            # Check cache first
            cache_key = f"{query}_{max_results}"
            if cache_key in self.search_cache:
                return self.search_cache[cache_key]
                
            # For demo, return enhanced mock data based on categories
            packages = self._get_enhanced_package_list(query, max_results)
            
            # Cache results
            self.search_cache[cache_key] = packages
            return packages
                    
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def _get_enhanced_package_list(self, query: str, max_results: int) -> List[PackageInfo]:
        """Get enhanced package list based on query and categories"""
        packages = []
        
        # Enhanced package database
        package_db = {
            # Core Data Science
            "numpy": PackageInfo("numpy", "1.24.3", "Fundamental package for array computing", "NumPy Developers", "BSD", "https://numpy.org", "", 50000000, 25000, category="Data Science & Analytics"),
            "pandas": PackageInfo("pandas", "2.0.3", "Powerful data analysis and manipulation library", "Pandas Team", "BSD", "https://pandas.pydata.org", "", 40000000, 35000, category="Data Science & Analytics"),
            "matplotlib": PackageInfo("matplotlib", "3.7.2", "Comprehensive library for creating static, animated visualizations", "Matplotlib Team", "PSF", "https://matplotlib.org", "", 30000000, 18000, category="Data Science & Analytics"),
            "seaborn": PackageInfo("seaborn", "0.12.2", "Statistical data visualization based on matplotlib", "Michael Waskom", "BSD", "https://seaborn.pydata.org", "", 15000000, 10000, category="Data Science & Analytics"),
            "scipy": PackageInfo("scipy", "1.11.1", "Fundamental algorithms for scientific computing", "SciPy Developers", "BSD", "https://scipy.org", "", 25000000, 12000, category="Scientific Computing"),
            "scikit-learn": PackageInfo("scikit-learn", "1.3.0", "Machine learning library for Python", "Scikit-learn Developers", "BSD", "https://scikit-learn.org", "", 20000000, 15000, category="Machine Learning & AI"),
            
            # Machine Learning & AI
            "tensorflow": PackageInfo("tensorflow", "2.13.0", "An end-to-end open source machine learning platform", "Google", "Apache", "https://tensorflow.org", "", 35000000, 180000, category="Machine Learning & AI"),
            "pytorch": PackageInfo("pytorch", "2.0.1", "Tensors and Dynamic neural networks in Python", "PyTorch Team", "BSD", "https://pytorch.org", "", 30000000, 65000, category="Machine Learning & AI"),
            "transformers": PackageInfo("transformers", "4.32.0", "State-of-the-art Machine Learning for JAX, PyTorch and TensorFlow", "Hugging Face", "Apache", "https://huggingface.co/transformers", "", 10000000, 95000, category="Machine Learning & AI"),
            "opencv-python": PackageInfo("opencv-python", "4.8.0", "Open Source Computer Vision Library", "OpenCV Team", "MIT", "https://opencv.org", "", 18000000, 13000, category="Animation & Graphics"),
            
            # Web Development
            "django": PackageInfo("django", "4.2.3", "High-level Python web framework", "Django Software Foundation", "BSD", "https://djangoproject.com", "", 25000000, 65000, category="Web Development"),
            "flask": PackageInfo("flask", "2.3.2", "A simple framework for building complex web applications", "Armin Ronacher", "BSD", "https://flask.palletsprojects.com", "", 22000000, 62000, category="Web Development"),
            "fastapi": PackageInfo("fastapi", "0.101.0", "FastAPI framework, high performance, easy to learn", "Sebastián Ramirez", "MIT", "https://fastapi.tiangolo.com", "", 15000000, 65000, category="Web Development"),
            "requests": PackageInfo("requests", "2.31.0", "HTTP library for Python", "Kenneth Reitz", "Apache", "https://requests.readthedocs.io", "", 45000000, 50000, category="Web Development"),
            
            # GUI Development
            "customtkinter": PackageInfo("customtkinter", "5.2.0", "Modern and customizable python UI-library based on Tkinter", "Tom Schimansky", "MIT", "https://github.com/TomSchimansky/CustomTkinter", "", 2000000, 8500, category="GUI & Desktop Development"),
            "pyqt5": PackageInfo("pyqt5", "5.15.9", "Python bindings for the Qt cross platform library", "Riverbank Computing", "GPL", "https://riverbankcomputing.com/software/pyqt", "", 12000000, 3500, category="GUI & Desktop Development"),
            "kivy": PackageInfo("kivy", "2.2.0", "Open source UI framework written in Python", "Kivy Organization", "MIT", "https://kivy.org", "", 5000000, 15000, category="GUI & Desktop Development"),
            
            # Animation & Graphics
            "manim": PackageInfo("manim", "0.17.3", "Mathematical Animation Engine", "3b1b & Manim Community", "MIT", "https://manim.community", "", 1500000, 12000, category="Animation & Graphics"),
            "pygame": PackageInfo("pygame", "2.5.0", "Python Game Development", "Pygame Community", "LGPL", "https://pygame.org", "", 8000000, 5000, category="Game Development"),
            "pillow": PackageInfo("pillow", "10.0.0", "Python Imaging Library (Fork)", "Alex Clark and Contributors", "PIL", "https://python-pillow.org", "", 25000000, 11000, category="Image Processing"),
            
            # Development Tools
            "pytest": PackageInfo("pytest", "7.4.0", "Framework makes it easy to write small tests", "Holger Krekel", "MIT", "https://pytest.org", "", 30000000, 11000, category="Development Tools"),
            "black": PackageInfo("black", "23.7.0", "The uncompromising Python code formatter", "Python Software Foundation", "MIT", "https://black.readthedocs.io", "", 12000000, 35000, category="Development Tools"),
            "jedi": PackageInfo("jedi", "0.18.2", "An autocompletion tool for Python", "David Halter", "MIT", "https://github.com/davidhalter/jedi", "", 15000000, 5500, category="Development Tools"),
            
            # Scientific Computing
            "sympy": PackageInfo("sympy", "1.12", "Python library for symbolic mathematics", "SymPy Development Team", "BSD", "https://sympy.org", "", 5000000, 10000, category="Scientific Computing"),
            "networkx": PackageInfo("networkx", "3.1", "Python package for network analysis", "NetworkX Developers", "BSD", "https://networkx.org", "", 8000000, 13000, category="Scientific Computing"),
            
            # Text Processing & NLP
            "nltk": PackageInfo("nltk", "3.8.1", "Natural Language Toolkit", "NLTK Team", "Apache", "https://nltk.org", "", 10000000, 12000, category="Text Processing & NLP"),
            "spacy": PackageInfo("spacy", "3.6.1", "Industrial-strength Natural Language Processing", "Explosion AI", "MIT", "https://spacy.io", "", 5000000, 25000, category="Text Processing & NLP"),
            
            # Database & ORM
            "sqlalchemy": PackageInfo("sqlalchemy", "2.0.19", "Database Abstraction Library", "Mike Bayer", "MIT", "https://sqlalchemy.org", "", 15000000, 5000, category="Database & ORM"),
            "pymongo": PackageInfo("pymongo", "4.4.1", "Python driver for MongoDB", "MongoDB, Inc.", "Apache", "https://pymongo.readthedocs.io", "", 8000000, 1500, category="Database & ORM"),
            
            # Cloud & Infrastructure
            "boto3": PackageInfo("boto3", "1.28.22", "The AWS SDK for Python", "Amazon Web Services", "Apache", "https://boto3.amazonaws.com", "", 20000000, 8500, category="Cloud & Infrastructure"),
            "docker": PackageInfo("docker", "6.1.3", "A Python library for the Docker Engine API", "Docker, Inc.", "Apache", "https://docker-py.readthedocs.io", "", 12000000, 6500, category="Cloud & Infrastructure"),
            
            # System utilities
            "psutil": PackageInfo("psutil", "5.9.5", "Cross-platform lib for process and system monitoring", "Giampaolo Rodola", "BSD", "https://github.com/giampaolo/psutil", "", 18000000, 8500, category="System & Networking"),
            "rich": PackageInfo("rich", "13.4.2", "Rich text and beautiful formatting in the terminal", "Will McGugan", "MIT", "https://rich.readthedocs.io", "", 5000000, 45000, category="System & Networking"),
            
            # Finance
            "yfinance": PackageInfo("yfinance", "0.2.20", "Download market data from Yahoo! Finance", "Ran Aroussi", "Apache", "https://github.com/ranaroussi/yfinance", "", 2000000, 11000, category="Finance & Trading"),
            
            # Audio/Video
            "moviepy": PackageInfo("moviepy", "1.0.3", "Video editing with Python", "Zulko", "MIT", "https://zulko.github.io/moviepy", "", 3000000, 11000, category="Audio & Video Processing"),
            "pydub": PackageInfo("pydub", "0.25.1", "Manipulate audio with a simple and easy high level interface", "James Robert", "MIT", "https://github.com/jiaaro/pydub", "", 8000000, 7000, category="Audio & Video Processing"),
        }
        
        # Filter packages based on query
        if query:
            query_lower = query.lower()
            filtered_packages = []
            
            # Search in package names, descriptions, and categories
            for pkg_name, pkg_info in package_db.items():
                if (query_lower in pkg_name.lower() or 
                    query_lower in pkg_info.description.lower() or
                    query_lower in pkg_info.category.lower()):
                    filtered_packages.append(pkg_info)
            
            # Sort by relevance (exact matches first)
            filtered_packages.sort(key=lambda p: (
                not p.name.lower().startswith(query_lower),
                -p.downloads
            ))
            
            packages = filtered_packages[:max_results]
        else:
            # Return popular packages if no query
            popular_package_names = POPULAR_PACKAGES[:max_results]
            packages = [package_db.get(name) for name in popular_package_names if name in package_db]
            packages = [p for p in packages if p is not None]
        
        return packages
    
    async def get_package_info(self, package_name: str) -> Optional[PackageInfo]:
        """Get detailed package information"""
        try:
            # Check cache first
            if package_name in self.package_cache:
                return self.package_cache[package_name]
                
            # For demo, return mock data
            mock_packages = self._get_enhanced_package_list("", 1000)
            for pkg in mock_packages:
                if pkg.name == package_name:
                    self.package_cache[package_name] = pkg
                    return pkg
                        
        except Exception as e:
            logger.error(f"Package info error: {e}")
            return None
    
    def get_popular_packages(self) -> List[str]:
        """Get list of popular packages"""
        return POPULAR_PACKAGES

class ManimStudioApp:
    def __init__(self, latex_path: Optional[str] = None, debug: bool = False):
        # Initialize main window
        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} - Professional Edition v{APP_VERSION}")
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(1600, screen_w - 100)
        height = min(1000, screen_h - 100)
        self.root.geometry(f"{width}x{height}")
        
        # Set minimum size
        self.root.minsize(1200, 800)
        
        # Try to set icon
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass
            
        # Store LaTeX path (``None`` if not found)
        self.latex_path = latex_path
        self.latex_installed = bool(latex_path)

        # Debug flag to allow re-running setup
        self.debug_mode = debug

        # Initialize logger reference
        self.logger = logger
        self.last_manim_output_path = None
        # Initialize virtual environment manager
        self.venv_manager = VirtualEnvironmentManager(self)
        
        # Initialize system terminal manager (will be created in create_output_area)
        self.terminal = None
        
        # IMPORTANT: Auto-activate manim_studio_default environment if it exists and is ready
        self.auto_activate_default_environment()
        
        # Run environment setup before showing UI (only if still needed after auto-activation)
        if self.debug_mode and self.venv_manager.needs_setup:
            self.root.withdraw()
            self.venv_manager.show_setup_dialog()
            self.root.deiconify()

        # Load settings before initializing variables that depend on them
        self.load_settings()
        self.initialize_variables()
        
        # Setup UI
        # Setup UI
        try:
            self.logger.info("Starting UI creation...")
            self.create_ui()
            self.logger.info("UI created successfully")
            
            # Apply VSCode color scheme
            self.apply_vscode_theme()
            self.logger.info("Theme applied successfully")
            
        except Exception as e:
            self.logger.error(f"UI creation failed: {e}")
            import traceback
            self.logger.error(f"UI creation traceback: {traceback.format_exc()}")
            raise
        
        # Log UI creation success
        self.logger.info("UI created successfully")
        
    def check_environment_setup(self):
        """Check if environment setup is needed"""
        if self.venv_manager.needs_setup:
            self.venv_manager.show_setup_dialog()
            
    def load_settings(self):
        """Load settings from file"""
        if getattr(sys, 'frozen', False):
            # Running as executable
            settings_dir = os.path.join(os.path.dirname(sys.executable), "settings")
        else:
            # Running as script
            settings_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")
    
        os.makedirs(settings_dir, exist_ok=True)
        self.settings_file = os.path.join(settings_dir, "settings.json")
        
        # Default settings
        self.settings = {
            "quality": "720p",
            "format": "MP4 Video",
            "fps": 30,
            "preview_quality": "Medium",
            "auto_preview": False,
            "theme": "Dark+",
            "font_size": 14,
            "current_venv": None,
            "intellisense_enabled": True,
            "auto_completion_delay": 500,
            "custom_theme": None,
            "cpu_usage": "Medium",
            "cpu_custom_cores": 2,
            "custom_width": 1920,
            "custom_height": 1080,
            "custom_fps": 30
        }
        
        # Load from file if exists
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    saved_settings = json.load(f)
                    self.settings.update(saved_settings)
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            
        # Apply custom theme if available
        if self.settings.get("custom_theme"):
            THEME_SCHEMES["Custom"] = self.settings["custom_theme"]
            
    def save_settings(self):
        """Save settings to file"""
        try:
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            
            # Update current venv in settings
            self.settings["current_venv"] = self.venv_manager.current_venv
            
            # Save custom resolution settings
            if hasattr(self, 'custom_width_var'):
                self.settings["custom_width"] = self.custom_width_var.get()
                self.settings["custom_height"] = self.custom_height_var.get()
                self.settings["custom_fps"] = self.custom_fps_var.get()
            
            # Save custom theme if it exists
            if "Custom" in THEME_SCHEMES:
                self.settings["custom_theme"] = THEME_SCHEMES["Custom"]
            
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            
    def initialize_variables(self):
        """Initialize all application variables"""
        # Application state
        self.current_code = ""
        self.current_file_path = None
        self.video_data = None
        self.audio_path = None
        self.image_paths = []
        self.last_preview_code = ""
        self.preview_video_path = None
        self.current_temp_dir = None
        self.current_scene_file = None

        # UI state
        self.is_rendering = False
        self.is_previewing = False
        self.render_process = None
        self.preview_process = None
        
        # Asset management
        self.asset_cards = []
        
        # Variables for UI controls
        self.quality_var = ctk.StringVar(value=self.settings["quality"])
        self.format_var = ctk.StringVar(value=self.settings["format"])
        self.fps_var = ctk.StringVar(value=str(self.settings["fps"]))
        self.preview_quality_var = ctk.StringVar(value=self.settings["preview_quality"])
        self.auto_preview_var = ctk.BooleanVar(value=self.settings["auto_preview"])
        self.font_size_var = ctk.IntVar(value=self.settings["font_size"])
        self.intellisense_var = ctk.BooleanVar(value=self.settings["intellisense_enabled"])
        self.current_theme = self.settings["theme"]
        
        # Custom resolution variables
        self.custom_width_var = ctk.IntVar(value=self.settings["custom_width"])
        self.custom_height_var = ctk.IntVar(value=self.settings["custom_height"])
        self.custom_fps_var = ctk.IntVar(value=self.settings["custom_fps"])
        
        # CPU information
        self.cpu_count = psutil.cpu_count(logical=True)
        self.cpu_usage_var = ctk.StringVar(value=self.settings.get("cpu_usage", "Medium"))
        self.cpu_custom_cores_var = ctk.IntVar(value=self.settings.get("cpu_custom_cores", 2))
        
        # Load the selected theme
        if self.current_theme in THEME_SCHEMES:
            global VSCODE_COLORS
            VSCODE_COLORS = THEME_SCHEMES[self.current_theme].copy()
            
            # Ensure critical colors exist after theme switch
            required_colors = {
                "success": "#16A085",
                "error": "#E74C3C", 
                "warning": "#F39C12",
                "info": "#3498DB"
            }
            for key, default_value in required_colors.items():
                if key not in VSCODE_COLORS:
                    VSCODE_COLORS[key] = default_value
        
    def apply_vscode_theme(self):
        """Apply VSCode-like color theme safely"""
        colors = VSCODE_COLORS
        
        try:
            # Apply to main window
            self.root.configure(fg_color=colors["background"])
            
            # Apply to sidebar
            if hasattr(self, 'sidebar'):
                try:
                    self.sidebar.configure(fg_color=colors["surface"])
                except Exception:
                    pass
                    
            # Apply to main area
            if hasattr(self, 'main_area'):
                try:
                    self.main_area.configure(fg_color=colors["background"])
                except Exception:
                    pass
            
            # FIXED: Apply to output text with error handling
            if hasattr(self, 'output_text'):
                try:
                    # Check if it's a CustomTkinter widget
                    if hasattr(self.output_text, 'fg_color'):
                        self.output_text.configure(
                            fg_color=colors["background"],
                            text_color=colors["text"]
                        )
                    else:
                        # It's a regular tkinter widget
                        self.output_text.configure(
                            bg=colors["background"],
                            fg=colors["text"],
                            insertbackground=colors["text"],
                            selectbackground=colors["selection"],
                            selectforeground=colors.get("text_bright", colors["text"])
                        )
                except Exception as e:
                    print(f"Warning: Could not apply theme to output_text: {e}")
            
            # Apply to code editor
            if hasattr(self, 'code_editor'):
                try:
                    self.code_editor.configure(
                        bg=colors["background"],
                        fg=colors["text"],
                        insertbackground=colors["text"],
                        selectbackground=colors["selection"]
                    )
                except Exception:
                    pass
            
            # Apply to other components safely
            components_to_theme = [
                'sidebar_scroll', 'assets_frame', 'preview_frame', 
                'render_frame', 'settings_frame'
            ]
            
            for component_name in components_to_theme:
                if hasattr(self, component_name):
                    try:
                        component = getattr(self, component_name)
                        if hasattr(component, 'configure'):
                            component.configure(fg_color=colors["surface"])
                    except Exception:
                        pass
                        
        except Exception as e:
            print(f"Warning: Theme application failed: {e}")     
    def apply_theme(self, theme_colors):
        """Apply a new theme to the application"""
        global VSCODE_COLORS
        VSCODE_COLORS = theme_colors.copy()
        
        # Update CustomTkinter colors
        ctk.set_appearance_mode("dark" if theme_colors["background"] == "#1E1E1E" else "light")
        
        # Apply to main components
        self.apply_vscode_theme()
        
        # Update editor colors
        if hasattr(self, 'code_editor'):
            self.code_editor.configure(
                bg=theme_colors["background"],
                fg=theme_colors["text"],
                insertbackground=theme_colors["text"],
                selectbackground=theme_colors["selection"],
                selectforeground=theme_colors["text_bright"]
            )
            
            # Reconfigure syntax highlighting tags
            self.code_editor.configure_tags()
            
            # Reapply syntax highlighting
            self.code_editor.apply_syntax_highlighting()
        
        # Update line numbers
        if hasattr(self, 'line_numbers'):
            self.line_numbers.configure(
                bg=theme_colors["line_numbers_bg"],
                fg=theme_colors["line_numbers"]
            )
            
        # Save the theme
        self.settings["theme"] = "Custom"  # Mark as custom theme
        self.save_settings()
        
    def create_ui(self):
        """Create the main user interface"""
        # Configure main window grid
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        
        # Create main components
        self.create_header()
        self.create_sidebar()
        self.create_main_area()
        self.create_status_bar()
        self.create_menu_bar()
        
        # Bind shortcuts
        self.bind_shortcuts()
        
    def create_header(self):
        """Create header with toolbar"""
        self.header = ctk.CTkFrame(self.root, height=60, corner_radius=0, fg_color=VSCODE_COLORS["surface"])
        self.header.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.header.grid_columnconfigure(1, weight=1)
        
        # Left side - Logo and title
        header_left = ctk.CTkFrame(self.header, fg_color="transparent")
        header_left.grid(row=0, column=0, sticky="w", padx=20, pady=10)
        
        # App icon/logo
        logo_label = ctk.CTkLabel(
            header_left,
            text="🎬",
            font=ctk.CTkFont(size=28)
        )
        logo_label.pack(side="left", padx=(0, 10))
        
        # App title
        title_label = ctk.CTkLabel(
            header_left,
            text=APP_NAME,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        )
        title_label.pack(side="left")
        
        # Subtitle
        subtitle_label = ctk.CTkLabel(
            header_left,
            text=f"Professional Edition v{APP_VERSION}",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        subtitle_label.pack(side="left", padx=(10, 0))
        
        # Center - Quick actions
        header_center = ctk.CTkFrame(self.header, fg_color="transparent")
        header_center.grid(row=0, column=1, pady=10)
        
        # Quick action buttons
        quick_actions = [
            ("📄", "New File", self.new_file),
            ("📁", "Open File", self.open_file),
            ("💾", "Save File", self.save_file),
            ("▶️", "Render Animation", self.render_animation),
            ("👁️", "Quick Preview", self.quick_preview),
            ("🔧", "Environment Setup", self.manage_environment),
        ]
        
        for icon, tooltip, command in quick_actions:
            btn = ctk.CTkButton(
                header_center,
                text=icon,
                width=45,
                height=40,
                font=ctk.CTkFont(size=16),
                command=command,
                fg_color="transparent",
                hover_color=VSCODE_COLORS["surface_light"],
                corner_radius=8
            )
            btn.pack(side="left", padx=2)
            self.create_tooltip(btn, tooltip)
            
        # Right side - Settings and controls
        header_right = ctk.CTkFrame(self.header, fg_color="transparent")
        header_right.grid(row=0, column=2, sticky="e", padx=20, pady=10)
        
        # IntelliSense toggle
        self.intellisense_checkbox = ctk.CTkCheckBox(
            header_right,
            text="IntelliSense",
            variable=self.intellisense_var,
            command=self.toggle_intellisense,
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text"]
        )
        self.intellisense_checkbox.pack(side="right", padx=15)
        
        # Virtual environment display
        venv_frame = ctk.CTkFrame(header_right, fg_color=VSCODE_COLORS["surface_light"])
        venv_frame.pack(side="right", padx=10)
        
        venv_label = ctk.CTkLabel(venv_frame, text="🔧", font=ctk.CTkFont(size=14))
        venv_label.pack(side="left", padx=(10, 5))
        
        venv_name = self.venv_manager.current_venv or "No environment"
        self.venv_status_label = ctk.CTkLabel(
            venv_frame,
            text=venv_name,
            font=ctk.CTkFont(size=11),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.venv_status_label.pack(side="left", padx=(0, 10))
        
        # Theme selector
        theme_frame = ctk.CTkFrame(header_right, fg_color="transparent")
        theme_frame.pack(side="right", padx=15)
        
        ctk.CTkLabel(
            theme_frame,
            text="Theme:",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text"]
        ).pack(side="left", padx=(0, 5))
        
        self.theme_var = ctk.StringVar(value=self.current_theme)
        theme_combo = ctk.CTkComboBox(
            theme_frame,
            values=list(THEME_SCHEMES.keys()),
            variable=self.theme_var,
            command=self.on_theme_change,
            width=120,
            height=35
        )
        theme_combo.pack(side="left")
        
        # Auto-preview toggle
        self.auto_preview_checkbox = ctk.CTkCheckBox(
            header_right,
            text="Auto Preview",
            variable=self.auto_preview_var,
            command=self.toggle_auto_preview,
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text"]
        )
        self.auto_preview_checkbox.pack(side="right", padx=15)
        
    def create_sidebar(self):
        """Create sidebar with settings and controls"""
        self.sidebar = ctk.CTkFrame(self.root, width=350, corner_radius=0, fg_color=VSCODE_COLORS["surface"])
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(0, weight=1)
        
        # Sidebar content with scrolling
        self.sidebar_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color=VSCODE_COLORS["surface"])
        self.sidebar_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Create sections
        self.create_render_section()
        self.create_preview_section()
        self.create_assets_section()
        
    def create_render_section(self):
        """Create render settings section"""
        # Section header
        render_header = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        render_header.pack(fill="x", pady=(0, 10))
        
        header_title = ctk.CTkLabel(
            render_header,
            text="🎬 Render Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        )
        header_title.pack(side="left", padx=15, pady=12)
        
        # Render settings frame
        render_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        render_frame.pack(fill="x", pady=(0, 20))
        
        # Quality setting
        quality_frame = ctk.CTkFrame(render_frame, fg_color="transparent")
        quality_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(
            quality_frame,
            text="Quality",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        ).pack(anchor="w")
        
        self.quality_combo = ctk.CTkComboBox(
            quality_frame,
            values=list(QUALITY_PRESETS.keys()),
            variable=self.quality_var,
            command=self.on_quality_change,
            height=36,
            font=ctk.CTkFont(size=12)
        )
        self.quality_combo.pack(fill="x", pady=(5, 0))
        
        # Quality info
        current_quality = self.settings["quality"]
        if current_quality == "Custom":
            resolution_text = f"{self.custom_width_var.get()}x{self.custom_height_var.get()}"
        else:
            resolution_text = QUALITY_PRESETS[current_quality]["resolution"]
            
        self.quality_info = ctk.CTkLabel(
            quality_frame,
            text=f"Resolution: {resolution_text}",
            font=ctk.CTkFont(size=11),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.quality_info.pack(anchor="w", pady=(3, 0))
        
        # Custom resolution frame
        self.custom_resolution_frame = ctk.CTkFrame(quality_frame, fg_color="transparent")
        self.custom_resolution_frame.pack(fill="x", pady=(10, 0))
        
        # Custom resolution inputs
        custom_header = ctk.CTkLabel(
            self.custom_resolution_frame,
            text="Custom Resolution:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        custom_header.pack(anchor="w", pady=(0, 5))
        
        # Resolution input frame
        resolution_input_frame = ctk.CTkFrame(self.custom_resolution_frame, fg_color="transparent")
        resolution_input_frame.pack(fill="x")
        resolution_input_frame.grid_columnconfigure((0, 2), weight=1)
        
        # Width input
        ctk.CTkLabel(
            resolution_input_frame, 
            text="Width:", 
            width=50
        ).grid(row=0, column=0, sticky="w", pady=2)
        
        self.custom_width_entry = ctk.CTkEntry(
            resolution_input_frame,
            textvariable=self.custom_width_var,
            width=80,
            height=28
        )
        self.custom_width_entry.grid(row=0, column=1, sticky="w", padx=(5, 10), pady=2)
        
        # Height input
        ctk.CTkLabel(
            resolution_input_frame, 
            text="Height:", 
            width=50
        ).grid(row=0, column=2, sticky="w", pady=2)
        
        self.custom_height_entry = ctk.CTkEntry(
            resolution_input_frame,
            textvariable=self.custom_height_var,
            width=80,
            height=28
        )
        self.custom_height_entry.grid(row=0, column=3, sticky="w", padx=(5, 0), pady=2)
        
        # Custom FPS input
        fps_input_frame = ctk.CTkFrame(self.custom_resolution_frame, fg_color="transparent")
        fps_input_frame.pack(fill="x", pady=(5, 0))
        
        ctk.CTkLabel(
            fps_input_frame, 
            text="FPS:", 
            width=50
        ).pack(side="left")
        
        self.custom_fps_entry = ctk.CTkEntry(
            fps_input_frame,
            textvariable=self.custom_fps_var,
            width=80,
            height=28
        )
        self.custom_fps_entry.pack(side="left", padx=(5, 0))
        
        # Custom resolution validation label
        self.custom_validation_label = ctk.CTkLabel(
            self.custom_resolution_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=VSCODE_COLORS["error"]
        )
        self.custom_validation_label.pack(anchor="w", pady=(2, 0))
        
        # Bind validation events
        self.custom_width_entry.bind('<KeyRelease>', self.validate_custom_resolution)
        self.custom_height_entry.bind('<KeyRelease>', self.validate_custom_resolution)
        self.custom_fps_entry.bind('<KeyRelease>', self.validate_custom_resolution)
        
        # Initially hide custom resolution frame if not custom
        if self.quality_var.get() != "Custom":
            self.custom_resolution_frame.pack_forget()
        
        # Format setting
        format_frame = ctk.CTkFrame(render_frame, fg_color="transparent")
        format_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(
            format_frame,
            text="Export Format",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        ).pack(anchor="w")
        
        self.format_combo = ctk.CTkComboBox(
            format_frame,
            values=list(EXPORT_FORMATS.keys()),
            variable=self.format_var,
            command=self.on_format_change,
            height=36,
            font=ctk.CTkFont(size=12)
        )
        self.format_combo.pack(fill="x", pady=(5, 0))
        
        # FPS setting
        fps_frame = ctk.CTkFrame(render_frame, fg_color="transparent")
        fps_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(
            fps_frame,
            text="Frame Rate (FPS)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        ).pack(anchor="w")
        
        self.fps_combo = ctk.CTkComboBox(
            fps_frame,
            values=["15", "24", "30", "60"],
            variable=self.fps_var,
            command=self.on_fps_change,
            height=36,
            font=ctk.CTkFont(size=12)
        )
        self.fps_combo.pack(fill="x", pady=(5, 0))
        
        # CPU Usage setting
        cpu_frame = ctk.CTkFrame(render_frame, fg_color="transparent")
        cpu_frame.pack(fill="x", padx=15, pady=10)

        cpu_header = ctk.CTkFrame(cpu_frame, fg_color="transparent")
        cpu_header.pack(fill="x")
        cpu_header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            cpu_header,
            text="CPU Usage",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        ).grid(row=0, column=0, sticky="w")

        # Show CPU cores available
        cpu_info_text = f"{self.cpu_count} cores available"
        self.cpu_info_label = ctk.CTkLabel(
            cpu_header,
            text=cpu_info_text,
            font=ctk.CTkFont(size=11),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.cpu_info_label.grid(row=0, column=1, sticky="e")

        # CPU usage preset selection
        self.cpu_usage_combo = ctk.CTkComboBox(
            cpu_frame,
            values=list(CPU_USAGE_PRESETS.keys()),
            variable=self.cpu_usage_var,
            command=self.on_cpu_usage_change,
            height=36,
            font=ctk.CTkFont(size=12)
        )
        self.cpu_usage_combo.pack(fill="x", pady=(5, 0))

        # Container for custom cores slider
        self.custom_cpu_frame = ctk.CTkFrame(cpu_frame, fg_color="transparent")
        self.custom_cpu_frame.pack(fill="x", pady=(5, 0))

        # Only show custom slider when "Custom" is selected
        if self.cpu_usage_var.get() != "Custom":
            self.custom_cpu_frame.pack_forget()

        # Custom cores slider
        cores_slider_frame = ctk.CTkFrame(self.custom_cpu_frame, fg_color="transparent")
        cores_slider_frame.pack(fill="x")

        self.cores_slider = ctk.CTkSlider(
            cores_slider_frame, 
            from_=1, 
            to=self.cpu_count,
            number_of_steps=self.cpu_count-1,
            variable=self.cpu_custom_cores_var,
            command=self.update_cores_label
        )
        self.cores_slider.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.cores_value_label = ctk.CTkLabel(
            cores_slider_frame,
            text=str(self.cpu_custom_cores_var.get()),
            font=ctk.CTkFont(size=12),
            width=30
        )
        self.cores_value_label.pack(side="right")

        # CPU usage description
        self.cpu_description = ctk.CTkLabel(
            cpu_frame,
            text=CPU_USAGE_PRESETS[self.cpu_usage_var.get()]["description"],
            font=ctk.CTkFont(size=11),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.cpu_description.pack(anchor="w", pady=(3, 0))
        
        # Render button
        self.render_button = ctk.CTkButton(
            render_frame,
            text="🚀 Render Animation",
            command=self.render_animation,
            height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=VSCODE_COLORS["primary"],
            hover_color=VSCODE_COLORS["primary_hover"]
        )
        self.render_button.pack(fill="x", padx=15, pady=15)
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(render_frame)
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 10))
        self.progress_bar.set(0)
        
        # Progress label
        self.progress_label = ctk.CTkLabel(
            render_frame,
            text="Ready to render",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.progress_label.pack(pady=(0, 15))
        
    def validate_custom_resolution(self, event=None):
        """Validate custom resolution inputs"""
        try:
            width = self.custom_width_var.get()
            height = self.custom_height_var.get()
            fps = self.custom_fps_var.get()
            
            # Validation rules
            errors = []
            
            if width < 100 or width > 7680:
                errors.append("Width must be between 100 and 7680")
            if height < 100 or height > 4320:
                errors.append("Height must be between 100 and 4320")
            if fps < 1 or fps > 120:
                errors.append("FPS must be between 1 and 120")
            
            # Check if width and height are even numbers (required for video encoding)
            if width % 2 != 0:
                errors.append("Width must be even")
            if height % 2 != 0:
                errors.append("Height must be even")
            
            if errors:
                self.custom_validation_label.configure(
                    text=" • ".join(errors),
                    text_color=VSCODE_COLORS["error"]
                )
                return False
            else:
                self.custom_validation_label.configure(
                    text="✓ Valid resolution",
                    text_color=VSCODE_COLORS["success"]
                )
                
                # Update quality info
                self.quality_info.configure(text=f"Resolution: {width}x{height} @ {fps}fps")
                return True
                
        except Exception as e:
            self.custom_validation_label.configure(
                text="Invalid input",
                text_color=VSCODE_COLORS["error"]
            )
            return False
    
    def get_current_resolution_settings(self):
        """Get current resolution settings based on quality selection"""
        quality = self.quality_var.get()
        
        if quality == "Custom":
            # Validate custom resolution first
            if not self.validate_custom_resolution():
                raise ValueError("Invalid custom resolution settings")
                
            width = self.custom_width_var.get()
            height = self.custom_height_var.get()
            fps = self.custom_fps_var.get()
            
            return {
                "resolution": f"{width}x{height}",
                "width": width,
                "height": height,
                "fps": str(fps),
                "flag": "-qh"  # Use high quality flag for custom
            }
        else:
            preset = QUALITY_PRESETS[quality]
            width, height = preset["resolution"].split("x")
            return {
                "resolution": preset["resolution"],
                "width": int(width),
                "height": int(height),
                "fps": preset["fps"],
                "flag": preset["flag"]
            }
        
    def create_preview_section(self):
        """Create preview settings section"""
        # Section header
        preview_header = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        preview_header.pack(fill="x", pady=(0, 10))
        
        header_title = ctk.CTkLabel(
            preview_header,
            text="👁️ Preview Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        )
        header_title.pack(side="left", padx=15, pady=12)
        
        # Preview settings frame
        preview_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        preview_frame.pack(fill="x", pady=(0, 20))
        
        # Preview quality
        quality_frame = ctk.CTkFrame(preview_frame, fg_color="transparent")
        quality_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(
            quality_frame,
            text="Preview Quality",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        ).pack(anchor="w")
        
        self.preview_quality_combo = ctk.CTkComboBox(
            quality_frame,
            values=list(PREVIEW_QUALITIES.keys()),
            variable=self.preview_quality_var,
            command=self.on_preview_quality_change,
            height=36,
            font=ctk.CTkFont(size=12)
        )
        self.preview_quality_combo.pack(fill="x", pady=(5, 0))
        
        # Preview quality info
        self.preview_info = ctk.CTkLabel(
            quality_frame,
            text=f"Resolution: {PREVIEW_QUALITIES[self.settings['preview_quality']]['resolution']}",
            font=ctk.CTkFont(size=11),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.preview_info.pack(anchor="w", pady=(3, 0))
        
        # Preview buttons
        self.quick_preview_button = ctk.CTkButton(
            preview_frame,
            text="⚡ Quick Preview",
            command=self.quick_preview,
            height=45,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=VSCODE_COLORS["accent"],
            hover_color=VSCODE_COLORS["info"]
        )
        self.quick_preview_button.pack(fill="x", padx=15, pady=15)
        
    def create_assets_section(self):
        """Create enhanced assets section with visual cards"""
        # Section header
        assets_header = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        assets_header.pack(fill="x", pady=(0, 10))
        
        header_frame = ctk.CTkFrame(assets_header, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=12)
        header_frame.grid_columnconfigure(0, weight=1)
        
        header_title = ctk.CTkLabel(
            header_frame,
            text="🎨 Assets Manager",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        )
        header_title.grid(row=0, column=0, sticky="w")
        
        # Add asset button
        add_btn = ctk.CTkButton(
            header_frame,
            text="+",
            width=30,
            height=25,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self.show_add_asset_menu,
            fg_color=VSCODE_COLORS["success"],
            hover_color="#117A65"
        )
        add_btn.grid(row=0, column=1, sticky="e")
        
        # Assets frame
        self.assets_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        self.assets_frame.pack(fill="x", pady=(0, 20))
        
        # Assets scroll area
        self.assets_scroll = ctk.CTkScrollableFrame(self.assets_frame, height=200, fg_color=VSCODE_COLORS["surface_light"])
        self.assets_scroll.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Assets info
        self.assets_info = ctk.CTkLabel(
            self.assets_frame,
            text="Click + to add images or audio files",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.assets_info.pack(pady=(0, 15))
        
        # Update assets display
        self.update_assets_display()
        
    def create_main_area(self):
        """Create main content area"""
        self.main_area = ctk.CTkFrame(self.root, corner_radius=0, fg_color=VSCODE_COLORS["background"])
        self.main_area.grid(row=1, column=1, sticky="nsew")
        self.main_area.grid_rowconfigure(0, weight=2)
        self.main_area.grid_rowconfigure(1, weight=1)
        self.main_area.grid_columnconfigure(0, weight=2)
        self.main_area.grid_columnconfigure(1, weight=1)
        
        # Top left - Code editor
        self.create_code_editor()
        
        # Top right - Preview
        self.create_preview_area()
        
        # Bottom - Output console with system terminal integration
        self.create_output_area()
        
    def create_code_editor(self):
        """Create enhanced code editor area with IntelliSense"""
        editor_frame = ctk.CTkFrame(self.main_area, fg_color=VSCODE_COLORS["surface"])
        editor_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=(10, 5))
        editor_frame.grid_rowconfigure(1, weight=1)
        editor_frame.grid_columnconfigure(0, weight=1)
        
        # Editor header
        editor_header = ctk.CTkFrame(editor_frame, height=50, fg_color=VSCODE_COLORS["surface_light"])
        editor_header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        editor_header.grid_columnconfigure(1, weight=1)
        
        # File tab frame
        tab_frame = ctk.CTkFrame(editor_header, fg_color="transparent")
        tab_frame.grid(row=0, column=0, sticky="w", padx=15, pady=8)
        
        # File tab
        self.file_tab = ctk.CTkButton(
            tab_frame,
            text="📄 scene.py",
            height=35,
            font=ctk.CTkFont(size=12),
            fg_color=VSCODE_COLORS["background"],
            hover_color=VSCODE_COLORS["surface_lighter"],
            corner_radius=8,
            anchor="w"
        )
        self.file_tab.pack(side="left")
        
        # Editor options
        editor_options = ctk.CTkFrame(editor_header, fg_color="transparent")
        editor_options.grid(row=0, column=1, sticky="e", padx=15, pady=8)
        
        # Find/Replace buttons
        find_btn = ctk.CTkButton(
            editor_options,
            text="🔍",
            width=30,
            height=30,
            command=self.show_find_dialog,
            fg_color="transparent",
            hover_color=VSCODE_COLORS["surface_lighter"],
            border_width=1
        )
        find_btn.pack(side="left", padx=2)
        
        # Font size controls
        font_controls = ctk.CTkFrame(editor_options, fg_color="transparent")
        font_controls.pack(side="right")
        
        ctk.CTkButton(
            font_controls,
            text="A-",
            width=30,
            height=30,
            command=self.decrease_font_size,
            fg_color="transparent",
            hover_color=VSCODE_COLORS["surface_lighter"],
            border_width=1
        ).pack(side="left", padx=1)
        
        ctk.CTkButton(
            font_controls,
            text="A+",
            width=30,
            height=30,
            command=self.increase_font_size,
            fg_color="transparent",
            hover_color=VSCODE_COLORS["surface_lighter"],
            border_width=1
        ).pack(side="left", padx=1)
        
        # Editor container with line numbers
        editor_container = ctk.CTkFrame(editor_frame, fg_color=VSCODE_COLORS["background"])
        editor_container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        editor_container.grid_rowconfigure(0, weight=1)
        editor_container.grid_columnconfigure(1, weight=1)
        
        # Initialize the enhanced editor with IntelliSense
        self.code_editor = EnhancedPythonEditor(
            editor_container,
            font=("Consolas", self.font_size_var.get())
        )
        self.code_editor.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        
        # Set parent app reference
        self.code_editor.parent_app = self
        
        # Configure IntelliSense settings
        self.code_editor.auto_completion_enabled = self.intellisense_var.get()
        self.code_editor.autocomplete_delay = self.settings["auto_completion_delay"]
        
        # Create line numbers widget
        self.line_numbers = LineNumbers(editor_container, self.code_editor)
        self.line_numbers.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        
        # Bind scrolling synchronization
        self.code_editor.bind('<MouseWheel>', self.on_editor_scroll)
        self.code_editor.bind('<Button-4>', self.on_editor_scroll)
        self.code_editor.bind('<Button-5>', self.on_editor_scroll)
        
        # Load default code
        self.load_default_code()
        
    def create_preview_area(self):
        """Create preview area"""
        preview_frame = ctk.CTkFrame(self.main_area, fg_color=VSCODE_COLORS["surface"])
        preview_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=(10, 5))
        preview_frame.grid_rowconfigure(1, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        
        # Preview header
        preview_header = ctk.CTkFrame(preview_frame, height=50, fg_color=VSCODE_COLORS["surface_light"])
        preview_header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        preview_header.grid_columnconfigure(1, weight=1)
        
        # Preview title
        preview_title = ctk.CTkLabel(
            preview_header,
            text="👁️ Live Preview",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        )
        preview_title.grid(row=0, column=0, sticky="w", padx=15, pady=10)
        
        # Preview controls
        preview_controls = ctk.CTkFrame(preview_header, fg_color="transparent")
        preview_controls.grid(row=0, column=1, sticky="e", padx=15, pady=10)

        # Refresh button
        refresh_btn = ctk.CTkButton(
            preview_controls,
            text="🔄",
            width=35,
            height=35,
            command=self.quick_preview,
            fg_color="transparent",
            hover_color=VSCODE_COLORS["surface_lighter"],
            border_width=1
        )
        refresh_btn.pack(side="right", padx=2)

        # Clear preview button
        clear_btn = ctk.CTkButton(
            preview_controls,
            text="🗑️",
            width=35,
            height=35,
            command=self.clear_preview_video,
            fg_color="transparent",
            hover_color=VSCODE_COLORS["surface_lighter"],
            border_width=1
        )
        clear_btn.pack(side="right", padx=2)
        
        # Video player
        self.video_player = VideoPlayerWidget(preview_frame)
        self.video_player.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        
    def create_output_area(self):
        """Create enhanced output console area with rich terminal features"""
        output_frame = ctk.CTkFrame(self.main_area, fg_color=VSCODE_COLORS["surface"])
        output_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(5, 10))
        output_frame.grid_rowconfigure(1, weight=1)
        output_frame.grid_columnconfigure(0, weight=1)
        
        # Enhanced output header with more controls
        output_header = ctk.CTkFrame(output_frame, height=50, fg_color=VSCODE_COLORS["surface_light"])
        output_header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        output_header.grid_columnconfigure(2, weight=1)
        
        # Output title with status indicator
        title_frame = ctk.CTkFrame(output_header, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w", padx=15, pady=10)
        
        output_title = ctk.CTkLabel(
            title_frame,
            text="📋 Enhanced Terminal",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        )
        output_title.pack(side="left")
        
        # Terminal status indicator
        self.terminal_status = ctk.CTkLabel(
            title_frame,
            text="● Ready",
            font=ctk.CTkFont(size=11),
            text_color="#00FF00"
        )
        self.terminal_status.pack(side="left", padx=(10, 0))
        
        # Search frame
        search_frame = ctk.CTkFrame(output_header, fg_color="transparent")
        search_frame.grid(row=0, column=1, padx=10, pady=10)
        
        # Search entry
        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Search output...",
            width=150,
            height=30,
            font=ctk.CTkFont(size=11)
        )
        self.search_entry.pack(side="left", padx=2)
        self.search_entry.bind("<KeyRelease>", self.search_terminal_output)
        
        # Enhanced terminal controls
        terminal_controls = ctk.CTkFrame(output_header, fg_color="transparent")
        terminal_controls.grid(row=0, column=3, sticky="e", padx=15, pady=10)
        
        # Auto-scroll toggle
        self.auto_scroll_var = ctk.BooleanVar(value=True)
        auto_scroll_check = ctk.CTkCheckBox(
            terminal_controls,
            text="Auto-scroll",
            variable=self.auto_scroll_var,
            font=ctk.CTkFont(size=10),
            checkbox_width=16,
            checkbox_height=16
        )
        auto_scroll_check.pack(side="right", padx=5)
        
        # Timestamps toggle
        self.timestamps_var = ctk.BooleanVar(value=True)
        timestamps_check = ctk.CTkCheckBox(
            terminal_controls,
            text="Timestamps",
            variable=self.timestamps_var,
            font=ctk.CTkFont(size=10),
            checkbox_width=16,
            checkbox_height=16
        )
        timestamps_check.pack(side="right", padx=5)
        
        # Clear button
        clear_btn = ctk.CTkButton(
            terminal_controls,
            text="🗑️",
            width=30,
            height=30,
            command=self.clear_output,
            fg_color="transparent",
            hover_color=VSCODE_COLORS["surface_lighter"],
            border_width=1
        )
        clear_btn.pack(side="right", padx=2)
        
        # Enhanced output display area
        output_container = ctk.CTkFrame(output_frame, fg_color=VSCODE_COLORS["background"])
        output_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        output_container.grid_rowconfigure(0, weight=1)
        output_container.grid_columnconfigure(0, weight=1)
        
        # Create enhanced text widget
        self.output_text = tk.Text(
            output_container,
            font=("Cascadia Code", 11),
            bg=VSCODE_COLORS["background"],
            fg=VSCODE_COLORS["text"],
            insertbackground=VSCODE_COLORS["text"],
            selectbackground=VSCODE_COLORS["selection"],
            selectforeground=VSCODE_COLORS["text_bright"],
            bd=0,
            highlightthickness=0,
            wrap="word",
            undo=False,
            state="disabled",
            cursor="arrow"
        )
        self.output_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Configure rich text tags
        self.setup_terminal_tags()
        
        # Add scrollbar
        scrollbar = ctk.CTkScrollbar(output_container, command=self.output_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        self.output_text.configure(yscrollcommand=scrollbar.set)
        
        # Enhanced command input frame
        input_frame = ctk.CTkFrame(output_frame, fg_color=VSCODE_COLORS["surface_light"], height=60)
        input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        input_frame.grid_columnconfigure(0, weight=1)
        
        # Command input
        self.command_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Enter command... (↑↓ for history, Tab for completion)",
            font=ctk.CTkFont(family="Cascadia Code", size=11),
            height=35
        )
        self.command_entry.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        self.command_entry.bind("<Return>", self.execute_command_from_input)
        self.command_entry.bind("<Up>", self.command_history_up)
        self.command_entry.bind("<Down>", self.command_history_down)
        
        # Execute button
        execute_btn = ctk.CTkButton(
            input_frame,
            text="▶️ Run",
            width=70,
            height=25,
            command=self.execute_command_from_input,
            fg_color=VSCODE_COLORS["success"],
            font=ctk.CTkFont(size=11, weight="bold")
        )
        execute_btn.grid(row=0, column=1, padx=(5, 10), pady=(10, 5))
        
        # Initialize enhanced features
        self.terminal = SystemTerminalManager(self)
        self.command_history = []
        self.command_history_index = -1
        self.search_matches = []
        self.current_search_index = -1
        self.terminal_buffer = []
        self.max_buffer_lines = 1000 
    def setup_terminal_tags(self):
        """Configure rich text tags for enhanced terminal formatting"""
        self.output_text.tag_configure("success", foreground="#00FF88", font=("Cascadia Code", 11, "bold"))
        self.output_text.tag_configure("error", foreground="#FF4444", font=("Cascadia Code", 11, "bold"))
        self.output_text.tag_configure("warning", foreground="#FFB366", font=("Cascadia Code", 11, "bold"))
        self.output_text.tag_configure("info", foreground="#66B3FF", font=("Cascadia Code", 11))
        self.output_text.tag_configure("command", foreground="#FFFF66", font=("Cascadia Code", 11, "bold"))
        self.output_text.tag_configure("progress", foreground="#88FF88", font=("Cascadia Code", 11))
        self.output_text.tag_configure("timestamp", foreground="#888888", font=("Cascadia Code", 9))
        self.output_text.tag_configure("search_match", background="#FFFF00", foreground="#000000")

    def append_terminal_output(self, text, msg_type="normal", show_timestamp=None):
        """Clean terminal output with proper spacing"""
        if not text or not text.strip():
            return
        
        # Clean the text
        clean_text = text.strip()
        
        # Add spacing between different types of messages
        spacing = ""
        if msg_type in ["command", "success", "error"]:
            spacing = "\n\n\n"
        
        # Format the final text
        formatted_text = f"{spacing}{clean_text}\n"
        
        try:
            # Enable editing
            self.output_text.configure(state="normal")
            
            # Simple color coding
            if hasattr(self.output_text, 'tag_configure'):
                if msg_type == "error" or "❌" in text or "ERROR" in text:
                    self.output_text.insert("end", formatted_text, "error")
                elif msg_type == "success" or "✅" in text:
                    self.output_text.insert("end", formatted_text, "success")
                elif msg_type == "warning" or "⚠️" in text:
                    self.output_text.insert("end", formatted_text, "warning")
                elif msg_type == "command" or text.startswith("$ "):
                    self.output_text.insert("end", formatted_text, "command")
                elif msg_type == "info":
                    self.output_text.insert("end", formatted_text, "info")
                else:
                    self.output_text.insert("end", formatted_text)
            else:
                self.output_text.insert("end", formatted_text)
            
            # Auto-scroll
            self.output_text.see("end")
            
            # Disable editing
            self.output_text.configure(state="disabled")
            
        except Exception:
            print(formatted_text, end='')
    
    def update_terminal_status(self, status, color="#00FF00"):
        """Update terminal status indicator"""
        if hasattr(self, 'terminal_status'):
            self.terminal_status.configure(text=f"● {status}", text_color=color)

    def search_terminal_output(self, event=None):
        """Search through terminal output"""
        if not hasattr(self, 'search_entry'):
            return
            
        search_term = self.search_entry.get().strip()
        
        # Clear previous search highlighting
        self.output_text.tag_remove("search_match", "1.0", "end")
        self.search_matches = []
        self.current_search_index = -1
        
        if not search_term:
            return
        
        # Search through text
        self.output_text.configure(state="normal")
        start_pos = "1.0"
        
        while True:
            pos = self.output_text.search(search_term, start_pos, "end", nocase=True)
            if not pos:
                break
                
            end_pos = f"{pos}+{len(search_term)}c"
            self.output_text.tag_add("search_match", pos, end_pos)
            self.search_matches.append(pos)
            start_pos = end_pos
        
        self.output_text.configure(state="disabled")
        
        # Show first match
        if self.search_matches:
            self.current_search_index = 0
            self.output_text.see(self.search_matches[0])

    def command_history_up(self, event):
        """Navigate command history up"""
        if hasattr(self, 'command_history') and self.command_history and self.command_history_index > 0:
            self.command_history_index -= 1
            self.command_entry.delete(0, "end")
            self.command_entry.insert(0, self.command_history[self.command_history_index])
        return "break"

    def command_history_down(self, event):
        """Navigate command history down"""
        if hasattr(self, 'command_history') and self.command_history and self.command_history_index < len(self.command_history) - 1:
            self.command_history_index += 1
            self.command_entry.delete(0, "end")
            self.command_entry.insert(0, self.command_history[self.command_history_index])
        elif hasattr(self, 'command_history') and self.command_history_index >= len(self.command_history) - 1:
            self.command_entry.delete(0, "end")
            self.command_history_index = len(self.command_history)
        return "break"

    def execute_command_from_input(self, event=None):
        """Execute command from the input field"""
        command = self.command_entry.get().strip()
        if not command:
            return
        
        # Clear input
        self.command_entry.delete(0, 'end')
        
        # Show command in output with proper spacing
        self.append_terminal_output(f"$ {command}", "command")
        
        # Detect manim commands
        is_manim_command = 'manim' in command.lower()
        
        # Execute command
        def on_complete(success, return_code):
            if success:
                self.append_terminal_output(f"\nCommand completed (exit code: {return_code})", "success")
            else:
                self.append_terminal_output(f"\nCommand failed (exit code: {return_code})", "error")
        
        # Use appropriate output type for manim
        output_type = "output" if is_manim_command else "normal"
        self.terminal.execute_command(command, capture_output=True, on_complete=on_complete)
    def log_separator(self, title="", char="=", width=60):
        """Add a visual separator to the terminal output"""
        if title:
            title_padded = f" {title} "
            separator_width = (width - len(title_padded)) // 2
            separator = char * separator_width + title_padded + char * separator_width
        else:
            separator = char * width
        
        self.append_terminal_output(f"\n{separator}\n", "info")

    def log_command_start(self, command_desc):
        """Log the start of a command with proper formatting"""
        self.log_separator(f"Starting: {command_desc}", "─", 50)

    def log_command_end(self, command_desc, success, duration=None):
        """Log the end of a command with proper formatting"""
        status = "✅ SUCCESS" if success else "❌ FAILED"
        duration_text = f" (took {duration:.1f}s)" if duration else ""
        
        self.append_terminal_output(f"\n{status}: {command_desc}{duration_text}\n", 
                                   "success" if success else "error")
        self.log_separator("", "─", 50)

    def log_info(self, message):
        """Log an info message with proper spacing"""
        self.append_terminal_output(f"ℹ️ {message}", "info")

    def log_warning(self, message):
        """Log a warning message with proper spacing"""
        self.append_terminal_output(f"⚠️ {message}", "warning")

    def log_error(self, message):
        """Log an error message with proper spacing"""
        self.append_terminal_output(f"❌ {message}", "error")

    def log_success(self, message):
        """Log a success message with proper spacing"""
        self.append_terminal_output(f"✅ {message}", "success")
    def clear_output(self):
        """Enhanced clear output"""
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")
        
        # Clear search and buffer
        if hasattr(self, 'search_matches'):
            self.search_matches = []
            self.current_search_index = -1
        if hasattr(self, 'terminal_buffer'):
            self.terminal_buffer = []
        
        # Show welcome message
        self.append_terminal_output("🚀 Enhanced Terminal Ready!\n", "info")
        self.update_status("Terminal cleared")
        if hasattr(self, 'update_terminal_status'):
            self.update_terminal_status("Ready", "#00FF00")
    def create_status_bar(self):
        """Create status bar"""
        self.status_bar = ctk.CTkFrame(self.root, height=35, corner_radius=0, fg_color=VSCODE_COLORS["surface"])
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.status_bar.grid_columnconfigure(1, weight=1)
        
        # Left side - Status
        status_left = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        status_left.grid(row=0, column=0, sticky="w", padx=15, pady=5)
        
        self.status_label = ctk.CTkLabel(
            status_left,
            text="Ready",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text"]
        )
        self.status_label.pack(side="left")
        
        # Center - IntelliSense status
        status_center = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        status_center.grid(row=0, column=1, pady=5)
        
        self.intellisense_status = ctk.CTkLabel(
            status_center,
            text="IntelliSense: " + ("Enabled" if JEDI_AVAILABLE and self.intellisense_var.get() else "Disabled"),
            font=ctk.CTkFont(size=11),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.intellisense_status.pack()
        
        # Right side - Info
        status_right = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        status_right.grid(row=0, column=2, sticky="e", padx=15, pady=5)

        # LaTeX detection status
        latex_color = VSCODE_COLORS["success"] if self.latex_installed else VSCODE_COLORS["error"]
        latex_text = (
            f"LaTeX: {self.latex_path}" if self.latex_installed else "LaTeX: Missing"
        )
        self.latex_status_label = ctk.CTkLabel(
            status_right,
            text=latex_text,
            font=ctk.CTkFont(size=12),
            text_color=latex_color,
        )
        self.latex_status_label.pack(side="right", padx=(0, 10))

        # Current time
        self.time_label = ctk.CTkLabel(
            status_right,
            text=datetime.now().strftime("%H:%M"),
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.time_label.pack(side="right")
        
    def create_menu_bar(self):
        """Create menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self.new_file, accelerator="Ctrl+N")
        file_menu.add_command(label="Open", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As", command=self.save_as_file, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Cut", command=lambda: self.code_editor.event_generate("<<Cut>>"), accelerator="Ctrl+X")
        edit_menu.add_command(label="Copy", command=lambda: self.code_editor.event_generate("<<Copy>>"), accelerator="Ctrl+C")
        edit_menu.add_command(label="Paste", command=lambda: self.code_editor.event_generate("<<Paste>>"), accelerator="Ctrl+V")
        edit_menu.add_separator()
        edit_menu.add_command(label="Find", command=self.show_find_dialog, accelerator="Ctrl+F")
        edit_menu.add_command(label="Replace", command=self.show_replace_dialog, accelerator="Ctrl+H")
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Toggle Fullscreen", command=self.toggle_fullscreen, accelerator="F11")
        view_menu.add_command(label="Increase Font Size", command=self.increase_font_size, accelerator="Ctrl++")
        view_menu.add_command(label="Decrease Font Size", command=self.decrease_font_size, accelerator="Ctrl+-")
        view_menu.add_separator()
        view_menu.add_checkbutton(label="IntelliSense", variable=self.intellisense_var, command=self.toggle_intellisense)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Environment Setup", command=self.manage_environment)
        tools_menu.add_command(label="Open System Terminal", command=self.open_system_terminal)
        
        # Animation menu
        animation_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Animation", menu=animation_menu)
        animation_menu.add_command(label="Quick Preview", command=self.quick_preview, accelerator="F5")
        animation_menu.add_command(label="Render Animation", command=self.render_animation, accelerator="F7")
        animation_menu.add_command(label="Stop Process", command=self.stop_process, accelerator="Esc")
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Manim Documentation", command=self.open_manim_docs)
        help_menu.add_command(label="Getting Started", command=self.show_getting_started)
        help_menu.add_command(label="About", command=self.show_about)
        
    def bind_shortcuts(self):
        """Bind keyboard shortcuts"""
        self.root.bind("<Control-n>", lambda e: self.new_file())
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.root.bind("<Control-Shift-S>", lambda e: self.save_as_file())
        self.root.bind("<Control-f>", lambda e: self.show_find_dialog())
        self.root.bind("<Control-h>", lambda e: self.show_replace_dialog())
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<F5>", lambda e: self.quick_preview())
        self.root.bind("<F7>", lambda e: self.render_animation())
        self.root.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda e: self.stop_process())
        self.root.bind("<Control-equal>", lambda e: self.increase_font_size())
        self.root.bind("<Control-minus>", lambda e: self.decrease_font_size())
        self.root.bind("<Control-l>", lambda e: self.clear_output())
        self.root.bind("<Control-Shift-T>", lambda e: self.open_system_terminal())
        self.root.bind("<Control-grave>", lambda e: self.command_entry.focus() if hasattr(self, 'command_entry') else None)
        # Handle window closing
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    # System Terminal Integration Methods
    def open_system_terminal(self):
        """Open system terminal in current directory"""
        success = self.terminal.open_terminal_here()
        if success:
            self.append_terminal_output("Opened system terminal\n")
            self.update_status("System terminal opened")
        else:
            self.append_terminal_output("Failed to open system terminal\n")
            self.update_status("Failed to open terminal")

    def execute_command_from_input(self, event=None):
        """Execute command from the input field"""
        command = self.command_entry.get().strip()
        if not command:
            return
        
        # Clear input
        self.command_entry.delete(0, 'end')
        
        # Show command in output
        self.append_terminal_output(f"$ {command}\n")
        
        # Execute command
        def on_complete(success, return_code):
            if success:
                self.append_terminal_output(f"Command completed (exit code: {return_code})\n\n")
            else:
                self.append_terminal_output(f"Command failed (exit code: {return_code})\n\n")
        
        self.terminal.execute_command(command, capture_output=True, on_complete=on_complete)

    def append_terminal_output(self, text, msg_type="normal", show_timestamp=None):
        """Enhanced terminal output with rich formatting and proper manim spacing"""
        if not text:
            return
            
        # Use setting for timestamps if not specified
        if show_timestamp is None:
            show_timestamp = self.timestamps_var.get() if hasattr(self, 'timestamps_var') else False
        
        # Detect manim output for special handling
        is_manim_output = any(keyword in text.lower() for keyword in 
                             ['manim', 'rendering', 'scene', 'animation', 'ffmpeg', 
                              'frame rate', 'resolution', 'quality', 'writing to'])
        
        # Detect pip output
        is_pip_output = any(keyword in text.lower() for keyword in 
                           ['collecting', 'downloading', 'installing', 'requirement already satisfied',
                            'successfully installed', 'pip install', 'upgrading'])
        
        # Handle text cleaning based on output type
        if is_manim_output:
            # For manim output, preserve internal spacing and line breaks
            clean_text = text.rstrip('\n\r')  # Only remove trailing newlines
            # Don't strip leading spaces as they might be important for manim's formatting
        elif is_pip_output:
            # For pip output, preserve formatting but clean up trailing whitespace
            clean_text = text.rstrip()
        else:
            # For other output, clean normally
            clean_text = text.strip()
        
        # Prepare timestamp
        timestamp = ""
        if show_timestamp:
            timestamp = f"[{time.strftime('%H:%M:%S')}] "
        
        # Add to buffer for search
        if hasattr(self, 'terminal_buffer'):
            full_text = timestamp + clean_text
            self.terminal_buffer.append({
                'timestamp': time.time(),
                'text': full_text,
                'type': msg_type
            })
            
            # Limit buffer size
            if len(self.terminal_buffer) > self.max_buffer_lines:
                self.terminal_buffer = self.terminal_buffer[-self.max_buffer_lines:]
        
        # Enable text widget for editing
        try:
            self.output_text.configure(state="normal")
        except:
            pass
        
        try:
            # Insert timestamp if enabled
            if timestamp:
                if hasattr(self.output_text, 'tag_configure'):
                    self.output_text.insert("end", timestamp, "timestamp")
                else:
                    self.output_text.insert("end", timestamp)
            
            # Determine the appropriate tag for formatting
            text_tag = self._get_text_tag(clean_text, msg_type, is_manim_output, is_pip_output)
            
            # Insert text with appropriate formatting
            if hasattr(self.output_text, 'tag_configure'):
                # Rich text widget - use tags
                if is_manim_output:
                    # For manim output, add proper line breaks and preserve formatting
                    if not clean_text.startswith('\n') and self.output_text.get("end-1c") != '\n':
                        self.output_text.insert("end", "\n")
                    self.output_text.insert("end", clean_text, text_tag)
                    if not clean_text.endswith('\n'):
                        self.output_text.insert("end", "\n")
                else:
                    # For other output types
                    self.output_text.insert("end", clean_text, text_tag)
                    if not clean_text.endswith('\n'):
                        self.output_text.insert("end", "\n")
            else:
                # Simple text widget - just insert text
                self.output_text.insert("end", clean_text)
                if not clean_text.endswith('\n'):
                    self.output_text.insert("end", "\n")
        
        except Exception as e:
            # Fallback: just insert the text without formatting
            try:
                self.output_text.insert("end", clean_text)
                if not clean_text.endswith('\n'):
                    self.output_text.insert("end", "\n")
            except:
                pass
        
        # Auto-scroll if enabled
        try:
            if hasattr(self, 'auto_scroll_var') and self.auto_scroll_var.get():
                self.output_text.see("end")
            elif not hasattr(self, 'auto_scroll_var'):
                # Default to auto-scroll if variable doesn't exist
                self.output_text.see("end")
        except:
            pass
        
        # Disable text widget editing
        try:
            self.output_text.configure(state="disabled")
        except:
            pass
    
    def _get_text_tag(self, text, msg_type, is_manim_output, is_pip_output):
        """Helper method to determine the appropriate text tag for formatting"""
        # Priority order for tag determination
        
        # 1. Check explicit message type first
        if msg_type == "error" or "❌" in text or "ERROR" in text.upper():
            return "error"
        elif msg_type == "success" or "✅" in text or "SUCCESS" in text.upper():
            return "success"
        elif msg_type == "warning" or "⚠️" in text or "WARNING" in text.upper():
            return "warning"
        elif msg_type == "info" or "ℹ️" in text or "INFO" in text.upper():
            return "info"
        elif msg_type == "command" or text.startswith("$ "):
            return "command"
        elif msg_type == "progress" or "%" in text:
            return "progress"
        
        # 2. Check for specific output types
        elif is_manim_output:
            # Use appropriate tag based on manim output content
            if any(word in text.lower() for word in ['error', 'failed', 'exception']):
                return "error"
            elif any(word in text.lower() for word in ['warning', 'warn']):
                return "warning"
            elif any(word in text.lower() for word in ['done', 'completed', 'finished']):
                return "success"
            else:
                return "output"  # Default for manim
        
        elif is_pip_output:
            # Use appropriate tag based on pip output content
            if "successfully installed" in text.lower():
                return "success"
            elif "requirement already satisfied" in text.lower():
                return "info"
            elif "error" in text.lower() or "failed" in text.lower():
                return "error"
            else:
                return "output"  # Default for pip
        
        # 3. Default fallback
        else:
            return None  # Use default formatting
    def clear_output(self):
        """Clear terminal output"""
        self.output_text.delete("1.0", "end")
        self.update_status("Output cleared")

    def clear_preview_video(self, silent=False):
        """Clear preview video from player and disk"""
        try:
            if self.preview_video_path and os.path.exists(self.preview_video_path):
                os.remove(self.preview_video_path)
                if not silent:
                    self.append_terminal_output(f"Removed preview: {self.preview_video_path}\n")
        except Exception as e:
            if not silent:
                self.append_terminal_output(f"Warning: Could not remove preview: {e}\n")
        self.preview_video_path = None
        if hasattr(self, "video_player"):
            self.video_player.clear()
        if not silent:
            self.update_status("Preview cleared")
    def load_preview_video(self, video_path):
        """Load preview video in the video player"""
        try:
            # Ensure video path exists
            if not os.path.exists(video_path):
                self.append_terminal_output(f"❌ Error: Video file not found: {video_path}\n")
                return False
            
            # Load video in player
            if hasattr(self, 'video_player') and self.video_player.load_video(video_path):
                self.preview_video_path = video_path
                self.append_terminal_output(f"✅ Preview loaded successfully: {os.path.basename(video_path)}\n")
                return True
            else:
                self.append_terminal_output("❌ Error: Could not load video in player\n")
                return False
                
        except Exception as e:
            self.append_terminal_output(f"❌ Error loading preview video: {e}\n")
            return False

    # Editor Methods
    def undo(self):
        """Undo text operation"""
        try:
            self.code_editor.edit_undo()
        except tk.TclError:
            pass
            
    def redo(self):
        """Redo text operation"""
        try:
            self.code_editor.edit_redo()
        except tk.TclError:
            pass
        
    def on_closing(self):
        """Handle application closing"""
        # Save settings
        self.save_settings()
        
        # Stop any running processes
        self.stop_process()
        
        # Destroy window
        self.root.destroy()
        
    def load_default_code(self):
        """Load default example code"""
        default_code = '''from manim import *

class MyScene(Scene):
    def construct(self):
        # Create a beautiful mathematical animation
        
        # Title
        title = Text("Manim Animation Studio", font_size=48)
        title.set_color(BLUE)
        title.move_to(UP * 2)
        
        # Mathematical equation
        equation = MathTex(
            r"\\sum_{n=1}^{\\infty} \\frac{1}{n^2} = \\frac{\\pi^2}{6}",
            font_size=36
        )
        equation.set_color(WHITE)
        
        # Geometric shapes
        circle = Circle(radius=1, color=BLUE, fill_opacity=0.3)
        square = Square(side_length=2, color=RED, fill_opacity=0.3)
        triangle = Triangle(fill_opacity=0.3, color=GREEN)
        
        shapes = VGroup(circle, square, triangle)
        shapes.arrange(RIGHT, buff=0.5)
        shapes.move_to(DOWN * 2)
        
        # Animation sequence
        self.play(Write(title))
        self.wait(0.5)
        
        self.play(Create(equation))
        self.wait(0.5)
        
        self.play(Create(shapes))
        self.wait(0.5)
        
        # Transform shapes
        self.play(
            Transform(circle, square.copy()),
            Transform(square, triangle.copy()),
            Transform(triangle, circle.copy())
        )
        
        self.wait(2)
        
        # Final fade out
        self.play(
            FadeOut(title),
            FadeOut(equation),
            FadeOut(shapes)
        )
'''
        
        self.code_editor.delete("1.0", "end")
        self.code_editor.insert("1.0", default_code)
        self.current_code = default_code
        self.update_line_numbers()
        
    def on_text_change(self, event=None):
        """Handle code changes"""
        self.current_code = self.code_editor.get("1.0", "end-1c")
        self.update_line_numbers()
        
        # Auto-preview if enabled
        if self.auto_preview_var.get() and not self.is_previewing:
            # Debounce auto-preview
            if hasattr(self, '_auto_preview_timer'):
                self.root.after_cancel(self._auto_preview_timer)
            self._auto_preview_timer = self.root.after(2000, self.auto_preview)
            
    def auto_preview(self):
        """Auto-preview when code changes"""
        if self.current_code != self.last_preview_code:
            self.quick_preview()
            
    # CPU Management Methods
    def on_cpu_usage_change(self, value):
        """Handle CPU usage preset change"""
        self.settings["cpu_usage"] = value
        self.cpu_description.configure(text=CPU_USAGE_PRESETS[value]["description"])
        
        # Show/hide custom slider based on selection
        if value == "Custom":
            self.custom_cpu_frame.pack(fill="x", pady=(5, 0))
        else:
            self.custom_cpu_frame.pack_forget()
        
        self.save_settings()

    def update_cores_label(self, value):
        """Update the cores value label"""
        cores = int(value)
        self.cores_value_label.configure(text=str(cores))
        self.settings["cpu_custom_cores"] = cores
        self.save_settings()

    def get_render_cores(self):
        """Get the number of cores to use for rendering based on settings"""
        usage_preset = self.cpu_usage_var.get()
        preset_data = CPU_USAGE_PRESETS[usage_preset]
        cores = preset_data["cores"]
        # For custom setting, use the slider value
        if usage_preset == "Custom":
            return self.cpu_custom_cores_var.get()
        
        # Special cases
        if cores is None:
            # Medium - use half available cores
            return max(1, self.cpu_count // 2)
        elif cores == -1:
            # High - use all cores
            return self.cpu_count
        
        # Return direct value (for Low)
        return cores
            
    # Dialog methods
    def show_find_dialog(self):
        """Show find and replace dialog"""
        if not hasattr(self, 'find_dialog') or not self.find_dialog.winfo_exists():
            self.find_dialog = FindReplaceDialog(self.root, self.code_editor)
        else:
            self.find_dialog.lift()
            self.find_dialog.focus()
            
    def show_replace_dialog(self):
        """Show find and replace dialog"""
        self.show_find_dialog()
        
    def manage_environment(self):
        """Open enhanced environment management dialog"""
        try:
            # Check if environment needs setup first
            if self.venv_manager.needs_setup:
                print("Environment needs setup, showing setup dialog...")
                self.venv_manager.show_setup_dialog()
            else:
               # Show enhanced environment management dialog
                dialog = EnhancedVenvManagerDialog(self.root, self.venv_manager)
                self.root.wait_window(dialog)
            
                # Update venv status after dialog closes
                if hasattr(self, 'venv_status_label') and self.venv_manager.current_venv:
                    self.venv_status_label.configure(text=self.venv_manager.current_venv)
        except Exception as e:
            print(f"Error in manage_environment: {e}")
            # Show error message if there's a problem
            messagebox.showerror(
                "Environment Error", 
                f"Error opening environment dialog:\n{str(e)}\n\n"
                "Please try restarting the application."
            )
            
    # Settings callbacks
    def on_quality_change(self, value):
        """Handle quality change"""
        self.settings["quality"] = value
        
        if value == "Custom":
            # Show custom resolution frame
            self.custom_resolution_frame.pack(fill="x", pady=(10, 0))
            self.validate_custom_resolution()
        else:
            # Hide custom resolution frame and show preset info
            self.custom_resolution_frame.pack_forget()
            quality_info = QUALITY_PRESETS[value]
            self.quality_info.configure(text=f"Resolution: {quality_info['resolution']}")
            
        self.save_settings()
        
    def on_format_change(self, value):
        """Handle format change"""
        self.settings["format"] = value
        self.save_settings()
        
    def on_fps_change(self, value):
        """Handle FPS change"""
        self.settings["fps"] = int(value)
        self.save_settings()
        
    def on_preview_quality_change(self, value):
        """Handle preview quality change"""
        self.settings["preview_quality"] = value
        quality_info = PREVIEW_QUALITIES[value]
        self.preview_info.configure(text=f"Resolution: {quality_info['resolution']}")
        self.save_settings()
        
    def on_theme_change(self, theme_name):
        """Handle theme change"""
        if theme_name in THEME_SCHEMES:
            self.current_theme = theme_name
            self.settings["theme"] = theme_name
            
            # Apply the new theme
            self.apply_theme(THEME_SCHEMES[theme_name])
            
    def toggle_auto_preview(self):
        """Toggle auto-preview"""
        self.settings["auto_preview"] = self.auto_preview_var.get()
        self.save_settings()
        
    def toggle_intellisense(self):
        """Toggle IntelliSense"""
        self.settings["intellisense_enabled"] = self.intellisense_var.get()
        self.code_editor.auto_completion_enabled = self.intellisense_var.get()
        
        # Update status
        status_text = "IntelliSense: " + ("Enabled" if JEDI_AVAILABLE and self.intellisense_var.get() else "Disabled")
        self.intellisense_status.configure(text=status_text)
        
        self.save_settings()
        
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))
        
    def increase_font_size(self):
        """Increase editor font size"""
        current_size = self.font_size_var.get()
        new_size = min(current_size + 1, 24)
        self.font_size_var.set(new_size)
        self.settings["font_size"] = new_size
        self.update_editor_font()
        self.save_settings()
        
    def decrease_font_size(self):
        """Decrease editor font size"""
        current_size = self.font_size_var.get()
        new_size = max(current_size - 1, 8)
        self.font_size_var.set(new_size)
        self.settings["font_size"] = new_size
        self.update_editor_font()
        self.save_settings()
        
    def update_editor_font(self):
        """Update editor font size"""
        font_size = self.font_size_var.get()
        
        # Update editor font
        self.code_editor.configure(font=("Consolas", font_size))
        self.line_numbers.configure(font=("Consolas", font_size))
        
        # Update line numbers
        self.update_line_numbers()
        
    def on_editor_scroll(self, event):
        """Synchronize scrolling between editor and line numbers"""
        # Redirect scroll to both editor and line numbers
        self.line_numbers.yview_moveto(self.code_editor.yview()[0])
        
    def update_line_numbers(self):
        """Update line numbers display"""
        if hasattr(self, 'line_numbers') and hasattr(self.code_editor, 'line_count'):
            self.line_numbers.update_line_numbers(self.code_editor.line_count)
            
    # Asset management
    def show_add_asset_menu(self):
        """Show menu for adding assets"""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="📷 Add Images", command=self.add_images)
        menu.add_command(label="🎵 Add Audio", command=self.add_audio)
        
        # Get button position
        x = self.root.winfo_rootx() + 200
        y = self.root.winfo_rooty() + 200
        
        try:
            menu.post(x, y)
        finally:
            menu.grab_release()
            
    def add_images(self):
        """Add image assets"""
        file_paths = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.svg")]
        )
        
        if file_paths:
            for file_path in file_paths:
                if file_path not in self.image_paths:
                    self.image_paths.append(file_path)
                    
            self.update_assets_display()
            self.append_terminal_output(f"Added {len(file_paths)} image(s)\n")
            
    def add_audio(self):
        """Add audio asset"""
        file_path = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[("Audio files", "*.mp3 *.wav *.ogg *.m4a")]
        )
        
        if file_path:
            self.audio_path = file_path
            self.update_assets_display()
            self.append_terminal_output(f"Added audio: {os.path.basename(file_path)}\n")
            
    def update_assets_display(self):
        """Update assets display with visual cards"""
        # Clear existing cards
        for widget in self.assets_scroll.winfo_children():
            widget.destroy()
        self.asset_cards.clear()
        
        # Add image assets
        for img_path in self.image_paths:
            card = AssetCard(
                self.assets_scroll,
                img_path,
                "image",
                self.use_asset,
                self.remove_asset,
                fg_color=VSCODE_COLORS["surface_lighter"]
            )
            card.pack(fill="x", pady=5)
            self.asset_cards.append(card)
            
        # Add audio asset
        if self.audio_path:
            card = AssetCard(
                self.assets_scroll,
                self.audio_path,
                "audio",
                self.use_asset,
                self.remove_asset,
                fg_color=VSCODE_COLORS["surface_lighter"]
            )
            card.pack(fill="x", pady=5)
            self.asset_cards.append(card)
            
        # Update info label
        total_assets = len(self.image_paths) + (1 if self.audio_path else 0)
        if total_assets > 0:
            info_parts = []
            if self.image_paths:
                info_parts.append(f"{len(self.image_paths)} image(s)")
            if self.audio_path:
                info_parts.append("1 audio file")
            self.assets_info.configure(text=", ".join(info_parts))
        else:
            self.assets_info.configure(text="Click + to add images or audio files")
            
    def use_asset(self, asset_path, asset_type):
        """Use an asset in the code"""
        if asset_type == "image":
            code_snippet = f"\n# Using image: {os.path.basename(asset_path)}\n"
            code_snippet += f"image = ImageMobject(r\"{asset_path}\")\n"
            code_snippet += "image.scale(2)  # Adjust size as needed\n"
            code_snippet += "self.add(image)\n"
        else:  # audio
            code_snippet = f"\n# Using audio: {os.path.basename(asset_path)}\n"
            code_snippet += f"self.add_sound(\"{asset_path}\")\n"
            
        # Insert at current cursor position
        current_pos = self.code_editor.index("insert")
        self.code_editor.insert(current_pos, code_snippet)
        
        self.append_terminal_output(f"Inserted code for {asset_type}: {os.path.basename(asset_path)}\n")
        
    def remove_asset(self, asset_path, card_widget):
        """Remove an asset"""
        # Remove from lists
        if asset_path in self.image_paths:
            self.image_paths.remove(asset_path)
        elif asset_path == self.audio_path:
            self.audio_path = None
            
        # Update display
        self.update_assets_display()
        
        self.append_terminal_output(f"Removed asset: {os.path.basename(asset_path)}\n")
        
    # File operations
    def new_file(self):
        """Create new file"""
        if messagebox.askyesno("New File", "Create a new file? Unsaved changes will be lost."):
            self.code_editor.delete("1.0", "end")
            self.current_code = ""
            self.current_file_path = None
            self.file_tab.configure(text="📄 Untitled")
            self.clear_preview_video(silent=True)
            self.clear_output()
            self.load_default_code()
            
    def open_file(self):
        """Open file"""
        file_path = filedialog.askopenfilename(
            title="Open Python File",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                self.code_editor.delete("1.0", "end")
                self.code_editor.insert("1.0", content)
                self.current_code = content
                self.current_file_path = file_path
                
                filename = os.path.basename(file_path)
                self.file_tab.configure(text=f"📄 {filename}")
                self.update_status(f"Opened: {filename}")
                self.update_line_numbers()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file:\n{e}")
                
    def save_file(self):
        """Save file"""
        if self.current_file_path:
            self.save_to_file(self.current_file_path)
        else:
            self.save_as_file()
            
    def save_as_file(self):
        """Save file as"""
        file_path = filedialog.asksaveasfilename(
            title="Save Python File",
            defaultextension=".py",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        
        if file_path:
            self.save_to_file(file_path)
            self.current_file_path = file_path
            filename = os.path.basename(file_path)
            self.file_tab.configure(text=f"📄 {filename}")
            
    def save_to_file(self, file_path):
        """Save content to file"""
        try:
            self.current_code = self.code_editor.get("1.0", "end-1c")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.current_code)
            self.update_status(f"Saved: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file:\n{e}")
            
    # Animation operations with System Terminal Integration
    def quick_preview(self):
        """Generate quick preview with streaming output - FIXED FOR v0.19.0"""
        if self.is_previewing:
            self.append_terminal_output("Preview already in progress...\n")
            return
        
        self.is_previewing = True
        self.quick_preview_button.configure(text="⏳ Generating...", state="disabled")
        
        # Clear output and reset tracking
        self.clear_output()
        self.last_manim_output_path = None  # Reset path tracking
        
        # Get current code
        self.current_code = self.code_editor.get("1.0", "end-1c")
        
        if not self.current_code.strip():
            self.append_terminal_output("No code to preview\n")
            self.quick_preview_button.configure(text="⚡ Quick Preview", state="normal")
            self.is_previewing = False
            return
        
        # Parse scene class
        scene_class = self.extract_scene_class_name(self.current_code)
        if not scene_class:
            self.append_terminal_output("No valid scene class found\n")
            self.quick_preview_button.configure(text="⚡ Quick Preview", state="normal")
            self.is_previewing = False
            return
        
        # Create temporary file
        temp_suffix = str(int(time.time() * 1000))
        temp_dir = os.path.join(BASE_DIR, ".preview_temp", temp_suffix)
        os.makedirs(temp_dir, exist_ok=True)
        
        temp_file = os.path.join(temp_dir, f"preview_{temp_suffix}.py")
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(self.current_code)
        
        # FIXED: Build correct manim command for v0.19.0
        command = [
            self.venv_manager.python_path,
            "-m", "manim", "render",
            temp_file,
            scene_class,
            "-qm",  # Medium quality
            "--format", "mp4",
            "--fps", "15",
            "--disable_caching",
            "-o", f"preview_{temp_suffix}"
        ]
        
        self.log_command_start(f"Preview Generation - {scene_class}")
        self.log_info("Quality: Medium (720p) @ 15fps")
        self.log_info(f"Command: {' '.join(command)}")
        
        # On preview complete callback - ENHANCED VERSION
        def on_preview_complete(success, return_code):
            try:
                # Reset UI state first
                self.quick_preview_button.configure(text="⚡ Quick Preview", state="normal")
                self.is_previewing = False
                
                if success:
                    self.append_terminal_output(f"\n✅ Preview generation completed successfully!\n", "success")
                    
                    # Enhanced file finding with detailed logging
                    output_file = self.find_output_file(temp_dir, scene_class, "mp4")

                    if output_file and os.path.exists(output_file):
                        self.append_terminal_output(f"✅ Output file confirmed: {output_file}\n", "success")

                        # Copy to cache and use cached file for playback
                        cache_dir = os.path.join(BASE_DIR, ".preview_cache")
                        os.makedirs(cache_dir, exist_ok=True)
                        cached_file = os.path.join(cache_dir, f"preview_{temp_suffix}.mp4")

                        try:
                            shutil.copy2(output_file, cached_file)
                            self.append_terminal_output(f"📁 Cached to: {cached_file}\n", "info")
                            self.load_preview_video(cached_file)
                            self.update_status("Preview ready")
                            self.last_preview_code = self.current_code
                        except Exception as e:
                            self.append_terminal_output(f"❌ Error caching preview: {e}\n", "error")
                            # Fallback: try to load directly
                            try:
                                self.load_preview_video(output_file)
                                self.update_status("Preview ready")
                                self.last_preview_code = self.current_code
                            except Exception as e2:
                                self.append_terminal_output(f"❌ Error loading preview: {e2}\n", "error")
                    else:
                        self.append_terminal_output("❌ No output file found after exhaustive search\n", "error")
                        
                        # Provide debugging information
                        self.append_terminal_output("\n🔍 Debugging information:\n", "info")
                        self.append_terminal_output(f"   Working directory: {os.getcwd()}\n", "info")
                        self.append_terminal_output(f"   Temp directory: {temp_dir}\n", "info")
                        self.append_terminal_output(f"   Scene class: {scene_class}\n", "info")
                        
                        # List contents of likely directories
                        debug_dirs = [
                            os.path.join(os.getcwd(), "media"),
                            os.path.join(BASE_DIR, "media"),
                            temp_dir
                        ]
                        
                        for debug_dir in debug_dirs:
                            if os.path.exists(debug_dir):
                                self.append_terminal_output(f"   Contents of {debug_dir}:\n", "info")
                                try:
                                    for root, dirs, files in os.walk(debug_dir):
                                        level = root.replace(debug_dir, '').count(os.sep)
                                        indent = ' ' * 4 * (level + 1)
                                        self.append_terminal_output(f"{indent}{os.path.basename(root)}/\n", "info")
                                        subindent = ' ' * 4 * (level + 2)
                                        for file in files:
                                            self.append_terminal_output(f"{subindent}{file}\n", "info")
                                except Exception as e:
                                    self.append_terminal_output(f"   Error listing {debug_dir}: {e}\n", "warning")
                else:
                    self.append_terminal_output(f"\n❌ Preview generation failed (exit code: {return_code})\n", "error")
                
                # Cleanup temp directory
                try:
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                except Exception as e:
                    self.append_terminal_output(f"⚠️ Could not clean temp directory: {e}\n", "warning")
                    
            except Exception as e:
                self.append_terminal_output(f"❌ Error in preview completion: {e}\n", "error")
        
        # Start the streaming preview with enhanced callback
        if hasattr(self.venv_manager, 'run_command_streaming'):
            self.venv_manager.run_command_streaming(
                command, 
                log_callback=self.enhanced_log_callback,  # ENHANCED: Use the new callback
                on_complete=on_preview_complete
            )
        else:
            # Fallback with enhanced output processing
            self.append_terminal_output("⚠️ Using fallback preview method\n", "warning")
            def run_fallback():
                try:
                    result = subprocess.run(
                        command, 
                        capture_output=True, 
                        text=True, 
                        timeout=300,
                        encoding='utf-8',
                        errors='replace'
                    )
                    
                    # Process all output through enhanced callback
                    if result.stdout:
                        self.enhanced_log_callback(result.stdout, "output")
                    if result.stderr:
                        self.enhanced_log_callback(result.stderr, "error")
                        
                    on_preview_complete(result.returncode == 0, result.returncode)
                except Exception as e:
                    self.append_terminal_output(f"❌ Fallback error: {e}\n", "error")
                    on_preview_complete(False, -1)
            
            threading.Thread(target=run_fallback, daemon=True).start()


    
    def get_subprocess_environment(self, num_cores):
        """Get enhanced environment for subprocess calls in onefile mode"""
        env = os.environ.copy()
        
        # Set threading environment variables
        env.update({
            "OMP_NUM_THREADS": str(num_cores),
            "OPENBLAS_NUM_THREADS": str(num_cores),
            "MKL_NUM_THREADS": str(num_cores),
            "NUMEXPR_NUM_THREADS": str(num_cores),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1"
        })
        
        # For onefile executables, ensure proper temp directory
        if getattr(sys, 'frozen', False):
            system_temp = os.environ.get('TEMP', tempfile.gettempdir())
            env.update({
                'TEMP': system_temp,
                'TMP': system_temp
            })
            
            # Add executable directory to PATH
            exe_dir = get_executable_directory()
            if 'PATH' in env:
                env['PATH'] = f"{exe_dir};{env['PATH']}"
            else:
                env['PATH'] = exe_dir
        
        return env
    def cleanup_temp_directory(self):
        """Clean up temporary directory used for preview"""
        if getattr(self, 'current_temp_dir', None):
            try:
                if os.path.exists(self.current_temp_dir):
                    time.sleep(0.5)
                    import gc
                    gc.collect()
                    shutil.rmtree(self.current_temp_dir)
                    self.append_terminal_output(f"Cleaned up: {self.current_temp_dir}\n")
            except Exception as e:
                self.append_terminal_output(f"Warning: Cleanup failed: {e}\n")
            finally:
                self.current_temp_dir = None
                self.current_scene_file = None

    def render_animation(self):
        """Render high-quality animation using system terminal"""
        if self.is_rendering:
            return
            
        if not self.current_code.strip():
            messagebox.showwarning("Warning", "Please enter code before rendering")
            return
            
        # Check if environment is active
        if not self.venv_manager.current_venv:
            messagebox.showwarning(
                "No Environment Active",
                "No Python environment is active. Please set up an environment first.\n\n"
                "Click the Environment Setup button to create one."
            )
            return
        
        # Validate custom resolution if selected
        try:
            resolution_settings = self.get_current_resolution_settings()
        except ValueError as e:
            messagebox.showerror("Invalid Resolution", str(e))
            return
            
        self.is_rendering = True
        self.render_button.configure(text="⏳ Rendering...", state="disabled")
        self.update_status("Starting render...")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Initializing render...")
        
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(
                prefix="manim_render_",
                dir=ensure_ascii_path(tempfile.gettempdir())
            )
            temp_dir = get_long_path(temp_dir)
            
            # Extract scene class name
            scene_class = self.extract_scene_class_name(self.current_code)
            
            # Write code to file
            scene_file = os.path.join(temp_dir, "scene.py")
            with open(scene_file, "w", encoding="utf-8") as f:
                f.write(self.current_code)
                
            # Get render settings
            quality_flag = resolution_settings["flag"]
            format_ext = EXPORT_FORMATS[self.settings["format"]]
            fps = resolution_settings["fps"]
            
            # Use environment Python
            python_exe = get_long_path(ensure_ascii_path(self.venv_manager.python_path))
            
            # Get the number of cores to use
            num_cores = self.get_render_cores()
                
            # Build manim command
            command = [
                str(python_exe), 
                "-m", "manim", "render",  # FIXED: Added "render" subcommand
                str(scene_file),
                str(scene_class),
                str(quality_flag),
                "--format", format_ext,   # FIXED: Separate format flag
                "--fps", str(fps),        # FIXED: Separate fps flag  
                "--renderer", "cairo"     # FIXED: Separate renderer flag
            ]
            
            # Add custom resolution if using custom quality
            if self.quality_var.get() == "Custom":
                command.extend([
                    "--resolution", f"{resolution_settings['width']},{resolution_settings['height']}"  # FIXED: Separate resolution flag
                ])
            
            # Add audio if available
            if self.audio_path and os.path.exists(self.audio_path):
                command.extend(["--sound", self.audio_path])
            
            # Set environment variable for CPU control
            env = {"OMP_NUM_THREADS": str(num_cores)}
            
            # Enhanced logging
            self.append_terminal_output(f"Starting render...\n")
            self.append_terminal_output(f"Resolution: {resolution_settings['resolution']} @ {fps}fps\n")
            self.append_terminal_output(f"Using {num_cores} CPU cores\n")
            
            # On render complete callback
            def on_render_complete(success, return_code):
                # Find output file
                output_file = self.find_output_file(temp_dir, scene_class, format_ext)
                
                # Reset UI state
                self.render_button.configure(text="🚀 Render Animation", state="normal")
                self.is_rendering = False
                
                if success and output_file and os.path.exists(output_file):
                    self.progress_bar.set(1.0)
                    self.progress_label.configure(text="Render completed!")
                    self.update_status("Render completed successfully")
                    
                    # Save rendered file
                    self.save_rendered_file(output_file, format_ext)
                else:
                    self.progress_bar.set(0)
                    self.progress_label.configure(text="Render failed")
                    self.update_status("Render failed")
                    self.append_terminal_output("Error: Output file not found or rendering failed\n")
                
                # Cleanup temp directory
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    self.append_terminal_output(f"Warning: Could not clean up temp directory: {e}\n")
            
            # Run command using system terminal
            self.terminal.run_command_redirected(command, on_render_complete, env)
                
        except Exception as e:
            self.update_status(f"Render error: {e}")
            self.append_terminal_output(f"Render error: {e}\n")
            self.render_button.configure(text="🚀 Render Animation", state="normal")
            self.is_rendering = False
        
    def extract_scene_class_name(self, code):
        """Extract scene class name from code"""
        import re
        scene_classes = re.findall(r'class\s+(\w+)\s*\([^)]*Scene[^)]*\)', code)
        return scene_classes[0] if scene_classes else "MyScene"
        
    def find_output_file(self, temp_dir, scene_class, format_ext):
        """Find rendered output file - FIXED for correct manim v0.19.0 output structure"""
        
        self.append_terminal_output(f"🔍 Searching for output file...\n", "info")
        self.append_terminal_output(f"   Scene class: {scene_class}\n", "info")
        self.append_terminal_output(f"   Format: {format_ext}\n", "info")
        self.append_terminal_output(f"   Temp dir: {temp_dir}\n", "info")
        
        # Method 1: Use the path extracted from manim output (most reliable)
        if hasattr(self, 'last_manim_output_path') and self.last_manim_output_path:
            if os.path.exists(self.last_manim_output_path):
                self.append_terminal_output(f"✅ Found via manim log: {self.last_manim_output_path}\n", "success")
                return self.last_manim_output_path
            else:
                self.append_terminal_output(f"⚠️ Manim log path doesn't exist: {self.last_manim_output_path}\n", "warning")
        
        # Method 2: Extract temp file prefix for directory name matching
        temp_file_name = os.path.basename(temp_dir)  # e.g., "preview_1750668520778"
        self.append_terminal_output(f"   Looking for directories containing: {temp_file_name}\n", "info")
        
        # Method 3: Search in probable manim output locations
        
        # Strategy A: Current working directory media folder (most common for manim v0.19.0)
        search_bases = [
            os.getcwd(),  # Current project directory
            BASE_DIR,     # Application base directory
            os.path.dirname(temp_dir),  # Parent of temp directory
            temp_dir      # Temp directory itself
        ]
        
        self.append_terminal_output(f"🔍 Searching in base directories:\n", "info")
        for base in search_bases:
            self.append_terminal_output(f"   - {base}\n", "info")
        
        # Strategy A1: Look for media/videos/TEMP_NAME/QUALITY/ structure
        for base_dir in search_bases:
            media_dir = os.path.join(base_dir, "media", "videos")
            if os.path.exists(media_dir):
                self.append_terminal_output(f"📁 Checking media directory: {media_dir}\n", "info")
                
                # Look for temp directory name
                temp_video_dir = os.path.join(media_dir, temp_file_name)
                if os.path.exists(temp_video_dir):
                    self.append_terminal_output(f"📁 Found temp video directory: {temp_video_dir}\n", "info")
                    
                    # Check quality subdirectories
                    quality_dirs = ["720p15", "720p30", "480p15", "480p30", "1080p60", "1080p30", "2160p60", "480p", "720p", "1080p", "2160p"]
                    for quality_dir in quality_dirs:
                        quality_path = os.path.join(temp_video_dir, quality_dir)
                        if os.path.exists(quality_path):
                            self.append_terminal_output(f"📁 Checking quality directory: {quality_path}\n", "info")
                            
                            for file in os.listdir(quality_path):
                                if file.endswith(f".{format_ext}"):
                                    full_path = os.path.join(quality_path, file)
                                    self.append_terminal_output(f"✅ Found output file: {full_path}\n", "success")
                                    return full_path
        
        # Strategy B: Search for any directory containing temp_file_name
        self.append_terminal_output(f"🔍 Searching for any directory containing {temp_file_name}...\n", "info")
        for base_dir in search_bases:
            if os.path.exists(base_dir):
                for root, dirs, files in os.walk(base_dir):
                    # Check if any directory in the path contains our temp name
                    if temp_file_name in root:
                        self.append_terminal_output(f"📁 Found matching directory: {root}\n", "info")
                        for file in files:
                            if file.endswith(f".{format_ext}"):
                                full_path = os.path.join(root, file)
                                self.append_terminal_output(f"✅ Found output file in matching directory: {full_path}\n", "success")
                                return full_path
        
        # Strategy C: Look for files containing scene class name or temp identifier
        self.append_terminal_output(f"🔍 Searching for files containing scene class or temp ID...\n", "info")
        search_patterns = [temp_file_name, scene_class, f"preview_{temp_file_name.split('_')[-1]}"]
        
        for base_dir in search_bases:
            if os.path.exists(base_dir):
                for root, dirs, files in os.walk(base_dir):
                    for file in files:
                        if file.endswith(f".{format_ext}"):
                            # Check if filename contains any of our search patterns
                            for pattern in search_patterns:
                                if pattern in file:
                                    full_path = os.path.join(root, file)
                                    self.append_terminal_output(f"✅ Found file with matching pattern '{pattern}': {full_path}\n", "success")
                                    return full_path
        
        # Strategy D: Look for any recent files (last resort)
        self.append_terminal_output(f"🔍 Looking for recently created {format_ext} files...\n", "info")
        recent_files = []
        current_time = time.time()
        
        for base_dir in search_bases:
            if os.path.exists(base_dir):
                for root, dirs, files in os.walk(base_dir):
                    for file in files:
                        if file.endswith(f".{format_ext}"):
                            full_path = os.path.join(root, file)
                            try:
                                mtime = os.path.getmtime(full_path)
                                age_seconds = current_time - mtime
                                if age_seconds < 120:  # Created within last 2 minutes
                                    recent_files.append((mtime, full_path))
                                    self.append_terminal_output(f"📄 Recent file: {full_path} (age: {age_seconds:.1f}s)\n", "info")
                            except:
                                pass
        
        if recent_files:
            # Sort by modification time (newest first)
            recent_files.sort(reverse=True)
            most_recent = recent_files[0][1]
            self.append_terminal_output(f"✅ Using most recent file: {most_recent}\n", "success")
            return most_recent
        
        # All strategies failed
        self.append_terminal_output(f"❌ No output file found after exhaustive search\n", "error")
        self.append_terminal_output(f"   Searched for: {format_ext} files\n", "error")
        self.append_terminal_output(f"   Scene class: {scene_class}\n", "error")
        self.append_terminal_output(f"   Temp identifier: {temp_file_name}\n", "error")
        
        return None
    def extract_file_path_from_output(self, output_text):
        """Extract the actual file path from manim output"""
        import re
        
        # Method 1: Look for "File ready at" followed by quoted path
        file_ready_match = re.search(r"File ready at\s*['\"]([^'\"]+)['\"]", output_text, re.MULTILINE | re.DOTALL)
        if file_ready_match:
            path = file_ready_match.group(1).strip()
            if os.path.exists(path):
                self.last_manim_output_path = path
                return path
        
        # Method 2: Look for multi-line file path (manim sometimes splits long paths)
        lines = output_text.split('\n')
        collecting_path = False
        path_parts = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Start collecting when we see "File ready at"
            if "File ready at" in line:
                collecting_path = True
                # Check if path starts on the same line
                remaining_line = line.split("File ready at")[-1].strip()
                if remaining_line:
                    if remaining_line.startswith("'") or remaining_line.startswith('"'):
                        path_parts = [remaining_line[1:]]  # Remove opening quote
                    else:
                        path_parts = [remaining_line]
                continue
            
            # If we're collecting and this line has content
            if collecting_path and line:
                # Check for closing quote
                if line.endswith("'") or line.endswith('"'):
                    path_parts.append(line[:-1])  # Remove closing quote
                    full_path = "".join(path_parts).strip()
                    
                    # Clean up the path
                    full_path = full_path.replace("\\", os.sep).replace("/", os.sep)
                    
                    if os.path.exists(full_path):
                        self.last_manim_output_path = full_path
                        return full_path
                    
                    collecting_path = False
                    path_parts = []
                else:
                    path_parts.append(line)
                    
                # Stop collecting after too many lines (avoid infinite collection)
                if len(path_parts) > 10:
                    collecting_path = False
                    path_parts = []
        
        # Method 3: Look for any path-like strings in the output
        path_patterns = [
            r"([C-Z]:[\\\/](?:[^\\\/\n\r]+[\\\/])*[^\\\/\n\r]*\.mp4)",  # Windows paths
            r"(\/(?:[^\/\n\r]+\/)*[^\/\n\r]*\.mp4)",  # Unix paths
        ]
        
        for pattern in path_patterns:
            matches = re.findall(pattern, output_text, re.MULTILINE)
            for match in matches:
                if os.path.exists(match):
                    self.last_manim_output_path = match
                    return match
        
        return None

# ==============================================================================
# Step 4: Add this enhanced log callback method
# ==============================================================================

    def enhanced_log_callback(self, text, msg_type="output"):
        """Enhanced log callback that also parses manim output for file paths"""
        # Call the original append_terminal_output
        self.append_terminal_output(text, msg_type)
        
        # Try to extract file path from this output
        if any(keyword in text for keyword in ["File ready at", ".mp4", ".mov", ".gif"]):
            file_path = self.extract_file_path_from_output(text)
            if file_path:
                self.append_terminal_output(f"📁 Extracted output path: {file_path}\n", "info")

    def save_rendered_file(self, source_file, format_ext):
        """Save rendered file to user location"""
        # Ask user where to save
        file_path = filedialog.asksaveasfilename(
            title="Save Rendered Animation",
            defaultextension=f".{format_ext}",
            filetypes=[(f"{format_ext.upper()} files", f"*.{format_ext}")]
        )
        
        if file_path:
            try:
                shutil.copy2(source_file, file_path)
                self.append_terminal_output(f"Animation saved to: {file_path}\n")
                messagebox.showinfo("Success", f"Animation saved successfully!\n\nLocation: {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file:\n{e}")
                
    def stop_process(self):
        """Stop current process"""
        stopped = False
        
        if self.render_process:
            try:
                self.render_process.terminate()
                self.render_process = None
                self.is_rendering = False
                self.render_button.configure(text="🚀 Render Animation", state="normal")
                self.progress_bar.set(0)
                self.progress_label.configure(text="Render stopped")
                stopped = True
            except:
                pass
                
        if self.preview_process:
            try:
                self.preview_process.terminate()
                self.preview_process = None
                self.is_previewing = False
                self.quick_preview_button.configure(text="⚡ Quick Preview", state="normal")
                stopped = True
            except:
                pass
                
        if stopped:
            self.update_status("Process stopped")
            self.append_terminal_output("Process stopped by user\n")
        else:
            self.update_status("No process running")
    
    # Utility methods
    def create_tooltip(self, widget, text):
        """Create tooltip for widget"""
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            
            label = tk.Label(
                tooltip,
                text=text,
                background="#2D2D30",
                foreground="#CCCCCC",
                relief="solid",
                borderwidth=1,
                font=("Arial", 9)
            )
            label.pack()
            
            widget.tooltip = tooltip
            
        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip
                
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        
    def update_status(self, message):
        """Update status bar"""
        self.status_label.configure(text=message)
        self.root.update_idletasks()
        
    def start_background_tasks(self):
        """Start background tasks"""
        # Update time every minute
        def update_time():
            self.time_label.configure(text=datetime.now().strftime("%H:%M"))
            self.root.after(60000, update_time)
            
        update_time()
        
        # Update virtual environment status
        def update_venv_status():
            if self.venv_manager.current_venv:
                self.venv_status_label.configure(text=self.venv_manager.current_venv)
            else:
                self.venv_status_label.configure(text="No environment")
            self.root.after(5000, update_venv_status)
            
        update_venv_status()
        
        # Check for dependencies
        self.root.after(1000, self.check_dependencies)
        
    def check_dependencies(self):
        """Check if required dependencies are installed using system terminal"""
        def check_thread():
            required = ["manim", "numpy", "PIL", "cv2"]
            missing = []
            
            # Use system terminal if available
            if hasattr(self, 'terminal'):
                # Create a script to check dependencies
                check_script = """
import sys

# Check for required packages
missing = []
packages = sys.argv[1:]
for package in packages:
    try:
        if package == 'PIL':
            import PIL
        elif package == 'cv2':
            import cv2
        else:
            __import__(package)
        print(f"[OK] {package} is installed")
    except ImportError:
        missing.append(package)
        print(f"[FAIL] Missing package: {package}")

if missing:
    print(f"Missing packages: {', '.join(missing)}")
    sys.exit(1)
else:
    print("All dependencies are installed!")
    sys.exit(0)
"""
                script_path = None
                try:
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                        f.write(check_script)
                        script_path = f.name
                        
                    # Run using the selected Python environment
                    python_exe = self.venv_manager.python_path if self.venv_manager.current_venv else sys.executable
                    
                    def on_check_complete(success, return_code):
                        if not success:
                            # Offer to install missing packages
                            # We get missing packages from terminal output
                            terminal_output = self.output_text.get("1.0", "end")
                            missing_line = [line for line in terminal_output.splitlines() if "Missing packages:" in line]
                            if missing_line:
                                missing_str = missing_line[0].split("Missing packages:")[1].strip()
                                missing = [pkg.strip() for pkg in missing_str.split(',')]
                                
                                # Map package names for installation
                                install_names = []
                                for pkg in missing:
                                    if pkg == 'PIL':
                                        install_names.append("Pillow")
                                    elif pkg == 'cv2':
                                        install_names.append("opencv-python")
                                    else:
                                        install_names.append(pkg)
                                        
                                # Ask to install
                                self.root.after(0, lambda: self.show_dependency_dialog(missing, install_names))
                    
                    self.terminal.run_command_redirected(
                        [python_exe, script_path] + required,
                        on_complete=on_check_complete
                    )
                finally:
                    # Clean up script later
                    if script_path:
                        self.root.after(5000, lambda: os.unlink(script_path) if os.path.exists(script_path) else None)
            else:
                # Fallback to direct checking
                # Use current virtual environment if available
                python_exe = self.venv_manager.python_path if self.venv_manager.current_venv else sys.executable
                    
                for package in required:
                    try:
                        # Check if package is installed
                        import_cmd = "PIL" if package == "PIL" else package
                        result = self.run_hidden_subprocess_nuitka_safe(
                            [python_exe, "-c", f"import {import_cmd}"],
                            capture_output=True
                        )
                        
                        if result.returncode != 0:
                            missing.append(package)
                    except:
                        missing.append(package)
                        
                if missing:
                    # Map package names for installation
                    install_names = []
                    for pkg in missing:
                        if pkg == 'PIL':
                            install_names.append("Pillow")
                        elif pkg == 'cv2':
                            install_names.append("opencv-python")
                        else:
                            install_names.append(pkg)
                            
                    self.root.after(0, lambda: self.show_dependency_dialog(missing, install_names))
                else:
                    self.root.after(0, lambda: self.update_status("All dependencies ready"))
                
        threading.Thread(target=check_thread, daemon=True).start()
        
    def show_dependency_dialog(self, missing_packages, install_names):
        """Show dialog for missing dependencies"""
        if messagebox.askyesno(
            "Missing Dependencies",
            f"The following packages are missing: {', '.join(missing_packages)}\n\n"
            f"ManimStudio can automatically install them: {', '.join(install_names)}\n\n"
            "Would you like to install them now?"
        ):
            self.install_missing_dependencies(install_names)
            
    def install_missing_dependencies(self, package_names):
        """Install missing dependencies with a progress dialog"""
        if not self.venv_manager.current_venv:
            messagebox.showwarning(
                "No Environment",
                "Please set up a virtual environment first before installing packages."
            )
            self.manage_environment()
            return

        DependencyInstallDialog(self.root, self.venv_manager, package_names)
        
    # Help functions
    def open_manim_docs(self):
        """Open Manim documentation"""
        import webbrowser
        webbrowser.open("https://docs.manim.community/")
        
    def show_getting_started(self):
        """Show getting started guide"""
        try:
            from tkinter import messagebox
            messagebox.showinfo(
                "Getting Started", 
                "Welcome to ManimStudio!\n\n"
                "• Create animations using the code editor\n"
                "• Use Quick Preview (F5) to test your code\n"
                "• Use Render Animation (F7) for final output\n"
                "• Check Tools → Environment Setup if needed\n\n"
                "See Help → Manim Documentation for more info."
            )
        except Exception as e:
            print(f"Error showing getting started: {e}")
        
    def show_about(self):
        """Show about dialog"""
        about_dialog = ctk.CTkToplevel(self.root)
        about_dialog.title(f"About {APP_NAME}")
        screen_w = about_dialog.winfo_screenwidth()
        screen_h = about_dialog.winfo_screenheight()
        width = min(500, screen_w - 100)
        height = min(600, screen_h - 100)
        about_dialog.geometry(f"{width}x{height}")
        about_dialog.transient(self.root)
        about_dialog.grab_set()
        
        # Center the dialog
        about_dialog.geometry("+%d+%d" % (
            self.root.winfo_rootx() + 100,
            self.root.winfo_rooty() + 100
        ))
        
        # Content frame
        content_frame = ctk.CTkFrame(about_dialog, fg_color=VSCODE_COLORS["surface"])
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # App icon
        icon_label = ctk.CTkLabel(
            content_frame,
            text="🎬",
            font=ctk.CTkFont(size=48)
        )
        icon_label.pack(pady=(20, 10))
        
        # Title
        title_label = ctk.CTkLabel(
            content_frame,
            text=APP_NAME,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        )
        title_label.pack(pady=5)
        
        # Subtitle
        subtitle_label = ctk.CTkLabel(
            content_frame,
            text=f"Professional Edition v{APP_VERSION}",
            font=ctk.CTkFont(size=16),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        subtitle_label.pack(pady=(0, 20))
        
        # Description
        description = f"""A modern, professional desktop application for creating
mathematical animations using the Manim library.

✨ Features:
- Advanced VSCode-like editor with IntelliSense
- System Terminal Integration for better performance
- Real-time Python autocompletion using Jedi
- Integrated environment management with automatic setup
- Real-time video preview with playback controls
- Multiple export formats (MP4, GIF, WebM, PNG)
- High-quality rendering up to 8K resolution
- Visual asset management with previews
- Professional UI with multiple themes
- Advanced find/replace functionality
- Smart auto-indentation and bracket matching
- One-click environment creation and package installation
- Professional syntax highlighting
- Multi-threaded rendering and preview
- Integrated asset manager for images and audio
- Custom theme support with live preview
- Custom resolution support for any video size

🛠️ Built with:
- Python & CustomTkinter for modern UI
- System Terminal Integration (Windows/macOS/Linux)
- Jedi Language Server for IntelliSense
- Advanced Text Widget with syntax highlighting
- Manim Community Edition for animations
- OpenCV for video processing
- PIL for image handling
- Integrated virtual environment management

👨‍💻 Author: {APP_AUTHOR}
📧 Email: {APP_EMAIL}

© 2025 {APP_AUTHOR}
Licensed under MIT License"""
        
        desc_label = ctk.CTkLabel(
            content_frame,
            text=description,
            font=ctk.CTkFont(size=12),
            justify="left",
            text_color=VSCODE_COLORS["text"]
        )
        desc_label.pack(pady=(0, 20), padx=20)
        
        # Buttons
        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.pack(pady=10)
        
        docs_btn = ctk.CTkButton(
            button_frame,
            text="📚 Documentation",
            command=self.open_manim_docs,
            width=120,
            fg_color=VSCODE_COLORS["primary"],
            hover_color=VSCODE_COLORS["primary_hover"]
        )
        docs_btn.pack(side="left", padx=5)
        
        close_btn = ctk.CTkButton(
            button_frame,
            text="Close",
            command=about_dialog.destroy,
            width=80
        )
        close_btn.pack(side="left", padx=5)
        
    def run(self):
        """Start the application main loop"""
        try:
            if self.root and self.root.winfo_exists():
                self.root.mainloop()
        except Exception as e:
            if "application has been destroyed" not in str(e):
                if hasattr(self, 'logger'):
                    self.logger.error(f"Main loop error: {e}")
                else:
                    print(f"Main loop error: {e}")
    def fix_manim_dependencies(self):
        """Fix common Manim dependency issues"""
        try:
            import tkinter.messagebox as messagebox
            # Show progress dialog
            progress_dialog = messagebox.askquestion(
                "Fix Dependencies", 
                "This will reinstall problematic Manim dependencies.\n"
                "This may take a few minutes. Continue?"
            )
            
            if progress_dialog == 'yes':
                # Fix mapbox_earcut
                success = self.venv_manager.fix_mapbox_earcut_issue()
                
                if success:
                    messagebox.showinfo(
                        "Fix Complete",
                        "Dependencies have been fixed!\n"
                        "Try running your animation again."
                    )
                else:
                    messagebox.showerror(
                        "Fix Failed",
                        "Could not fix all dependencies.\n"
                        "You may need to reinstall the environment."
                    )
                    
        except Exception as e:
            logger.error(f"Error fixing dependencies: {e}")
            import tkinter.messagebox as messagebox
            messagebox.showerror(
                "Error",
                f"An error occurred while fixing dependencies: {e}"
            )
    def auto_activate_default_environment(self):
        """Automatically activate manim_studio_default environment if it exists and is ready"""
        try:
            default_venv_path = os.path.join(self.venv_manager.venv_dir, "manim_studio_default")
            
            if os.path.exists(default_venv_path):
                self.logger.info("Checking manim_studio_default environment for auto-activation...")
                
                # Check if environment is valid
                if self.venv_manager.is_valid_venv(default_venv_path):
                    self.logger.info("manim_studio_default environment structure is valid")
                    
                    # Set up paths
                    if os.name == 'nt':
                        python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
                        pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
                    else:
                        python_path = os.path.join(default_venv_path, "bin", "python")
                        pip_path = os.path.join(default_venv_path, "bin", "pip")
                    
                    # Verify executables exist
                    if os.path.exists(python_path) and os.path.exists(pip_path):
                        # Update VirtualEnvironmentManager state
                        self.venv_manager.python_path = python_path
                        self.venv_manager.pip_path = pip_path
                        self.venv_manager.current_venv = "manim_studio_default"
                        
                        # Check if environment is already validated (fast check)
                        if self.venv_manager._is_environment_validated("manim_studio_default"):
                            self.logger.info("✅ Auto-activated manim_studio_default environment from cache")
                            self.venv_manager.needs_setup = False
                            self.root.after(1000, self.update_environment_status)
                        else:
                            # Need to validate for the first time
                            self.logger.info("Validating manim_studio_default environment...")
                            if self.venv_manager.check_manim_availability():
                                self.logger.info("✅ Auto-activated manim_studio_default environment successfully")
                                self.venv_manager.needs_setup = False
                                self.root.after(1000, self.update_environment_status)
                            else:
                                self.logger.info("manim_studio_default exists but manim is not working properly")
                                # Keep needs_setup as True to trigger repair
                    else:
                        self.logger.warning("manim_studio_default environment has missing executables")
                else:
                    self.logger.warning("manim_studio_default environment structure is invalid")
            else:
                self.logger.info("No manim_studio_default environment found - will need to create one")
                
        except Exception as e:
            self.logger.error(f"Error during auto-activation: {e}")
    def force_environment_revalidation(self, env_name=None):
        """Force re-validation of environment (clear cache)"""
        if not env_name:
            env_name = self.current_venv
        
        if env_name:
            config = self._load_environment_config()
            if env_name in config:
                del config[env_name]
                self._save_environment_config(config)
                self.logger.info(f"Cleared validation cache for environment: {env_name}")
    def update_environment_status(self):
        """Update environment status in the UI"""
        try:
            # Update status bar if it exists
            if hasattr(self, 'status_label'):
                if self.venv_manager.current_venv:
                    env_status = f"Environment: {self.venv_manager.current_venv}"
                    if self.venv_manager.check_manim_availability():
                        env_status += " ✅"
                    else:
                        env_status += " ⚠️"
                    self.status_label.configure(text=env_status)
                else:
                    self.status_label.configure(text="No environment active")
            
            # Remove this problematic section - SystemTerminalManager doesn't have update_environment
            # if hasattr(self, 'terminal') and self.terminal:
            #     self.terminal.update_environment()
                
        except Exception as e:
            self.logger.error(f"Error updating environment status: {e}")
class DependencyInstallDialog(ctk.CTkToplevel):
    """Dialog showing progress while installing packages."""

    def __init__(self, parent, venv_manager, packages):
        super().__init__(parent)
        self.venv_manager = venv_manager
        self.packages = packages

        self.title("Installing Packages")

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(500, screen_w - 100)
        height = min(400, screen_h - 100)
        self.geometry(f"{width}x{height}")
        self.minsize(400, 300)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ctk.CTkFrame(self, fg_color=VSCODE_COLORS["surface"])
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        self.status_label = ctk.CTkLabel(frame, text="Preparing...", font=ctk.CTkFont(size=14))
        self.status_label.pack(pady=(0, 10))

        self.progress_bar = ctk.CTkProgressBar(frame)
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)

        self.log_text = ctk.CTkTextbox(frame, height=200, font=ctk.CTkFont(size=11, family="Consolas"))
        self.log_text.pack(fill="both", expand=True, pady=15)

        threading.Thread(target=self.install_worker, daemon=True).start()

    def log(self, message):
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.update_idletasks()

    def install_worker(self):
        total = len(self.packages)
        for i, pkg in enumerate(self.packages, 1):
            self.status_label.configure(text=f"Installing {pkg} ({i}/{total})")
            self.progress_bar.set((i - 1) / total)
            cmd = self.venv_manager.get_pip_command() + ["install", pkg]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.log(f"✓ {pkg} installed")
            else:
                self.log(f"✗ Failed to install {pkg}")
            self.progress_bar.set(i / total)

        self.status_label.configure(text="Installation complete")
        self.after(1000, self.destroy)
class GettingStartedDialog(ctk.CTkToplevel):
    """Getting started guide dialog"""

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.venv_manager = app.venv_manager
        self.package_queue = queue.Queue()
        
        self.title("Getting Started - Manim Animation Studio")

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        width = max(600, min(int(screen_w * 0.6), screen_w - 100, 1000))
        height = max(500, min(int(screen_h * 0.8), screen_h - 100, 850))
        self.geometry(f"{width}x{height}")
        self.minsize(600, 500)
        self.resizable(True, True)
        self.transient(app.root)
        self.grab_set()
        
        # Center the dialog
        self.geometry("+%d+%d" % (
            app.root.winfo_rootx() + 50,
            app.root.winfo_rooty() + 50
        ))

        self.setup_ui()
        self.update_env_status()

    def __getattr__(self, name):
        """Delegate attribute access to the parent app when not found here."""
        return getattr(self.app, name)

    def setup_environment(self):
        """Launch the environment setup dialog via the app's manager."""
        self.venv_manager.show_setup_dialog()
        self.update_env_status()

    def fix_manim_dependencies(self):
        self.app.fix_manim_dependencies()
        self.update_env_status()

    def manage_environments(self):
        self.app.manage_environment()
        self.update_env_status()

    def update_env_status(self):
        if self.venv_manager.is_environment_ready():
            status = "Environment ready"
        else:
            status = "Environment not set up"
        self.env_status_label.configure(text=status)
        env_path = os.path.join(self.venv_manager.venv_dir, "manim_studio_default")
        self.env_path_display.configure(text=env_path)
        ready = self.venv_manager.is_environment_ready()
        if ready and not getattr(self.app, "debug_mode", False):
            self.setup_button.configure(state="disabled")
        else:
            self.setup_button.configure(state="normal")

        if ready:
            self.fix_button.configure(state="normal")
            self.manage_button.configure(state="normal")
        else:
            self.fix_button.configure(state="disabled")
            self.manage_button.configure(state="disabled")

    def setup_ui(self):
        """Setup the main UI"""
        # Create main frame
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="Manim Studio",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=20)
        
        # Environment status frame
        status_frame = ctk.CTkFrame(main_frame)
        status_frame.pack(fill="x", padx=10, pady=5)
        
        # Environment status
        self.env_status_label = ctk.CTkLabel(
            status_frame,
            text="Checking environment...",
            font=ctk.CTkFont(size=12)
        )
        self.env_status_label.pack(pady=(10, 5))

        # Environment path
        env_path = os.path.join(self.venv_manager.venv_dir, "manim_studio_default")
        self.env_path_display = ctk.CTkLabel(
            status_frame,
            text=env_path,
            font=ctk.CTkFont(size=10)
        )
        self.env_path_display.pack(pady=(0, 10))
        
        # Button frame
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x", padx=10, pady=10)
        
        # Setup button
        self.setup_button = ctk.CTkButton(
            button_frame,
            text="Setup Environment",
            command=self.setup_environment,
            state="disabled",
            width=200
        )
        self.setup_button.pack(side="left", padx=5, pady=10)
        
        # Fix dependencies button
        self.fix_button = ctk.CTkButton(
            button_frame,
            text="Fix Manim Dependencies",
            command=self.fix_manim_dependencies,
            fg_color="orange",
            hover_color="darkorange",
            width=200
        )
        self.fix_button.pack(side="left", padx=5, pady=10)
        
        # Environment management button
        self.manage_button = ctk.CTkButton(
            button_frame,
            text="Manage Environments",
            command=self.manage_environments,
            fg_color="purple",
            hover_color="darkviolet",
            width=200
        )
        self.manage_button.pack(side="left", padx=5, pady=10)
        
        # Main content area
        content_frame = ctk.CTkFrame(main_frame)
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create tabview for different sections
        self.tabview = ctk.CTkTabview(content_frame)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        # Code Editor Tab
        self.editor_tab = self.tabview.add("Code Editor")
        self.setup_editor_tab()

        # Settings Tab
        self.settings_tab = self.tabview.add("Settings")
        self.setup_settings_tab()

        # Log Tab
        self.log_tab = self.tabview.add("Logs")
        self.setup_log_tab()

        # Status bar
        self.status_bar = ctk.CTkLabel(
            main_frame,
            text="Ready",
            font=ctk.CTkFont(size=10),
            fg_color="gray20",
            corner_radius=5
        )
        self.status_bar.pack(fill="x", padx=10, pady=(0, 10))

    def setup_editor_tab(self):
        """Setup the code editor tab"""
        # Code editor frame
        editor_frame = ctk.CTkFrame(self.editor_tab)
        editor_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Editor toolbar
        toolbar_frame = ctk.CTkFrame(editor_frame)
        toolbar_frame.pack(fill="x", padx=5, pady=5)
        
        # Toolbar buttons
        new_button = ctk.CTkButton(
            toolbar_frame,
            text="New",
            command=self.new_file,
            width=80
        )
        new_button.pack(side="left", padx=5)
        
        open_button = ctk.CTkButton(
            toolbar_frame,
            text="Open",
            command=self.open_file,
            width=80
        )
        open_button.pack(side="left", padx=5)
        
        save_button = ctk.CTkButton(
            toolbar_frame,
            text="Save",
            command=self.save_file,
            width=80
        )
        save_button.pack(side="left", padx=5)
        
        # Removed animation rendering button for simplified setup UI
        
        # Text editor
        self.text_editor = ctk.CTkTextbox(
            editor_frame,
            font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.text_editor.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Insert default Manim code
        default_code = '''from manim import *

class MyScene(Scene):
    def construct(self):
        # Create a circle
        circle = Circle()
        circle.set_fill(BLUE, opacity=0.5)
        circle.set_stroke(BLUE_C, width=4)
        
        # Create text
        text = Text("Hello, Manim!")
        text.next_to(circle, DOWN)
        
        # Animate
        self.play(Create(circle))
        self.play(Write(text))
        self.wait(2)
'''
        self.text_editor.insert("0.0", default_code)


    def setup_settings_tab(self):
        """Setup the settings tab"""
        # Settings frame
        settings_frame = ctk.CTkFrame(self.settings_tab)
        settings_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Environment settings
        env_frame = ctk.CTkFrame(settings_frame)
        env_frame.pack(fill="x", padx=10, pady=10)
        
        env_title = ctk.CTkLabel(
            env_frame,
            text="Environment Settings",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        env_title.pack(pady=10)
        
        # Current environment display
        self.current_env_label = ctk.CTkLabel(
            env_frame,
            text=f"Current: {self.venv_manager.current_venv or 'None'}",
            font=ctk.CTkFont(size=12)
        )
        self.current_env_label.pack(pady=5)
        
        # Python path display
        self.python_path_label = ctk.CTkLabel(
            env_frame,
            text=f"Python: {self.venv_manager.python_path or 'None'}",
            font=ctk.CTkFont(size=10)
        )
        self.python_path_label.pack(pady=5)

    def setup_log_tab(self):
        """Setup the log tab"""
        # Log frame
        log_frame = ctk.CTkFrame(self.log_tab)
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Log controls
        log_controls = ctk.CTkFrame(log_frame)
        log_controls.pack(fill="x", padx=5, pady=5)
        
        clear_button = ctk.CTkButton(
            log_controls,
            text="Clear Logs",
            command=self.clear_logs,
            width=100
        )
        clear_button.pack(side="left", padx=5)
        
        refresh_button = ctk.CTkButton(
            log_controls,
            text="Refresh",
            command=self.refresh_logs,
            width=100
        )
        refresh_button.pack(side="left", padx=5)
        
        # Log display
        self.log_display = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Consolas", size=10)
        )
        self.log_display.pack(fill="both", expand=True, padx=5, pady=5)

        # Load log contents initially
        self.refresh_logs()

    def refresh_logs(self):
        """Load the application log file into the display."""
        try:
            with open(os.path.join(os.path.expanduser("~"), ".manim_studio", "manim_studio.log"), "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:  # File not found or read error
            content = f"Error reading log: {e}"
        self.log_display.delete("1.0", "end")
        self.log_display.insert("1.0", content)

    def clear_logs(self):
        """Clear the log file and the display."""
        try:
            log_path = os.path.join(os.path.expanduser("~"), ".manim_studio", "manim_studio.log")
            open(log_path, "w").close()
        except Exception as e:
            self.log_display.delete("1.0", "end")
            self.log_display.insert("1.0", f"Error clearing log: {e}")
            return
        self.log_display.delete("1.0", "end")
    def create_setup_tab(self):
        """Create setup tab content"""
        content = ctk.CTkScrollableFrame(self.step1)
        content.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Title
        ctk.CTkLabel(
            content,
            text="🚀 Getting Started with Manim Studio",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(0, 20))
        
        # Steps (installation focused)
        steps = [
            ("1. Automatic Environment Setup", """
✅ ManimStudio automatically detects your Python environment
✅ On first run, it will guide you through setting up a complete environment
✅ All essential packages (manim, numpy, matplotlib, jedi) are installed automatically
✅ No manual configuration required - everything works out of the box
✅ Virtual environments are created and managed automatically
            """),
            ("2. Environment Management", """
✅ Click the 🔧 Environment Setup button to manage your Python environment
✅ Create isolated environments for different projects
✅ One-click installation of Python packages
✅ Automatic dependency management
✅ Export/import requirements.txt files
✅ Seamless switching between environments
            """)
        ]
        
        for title, desc in steps:
            step_frame = ctk.CTkFrame(content)
            step_frame.pack(fill="x", pady=10)
            
            ctk.CTkLabel(
                step_frame,
                text=title,
                font=ctk.CTkFont(size=16, weight="bold")
            ).pack(anchor="w", padx=15, pady=(10, 5))
            
            ctk.CTkLabel(
                step_frame,
                text=desc.strip(),
                font=ctk.CTkFont(size=12),
                justify="left"
            ).pack(anchor="w", padx=15, pady=(0, 10))
            
    def create_first_animation_tab(self):
        """Create first animation tab content"""
        content = ctk.CTkScrollableFrame(self.step2)
        content.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Title
        ctk.CTkLabel(
            content,
            text="🎬 Creating Your First Animation",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(0, 20))
        
        # Code example
        code_frame = ctk.CTkFrame(content)
        code_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            code_frame,
            text="Basic Scene Example:",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        example_code = '''from manim import *

class HelloWorld(Scene):
    def construct(self):
        # Create text
        text = Text("Hello, World!")
        text.set_color(BLUE)
        
        # Animate text appearance
        self.play(Write(text))
        self.wait(1)
        
        # Transform text
        new_text = Text("Welcome to Manim!")
        new_text.set_color(GREEN)
        
        self.play(Transform(text, new_text))
        self.wait(2)'''
        
        code_text = ctk.CTkTextbox(code_frame, height=250)
        code_text.pack(fill="x", padx=15, pady=(0, 10))
        code_text.insert("1.0", example_code)
        
        # Instructions
        instructions = [
            "1. Replace the default code with this example",
            "2. Click 'Quick Preview' to see the animation",
            "3. Experiment with different colors and text",
            "4. Try adding more objects and animations",
            "5. Use IntelliSense (Ctrl+Space) for code suggestions"
        ]
        
        for instruction in instructions:
            ctk.CTkLabel(
                content,
                text=instruction,
                font=ctk.CTkFont(size=12),
                anchor="w"
            ).pack(fill="x", padx=15, pady=2)
            
    def create_advanced_tab(self):
        """Create advanced features tab content"""
        content = ctk.CTkScrollableFrame(self.step3)
        content.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Title
        ctk.CTkLabel(
            content,
            text="⚡ Advanced Features",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(0, 20))
        
        # Features
        features = [
            ("Automatic Environment Management", """
🔧 Detects and uses existing Python environments automatically
🔧 Creates virtual environments with one click
🔧 Installs all required packages automatically
🔧 Manages dependencies and package versions
🔧 Seamless switching between environments
            """),
            ("Professional Code Editor", """
💡 Real-time autocompletion using Jedi
💡 Function signatures and documentation
💡 Advanced syntax highlighting with VSCode colors
💡 Smart indentation and bracket matching
💡 Find and replace with regex support
💡 Line manipulation (duplicate, move, comment)
💡 Customizable font sizes and themes
            """),
            ("Advanced Rendering System", """
🎬 Real-time video preview with playback controls
🎬 Multiple output formats (MP4, GIF, WebM, PNG)
🎬 Quality presets from 480p to 8K
🎬 Professional UI with progress tracking
🎬 Multi-threaded rendering system
🎬 Audio synchronization support
🎬 Frame-by-frame playback controls
            """),
            ("Professional UI Features", """
🎨 Multiple built-in themes (Dark+, Light+, Monokai, Solarized)
🎨 Professional VSCode-style interface
🎨 Visual asset manager for images and audio
🎨 Drag-and-drop asset integration
🎨 Professional status bar and tooltips
🎨 Contextual menus and shortcuts
            """),
            ("Keyboard Shortcuts", """
⌨️ Ctrl+S: Save file
⌨️ F5: Quick preview
⌨️ F7: Render animation
⌨️ Ctrl+Space: Trigger autocompletion
⌨️ Ctrl+F: Find and replace
⌨️ Ctrl+/: Toggle comments
⌨️ Alt+Up/Down: Move lines
⌨️ F11: Toggle fullscreen
⌨️ Ctrl++/-: Adjust font size
⌨️ Ctrl+D: Duplicate line
            """)
        ]
        
        for title, desc in features:
            feature_frame = ctk.CTkFrame(content)
            feature_frame.pack(fill="x", pady=10)
            
            ctk.CTkLabel(
                feature_frame,
                text=title,
                font=ctk.CTkFont(size=16, weight="bold")
            ).pack(anchor="w", padx=15, pady=(10, 5))
            
            ctk.CTkLabel(
                feature_frame,
                text=desc.strip(),
                font=ctk.CTkFont(size=12),
                justify="left"
            ).pack(anchor="w", padx=15, pady=(0, 10))
            
    def previous_step(self):
        """Go to previous step"""
        current = self.notebook.get()
        if current == "2. First Animation":
            self.notebook.set("1. Setup")
        elif current == "3. Advanced Features":
            self.notebook.set("2. First Animation")
            
    def next_step(self):
        """Go to next step"""
        current = self.notebook.get()
        if current == "1. Setup":
            self.notebook.set("2. First Animation")
        elif current == "2. First Animation":
            self.notebook.set("3. Advanced Features")

class SimpleEnvironmentDialog(ctk.CTkToplevel):
    """Emergency fallback dialog if other dialogs fail"""
    
    def __init__(self, parent, venv_manager):
        super().__init__(parent)
        
        self.venv_manager = venv_manager
        self.title("Environment Setup")

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(500, screen_w - 100)
        height = min(300, screen_h - 100)
        self.geometry(f"{width}x{height}")
        self.minsize(400, 250)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        
        # Center the dialog
        self.geometry("+%d+%d" % (
            parent.winfo_rootx() + 100,
            parent.winfo_rooty() + 100
        ))
        
        # Main frame
        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        ctk.CTkLabel(
            frame,
            text="Manim Studio Environment Setup",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(0, 20))
        
        # Info text
        ctk.CTkLabel(
            frame,
            text="This will set up a new Python environment for Manim animations. Continue?",
            wraplength=400
        ).pack(pady=(0, 20))
        
        # Buttons
        button_frame = ctk.CTkFrame(frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        
        ctk.CTkButton(
            button_frame,
            text="Create Environment",
            command=self.create_environment
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self.destroy
        ).pack(side="right", padx=5)
        
    def create_environment(self):
        """Create environment and close"""
        try:
            success = self.venv_manager.create_default_environment()
            if success:
                from tkinter import messagebox
                messagebox.showinfo(
                    "Success", 
                    "Environment created successfully!"
                )
                self.destroy()
            else:
                from tkinter import messagebox
                messagebox.showerror(
                    "Error", 
                    "Failed to create environment. Please try again."
                )
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror(
                "Error", 
                f"Error creating environment: {str(e)}"
            )



def setup_logging(app_dir=None):
    """Setup logging configuration"""
    if app_dir is None:
        app_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")
        os.makedirs(app_dir, exist_ok=True)
    
    log_file = os.path.join(app_dir, "manim_studio.log")
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ],
        force=True  # Override any existing configuration
    )
    
    logger = logging.getLogger(__name__)
    return logger

def main():
    """Main application entry point"""
    # NOTE: Do NOT import sys here - it's already imported at module level
    # Any import of sys inside this function will cause UnboundLocalError

    logger = None  # Initialize logger variable to avoid UnboundLocalError

    debug_mode = "--debug" in sys.argv

    # Initialize encoding early to avoid Unicode issues
    try:
        import startup
        startup.initialize_encoding()
    except Exception:
        pass
    
    try:
        # Hide console window on Windows for packaged executable
        if sys.platform == "win32" and hasattr(sys, 'frozen'):
            try:
                import ctypes
                from ctypes import wintypes
                
                kernel32 = ctypes.windll.kernel32
                user32 = ctypes.windll.user32
                
                console_window = kernel32.GetConsoleWindow()
                if console_window:
                    # SW_HIDE = 0
                    user32.ShowWindow(console_window, 0)
                        
            except Exception:
                pass

        # Ensure working directory is the application directory
        os.chdir(BASE_DIR)

        # Early load of fixes module to handle runtime issues
        try:
            import fixes
            if hasattr(fixes, "apply_fixes"):
                fixes.apply_fixes()
            elif hasattr(fixes, "apply_all_fixes"):
                fixes.apply_all_fixes()
        except (ImportError, AttributeError):
            pass

        # Set up application directories
        if getattr(sys, 'frozen', False):
            # Running as executable
            app_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")
        else:
            # Running as script
            app_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")

        os.makedirs(app_dir, exist_ok=True)

        # Simple single instance check
        lock_file = os.path.join(app_dir, "manim_studio.lock")
        try:
            if os.path.exists(lock_file):
                try:
                    with open(lock_file, "r") as f:
                        pid = int(f.read().strip())
                    # Simple check - if we can read the PID, assume another instance is running
                    print("Another instance may be running. Continuing anyway...")
                except:
                    # Remove invalid lock file
                    try:
                        os.remove(lock_file)
                    except:
                        pass
            
            # Create new lock file
            with open(lock_file, "w") as f:
                f.write(str(os.getpid()))
                
            # Cleanup function
            import atexit
            def cleanup_lock():
                try:
                    os.remove(lock_file)
                except:
                    pass
            atexit.register(cleanup_lock)
            
        except Exception:
            # If lock file operations fail, continue anyway
            pass
        
        # Set up logging - MOVED EARLIER to ensure logger is available
        log_file = os.path.join(app_dir, "manim_studio.log")
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        logger = logging.getLogger(__name__)  # Now logger is properly defined
        
        # Log startup information
        logger.info("=== ManimStudio Starting ===")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Platform: {sys.platform}")
        logger.info(f"Frozen: {hasattr(sys, 'frozen')}")
        logger.info(f"Base directory: {BASE_DIR}")
        logger.info(f"App directory: {app_dir}")

        # Check for Jedi availability
        if not JEDI_AVAILABLE:
            logger.warning("Jedi not available. IntelliSense features will be limited.")
            print("Warning: Jedi not available. IntelliSense features will be limited.")
            print("Install Jedi with: pip install jedi")

        # Check LaTeX availability and pass result to UI
        logger.info("Checking LaTeX installation...")
        latex_path = check_latex_installation()
        if latex_path:
            logger.info(f"LaTeX found at: {latex_path}")
        else:
            logger.warning("LaTeX not found")

        # Create and run application
        logger.info("Creating main application...")
        app = ManimStudioApp(latex_path=latex_path, debug=debug_mode)
        
        # Check environment and show setup if needed
        logger.info("Checking environment status...")
        if not app.venv_manager.is_environment_ready():
            logger.info("Environment not ready - showing setup dialog")
            app.root.withdraw()
            try:
                # Show environment setup dialog directly
                dialog = EnvironmentSetupDialog(app.root, app.venv_manager)
                app.root.wait_window(dialog)
                
                # Check if setup was completed
                if not app.venv_manager.is_environment_ready():
                    logger.error("Environment setup incomplete after dialog")
                    try:
                        from tkinter import messagebox
                        messagebox.showwarning(
                            "Setup Incomplete", 
                            "Environment setup was not completed.\n"
                            "ManimStudio requires a working environment to function.\n\n"
                            "Please try again or run with --debug flag."
                        )
                    except:
                        pass
                    return
                    
                logger.info("Environment setup completed successfully")
                
            except Exception as e:
                logger.error(f"Error in environment setup: {e}")
                try:
                    from tkinter import messagebox
                    messagebox.showerror(
                        "Setup Error", 
                        f"Error during environment setup: {e}\n\n"
                        "Please try again or check the log file."
                    )
                except:
                    pass
                return
        else:
            logger.info("Environment ready - proceeding to main application")

        logger.info("Performing final pre-launch checks...")
        
        # FIXED: Final verification that environment is working (REMOVED PROBLEMATIC IMPORT TEST)
        try:
            # REPLACED: Quick test that manim package exists (safe mode) - NO MORE 3221225477 ERROR
            manim_available = app.venv_manager.check_manim_availability()
            if manim_available:
                logger.info("✅ Manim package found")
            else:
                logger.warning("⚠️ Manim package not found")
        except Exception as e:
            logger.warning(f"⚠️ Could not verify manim package: {e}")

        logger.info("Starting application main loop...")
        
        # Show window and start main loop
        try:
            # Ensure window is visible
            if app.root and app.root.winfo_exists():
                app.root.deiconify()
                app.root.update()
                app.root.lift()
                app.root.focus_force()
                logger.info("Window made visible")
            
            # Start the main loop
            app.run()
            
        except Exception as e:
            # Handle UI errors gracefully
            error_msg = str(e)
            if "application has been destroyed" in error_msg or "invalid command name" in error_msg:
                logger.info("Application closed by user")
            else:
                logger.error(f"UI error: {e}")
                import traceback
                logger.error(f"UI Traceback: {traceback.format_exc()}")
        
    except Exception as e:
        # Handle startup errors
        error_msg = f"Startup error: {e}"
        
        if logger:
            logger.error(error_msg)
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        else:
            print(error_msg)
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            
        try:
            from tkinter import messagebox
            messagebox.showerror("Startup Error", f"Failed to start application: {e}")
        except:
            print(f"Failed to start application: {e}")
    
    finally:
        # Cleanup logging handlers to prevent issues on restart
        if logger:
            try:
                for handler in logger.handlers[:]:
                    handler.close()
                    logger.removeHandler(handler)
            except:
                pass

if __name__ == "__main__":
    main()
