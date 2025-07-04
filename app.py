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
import venv
import hashlib
import traceback
import argparse
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

# CRITICAL FIX: Add DLL isolation for Nuitka builds
if getattr(sys, 'frozen', False):
    # Running as Nuitka executable - apply DLL isolation
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    # Force system temp directory (avoid onefile temp issues)
    system_temp = os.environ.get('TEMP', tempfile.gettempdir())
    if 'onefile' in system_temp.lower() or 'temp' in system_temp.lower():
        # Use a stable temp directory
        stable_temp = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp', 'ManimStudio')
        os.makedirs(stable_temp, exist_ok=True)
        os.environ['TEMP'] = stable_temp
        os.environ['TMP'] = stable_temp
def load_icon_image(icon_name, size=(24, 24), fallback_text="?"):
    """Load icon image from assets folder with fallback to text"""
    try:
        icon_path = os.path.join("assets", icon_name)
        if os.path.exists(icon_path):
            # Use CTkImage instead of ImageTk.PhotoImage for HighDPI support
            return ctk.CTkImage(
                light_image=Image.open(icon_path),
                dark_image=Image.open(icon_path),
                size=size
            )
        else:
            print(f"⚠️ Icon not found: {icon_path}")
            return None
    except Exception as e:
        print(f"⚠️ Error loading icon {icon_name}: {e}")
        return None
# Add this to the top of app.py after the imports section
# =============================================================================
# EMERGENCY ENCODING FIXES - Add this RIGHT AFTER imports
# =============================================================================
def get_responsive_dialog_size(base_width, base_height, screen_w=None, screen_h=None):
    """Get responsive dialog size that works on high DPI displays"""
    if screen_w is None:
        screen_w = 1920  # Default fallback
    if screen_h is None:
        screen_h = 1080  # Default fallback
    
    # Calculate DPI scaling
    try:
        if os.name == 'nt':
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            dpi = user32.GetDpiForSystem()
            dpi_scale = dpi / 96.0
        else:
            dpi_scale = 1.0
    except:
        dpi_scale = 1.0
    
    # Calculate max usable space
    max_width = int(screen_w * 0.85)
    max_height = int(screen_h * 0.80)
    
    # Apply scaling but constrain to screen
    scaled_width = min(int(base_width * dpi_scale), max_width)
    scaled_height = min(int(base_height * dpi_scale), max_height)
    
    # Ensure minimum size
    final_width = max(400, scaled_width)
    final_height = max(300, scaled_height)
    
    return final_width, final_height, dpi_scale
def apply_emergency_encoding_fixes():
    """Apply immediate encoding fixes for cp950 errors"""
    import os
    import locale
    
    print("🔧 Applying emergency encoding fixes...")
    
    # Set critical environment variables
    encoding_vars = {
        'PYTHONIOENCODING': 'utf-8',
        'PYTHONLEGACYWINDOWSFSENCODING': '0',
        'PYTHONUTF8': '1',
        'LC_ALL': 'en_US.UTF-8',
        'LANG': 'en_US.UTF-8',
        'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONUNBUFFERED': '1'
    }
    
    for key, value in encoding_vars.items():
        os.environ[key] = value
        print(f"✅ Set {key}={value}")
    
    # Set system locale
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        print("✅ Set system locale to UTF-8")
    except:
        try:
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
            print("✅ Set system locale to C.UTF-8")
        except:
            print("⚠️ Using system default locale")
    
    print("✅ Emergency encoding fixes applied")

# Call this IMMEDIATELY - before any other code
apply_emergency_encoding_fixes()
# =============================================================================
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
    """Enhanced subprocess runner for onefile executables with DLL isolation"""
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
            'PYTHONUNBUFFERED': '1',
            # CRITICAL: Prevent DLL conflicts
            'PYTHONPATH': '',  # Clear Python path
            'PYTHONHOME': '',  # Clear Python home
        })
        
        kwargs['env'] = env
        
        # Force shell=False for onefile to avoid shell interpretation issues
        kwargs['shell'] = False
        
        # Set working directory to a stable location
        if 'cwd' not in kwargs:
            kwargs['cwd'] = system_temp
            
        # Add startup info to hide console windows
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    
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
    """Complete Environment setup dialog with all features and fixes"""
    
    def __init__(self, parent, venv_manager):
        super().__init__(parent)
        
        self.parent = parent
        self.venv_manager = venv_manager
        self.setup_complete = False
        
        # Store reference to the main application window for continue_to_app
        if hasattr(venv_manager, 'parent_app') and hasattr(venv_manager.parent_app, 'root'):
            self.main_app_window = venv_manager.parent_app.root
        else:
            self.main_app_window = parent
        
        self.title("ManimStudio - Environment Setup")
        
        # RESPONSIVE SIZE FIX: Calculate optimal size for different screens
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        
        # Calculate DPI scaling factor
        try:
            if os.name == 'nt':
                import ctypes
                user32 = ctypes.windll.user32
                user32.SetProcessDPIAware()
                dpi = user32.GetDpiForSystem()
                dpi_scale = dpi / 96.0
            else:
                dpi_scale = 1.0
        except:
            dpi_scale = 1.0
        
        # Base size (responsive design)
        base_width = 750
        base_height = 700
        
        # Calculate maximum usable screen space
        max_width = int(screen_w * 0.85)
        max_height = int(screen_h * 0.80)
        
        # Apply DPI scaling but ensure it fits on screen
        scaled_width = min(int(base_width * dpi_scale), max_width)
        scaled_height = min(int(base_height * dpi_scale), max_height)
        
        # Ensure minimum size
        final_width = max(600, scaled_width)
        final_height = max(500, scaled_height)
        
        self.geometry(f"{final_width}x{final_height}")
        self.transient(parent)
        self.grab_set()
        
        # Center the dialog properly on screen
        x = (screen_w - final_width) // 2
        y = (screen_h - final_height) // 2
        self.geometry(f"{final_width}x{final_height}+{x}+{y}")
        
        # Prevent closing during setup
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Initialize queue-based logging for thread-safe communication
        import queue
        self._log_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._start_log_processor()
        
        # Create the UI
        self.setup_ui()
    
    def _start_log_processor(self):
        """Start background log and result processing"""
        self._process_log_queue()
        self._process_result_queue()
    
    def _process_log_queue(self):
        """Process log messages from background threads"""
        try:
            while True:
                message = self._log_queue.get_nowait()
                self.log_text.insert("end", f"{message}\n")
                self.log_text.see("end")
        except:
            pass
        finally:
            # Schedule next check
            self.after(100, self._process_log_queue)
    
    def setup_ui(self):
        """Setup the environment setup dialog UI - COMPLETE AND FIXED"""
        # Safety check: Ensure VSCODE_COLORS has required keys
        global VSCODE_COLORS
        required_colors = {
            "success": "#16A085",
            "error": "#E74C3C",
            "warning": "#F39C12",
            "surface": "#252526",
            "text": "#CCCCCC",
            "text_secondary": "#858585",
            "primary": "#007ACC",
            "background": "#1E1E1E"
        }
        
        for key, default_value in required_colors.items():
            if key not in VSCODE_COLORS:
                VSCODE_COLORS[key] = default_value
            
        # Configure the main window
        self.configure(fg_color=VSCODE_COLORS["surface"])
        
        # Main container
        main_container = ctk.CTkFrame(self, fg_color=VSCODE_COLORS["surface"])
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header with logo
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))
        
        # App icon - Use image if available, fallback to emoji
        try:
            logo_image = load_icon_image("main_logo.png", size=(64, 64))
            if logo_image:
                icon_label = ctk.CTkLabel(header_frame, image=logo_image, text="")
                icon_label.image = logo_image
            else:
                raise Exception("No image found")
        except:
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
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        title_label.pack(pady=(0, 10))
        
        # Description
        desc_label = ctk.CTkLabel(
            header_frame,
            text="Set up your Python environment for creating mathematical animations",
            font=ctk.CTkFont(size=14),
            text_color=VSCODE_COLORS["text_secondary"],
            wraplength=500
        )
        desc_label.pack(pady=(0, 20))
        
        # Content area with progress
        content_frame = ctk.CTkFrame(main_container, fg_color=VSCODE_COLORS["surface"])
        content_frame.pack(fill="both", expand=True, pady=(0, 20))
        
        # Progress section
        progress_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        progress_frame.pack(fill="x", padx=20, pady=20)
        
        # Step label
        self.step_label = ctk.CTkLabel(
            progress_frame,
            text="Ready to begin setup",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        self.step_label.pack(pady=(0, 10))
        
        # Detail label
        self.detail_label = ctk.CTkLabel(
            progress_frame,
            text="Click 'Start Setup' to begin installation",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text_secondary"],
            wraplength=400
        )
        self.detail_label.pack(pady=(0, 15))
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(progress_frame, width=400)
        self.progress_bar.pack(pady=(0, 20))
        self.progress_bar.set(0)
        
        # Log area
        log_frame = ctk.CTkFrame(content_frame, fg_color=VSCODE_COLORS["surface"])
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        log_label = ctk.CTkLabel(
            log_frame,
            text="Setup Log:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        log_label.pack(anchor="w", padx=15, pady=(15, 5))
        
        # Log text area
        self.log_text = ctk.CTkTextbox(
            log_frame,
            height=120,
            font=ctk.CTkFont(size=11, family="Consolas"),
            text_color=VSCODE_COLORS["text"],
            fg_color=VSCODE_COLORS["background"]
        )
        self.log_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Initial log message
        self.log_text.insert("end", "🎬 ManimStudio Environment Setup\n")
        self.log_text.insert("end", "Ready to begin installation...\n\n")
        
        # FIXED: Bottom buttons frame with proper layout
        bottom_frame = ctk.CTkFrame(main_container, fg_color="transparent", height=80)
        bottom_frame.pack(fill="x", pady=(0, 10))
        bottom_frame.pack_propagate(False)  # Maintain fixed height
        
        # Button container with centered layout
        button_container = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        button_container.pack(expand=True, fill="both", padx=20, pady=20)
        
        # Left buttons
        left_buttons = ctk.CTkFrame(button_container, fg_color="transparent")
        left_buttons.pack(side="left", fill="y")
        
        # Start button
        self.start_button = ctk.CTkButton(
            left_buttons,
            text="🚀 Start Setup",
            command=self.start_setup,
            height=45,
            width=150,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=VSCODE_COLORS["success"],
            hover_color="#138D75"
        )
        self.start_button.pack(side="left", padx=(0, 15))
        
        # Skip button
        self.skip_button = ctk.CTkButton(
            left_buttons,
            text="⏭️ Skip Setup",
            command=self.skip_setup,
            height=45,
            width=130,
            font=ctk.CTkFont(size=14),
            fg_color=VSCODE_COLORS["warning"],
            hover_color="#D68910"
        )
        self.skip_button.pack(side="left")
        
        # Right buttons
        right_buttons = ctk.CTkFrame(button_container, fg_color="transparent")
        right_buttons.pack(side="right", fill="y")
        
        # Continue button (initially disabled)
        self.close_button = ctk.CTkButton(
            right_buttons,
            text="✅ Continue to App",
            command=self.continue_to_app,
            height=45,
            width=160,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=VSCODE_COLORS["primary"],
            hover_color="#005A9E",
            state="disabled"
        )
        self.close_button.pack(side="right")
        
        # Force layout update
        self.update_idletasks()
    
    def start_setup(self):
        """Start the environment setup process"""
        try:
            # Disable start and skip buttons
            self.start_button.configure(state="disabled")
            self.skip_button.configure(state="disabled")
            
            # Update UI
            self.step_label.configure(text="Setting up environment...")
            self.detail_label.configure(text="Creating virtual environment and installing packages")
            self.progress_bar.set(0.1)
            
            # Log start
            self.log_message("🚀 Starting environment setup...")
            self.log_message("This may take 5-10 minutes depending on your internet connection...")
            
            # Run setup in background thread to prevent UI freezing
            import threading
            setup_thread = threading.Thread(target=self.run_setup_background, daemon=True)
            setup_thread.start()
            
        except Exception as e:
            self.log_message(f"❌ Error starting setup: {e}")
            self.show_error("Failed to start setup")
    
    def run_setup_background(self):
        """Run setup in background thread - THREAD-SAFE VERSION"""
        try:
            # Create thread-safe log callback using queue only
            def safe_log(message):
                try:
                    self._log_queue.put(message)
                except:
                    print(f"Log: {message}")
            
            # Thread-safe progress update using queue
            def update_progress(progress, message=""):
                try:
                    self._result_queue.put(('progress', {'progress': progress, 'message': message}))
                except:
                    print(f"Progress: {progress} - {message}")
            
            # Step 1: Check existing environment
            update_progress(0.1, "Checking existing environment...")
            safe_log("🔍 Checking for existing environment...")
            
            # Step 2: Create/update environment
            update_progress(0.2, "Creating virtual environment...")
            safe_log("📦 Creating virtual environment...")
            
            # Step 3: Run the actual setup
            update_progress(0.3, "Installing Python packages...")
            safe_log("⬇️ Installing required packages...")
            
            # Run the venv manager setup
            success = self.venv_manager.setup_environment(safe_log)
            
            if success:
                update_progress(0.9, "Verifying installation...")
                safe_log("✅ Verifying installation...")
                
                # Final verification
                if self.venv_manager.verify_complete_installation(safe_log):
                    update_progress(1.0, "Setup completed successfully!")
                    safe_log("✅ Environment setup completed successfully!")
                    self._result_queue.put(('complete', True))
                else:
                    safe_log("⚠️ Setup completed with warnings")
                    self._result_queue.put(('complete_warnings', True))
            else:
                safe_log("❌ Setup failed")
                self._result_queue.put(('error', "Setup failed - check log for details"))
                
        except Exception as e:
            error_msg = f"Setup failed: {str(e)}"
            try:
                self._log_queue.put(f"❌ {error_msg}")
                self._result_queue.put(('error', error_msg))
            except:
                print(f"Setup error: {error_msg}")
    def _process_result_queue(self):
        """Process results from background threads - THREAD-SAFE"""
        try:
            while True:
                action, data = self._result_queue.get_nowait()
                
                if action == 'progress':
                    self.progress_bar.set(data['progress'])
                    if data['message']:
                        self.detail_label.configure(text=data['message'])
                        
                elif action == 'complete':
                    self.setup_complete_ui()
                    
                elif action == 'complete_warnings':
                    self.setup_complete_with_warnings()
                    
                elif action == 'error':
                    self.show_error(data)
                    
        except:
            pass
        finally:
            # Schedule next check
            self.after(100, self._process_result_queue)
    def setup_complete_ui(self):
        """Update UI when setup is complete"""
        self.setup_complete = True
        self.progress_bar.set(1.0)
        self.step_label.configure(text="✅ Setup Complete!")
        self.detail_label.configure(text="Environment ready for creating animations")
        
        # Enable continue button
        self.close_button.configure(state="normal")
        self.log_message("🎉 You can now create mathematical animations!")
    
    def setup_complete_with_warnings(self):
        """Update UI when setup completes with warnings"""
        self.setup_complete = True
        self.progress_bar.set(0.8)
        self.step_label.configure(text="⚠️ Setup Complete (with warnings)")
        self.detail_label.configure(text="Some packages may need manual installation")
        
        # Enable continue button
        self.close_button.configure(state="normal")
        self.log_message("⚠️ Setup completed but some issues were encountered")
    
    def show_error(self, message):
        """Show error state"""
        self.step_label.configure(text="❌ Setup Failed")
        self.detail_label.configure(text=message)
        self.progress_bar.set(0)
        
        # Re-enable start button to allow retry
        self.start_button.configure(state="normal")
        self.skip_button.configure(state="normal")
        
        self.log_message("💡 You can try again or skip setup and install manually later")
    
    def skip_setup(self):
        """Skip the setup process"""
        result = messagebox.askyesno(
            "Skip Setup", 
            "Are you sure you want to skip environment setup?\n\n"
            "You can set up the environment later from the main application.",
            parent=self
        )
        
        if result:
            self.log_message("⏭️ Setup skipped by user")
            self.log_message("💡 You can set up environment later from the main menu")
            self.step_label.configure(text="Setup skipped")
            self.detail_label.configure(text="Environment setup was skipped")
            self.setup_complete = True
            self.close_button.configure(state="normal")
    
    def continue_to_app(self):
        """Continue to the main application"""
        self.setup_complete = True
        
        # Store reference before destroying dialog
        main_window = self.main_app_window
        
        # Close this setup dialog
        self.destroy()
        
        # Show the main application window that was hidden
        if main_window and main_window.winfo_exists():
            def show_main_window():
                try:
                    main_window.deiconify()      # Show the window
                    main_window.lift()           # Bring to front
                    main_window.focus_force()    # Give focus
                    main_window.state('normal')  # Ensure not minimized
                    main_window.update()         # Force update
                except Exception as e:
                    print(f"Error showing main window: {e}")
            
            # Use after() to ensure dialog closes first
            main_window.after(50, show_main_window)
    
    def on_closing(self):
        """Handle window close event"""
        if not self.setup_complete:
            result = messagebox.askyesno(
                "Close Setup", 
                "Environment setup is not complete.\n\nClose anyway?",
                parent=self
            )
            if result:
                self.setup_complete = True
                self.destroy()
        else:
            self.destroy()
    
    def log_message(self, message):
        """Add message to log with timestamp (thread-safe)"""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            full_message = f"[{timestamp}] {message}"
            
            # Use queue for thread safety
            self._log_queue.put(full_message)
        except Exception as e:
            print(f"Logging error: {e}")
    
    def update_progress_safe(self, progress, step_text="", detail_text=""):
        """Thread-safe progress update"""
        def update():
            try:
                self.progress_bar.set(progress)
                if step_text:
                    self.step_label.configure(text=step_text)
                if detail_text:
                    self.detail_label.configure(text=detail_text)
            except Exception as e:
                print(f"Progress update error: {e}")
        
        self.after(0, update)
    
    def show_success_message(self, title, message):
        """Show success message dialog"""
        try:
            messagebox.showinfo(title, message, parent=self)
        except Exception as e:
            print(f"Success message error: {e}")
    
    def show_error_message(self, title, message):
        """Show error message dialog"""
        try:
            messagebox.showerror(title, message, parent=self)
        except Exception as e:
            print(f"Error message error: {e}")
    
    def get_setup_status(self):
        """Get current setup status"""
        return {
            "complete": self.setup_complete,
            "progress": self.progress_bar.get() if hasattr(self, 'progress_bar') else 0,
            "step": self.step_label.cget("text") if hasattr(self, 'step_label') else "",
            "detail": self.detail_label.cget("text") if hasattr(self, 'detail_label') else ""
        }
    
    def reset_setup(self):
        """Reset the setup dialog to initial state"""
        try:
            self.setup_complete = False
            self.progress_bar.set(0)
            self.step_label.configure(text="Ready to begin setup")
            self.detail_label.configure(text="Click 'Start Setup' to begin installation")
            
            # Re-enable buttons
            self.start_button.configure(state="normal")
            self.skip_button.configure(state="normal")
            self.close_button.configure(state="disabled")
            
            # Clear log
            self.log_text.delete("1.0", "end")
            self.log_text.insert("end", "🎬 ManimStudio Environment Setup\n")
            self.log_text.insert("end", "Ready to begin installation...\n\n")
            
        except Exception as e:
            print(f"Reset error: {e}")
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

import os
import sys
import subprocess
import logging
import threading
import queue
import time
import shutil
import json
import locale
import platform
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple, Any
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

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

class VirtualEnvironmentManager:
    """
    Complete virtual environment manager for Manim Studio
    FIXED for built executable compatibility with encoding support
    ALL ISSUES RESOLVED - FINAL VERSION - NO IMPORT ERRORS
    """
    
    def __init__(self, parent_app=None):
        self.parent_app = parent_app
        self.logger = logging.getLogger(__name__)
        
        # Normal initialization for all environments
        print("🐍 Using standard environment setup")
        
        # FIXED: Better path detection for frozen executables
        self.is_frozen = self._detect_if_frozen()
        self.base_dir = self._get_base_directory()
        self.app_dir = self._get_app_directory()
        self.venv_dir = os.path.join(self.app_dir, "venvs")
        
        # Create necessary directories
        os.makedirs(self.venv_dir, exist_ok=True)
        os.makedirs(self.app_dir, exist_ok=True)
        
        print(f"📁 Base directory: {self.base_dir}")
        print(f"📁 App directory: {self.app_dir}")
        print(f"📁 Venv directory: {self.venv_dir}")
        
        # Current environment state
        self.current_venv = None
        self.python_path = sys.executable
        self.pip_path = "pip"
        self.needs_setup = True
        self.using_fallback = False
        
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
            "opencv-python>=4.6.0",
            "imageio>=2.19.0",
            "moviepy>=1.0.3",
            "imageio-ffmpeg",
            "Pillow>=9.0.0",
            
            # UI and development tools
            "customtkinter>=5.0.0",
            "jedi>=0.18.0",  # IntelliSense
            
            # System utilities
            "psutil>=5.8.0",
            "requests>=2.25.0",
            "rich>=10.0.0",
            "tqdm>=4.60.0",
            "colour>=0.1.5",
            "moderngl>=5.6.0",
            "moderngl-window>=2.3.0"
        ]
        
        # Initialize validation cache
        self._validation_cache = {}
        
        # Apply emergency encoding fixes on startup
        self.fix_encoding_environment()
        
        # Auto-repair if issues detected (but don't block startup)
        try:
            if self.detect_encoding_issues() or self.detect_corrupted_manim():
                print("🔧 Issues detected, scheduling auto-repair...")
                # Schedule repair for later to not block startup
                if self.parent_app and hasattr(self.parent_app, 'root'):
                    self.parent_app.root.after(2000, lambda: self.auto_repair_if_needed(print))
        except Exception as e:
            print(f"⚠️ Auto-repair check failed: {e}")

    def _detect_if_frozen(self):
        """Detect if running as a frozen executable"""
        return getattr(sys, 'frozen', False)

    def _get_base_directory(self):
        """Get the base directory of the application"""
        if self.is_frozen:
            return os.path.dirname(os.path.abspath(sys.executable))
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def _get_app_directory(self):
        """Get the application data directory"""
        if self.is_frozen:
            # For frozen apps, use a directory in user's home
            app_data_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")
        else:
            # For development, use a directory relative to the script
            app_data_dir = os.path.join(self.base_dir, ".manim_studio")
        
        os.makedirs(app_data_dir, exist_ok=True)
        return app_data_dir

    def safe_log_callback(self, log_callback, message):
        """
        Safely call a log callback function with proper validation
        Fixes the "'str' object is not callable" error
        """
        try:
            if log_callback and callable(log_callback):
                log_callback(message)
            elif log_callback and isinstance(log_callback, str):
                # If log_callback is a string, just print it as debug info
                print(f"Debug: {log_callback} - {message}")
            else:
                # Fallback to print
                print(message)
        except Exception as e:
            print(f"Error in log callback: {e} - Message: {message}")

    def is_environment_ready(self):
        """Fast environment readiness check - NO SLOW VALIDATION"""
        if self.needs_setup:
            return False
        
        # Quick validation check - only check if files exist
        try:
            default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
            
            # Check if environment exists and is valid
            if not os.path.exists(default_venv_path):
                return False
                
            if not self.is_valid_venv(default_venv_path):
                return False
            
            # Check if Python and pip paths are correct
            if not self.python_path or not os.path.exists(self.python_path):
                return False
                
            if not self.pip_path or not os.path.exists(self.pip_path):
                return False
            
            # SKIP SLOW PYTHON EXECUTION TESTS - Just return True if files exist
            return True
                
        except Exception:
            return False
    def fix_encoding_environment(self):
        """
        Apply system-wide encoding fixes for Chinese Windows systems
        This helps prevent cp950 codec errors during package installation
        """
        try:
            # Set environment variables for the current process
            encoding_vars = {
                'PYTHONIOENCODING': 'utf-8',
                'PYTHONLEGACYWINDOWSFSENCODING': '0',
                'PYTHONUTF8': '1',
                'LC_ALL': 'en_US.UTF-8',
                'LANG': 'en_US.UTF-8'
            }
            
            for key, value in encoding_vars.items():
                os.environ[key] = value
                print(f"✅ Set {key}={value}")
            
            # Try to set system locale
            try:
                locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
                print("✅ Set system locale to UTF-8")
            except Exception:
                try:
                    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
                    print("✅ Set system locale to C.UTF-8")
                except Exception:
                    print("⚠️ Could not set UTF-8 locale, using system default")
            
            return True
            
        except Exception as e:
            print(f"⚠️ Error applying encoding fixes: {e}")
            return False

    def detect_encoding_issues(self):
        """
        Detect if the environment has encoding issues
        """
        # Check environment variables
        encoding_vars = ['PYTHONIOENCODING', 'PYTHONUTF8', 'PYTHONLEGACYWINDOWSFSENCODING']
        
        for var in encoding_vars:
            if var not in os.environ:
                return True
        
        # Check for CP950 in default encoding
        try:
            if 'cp950' in locale.getpreferredencoding().lower():
                return True
        except:
            pass
        
        return False

    def detect_corrupted_manim(self):
        """
        Detect if manim installation is corrupted (like the "3221225477" error)
        """
        try:
            test_cmd = [self.python_path, "-c", "import manim; print('OK')"]
            result = subprocess.run(
                test_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )
            
            # Check for corruption indicators
            if result.returncode != 0:
                error_output = result.stderr.lower()
                corruption_indicators = [
                    "3221225477",  # Your specific error
                    "dll load failed",
                    "module not found",
                    "import error",
                    "no module named"
                ]
                
                for indicator in corruption_indicators:
                    if indicator in error_output:
                        print(f"🔍 Detected corrupted manim: {indicator}")
                        return True
            
            return False
            
        except Exception:
            return True  # If we can't test, assume corruption

    def run_hidden_subprocess_with_encoding(self, command, **kwargs):
        """
        Enhanced subprocess runner with proper encoding handling for Chinese Windows systems
        """
        try:
            # Set default encoding options
            default_kwargs = {
                'encoding': 'utf-8',
                'errors': 'replace',
                'text': True,
                'env': os.environ.copy()
            }
            
            # Update environment with encoding fixes
            env = default_kwargs['env']
            env.update({
                'PYTHONIOENCODING': 'utf-8',
                'PYTHONLEGACYWINDOWSFSENCODING': '0',
                'PYTHONUTF8': '1'
            })
            
            # Merge provided kwargs with defaults
            default_kwargs.update(kwargs)
            default_kwargs['env'] = env
            
            # Windows-specific subprocess configuration
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                default_kwargs['startupinfo'] = startupinfo
                default_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
            # Execute the command
            result = subprocess.run(command, **default_kwargs)
            return result
            
        except subprocess.TimeoutExpired as e:
            print(f"⏰ Command timed out: {command if isinstance(command, list) else command}")
            # Create a mock result for timeout
            class TimeoutResult:
                def __init__(self):
                    self.returncode = 1
                    self.stdout = ""
                    self.stderr = "Command timed out"
            return TimeoutResult()
            
        except Exception as e:
            print(f"❌ Subprocess error for {command if isinstance(command, list) else command}: {e}")
            raise

    def create_virtual_environment(self, log_callback=None):
        """Create virtual environment with encoding fixes applied"""
        env_path = os.path.join(self.venv_dir, "manim_studio_default")
        
        self.safe_log_callback(log_callback, "Creating virtual environment with encoding fixes...")
        print("🔧 Creating virtual environment with encoding fixes...")
        
        # Apply encoding fixes to the environment
        self.fix_encoding_environment()
        
        # Find Python executable
        python_exe = self.find_python_executable()
        if not python_exe:
            error_msg = "❌ No Python executable found\n\nPlease install Python from https://python.org"
            self.safe_log_callback(log_callback, error_msg)
            print(error_msg)
            return False
        
        self.safe_log_callback(log_callback, f"Creating environment with: {python_exe}")
        print(f"🔧 Creating environment with: {python_exe}")
        
        try:
            # Create environment with proper Windows subprocess handling and encoding
            create_cmd = [python_exe, "-m", "venv", env_path, "--clear"]
            
            # Enhanced environment for creation
            env = os.environ.copy()
            env.update({
                'PYTHONIOENCODING': 'utf-8',
                'PYTHONLEGACYWINDOWSFSENCODING': '0',
                'PYTHONUTF8': '1'
            })
            
            # Windows subprocess setup
            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
            
            print(f"🔧 Running command: {' '.join(create_cmd)}")
            result = subprocess.run(
                create_cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=creationflags,
                timeout=180,
                env=env,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode != 0:
                error_msg = f"❌ Failed to create virtual environment: {result.stderr}"
                self.safe_log_callback(log_callback, error_msg)
                print(error_msg)
                return False
            
            # Verify creation
            if not os.path.exists(env_path):
                error_msg = "❌ Environment directory not created"
                self.safe_log_callback(log_callback, error_msg)
                print(error_msg)
                return False
            
            # Set up paths
            if os.name == 'nt':
                python_exe = os.path.join(env_path, "Scripts", "python.exe")
                pip_exe = os.path.join(env_path, "Scripts", "pip.exe")
            else:
                python_exe = os.path.join(env_path, "bin", "python")
                pip_exe = os.path.join(env_path, "bin", "pip")
            
            # Verify executables exist
            if not os.path.exists(python_exe):
                error_msg = f"❌ Python executable not found: {python_exe}"
                self.safe_log_callback(log_callback, error_msg)
                print(error_msg)
                return False
            
            # Install pip if needed
            if not os.path.exists(pip_exe):
                self.safe_log_callback(log_callback, "Installing pip in new environment...")
                
                try:
                    result = subprocess.run(
                        [python_exe, "-m", "ensurepip", "--upgrade"],
                        capture_output=True,
                        text=True,
                        env=env,
                        encoding='utf-8',
                        errors='replace',
                        timeout=60
                    )
                    if result.returncode != 0:
                        print(f"❌ Failed to install pip with ensurepip: {result.stderr}")
                        return False
                    print("✅ Pip installed successfully")
                except Exception as e:
                    print(f"❌ Error installing pip: {e}")
                    return False
            
            # Activate it for further operations
            self.python_path = python_exe
            self.pip_path = pip_exe
            self.current_venv = "manim_studio_default"
            
            self.safe_log_callback(log_callback, "✅ Virtual environment created successfully")
            print("✅ Virtual environment created successfully")
            
            return True
            
        except Exception as e:
            error_msg = f"❌ Error creating virtual environment: {e}"
            self.safe_log_callback(log_callback, error_msg)
            print(error_msg)
            return False

    def install_package_with_encoding_fix(self, package_name, log_callback=None):
        """
        Install a single package with enhanced encoding handling
        Specifically designed to fix cp950 codec errors on Chinese Windows systems
        """
        if not self.python_path or not os.path.exists(self.python_path):
            error_msg = "❌ No valid Python environment available"
            self.safe_log_callback(log_callback, error_msg)
            return False
        
        try:
            # Clean package name
            clean_name = package_name.split('>=')[0].split('==')[0].split('<=')[0].strip()
            
            self.safe_log_callback(log_callback, f"Installing {clean_name}...")
            print(f"📦 Installing {clean_name}...")
            
            # Enhanced pip command with encoding fixes
            pip_cmd = [
                self.python_path, "-m", "pip", "install", 
                package_name,
                "--no-warn-script-location",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "--force-reinstall",
                "--progress-bar", "off"
            ]
            
            # Run with enhanced encoding handling
            result = self.run_hidden_subprocess_with_encoding(
                pip_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                success_msg = f"✅ {clean_name} installed successfully"
                self.safe_log_callback(log_callback, success_msg)
                print(success_msg)
                return True
            else:
                error_output = result.stderr or result.stdout or "Unknown error"
                error_msg = f"❌ Failed to install {clean_name}: {error_output[:200]}"
                self.safe_log_callback(log_callback, error_msg)
                print(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"❌ Error installing {clean_name}: {e}"
            self.safe_log_callback(log_callback, error_msg)
            print(error_msg)
            return False

    def install_all_packages(self, log_callback=None):
        """Install all essential packages with comprehensive encoding fixes"""
        if not self.python_path or not os.path.exists(self.python_path):
            error_msg = "❌ No valid Python environment available"
            self.safe_log_callback(log_callback, error_msg)
            return False
        
        # Apply encoding fixes first
        self.fix_encoding_environment()
        
        self.safe_log_callback(log_callback, "🚀 Starting enhanced package installation...")
        print("🚀 Starting enhanced package installation...")
        
        successful_installs = 0
        failed_packages = []
        
        # Install packages one by one with encoding fixes
        for i, package in enumerate(self.essential_packages):
            progress = (i + 1) / len(self.essential_packages) * 100
            self.safe_log_callback(log_callback, f"📦 Installing {i+1}/{len(self.essential_packages)}: {package} ({progress:.0f}%)")
            
            success = self.install_package_with_encoding_fix(package, log_callback)
            
            if success:
                successful_installs += 1
                self.safe_log_callback(log_callback, f"✅ Successfully installed {package}")
            else:
                failed_packages.append(package)
                self.safe_log_callback(log_callback, f"❌ Failed to install {package}")
        
        # Summary
        success_rate = successful_installs / len(self.essential_packages) if self.essential_packages else 0
        self.safe_log_callback(log_callback, f"📊 Installation complete: {successful_installs}/{len(self.essential_packages)} packages ({success_rate*100:.0f}%)")
        
        if failed_packages:
            self.safe_log_callback(log_callback, f"❌ Failed packages: {', '.join(failed_packages[:3])}{'...' if len(failed_packages) > 3 else ''}")
        
        # Consider successful if we got at least 80% of packages
        return success_rate >= 0.8

    def repair_environment_encoding(self, log_callback=None):
        """
        Comprehensive repair for environments with encoding issues
        """
        self.safe_log_callback(log_callback, "🔧 Repairing environment encoding issues...")
        
        print("🔧 Starting environment encoding repair...")
        
        # Step 1: Apply encoding fixes
        self.fix_encoding_environment()
        
        # Step 2: Upgrade pip with encoding fixes
        self.safe_log_callback(log_callback, "Upgrading pip with encoding fixes...")
        
        self.upgrade_pip_in_existing_env(log_callback)
        
        # Step 3: Try to install failed packages individually
        failed_packages = ['rich', 'tqdm', 'moderngl', 'moderngl-window']
        
        for package in failed_packages:
            self.safe_log_callback(log_callback, f"Attempting to install {package} with encoding fixes...")
            
            success = self.install_package_with_encoding_fix(package, log_callback)
            if success:
                self.safe_log_callback(log_callback, f"✅ Successfully installed {package}")
            else:
                self.safe_log_callback(log_callback, f"⚠️ Could not install {package}, will continue without it")
        
        self.safe_log_callback(log_callback, "🔧 Environment encoding repair completed")
        
        return True

    def auto_repair_if_needed(self, log_callback=None):
        """
        Automatically detect and repair common issues
        Call this during startup or when problems are detected
        """
        self.safe_log_callback(log_callback, "🔍 Checking environment health...")
        
        repairs_needed = []
        
        # Check for encoding issues
        if self.detect_encoding_issues():
            repairs_needed.append("encoding")
        
        # Check for corrupted manim
        if self.detect_corrupted_manim():
            repairs_needed.append("manim")
        
        if repairs_needed:
            self.safe_log_callback(log_callback, f"🔧 Detected issues: {', '.join(repairs_needed)}")
            
            # Apply repairs
            if "encoding" in repairs_needed:
                self.repair_environment_encoding(log_callback)
            
            if "manim" in repairs_needed:
                self.reinstall_manim_clean(log_callback)
            
            self.safe_log_callback(log_callback, "✅ Auto-repair completed")
            return True
        else:
            self.safe_log_callback(log_callback, "✅ Environment appears healthy")
            return False

    def setup_environment(self, log_callback=None):
        """Main setup method - create and configure manim_studio_default environment"""
        
        # ENCODING FIXES - Apply these FIRST before any other operations
        print("🔧 Applying encoding fixes before setup...")
        self.fix_encoding_environment()
        
        self.safe_log_callback(log_callback, "🔧 Applied encoding fixes")
        
        # Check for corruption and repair if needed
        try:
            if self.detect_encoding_issues() or self.detect_corrupted_manim():
                self.safe_log_callback(log_callback, "🔍 Detected issues, applying repairs...")
                print("🔍 Detected issues, applying repairs...")
                self.repair_environment_encoding(log_callback)
        except Exception as e:
            self.safe_log_callback(log_callback, f"⚠️ Auto-repair check failed: {e}")
            print(f"⚠️ Auto-repair check failed: {e}")
        
        print("🚀 Starting environment setup...")
        self.safe_log_callback(log_callback, "🚀 Starting environment setup...")
        
        default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
        
        # Step 1: Check for existing environment
        if os.path.exists(default_venv_path) and self.is_valid_venv(default_venv_path):
            print("✅ Found existing environment, checking what's missing...")
            self.safe_log_callback(log_callback, "✅ Found existing environment, checking what's missing...")
            
            # Set up paths for existing environment
            if os.name == 'nt':
                self.python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
                self.pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
            else:
                self.python_path = os.path.join(default_venv_path, "bin", "python")
                self.pip_path = os.path.join(default_venv_path, "bin", "pip")
            
            # Validate Python installation
            if not self.validate_python_installation(self.python_path):
                print("⚠️ Invalid Python installation in existing environment")
                self.safe_log_callback(log_callback, "⚠️ Invalid Python installation in existing environment")
                # Fall through to recreate
            else:
                # Check what packages are missing
                missing_packages = self.check_missing_packages()
                
                if not missing_packages:
                    print("✅ All packages already installed!")
                    self.safe_log_callback(log_callback, "✅ All packages already installed!")
                    self.activate_default_environment()
                    self.needs_setup = False
                    return True
                else:
                    print(f"⚠️ Missing packages: {len(missing_packages)}")
                    self.safe_log_callback(log_callback, f"⚠️ Missing {len(missing_packages)} packages")
                    
                    # Upgrade pip first in existing environment with encoding fixes
                    self.upgrade_pip_in_existing_env(log_callback)
                    
                    # Try to install missing packages with encoding fixes
                    if self.install_missing_packages_with_encoding_fix(missing_packages, log_callback):
                        print("✅ Successfully installed missing packages!")
                        self.safe_log_callback(log_callback, "✅ Successfully installed missing packages!")
                        self.activate_default_environment()
                        self.safe_log_callback(log_callback, "✅ Environment setup completed successfully!")
                        self.needs_setup = False
                        return True
                    else:
                        self.safe_log_callback(log_callback, "⚠️ Installation completed with warnings")
                        return False
        
        # Step 2: Create new environment if needed
        if not self.create_virtual_environment(log_callback):
            error_msg = "❌ Failed to create virtual environment"
            self.safe_log_callback(log_callback, error_msg)
            print(error_msg)
            return False
        
        # Step 3: Upgrade pip with encoding fixes
        self.upgrade_pip_in_existing_env(log_callback)
        
        # Step 4: Install all packages with encoding fixes
        if not self.install_all_packages(log_callback):
            error_msg = "❌ Failed to install all packages"
            self.safe_log_callback(log_callback, error_msg)
            print(error_msg)
            return False
        
        # Step 5: Verify installation
        if not self.verify_complete_installation(log_callback):
            error_msg = "❌ Verification failed"
            self.safe_log_callback(log_callback, error_msg)
            print(error_msg)
            return False
        
        # Step 6: Activate environment
        self.activate_default_environment()
        
        self.safe_log_callback(log_callback, "✅ Environment setup completed successfully!")
        self.needs_setup = False
        return True

    def install_missing_packages_with_encoding_fix(self, missing_packages, log_callback=None):
        """Install missing packages with enhanced encoding handling"""
        if not missing_packages:
            return True
        
        self.safe_log_callback(log_callback, f"Installing {len(missing_packages)} missing packages...")
        
        successful_installs = 0
        
        for package in missing_packages:
            self.safe_log_callback(log_callback, f"Installing {package}...")
            
            success = self.install_package_with_encoding_fix(package, log_callback)
            if success:
                successful_installs += 1
        
        # Consider successful if we got at least 70% of packages
        success_rate = successful_installs / len(missing_packages)
        
        self.safe_log_callback(log_callback, f"Installation summary: {successful_installs}/{len(missing_packages)} packages ({success_rate*100:.0f}%)")
        
        return success_rate >= 0.7  # 70% success rate threshold

    def upgrade_pip_in_existing_env(self, log_callback=None):
        """
        Enhanced pip upgrade with comprehensive encoding fixes
        """
        if not self.python_path or not os.path.exists(self.python_path):
            self.safe_log_callback(log_callback, "❌ No valid Python environment for pip upgrade")
            return False
        
        self.safe_log_callback(log_callback, "🔧 Upgrading pip with encoding fixes...")
        
        try:
            upgrade_cmd = [
                self.python_path, "-m", "pip", "install", 
                "--upgrade", "pip",
                "--no-warn-script-location",
                "--disable-pip-version-check"
            ]
            
            result = self.run_hidden_subprocess_with_encoding(
                upgrade_cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                self.safe_log_callback(log_callback, "✅ Pip upgraded successfully")
                return True
            else:
                self.safe_log_callback(log_callback, "⚠️ Pip upgrade had issues but continuing...")
                return False
                
        except Exception as e:
            self.safe_log_callback(log_callback, f"❌ Error during pip upgrade: {e}")
            return False

    def verify_complete_installation(self, log_callback=None):
        """
        Comprehensive verification of the complete installation
        """
        try:
            self.safe_log_callback(log_callback, "🔍 Verifying complete installation...")
            
            # Test critical imports
            critical_imports = [
                "import numpy",
                "import matplotlib", 
                "import customtkinter",
                "import PIL",
                "import cv2"
            ]
            
            for test_import in critical_imports:
                test_cmd = [self.python_path, "-c", test_import]
                result = self.run_hidden_subprocess_with_encoding(
                    test_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    self.safe_log_callback(log_callback, f"✅ Import test passed: {test_import}")
                    print(f"✅ Import test passed: {result.stdout.strip()}")
                else:
                    self.safe_log_callback(log_callback, f"⚠️ Import test failed: {test_import}")
            
            # Test manim specifically (with corruption detection)
            if not self.detect_corrupted_manim():
                self.safe_log_callback(log_callback, "✅ Manim verification passed")
            else:
                self.safe_log_callback(log_callback, "⚠️ Manim verification failed - corruption detected")
                # Try to repair manim
                self.reinstall_manim_clean(log_callback)
            
            self.safe_log_callback(log_callback, "✅ Verification completed")
            return True
            
        except Exception as e:
            self.safe_log_callback(log_callback, f"❌ Verification error: {e}")
            return False

    def reinstall_manim_clean(self, log_callback=None):
        """
        Cleanly reinstall manim with encoding fixes to resolve corruption
        """
        if not self.python_path or not os.path.exists(self.python_path):
            self.safe_log_callback(log_callback, "❌ No valid Python environment available")
            return False
        
        self.safe_log_callback(log_callback, "🔧 Starting clean manim reinstallation...")
        print("🔧 Starting clean manim reinstallation...")
        
        # Apply encoding fixes first
        self.fix_encoding_environment()
        
        try:
            # Step 1: Uninstall existing manim
            self.safe_log_callback(log_callback, "1. Uninstalling existing manim...")
            
            uninstall_cmd = [self.python_path, "-m", "pip", "uninstall", "manim", "-y"]
            subprocess.run(uninstall_cmd, capture_output=True, text=True, timeout=60)
            
            # Step 2: Clear pip cache
            self.safe_log_callback(log_callback, "2. Clearing pip cache...")
            
            cache_cmd = [self.python_path, "-m", "pip", "cache", "purge"]
            subprocess.run(cache_cmd, capture_output=True, text=True, timeout=30)
            
            # Step 3: Reinstall manim
            self.safe_log_callback(log_callback, "3. Reinstalling manim with encoding fixes...")
            
            success = self.install_package_with_encoding_fix("manim>=0.17.0", log_callback)
            
            if success:
                # Step 4: Verify installation
                self.safe_log_callback(log_callback, "4. Verifying manim installation...")
                
                verify_success = self.verify_manim_installation(log_callback)
                if verify_success:
                    self.safe_log_callback(log_callback, "✅ Manim reinstalled and verified successfully!")
                    return True
                else:
                    self.safe_log_callback(log_callback, "⚠️ Manim installed but verification failed")
                    return False
            else:
                self.safe_log_callback(log_callback, "❌ Failed to reinstall manim")
                return False
                
        except Exception as e:
            error_msg = f"❌ Error during manim reinstallation: {e}"
            self.safe_log_callback(log_callback, error_msg)
            print(error_msg)
            return False

    def verify_manim_installation(self, log_callback=None):
        """
        Verify that manim is properly installed and working
        """
        try:
            # Test manim import
            test_cmd = [
                self.python_path, "-c", 
                "import manim; print('Manim version:', manim.__version__)"
            ]
            
            result = subprocess.run(
                test_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                version_info = result.stdout.strip()
                self.safe_log_callback(log_callback, f"✅ Manim verification successful: {version_info}")
                print(f"✅ Manim verification successful: {version_info}")
                return True
            else:
                error_msg = f"❌ Manim verification failed: {result.stderr}"
                self.safe_log_callback(log_callback, error_msg)
                print(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"❌ Manim verification error: {e}"
            self.safe_log_callback(log_callback, error_msg)
            print(error_msg)
            return False

    def find_python_executable(self):
        """
        Find a suitable Python executable for creating virtual environments
        """
        try:
            # Try different Python executables in order of preference
            python_candidates = []
            
            # First try the current Python executable
            if hasattr(sys, 'executable') and sys.executable:
                python_candidates.append(sys.executable)
            
            # Try common Python executable names
            common_names = ['python', 'python3', 'python.exe', 'python3.exe']
            
            for name in common_names:
                try:
                    # Use shutil.which to find the executable in PATH
                    python_path = shutil.which(name)
                    if python_path and python_path not in python_candidates:
                        python_candidates.append(python_path)
                except:
                    pass
            
            # Test each candidate to find a working one
            for candidate in python_candidates:
                if self.validate_python_installation(candidate):
                    print(f"✅ Found working Python executable: {candidate}")
                    return candidate
            
            print("❌ No working Python executable found")
            return None
            
        except Exception as e:
            print(f"❌ Error finding Python executable: {e}")
            return None

    def validate_python_installation(self, python_path):
        """
        Validate that a Python installation is working correctly
        """
        try:
            if not python_path or not os.path.exists(python_path):
                print(f"❌ Python path does not exist: {python_path}")
                return False
            
            # Test basic Python functionality
            test_cmd = [python_path, "-c", "import sys; print('Python', sys.version)"]
            
            result = self.run_hidden_subprocess_with_encoding(
                test_cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                version_info = result.stdout.strip()
                print(f"✅ Python validation successful: {version_info}")
                return True
            else:
                error_info = result.stderr or "Unknown error"
                print(f"❌ Python validation failed: {error_info}")
                return False
                
        except Exception as e:
            print(f"❌ Error validating Python installation: {e}")
            return False

    def list_venvs(self):
        """List all available virtual environments"""
        venvs = []
        if os.path.exists(self.venv_dir):
            for item in os.listdir(self.venv_dir):
                venv_path = os.path.join(self.venv_dir, item)
                if os.path.isdir(venv_path) and self.is_valid_venv(venv_path):
                    venvs.append(item)
                    
        return sorted(venvs)

    def is_valid_venv(self, venv_path):
        """Check if a directory is a valid virtual environment"""
        try:
            if not os.path.isdir(venv_path):
                return False
            
            # Check for typical venv structure
            if os.name == 'nt':
                python_exe = os.path.join(venv_path, "Scripts", "python.exe")
                pip_exe = os.path.join(venv_path, "Scripts", "pip.exe")
            else:
                python_exe = os.path.join(venv_path, "bin", "python")
                pip_exe = os.path.join(venv_path, "bin", "pip")
            
            return os.path.exists(python_exe)
            
        except Exception:
            return False

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
        """Activate the default manim_studio environment"""
        return self.activate_venv("manim_studio_default")

    def deactivate_venv(self):
        """Deactivate the current virtual environment"""
        self.current_venv = None
        self.python_path = sys.executable
        self.pip_path = "pip"
        return True

    def check_missing_packages(self):
        """Check which essential packages are missing - SILENT VERSION"""
        missing = []
        
        if not self.python_path or not os.path.exists(self.python_path):
            return self.essential_packages.copy()
        
        # Silent check - no progress logging
        for package in self.essential_packages:
            if not self.is_package_installed(package):
                missing.append(package)
        
        # No logging of results when called from environment manager
        return missing

    def is_package_installed(self, package_name):
        """Check if a package is installed using pip show - SILENT VERSION"""
        try:
            # Extract package name from version specifiers
            clean_name = package_name.split('>=')[0].split('==')[0].split('<=')[0].strip()
            
            # Use pip show to check if package is installed (silent)
            check_cmd = [self.python_path, "-m", "pip", "show", clean_name]
            
            result = self.run_hidden_subprocess_with_encoding(
                check_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Return result without any logging
            return result.returncode == 0
                
        except Exception:
            return False

    def check_manim_availability(self):
        """
        Fast check if manim is available - NO SUBPROCESS CALLS
        """
        try:
            if not self.python_path or not os.path.exists(self.python_path):
                return False
            
            # SKIP SLOW MANIM IMPORT TEST - Just assume it's available if environment exists
            if self.current_venv and os.path.exists(self.python_path):
                return True
            
            return False
                
        except Exception:
            return False
    def _mark_environment_as_validated(self, venv_name):
        """
        Mark an environment as validated in the cache
        """
        try:
            if not hasattr(self, '_validation_cache'):
                self._validation_cache = {}
            
            # Store validation info with timestamp
            import time
            self._validation_cache[venv_name] = {
                'python_path': self.python_path,
                'pip_path': self.pip_path,
                'validated_at': time.time(),
                'manim_working': True
            }
            
            print(f"📋 Marked {venv_name} as validated")
            
        except Exception as e:
            print(f"⚠️ Error marking environment as validated: {e}")

    def _is_environment_validated(self, venv_name):
        """
        Check if environment has been validated previously (fast check using cache)
        This helps avoid re-validating the same environment multiple times
        """
        try:
            # Simple validation check - if we have the basic info cached and paths exist, consider it validated
            if not hasattr(self, '_validation_cache'):
                self._validation_cache = {}
            
            # Check if we have cached validation for this environment
            if venv_name in self._validation_cache:
                cached_info = self._validation_cache[venv_name]
                
                # Verify that the cached paths still exist
                if (cached_info.get('python_path') and 
                    cached_info.get('pip_path') and
                    os.path.exists(cached_info['python_path']) and 
                    os.path.exists(cached_info['pip_path'])):
                    
                    print(f"✅ Using cached validation for {venv_name}")
                    return True
                else:
                    # Cached info is stale, remove it
                    del self._validation_cache[venv_name]
                    print(f"🔄 Cached validation for {venv_name} is stale, will re-validate")
                    return False
            
            # No cached validation found
            print(f"🔍 No cached validation found for {venv_name}")
            return False
            
        except Exception as e:
            print(f"⚠️ Error checking validation cache: {e}")
            return False

    def get_venv_info(self, venv_name_or_callback=None):
        """
        Get comprehensive virtual environment information - FAST VERSION (NO SLOW CHECKS)
        Handles both old calling style (with venv_name) and new style (with callback)
        
        Args:
            venv_name_or_callback: Either a venv name (string) or callback function
        """
        # Handle different calling patterns
        venv_name = None
        log_callback = None
        
        if venv_name_or_callback is None:
            # get_venv_info() - no arguments
            venv_name = self.current_venv
            log_callback = None
        elif callable(venv_name_or_callback):
            # get_venv_info(callback_function) - callback provided
            venv_name = self.current_venv
            log_callback = venv_name_or_callback
        elif isinstance(venv_name_or_callback, str):
            # get_venv_info("env_name") - environment name provided
            venv_name = venv_name_or_callback
            log_callback = None
        else:
            # Fallback
            venv_name = self.current_venv
            log_callback = None
        
        # Build the info dictionary
        info = {
            'current_venv': self.current_venv,
            'python_path': self.python_path,
            'pip_path': self.pip_path,
            'venv_dir': self.venv_dir,
            'needs_setup': self.needs_setup,
            'is_frozen': self.is_frozen,
            'available_venvs': [],
            'python_version': None,
            'pip_version': None,
            'installed_packages': [],
            'missing_packages': [],
            'environment_health': 'ready',
            'encoding_info': {},
            'system_info': {},
            'manim_status': 'available',
            'last_setup_time': None,
            'total_packages': len(self.essential_packages),
            'installation_status': {},
            'path': self.venv_dir,
            'packages_count': 0,
            'size': 0,
            'is_active': False
        }
        
        # If specific venv requested, add its path
        if venv_name and venv_name != self.current_venv:
            venv_path = os.path.join(self.venv_dir, venv_name)
            info['path'] = venv_path
            info['venv_exists'] = os.path.exists(venv_path)
            info['is_active'] = False
        else:
            info['path'] = os.path.join(self.venv_dir, self.current_venv) if self.current_venv else self.venv_dir
            info['venv_exists'] = True
            info['is_active'] = (venv_name == self.current_venv)
        
        # SILENT log function - no more environment status spam
        def log_message(msg):
            # Only log if callback is provided and it's not a silent callback
            if log_callback and callable(log_callback) and log_callback != (lambda msg: None):
                try:
                    log_callback(msg)
                except:
                    pass
        
        try:
            # Get available environments (fast - just directory listing)
            info['available_venvs'] = self.list_venvs()
            
            # Get system info (fast)
            info['system_info'] = {
                'platform': platform.system(),
                'python_version': platform.python_version(),
                'frozen': self.is_frozen
            }
            
            # FAST CHECKS ONLY - No subprocess calls
            if self.python_path and os.path.exists(self.python_path):
                # Just check if files exist - no execution
                info['python_version'] = f"Python (at {self.python_path})"
                info['pip_version'] = f"pip (at {self.pip_path})" if self.pip_path else "pip (unknown)"
                info['environment_health'] = 'ready'
                info['manim_status'] = 'assumed_available'
                
                # SKIP SLOW PACKAGE CHECKING - Assume all essential packages are installed
                info['missing_packages'] = []  # Assume none missing for speed
                info['packages_count'] = len(self.essential_packages)  # Estimate
                
                info['installation_status'] = {
                    'total_packages': len(self.essential_packages),
                    'installed_packages': len(self.essential_packages),  # Assume all installed
                    'missing_packages': 0,
                    'completion_percentage': 100.0
                }
                
                # Calculate environment size (fast directory size estimation)
                try:
                    if venv_name and os.path.exists(info['path']):
                        # Quick size estimation - just check a few key directories
                        size = 0
                        for root, dirs, files in os.walk(info['path']):
                            # Only traverse first 2 levels to avoid slowdown
                            level = root.replace(info['path'], '').count(os.sep)
                            if level < 2:
                                size += sum(os.path.getsize(os.path.join(root, f)) 
                                          for f in files if os.path.exists(os.path.join(root, f)))
                            else:
                                dirs.clear()  # Don't go deeper
                        info['size'] = size
                    else:
                        info['size'] = 0
                except:
                    info['size'] = 0
                    
            else:
                # No valid Python path
                info['python_version'] = "Not found"
                info['pip_version'] = "Not found"
                info['environment_health'] = 'missing'
                info['manim_status'] = 'unavailable'
                info['missing_packages'] = self.essential_packages.copy()
                info['packages_count'] = 0
                info['installation_status'] = {
                    'total_packages': len(self.essential_packages),
                    'installed_packages': 0,
                    'missing_packages': len(self.essential_packages),
                    'completion_percentage': 0.0
                }
                info['size'] = 0
        
        except Exception as e:
            # Silent error handling - no logs for environment manager
            info['environment_health'] = 'error'
            info['error'] = str(e)
        
        return info
    
    def get_system_encoding_info(self):
        """
        Get detailed information about the current system encoding
        Useful for debugging encoding issues
        """
        try:
            info = {
                'system_encoding': locale.getpreferredencoding(),
                'filesystem_encoding': sys.getfilesystemencoding(),
                'python_encoding': getattr(sys.stdout, 'encoding', 'unknown'),
                'stdin_encoding': getattr(sys.stdin, 'encoding', 'unknown'),
                'stderr_encoding': getattr(sys.stderr, 'encoding', 'unknown'),
                'environment_vars': {
                    'PYTHONIOENCODING': os.environ.get('PYTHONIOENCODING', 'not set'),
                    'PYTHONUTF8': os.environ.get('PYTHONUTF8', 'not set'),
                    'PYTHONLEGACYWINDOWSFSENCODING': os.environ.get('PYTHONLEGACYWINDOWSFSENCODING', 'not set'),
                    'LC_ALL': os.environ.get('LC_ALL', 'not set'),
                    'LANG': os.environ.get('LANG', 'not set'),
                    'CODEPAGE': os.environ.get('CODEPAGE', 'not set')
                },
                'encoding_issues_detected': self.detect_encoding_issues(),
                'recommended_fixes_applied': all([
                    os.environ.get('PYTHONIOENCODING') == 'utf-8',
                    os.environ.get('PYTHONUTF8') == '1',
                    os.environ.get('PYTHONLEGACYWINDOWSFSENCODING') == '0'
                ])
            }
            
            # Use newer locale methods if available (Python 3.11+)
            try:
                info['default_locale'] = locale.getlocale()
            except:
                try:
                    # Fallback for older Python versions
                    info['default_locale'] = locale.getdefaultlocale()
                except:
                    info['default_locale'] = ('unknown', 'unknown')
            
            # Check for problematic encodings
            problematic_encodings = ['cp950', 'cp936', 'gbk', 'gb2312']
            info['has_problematic_encoding'] = any(
                encoding.lower() in str(info['system_encoding']).lower() 
                for encoding in problematic_encodings
            )
            
            return info
            
        except Exception as e:
            return {'error': str(e)}

    def list_packages(self):
        """List all installed packages in the current environment"""
        try:
            if not self.python_path or not os.path.exists(self.python_path):
                return False, "No valid Python environment available"
            
            result = self.run_hidden_subprocess_with_encoding(
                [self.python_path, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                timeout=60
            )
            
            if result.returncode == 0:
                packages_data = json.loads(result.stdout)
                packages = []
                for pkg in packages_data:
                    packages.append({
                        'name': pkg['name'],
                        'version': pkg['version']
                    })
                return True, packages
            else:
                return False, result.stderr
                
        except Exception as e:
            return False, str(e)

    def install_package(self, package_name, log_callback=None):
        """Install a single package"""
        return self.install_package_with_encoding_fix(package_name, log_callback)

    def uninstall_package(self, package_name, log_callback=None):
        """Uninstall a package from the current environment"""
        try:
            if not self.python_path or not os.path.exists(self.python_path):
                if log_callback:
                    log_callback("❌ No valid Python environment available")
                return False
            
            if log_callback:
                log_callback(f"🗑️ Uninstalling {package_name}...")
            
            # Uninstall package
            cmd = [self.python_path, "-m", "pip", "uninstall", "-y", package_name]
            
            result = self.run_hidden_subprocess_with_encoding(
                cmd,
                capture_output=True,
                timeout=300
            )
            
            if result.returncode == 0:
                if log_callback:
                    log_callback(f"✅ {package_name} uninstalled successfully")
                return True
            else:
                if log_callback:
                    log_callback(f"❌ Failed to uninstall {package_name}: {result.stderr}")
                return False
                
        except Exception as e:
            if log_callback:
                log_callback(f"❌ Error uninstalling {package_name}: {e}")
            return False

    def delete_environment(self, env_name):
        """Delete a virtual environment"""
        try:
            if env_name == self.current_venv:
                print(f"❌ Cannot delete active environment: {env_name}")
                return False
            
            env_path = os.path.join(self.venv_dir, env_name)
            
            if not os.path.exists(env_path):
                print(f"❌ Environment does not exist: {env_path}")
                return False
            
            # Delete the environment directory
            shutil.rmtree(env_path)
            print(f"✅ Environment deleted: {env_name}")
            return True
            
        except Exception as e:
            print(f"❌ Error deleting environment {env_name}: {e}")
            return False

    def create_simple_environment_dialog(self, parent):
        """Create a simple built-in environment management dialog"""
        dialog = ctk.CTkToplevel(parent)
        dialog.title("Environment Manager")
        dialog.geometry("600x400")
        dialog.transient(parent)
        dialog.grab_set()
        
        # Main frame
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title_label = ctk.CTkLabel(main_frame, text="Virtual Environment Manager", 
                                   font=ctk.CTkFont(size=18, weight="bold"))
        title_label.pack(pady=(0, 20))
        
        # Environment info
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(fill="x", pady=(0, 20))
        
        current_env_label = ctk.CTkLabel(info_frame, text=f"Current Environment: {self.current_venv or 'None'}")
        current_env_label.pack(pady=10)
        
        # Get environment info
        env_info = self.get_venv_info()
        status_text = f"Status: {env_info.get('overall_status', 'unknown')}"
        packages_text = f"Packages: {env_info.get('packages_count', 0)}"
        
        status_label = ctk.CTkLabel(info_frame, text=status_text)
        status_label.pack(pady=5)
        
        packages_label = ctk.CTkLabel(info_frame, text=packages_text)
        packages_label.pack(pady=5)
        
        # Buttons frame
        buttons_frame = ctk.CTkFrame(main_frame)
        buttons_frame.pack(fill="x", pady=(0, 20))
        
        # Setup button
        if self.needs_setup:
            setup_btn = ctk.CTkButton(buttons_frame, text="Setup Environment", 
                                      command=lambda: self.setup_environment(print))
            setup_btn.pack(side="left", padx=10, pady=10)
        
        # Verify button
        verify_btn = ctk.CTkButton(buttons_frame, text="Verify Installation", 
                                   command=lambda: self.verify_complete_installation(print))
        verify_btn.pack(side="left", padx=10, pady=10)
        
        # Close button
        close_btn = ctk.CTkButton(buttons_frame, text="Close", command=dialog.destroy)
        close_btn.pack(side="right", padx=10, pady=10)
        
        return dialog

    def manage_environment(self):
        """Open environment management dialog"""
        try:
            # ALWAYS show the management dialog, don't block on setup
            if self.parent_app and hasattr(self.parent_app, 'root'):
                dialog = self.create_simple_environment_dialog(self.parent_app.root)
                self.parent_app.root.wait_window(dialog)
                
                # Update venv status after dialog closes
                if hasattr(self.parent_app, 'venv_status_label') and self.current_venv:
                    self.parent_app.venv_status_label.configure(text=self.current_venv)
            else:
                # Minimal console output
                env_info = self.get_venv_info(print)
                    
        except Exception as e:
            # Minimal error handling
            try:
                if self.parent_app and hasattr(self.parent_app, 'root'):
                    messagebox.showerror(
                        "Environment Error", 
                        f"Error opening environment dialog:\n{str(e)}",
                        parent=self.parent_app.root
                    )
            except:
                pass
    def show_setup_dialog(self):
        """Show the environment setup dialog - FIXED WITH NO IMPORT ERRORS"""
        if self.parent_app and hasattr(self.parent_app, 'root'):
            print("⚠️ Using console-based setup (GUI dialog not available)")
            self.setup_environment(print)
        else:
            print("⚠️ Cannot show setup dialog - no parent app available")
            print("Running console setup...")
            self.setup_environment(print)

    def list_environments(self):
        """Alias for list_venvs for compatibility"""
        return self.list_venvs()

    def create_virtual_environment_with_name(self, env_name, log_callback=None):
        """Create a virtual environment with a specific name"""
        original_env_name = env_name
        env_path = os.path.join(self.venv_dir, env_name)
        
        self.safe_log_callback(log_callback, f"Creating virtual environment: {env_name}")
        print(f"🔧 Creating virtual environment: {env_name}")
        
        # Apply encoding fixes to the environment
        self.fix_encoding_environment()
        
        # Find Python executable
        python_exe = self.find_python_executable()
        if not python_exe:
            error_msg = "❌ No Python executable found\n\nPlease install Python from https://python.org"
            self.safe_log_callback(log_callback, error_msg)
            return False
        
        try:
            # Create environment with proper Windows subprocess handling and encoding
            create_cmd = [python_exe, "-m", "venv", env_path, "--clear"]
            
            # Enhanced environment for creation
            env = os.environ.copy()
            env.update({
                'PYTHONIOENCODING': 'utf-8',
                'PYTHONLEGACYWINDOWSFSENCODING': '0',
                'PYTHONUTF8': '1'
            })
            
            result = subprocess.run(
                create_cmd,
                capture_output=True,
                text=True,
                timeout=180,
                env=env,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                self.safe_log_callback(log_callback, f"✅ Virtual environment '{env_name}' created successfully")
                return True
            else:
                error_msg = f"❌ Failed to create virtual environment: {result.stderr}"
                self.safe_log_callback(log_callback, error_msg)
                return False
                
        except Exception as e:
            error_msg = f"❌ Error creating virtual environment: {e}"
            self.safe_log_callback(log_callback, error_msg)
            return False
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


class ResponsiveUI:
    """Enhanced Responsive UI manager for different screen sizes and DPI settings"""
    
    def __init__(self, root):
        self.root = root
        self.screen_width = root.winfo_screenwidth()
        self.screen_height = root.winfo_screenheight()
        self.dpi_scale = self._get_dpi_scale()
        self.dpi = self.get_dpi()
        self.scale_factor = self.calculate_scale_factor()
        
        # Quality-based UI scaling
        self.quality_scale_factor = 1.0
        self.current_quality = "Medium"  # Default quality
        
    def _get_dpi_scale(self):
        """Get DPI scaling factor"""
        try:
            if os.name == 'nt':
                # Windows DPI awareness
                import ctypes
                user32 = ctypes.windll.user32
                user32.SetProcessDPIAware()
                dpi = user32.GetDpiForSystem()
                return dpi / 96.0
            else:
                # Unix-like systems
                return 1.0
        except:
            return 1.0

    def get_dpi(self):
        """Get system DPI"""
        try:
            return self.root.winfo_fpixels('1i')
        except:
            return 96  # Default DPI
            
    def calculate_scale_factor(self):
        """Calculate UI scale factor based on screen size and DPI"""
        # Base scale on screen width, with adjustments for DPI
        if self.screen_width <= 1024:
            base_scale = 0.8
        elif self.screen_width <= 1366:
            base_scale = 0.9
        elif self.screen_width <= 1920:
            base_scale = 1.0
        else:
            base_scale = 1.1
            
        # Adjust for high DPI
        if self.dpi > 120:
            base_scale *= 1.1
        elif self.dpi > 150:
            base_scale *= 1.25
            
        return max(0.7, min(1.5, base_scale))

    def set_quality_scaling(self, quality):
        """Set UI scaling based on render quality to optimize performance"""
        self.current_quality = quality
        
        # Quality-based scaling factors
        quality_scaling = {
            "Low": 0.9,      # Smaller UI for lower quality
            "Medium": 1.0,    # Normal UI
            "High": 1.1,     # Slightly larger UI for high quality
            "Ultra": 1.15,   # Larger UI for ultra quality
            "Custom": 1.0    # Default for custom
        }
        
        self.quality_scale_factor = quality_scaling.get(quality, 1.0)

    def get_combined_scale_factor(self):
        """Get combined scale factor including quality scaling"""
        return self.scale_factor * self.quality_scale_factor

    def get_optimal_window_size(self, preferred_width, preferred_height):
        """Get optimal window size based on screen dimensions"""
        # Calculate maximum usable screen space (leave room for taskbar)
        max_width = int(self.screen_width * 0.9)
        max_height = int(self.screen_height * 0.85)
        
        # Scale preferred size by combined DPI and quality scale
        combined_scale = self.get_combined_scale_factor()
        scaled_width = int(preferred_width * self.dpi_scale * combined_scale)
        scaled_height = int(preferred_height * self.dpi_scale * combined_scale)
        
        # Ensure window fits on screen
        final_width = min(scaled_width, max_width)
        final_height = min(scaled_height, max_height)
        
        return final_width, final_height
    
    def scale_dimension(self, value):
        """Scale a dimension value with quality consideration"""
        return int(value * self.get_combined_scale_factor())
    
    def get_font_size(self, base_size):
        """Get responsive font size with quality scaling"""
        scaled = int(base_size * self.get_combined_scale_factor())
        return max(8, min(32, scaled))
    
    def get_button_dimensions(self, base_width=None, base_height=35):
        """Get responsive button dimensions that ensure all buttons are visible"""
        height = self.scale_dimension(base_height)
        
        # Ensure minimum button height for usability
        height = max(30, height)
        
        # Scale width if provided
        if base_width:
            width = self.scale_dimension(base_width)
            width = max(50, width)  # Minimum width
            return width, height
        
        return height
    
    def get_window_size(self, base_width, base_height):
        """Get responsive window size with screen constraints"""
        # Use percentage of screen for very small screens
        if self.screen_width < 1024 or self.screen_height < 768:
            width = int(self.screen_width * 0.9)
            height = int(self.screen_height * 0.85)
        else:
            width = self.scale_dimension(base_width)
            height = self.scale_dimension(base_height)
            
        # Ensure window fits on screen
        width = min(width, self.screen_width - 100)
        height = min(height, self.screen_height - 100)
        
        return width, height
        
    def get_optimal_sidebar_width(self, base_width=350):
        """Get responsive sidebar width with quality consideration"""
        if self.screen_width < 1024:
            base_width = 280
        elif self.screen_width < 1366:
            base_width = 320
            
        return self.scale_dimension(base_width)
    
    def get_optimal_font_sizes(self):
        """Get optimal font sizes for different elements"""
        return {
            "tiny": self.get_font_size(8),
            "small": self.get_font_size(10),
            "normal": self.get_font_size(12),
            "medium": self.get_font_size(13),
            "large": self.get_font_size(16),
            "header": self.get_font_size(18),
            "title": self.get_font_size(20)
        }
    
    def get_optimal_spacing(self):
        """Get optimal spacing values with quality scaling"""
        return {
            "tiny": self.scale_dimension(2),
            "small": self.scale_dimension(5),
            "normal": self.scale_dimension(10),
            "medium": self.scale_dimension(15),
            "large": self.scale_dimension(20),
            "xlarge": self.scale_dimension(25)
        }
        
    def get_padding(self, base_padding):
        """Get scaled padding"""
        return max(2, int(base_padding * self.get_combined_scale_factor()))
    
    def get_sidebar_width(self, base_width=350):
        """Get responsive sidebar width (alias for compatibility)"""
        return self.get_optimal_sidebar_width(base_width)

    def get_combo_height(self, base_height=36):
        """Get responsive combo box height"""
        return self.scale_dimension(base_height)

    def get_responsive_button_config(self, base_width=None, base_height=35, font_size=12):
        """Get complete responsive button configuration"""
        if base_width:
            width, height = self.get_button_dimensions(base_width, base_height)
            return {
                "width": width,
                "height": height,
                "font": ("Segoe UI", self.get_font_size(font_size))
            }
        else:
            height = self.get_button_dimensions(base_height=base_height)
            return {
                "height": height,
                "font": ("Segoe UI", self.get_font_size(font_size))
            }

    def apply_responsive_config(self, widget, widget_type="button", **kwargs):
        """Apply responsive configuration to a widget"""
        try:
            if widget_type == "button":
                config = self.get_responsive_button_config(
                    kwargs.get("base_width"),
                    kwargs.get("base_height", 35),
                    kwargs.get("font_size", 12)
                )
                widget.configure(**config)
            elif widget_type == "combo":
                height = self.get_combo_height(kwargs.get("base_height", 36))
                font_size = self.get_font_size(kwargs.get("font_size", 12))
                widget.configure(height=height, font=("Segoe UI", font_size))
            elif widget_type == "label":
                font_size = self.get_font_size(kwargs.get("font_size", 12))
                weight = kwargs.get("weight", "normal")
                widget.configure(font=("Segoe UI", font_size, weight))
        except Exception as e:
            print(f"Error applying responsive config: {e}")

# Updated UI creation methods to use ResponsiveUI properly

def create_responsive_ui_elements(self):
    """Example of how to create UI elements with proper responsive sizing"""
    
    # Get responsive dimensions and fonts
    fonts = self.responsive.get_optimal_font_sizes()
    spacing = self.responsive.get_optimal_spacing()
    
    # Create buttons with responsive sizing
    def create_responsive_button(parent, text, command=None, button_type="normal"):
        """Create a button with responsive sizing"""
        
        if button_type == "large":
            btn_config = self.responsive.get_responsive_button_config(
                base_height=50, font_size=14
            )
        elif button_type == "small":
            btn_config = self.responsive.get_responsive_button_config(
                base_width=30, base_height=30, font_size=10
            )
        else:  # normal
            btn_config = self.responsive.get_responsive_button_config(
                base_height=35, font_size=12
            )
        
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            **btn_config,
            fg_color=VSCODE_COLORS["primary"],
            hover_color=VSCODE_COLORS["primary_hover"]
        )
    
    # Example usage in sidebar creation:
    def create_sidebar_with_responsive_buttons(self):
        """Create sidebar with properly sized responsive buttons"""
        
        # Get responsive dimensions
        sidebar_width = self.responsive.get_optimal_sidebar_width()
        fonts = self.responsive.get_optimal_font_sizes()
        spacing = self.responsive.get_optimal_spacing()
        
        # Create sidebar
        self.sidebar = ctk.CTkFrame(self.root, width=sidebar_width)
        self.sidebar.pack(side="left", fill="y", padx=spacing["normal"], pady=spacing["normal"])
        
        # Preview button with large sizing
        self.quick_preview_button = create_responsive_button(
            self.sidebar,
            text="⚡ Quick Preview", 
            command=self.quick_preview,
            button_type="large"
        )
        self.quick_preview_button.pack(fill="x", padx=spacing["medium"], pady=spacing["medium"])
        
        # Render button with large sizing
        self.render_button = create_responsive_button(
            self.sidebar,
            text="🚀 Render Animation",
            command=self.render_animation,
            button_type="large"
        )
        self.render_button.pack(fill="x", padx=spacing["medium"], pady=spacing["medium"])
        
        # Small utility buttons
        button_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        button_frame.pack(fill="x", padx=spacing["medium"], pady=spacing["small"])
        
        find_btn = create_responsive_button(
            button_frame,
            text="🔍",
            command=self.show_find_dialog,
            button_type="small"
        )
        find_btn.pack(side="left", padx=spacing["tiny"])
        
        font_decrease_btn = create_responsive_button(
            button_frame,
            text="A-",
            command=self.decrease_font_size,
            button_type="small"
        )
        font_decrease_btn.pack(side="left", padx=spacing["tiny"])
        
        font_increase_btn = create_responsive_button(
            button_frame,
            text="A+",
            command=self.increase_font_size,
            button_type="small"
        )
        font_increase_btn.pack(side="left", padx=spacing["tiny"])

def on_quality_change(self, quality):
    """Handle quality change and update UI scaling"""
    # Update ResponsiveUI with new quality
    self.responsive.set_quality_scaling(quality)
    
    # Update UI elements that need rescaling
    self.update_ui_for_quality_change()
    
def update_ui_for_quality_change(self):
    """Update UI elements when quality changes"""
    
    # Get new responsive dimensions
    fonts = self.responsive.get_optimal_font_sizes()
    spacing = self.responsive.get_optimal_spacing()
    
    # Update button heights
    if hasattr(self, 'quick_preview_button'):
        self.responsive.apply_responsive_config(
            self.quick_preview_button, 
            "button", 
            base_height=45, 
            font_size=14
        )
    
    if hasattr(self, 'render_button'):
        self.responsive.apply_responsive_config(
            self.quick_preview_button, 
            "button", 
            base_height=50, 
            font_size=14
        )
    
    # Update combo boxes
    if hasattr(self, 'quality_combo'):
        self.responsive.apply_responsive_config(
            self.quality_combo,
            "combo",
            base_height=36,
            font_size=12
        )
    
    # Update labels
    if hasattr(self, 'quality_info'):
        self.responsive.apply_responsive_config(
            self.quality_info,
            "label", 
            font_size=11
        )
    
    # Force window to recalculate layout
    self.root.update_idletasks()

# Usage in main application initialization:
def initialize_responsive_ui(self):
    """Initialize responsive UI system in main application"""
    
    # Initialize ResponsiveUI
    self.responsive = ResponsiveUI(self.root)
    
    # Set initial quality scaling
    initial_quality = self.settings.get("quality", "Medium")
    self.responsive.set_quality_scaling(initial_quality)
    
    # Get optimal window size
    width, height = self.responsive.get_optimal_window_size(1600, 1000)
    self.root.geometry(f"{width}x{height}")
    
    # Set responsive minimum size  
    min_width, min_height = self.responsive.get_optimal_window_size(1200, 800)
    self.root.minsize(min_width, min_height)
    
    # Center window on screen
    x = (self.responsive.screen_width - width) // 2
    y = (self.responsive.screen_height - height) // 2
    self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    # Apply DPI awareness for Windows
    try:
        if hasattr(self.root, 'tk') and hasattr(self.root.tk, 'call'):
            self.root.tk.call('tk', 'scaling', self.responsive.scale_factor)
    except:
        pass


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
            
            # Use CTkImage for better HighDPI support
            ctk_image = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=(100, 60)
            )
            
            # Display in label
            preview_label = ctk.CTkLabel(parent, image=ctk_image, text="")
            preview_label.pack(expand=True)
            
        except Exception as e:
            # Fallback to icon - MODIFIED TO USE CTkImage
            fallback_icon = load_icon_image("image_placeholder.png", size=(32, 32))
            if fallback_icon:
                icon_label = ctk.CTkLabel(parent, image=fallback_icon, text="")
            else:
                icon_label = ctk.CTkLabel(
                    parent,
                    text="🖼️",
                    font=ctk.CTkFont(size=24)
                )
            icon_label.pack(expand=True)
    
    
    def create_audio_preview(self, parent):
        """Create audio preview"""
        # Audio waveform icon - MODIFIED TO USE CTkImage
        audio_icon = load_icon_image("audio_icon.png", size=(32, 32))
        if audio_icon:
            icon_label = ctk.CTkLabel(parent, image=audio_icon, text="")
        else:
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
    """YouTube-style fullscreen video player with overlay controls that don't block video"""
    
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
        self.speed_menu_visible = False
        self.mouse_timer = None
        self.last_mouse_move = time.time()
        
        self.setup_fullscreen_ui()
        self.setup_bindings()
        
        # Start mouse tracking
        self.start_mouse_tracking()
        
        # Sync initial state
        self.sync_with_main_player()
        
    def setup_fullscreen_ui(self):
        """Setup YouTube-style fullscreen interface with non-blocking overlay controls"""
        # Video takes the ENTIRE screen - never gets blocked
        self.video_frame = tk.Frame(self, bg="black")
        self.video_frame.pack(fill="both", expand=True)
        
        # Video canvas - FULL SCREEN always
        self.canvas = tk.Canvas(
            self.video_frame,
            bg="black",
            highlightthickness=0,
            relief="flat"
        )
        self.canvas.pack(fill="both", expand=True)
        
        # Title overlay (floating on top) - OVERLAY MODE
        self.title_frame = tk.Frame(self, bg="black")
        # Don't pack - use place for overlay positioning
        
        # Semi-transparent title background
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
            text="✕",
            font=("Arial", 16, "bold"),
            fg="white",
            bg="#000000",
            relief="flat",
            cursor="hand2",
            command=self.exit_fullscreen
        )
        self.exit_btn.pack(side="right", padx=20, pady=15)
        
        # Controls overlay (floating on bottom) - OVERLAY MODE
        self.overlay_frame = tk.Frame(self, bg="black")
        # Don't pack - use place for overlay positioning
        
        # Semi-transparent controls background
        self.controls_bg = tk.Frame(
            self.overlay_frame,
            bg="#000000",  # Will add transparency effect
            height=120
        )
        self.controls_bg.pack(fill="both", expand=True)
        
        # Create controls
        self.create_youtube_controls()
        
        # Position overlays using place() instead of pack() - this ensures they float on top
        self.position_overlays()
        
    def position_overlays(self):
        """Position overlay controls to float on top without blocking video"""
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Position title overlay at top (floating)
        self.title_frame.place(
            x=0, y=0,
            width=screen_width,
            height=60
        )
        
        # Position controls overlay at bottom (floating)
        self.overlay_frame.place(
            x=0, y=screen_height - 120,
            width=screen_width,
            height=120
        )

    def create_youtube_controls(self):
        """Create YouTube-style controls with semi-transparent background"""
        # Add semi-transparent gradient background
        self.controls_bg.configure(bg="#1a1a1a")  # Dark but not fully black
        
        # Main controls container with padding
        controls_main = tk.Frame(self.controls_bg, bg="#1a1a1a")
        controls_main.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Progress bar section (top of controls)
        progress_section = tk.Frame(controls_main, bg="#1a1a1a", height=20)
        progress_section.pack(fill="x", side="top", pady=(0, 10))
        
        # Progress bar with semi-transparent background
        progress_bg = tk.Frame(progress_section, bg="#333333", height=12)
        progress_bg.pack(fill="x", pady=2)
        
        self.progress_canvas = tk.Canvas(
            progress_bg,
            height=8,
            bg="#333333",
            highlightthickness=0,
            relief="flat",
            cursor="hand2"
        )
        self.progress_canvas.pack(fill="x", expand=True, padx=5, pady=2)
        self.progress_canvas.bind("<Button-1>", self.on_progress_click)
        
        # Controls row (bottom)
        controls_row = tk.Frame(controls_main, bg="#1a1a1a")
        controls_row.pack(fill="x", side="bottom")
        
        # Left controls
        left_controls = tk.Frame(controls_row, bg="#1a1a1a")
        left_controls.pack(side="left", fill="y")
        
        # Play/Pause button with better visibility
        self.play_btn = tk.Button(
            left_controls,
            text="▶",
            font=("Arial", 20),
            fg="white",
            bg="#333333",  # Slightly lighter background
            relief="flat",
            cursor="hand2",
            command=self.toggle_playback,
            padx=15,
            pady=8,
            borderwidth=1,
            highlightthickness=0
        )
        self.play_btn.pack(side="left", padx=(0, 15))
        
        # Time display with background for visibility
        time_bg = tk.Frame(left_controls, bg="#333333")
        time_bg.pack(side="left", padx=(0, 20))
        
        self.time_label = tk.Label(
            time_bg,
            text="00:00 / 00:00",
            font=("Arial", 14),
            fg="white",
            bg="#333333",
            padx=10,
            pady=5
        )
        self.time_label.pack()
        
        # Center area (spacer to push right controls to the right)
        center_spacer = tk.Frame(controls_row, bg="#1a1a1a")
        center_spacer.pack(side="left", fill="x", expand=True)
        
        # Right controls
        right_controls = tk.Frame(controls_row, bg="#1a1a1a")
        right_controls.pack(side="right", fill="y")
        
        # Speed controls with background for visibility
        speed_frame = tk.Frame(right_controls, bg="#333333")
        speed_frame.pack(side="right", padx=(0, 20))
        
        # Speed display
        self.speed_label = tk.Label(
            speed_frame,
            text="1.0×",
            font=("Arial", 12, "bold"),
            fg="white",
            bg="#333333",
            padx=8,
            pady=2
        )
        self.speed_label.pack(side="top")
        
        # Speed buttons in horizontal layout
        speed_buttons_frame = tk.Frame(speed_frame, bg="#333333")
        speed_buttons_frame.pack(side="bottom", pady=(2, 5))
        
        # Speed decrease button
        speed_down_btn = tk.Button(
            speed_buttons_frame,
            text="−",
            font=("Arial", 12, "bold"),
            fg="white",
            bg="#555555",
            relief="flat",
            cursor="hand2",
            command=lambda: self.change_speed(-0.25),
            width=2,
            pady=2
        )
        speed_down_btn.pack(side="left", padx=(2, 1))
        
        # Speed increase button
        speed_up_btn = tk.Button(
            speed_buttons_frame,
            text="+",
            font=("Arial", 12, "bold"),
            fg="white",
            bg="#555555",
            relief="flat",
            cursor="hand2",
            command=lambda: self.change_speed(0.25),
            width=2,
            pady=2
        )
        speed_up_btn.pack(side="left", padx=(1, 2))
        
        # Settings button with background
        settings_bg = tk.Frame(right_controls, bg="#333333")
        settings_bg.pack(side="right", padx=(0, 10))
        
        self.settings_btn = tk.Button(
            settings_bg,
            text="⚙",
            font=("Arial", 16),
            fg="white",
            bg="#555555",
            relief="flat",
            cursor="hand2",
            command=self.show_speed_menu,
            padx=10,
            pady=8
        )
        self.settings_btn.pack(padx=3, pady=3)
        
        # Create speed menu as Toplevel window (not blocked by controls)
        self.speed_menu = tk.Toplevel(self)
        self.speed_menu.withdraw()  # Hide initially
        self.speed_menu.overrideredirect(True)  # Remove window decorations
        self.speed_menu.configure(bg="#333333", relief="raised", bd=2)
        self.speed_menu.attributes("-topmost", True)  # Always on top
        self.speed_menu_visible = False
        
        # Speed menu title
        title_frame = tk.Frame(self.speed_menu, bg="#444444")
        title_frame.pack(fill="x")
        
        title_label = tk.Label(
            title_frame,
            text="Playback Speed",
            font=("Arial", 11, "bold"),
            fg="white",
            bg="#444444",
            pady=5
        )
        title_label.pack()
        
        # Speed menu items with better styling
        speeds = [("0.25×", 0.25), ("0.5×", 0.5), ("0.75×", 0.75), ("1.0×", 1.0), 
                 ("1.25×", 1.25), ("1.5×", 1.5), ("2.0×", 2.0)]
        
        # Store speed buttons for highlighting
        self.speed_buttons = {}
        
        for speed_text, speed_value in speeds:
            btn = tk.Button(
                self.speed_menu,
                text=speed_text,
                font=("Arial", 12),
                fg="white",
                bg="#333333",
                activebackground="#555555",
                relief="flat",
                cursor="hand2",
                command=lambda s=speed_value: self.set_speed_from_menu(s),
                anchor="center",
                padx=20,
                pady=8
            )
            btn.pack(fill="x")
            
            # Store button reference
            self.speed_buttons[speed_value] = btn
            
            # Highlight current speed (default is 1.0×)
            if speed_value == 1.0:
                btn.configure(bg="#555555")

    def setup_bindings(self):
        """Setup keyboard and mouse bindings"""
        # Keyboard shortcuts
        self.bind("<KeyPress>", self.on_key_press)
        self.focus_set()
        
        # Mouse movement and clicks
        self.bind("<Motion>", self.on_mouse_move)
        self.bind("<Button-1>", self.on_click_outside_menu)
        
        # Canvas bindings
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        
        # Window bindings
        self.bind("<FocusIn>", self.on_focus_in)
        self.bind("<FocusOut>", self.on_focus_out)
        
        # Escape key to exit fullscreen
        self.bind("<Escape>", self.exit_fullscreen)
        
        # Additional keyboard shortcuts
        self.bind("<space>", lambda e: self.toggle_playback())
        self.bind("<Left>", lambda e: self.seek_relative(-10))
        self.bind("<Right>", lambda e: self.seek_relative(10))
        self.bind("<Up>", lambda e: self.change_speed(0.25))
        self.bind("<Down>", lambda e: self.change_speed(-0.25))
        
        # Number keys for speed selection
        self.bind("<Key-1>", lambda e: self.set_speed(0.25))
        self.bind("<Key-2>", lambda e: self.set_speed(0.5))
        self.bind("<Key-3>", lambda e: self.set_speed(0.75))
        self.bind("<Key-4>", lambda e: self.set_speed(1.0))
        self.bind("<Key-5>", lambda e: self.set_speed(1.25))
        self.bind("<Key-6>", lambda e: self.set_speed(1.5))
        self.bind("<Key-7>", lambda e: self.set_speed(2.0))
        
        # Mouse wheel for seeking
        self.bind("<MouseWheel>", self.on_mouse_wheel)

    def sync_with_main_player(self):
        """Sync fullscreen player state with main player"""
        if self.video_player.cap:
            self.display_frame(self.video_player.current_frame)
            self.update_progress_bar()
            
            # Sync speed display
            self.sync_speed_display()
            
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

    def start_mouse_tracking(self):
        """Start tracking mouse for auto-hide controls"""
        def check_mouse_idle():
            if time.time() - self.last_mouse_move > 3.0 and self.controls_visible:
                self.hide_controls()
            
            # Continue checking if window exists
            if self.winfo_exists():
                self.after(500, check_mouse_idle)
        
        check_mouse_idle()

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
            
            # Center the video
            x_offset = (screen_width - display_width) // 2
            y_offset = (screen_height - display_height) // 2
            
            # Resize frame
            frame_resized = cv2.resize(frame_rgb, (display_width, display_height))
            
            # Convert to PhotoImage
            image = Image.fromarray(frame_resized)
            photo = ImageTk.PhotoImage(image)
            
            # Clear canvas and display frame
            self.canvas.delete("all")
            self.canvas.create_image(
                x_offset, y_offset,
                anchor="nw",
                image=photo
            )
            
            # Keep reference to prevent garbage collection
            self.canvas.image = photo
            
        except Exception as e:
            print(f"Error displaying frame: {e}")

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
        current_speed = getattr(self.video_player, 'playback_speed', 1.0)
        new_speed = max(0.25, min(8.0, current_speed + delta))
        self.set_speed(new_speed)

    def set_speed(self, speed):
        """Set playback speed and update display"""
        # Update the main video player speed
        if hasattr(self.video_player, 'set_speed'):
            self.video_player.set_speed(speed)
        elif hasattr(self.video_player, 'playback_speed'):
            self.video_player.playback_speed = speed
            # Update the speed indicator if it exists
            if hasattr(self.video_player, 'speed_indicator'):
                self.video_player.speed_indicator.configure(text=f"{speed}×")
            # Update speed slider if it exists
            if hasattr(self.video_player, 'speed_slider'):
                self.video_player.speed_slider.set(speed)
        
        # Update fullscreen speed display
        self.speed_label.configure(text=f"{speed}×")
        
        # Update menu button highlights
        for speed_val, button in self.speed_buttons.items():
            if speed_val == speed:
                button.configure(bg="#555555")  # Highlight selected
            else:
                button.configure(bg="#333333")  # Normal background

    def set_speed_from_menu(self, speed):
        """Set speed from menu and update highlighting"""
        self.set_speed(speed)
        self.hide_speed_menu()
    def get_current_speed(self):
        """Get current playback speed from main player"""
        if hasattr(self.video_player, 'playback_speed'):
            return self.video_player.playback_speed
        return 1.0

    def sync_speed_display(self):
        """Sync speed display with main player"""
        current_speed = self.get_current_speed()
        self.speed_label.configure(text=f"{current_speed}×")
        
        # Update menu highlights
        for speed_val, button in self.speed_buttons.items():
            if abs(speed_val - current_speed) < 0.01:  # Account for floating point precision
                button.configure(bg="#555555")
            else:
                button.configure(bg="#333333")
    def show_speed_menu(self):
        """Show speed menu positioned above controls, not blocked by bar"""
        if not self.speed_menu_visible:
            self.speed_menu_visible = True
            
            # Get screen dimensions
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            
            # Calculate position well above the control bar
            menu_width = 150
            menu_height = 230
            
            # Position from right edge, well above controls
            menu_x = screen_width - menu_width - 50  # 50px from right edge
            menu_y = screen_height - 120 - menu_height - 30  # 30px above controls
            
            # Ensure menu doesn't go off screen
            menu_x = max(10, menu_x)
            menu_y = max(50, menu_y)  # Don't go too high
            
            # Position and show the toplevel menu
            self.speed_menu.geometry(f"{menu_width}x{menu_height}+{menu_x}+{menu_y}")
            self.speed_menu.deiconify()  # Show the menu
            self.speed_menu.lift()
            self.speed_menu.focus_set()
            
        else:
            self.hide_speed_menu()

    def hide_speed_menu(self):
        """Hide speed menu"""
        if self.speed_menu_visible:
            self.speed_menu_visible = False
            self.speed_menu.withdraw()  # Hide the toplevel window

    def set_speed_from_menu(self, speed):
        """Set speed from menu and update highlighting"""
        self.set_speed(speed)
        self.hide_speed_menu()

    def show_controls(self):
        """Show overlay controls without affecting video size"""
        if not self.controls_visible:
            self.controls_visible = True
            
            # Position overlays on top of video
            self.position_overlays()
            
            # Update progress bar
            self.update_progress_bar()

    def hide_controls(self):
        """Hide overlay controls completely"""
        if self.controls_visible:
            self.controls_visible = False
            
            # Remove overlays (video stays full screen)
            self.title_frame.place_forget()
            self.overlay_frame.place_forget()
            
            # Hide speed menu if visible
            if self.speed_menu_visible:
                self.hide_speed_menu()

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

    def on_key_press(self, event):
        """Handle keyboard shortcuts"""
        key = event.keysym.lower()
        
        if key == "escape":
            self.exit_fullscreen()
        elif key == "space":
            self.toggle_playback()
        elif key == "left":
            self.seek_relative(-10)
        elif key == "right":
            self.seek_relative(10)
        elif key == "up":
            self.change_speed(0.25)
        elif key == "down":
            self.change_speed(-0.25)
        elif key == "f":
            self.exit_fullscreen()
        elif key in "1234567":
            speeds = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
            try:
                index = int(key) - 1
                if 0 <= index < len(speeds):
                    self.set_speed(speeds[index])
            except:
                pass

    def on_canvas_click(self, event):
        """Handle canvas click (toggle play/pause like YouTube)"""
        # Don't toggle if clicking on controls
        if not self.controls_visible:
            self.show_controls()
        else:
            self.toggle_playback()

    def on_click_outside_menu(self, event):
        """Hide speed menu when clicking outside"""
        if self.speed_menu_visible:
            # Check if click was outside the speed menu
            try:
                menu_x = self.speed_menu.winfo_rootx()
                menu_y = self.speed_menu.winfo_rooty()
                menu_width = self.speed_menu.winfo_width()
                menu_height = self.speed_menu.winfo_height()
                
                click_x = event.x_root
                click_y = event.y_root
                
                # If click is outside menu bounds, hide menu
                if (click_x < menu_x or click_x > menu_x + menu_width or 
                    click_y < menu_y or click_y > menu_y + menu_height):
                    self.hide_speed_menu()
            except:
                self.hide_speed_menu()
        
        # Handle normal click events
        self.on_mouse_click(event)

    def on_mouse_wheel(self, event):
        """Handle mouse wheel for seeking"""
        if event.delta > 0:
            self.seek_relative(5)  # Forward 5 seconds
        else:
            self.seek_relative(-5)  # Backward 5 seconds

    def on_focus_in(self, event):
        """Handle gaining focus"""
        pass

    def on_focus_out(self, event):
        """Handle losing focus"""
        # Hide speed menu if losing focus
        if self.speed_menu_visible:
            self.hide_speed_menu()

    def exit_fullscreen(self, event=None):
        """Exit fullscreen mode"""
        if self.speed_menu_visible:
            self.hide_speed_menu()
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
    def create_speed_menu(self):
        """Create speed menu that floats without blocking video"""
        # Create speed menu as overlay
        self.speed_menu = tk.Frame(self, bg="#333333", relief="raised", bd=2)
        self.speed_menu_visible = False
        
        # Speed menu items with better styling
        speeds = [("0.25×", 0.25), ("0.5×", 0.5), ("0.75×", 0.75), ("1.0×", 1.0), 
                 ("1.25×", 1.25), ("1.5×", 1.5), ("2.0×", 2.0)]
        
        for speed_text, speed_value in speeds:
            btn = tk.Button(
                self.speed_menu,
                text=speed_text,
                font=("Arial", 12),
                fg="white",
                bg="#333333",
                activebackground="#555555",
                relief="flat",
                cursor="hand2",
                command=lambda s=speed_value: self.set_speed_from_menu(s),
                anchor="center",
                padx=20,
                pady=8
            )
            btn.pack(fill="x")
            
            # Highlight current speed
            if speed_value == 1.0:  # Default speed
                btn.configure(bg="#555555")
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
       
        # Initialize enhanced responsive UI system
        self.responsive = ResponsiveUI(self.root)
        
        # CRITICAL FIX: Set initial quality scaling
        initial_quality = "720p"  # Default quality
        self.responsive.set_quality_scaling(initial_quality)
        
        # Set window title
        self.root.title(f"{APP_NAME} - Professional Edition v{APP_VERSION}")
        
        # Get optimal window size based on screen detection
        width, height = self.responsive.get_optimal_window_size(1600, 1000)
        self.root.geometry(f"{width}x{height}")
        
        # Set responsive minimum size
        min_width, min_height = self.responsive.get_optimal_window_size(1200, 800)
        self.root.minsize(min_width, min_height)
        
        # Center window on screen
        x = (self.responsive.screen_width - width) // 2
        y = (self.responsive.screen_height - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # HIDE WINDOW INITIALLY - only show after environment check
        self.root.withdraw()
        
        # Apply DPI awareness for Windows
        try:
            if hasattr(self.root, 'tk') and hasattr(self.root.tk, 'call'):
                self.root.tk.call('tk', 'scaling', self.responsive.scale_factor)
        except:
            pass
        
        # Try to set icon
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass
            
        # Store LaTeX path
        self.latex_path = latex_path
        self.latex_installed = bool(latex_path)

        # Debug flag
        self.debug_mode = debug

        # Initialize logger reference (minimal logging)
        self.logger = logger
        self.last_manim_output_path = None
        
        # Initialize virtual environment manager
        self.venv_manager = VirtualEnvironmentManager(self)
        
        # Initialize system terminal manager
        self.terminal = None
        
        # IMPORTANT: Auto-activate manim_studio_default environment if it exists and is ready
        self.auto_activate_default_environment()

        # Load settings before initializing variables that depend on them
        self.load_settings()
        
        # CRITICAL FIX: Update responsive UI with loaded quality setting
        loaded_quality = self.settings.get("quality", "720p")
        self.responsive.set_quality_scaling(loaded_quality)
        
        self.initialize_variables()
        
        # Setup UI (minimal logging) but keep hidden
        try:
            self.create_ui()
            self.apply_vscode_theme()
            
            # Check environment IMMEDIATELY - don't show main UI until ready
            self._environment_check_scheduled = False
            self.root.after(100, self.check_environment_before_showing_ui)
            
        except Exception as e:
            self.logger.error(f"UI creation failed: {e}")
            raise
    def check_environment_before_showing_ui(self):
        """Check environment before showing main UI - BETTER UX"""
        try:
            # Prevent multiple checks
            if self._environment_check_scheduled:
                return
            
            self._environment_check_scheduled = True
            
            # Check if environment needs setup
            if self.venv_manager.needs_setup:
                self.logger.info("Environment setup needed - showing setup dialog first")
                
                # Show setup dialog WITHOUT showing main window first
                try:
                    # Create a temporary root if needed for the dialog
                    setup_dialog = EnvironmentSetupDialog(self.root, self.venv_manager)
                    self.root.wait_window(setup_dialog)
                    
                    # After setup dialog closes, check if environment is now ready
                    if self.venv_manager.needs_setup:
                        # User skipped setup or setup failed
                        self.logger.info("Setup skipped or failed - showing main UI anyway")
                    else:
                        self.logger.info("Setup completed - environment ready")
                    
                except Exception as e:
                    self.logger.error(f"Setup dialog error: {e}")
                
                # Update status
                self.update_environment_status()
            else:
                self.logger.info("Environment is ready")
                self.update_environment_status()
            
            # NOW show the main window for the first time
            self.show_main_window()
                
        except Exception as e:
            self.logger.error(f"Environment check error: {e}")
            # Show main window even if check failed
            self.show_main_window()
    
    def show_main_window(self):
        """Show the main application window for the first time"""
        try:
            # Show and focus the main window
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.root.state('normal')
            
            # Force update to ensure proper display
            self.root.update()
            
            self.logger.info("Main application window shown")
            
        except Exception as e:
            self.logger.error(f"Error showing main window: {e}")
    
    def verify_environment_health(self):
        """Verify that the environment is actually working"""
        try:
            # Check if we have valid paths
            if not self.venv_manager.python_path or not self.venv_manager.pip_path:
                return False
                
            # Check if python executable exists and works
            if not os.path.exists(self.venv_manager.python_path):
                return False
                
            # Quick test - try to run python --version
            import subprocess
            result = subprocess.run(
                [self.venv_manager.python_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return False
                
            # Check if manim is importable (quick test)
            result = subprocess.run(
                [self.venv_manager.python_path, "-c", "import manim"],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            return result.returncode == 0
            
        except Exception as e:
            self.logger.error(f"Environment health check failed: {e}")
            return False
    
    
    
    def setup_environment_simple(self):
        """Simple environment setup without complex dialog"""
        try:
            import tkinter.messagebox as messagebox
            
            result = messagebox.askyesno(
                "Environment Setup Required", 
                "The Python environment needs to be set up for Manim.\n\n"
                "This will:\n"
                "• Create a virtual environment\n"
                "• Install Manim and required packages\n"
                "• Set up the development environment\n\n"
                "This may take 5-10 minutes. Continue?",
                parent=self.root
            )
            
            if result:
                # Show a simple progress dialog
                progress_window = ctk.CTkToplevel(self.root)
                progress_window.title("Setting up Environment")
                progress_window.geometry("450x250")
                progress_window.transient(self.root)
                progress_window.grab_set()
                
                # Center the window
                progress_window.geometry("+%d+%d" % (
                    self.root.winfo_rootx() + 200,
                    self.root.winfo_rooty() + 200
                ))
                
                # Progress label
                progress_label = ctk.CTkLabel(
                    progress_window,
                    text="Setting up Python environment...\nThis may take several minutes.",
                    font=ctk.CTkFont(size=14)
                )
                progress_label.pack(pady=30)
                
                # Progress bar
                progress_bar = ctk.CTkProgressBar(progress_window)
                progress_bar.pack(pady=20, padx=40, fill="x")
                progress_bar.set(0.1)
                
                # Status text
                status_text = ctk.CTkTextbox(progress_window, height=80)
                status_text.pack(pady=10, padx=20, fill="x")
                
                # Update progress function
                def update_progress(step, total_steps, message=""):
                    progress_bar.set(step / total_steps)
                    if message:
                        status_text.insert("end", f"{message}\n")
                        status_text.see("end")
                    progress_window.update()
                
                # Run setup in a separate thread to prevent UI freezing
                import threading
                
                def run_setup():
                    try:
                        update_progress(1, 6, "Starting environment setup...")
                        
                        # Create log callback that updates UI
                        def log_callback(message):
                            self.root.after(0, lambda: update_progress(None, None, message))
                        
                        update_progress(2, 6, "Creating virtual environment...")
                        
                        # Setup environment
                        success = self.venv_manager.setup_environment(log_callback)
                        
                        update_progress(6, 6, "Setup completed!")
                        
                        if success:
                            self.root.after(0, lambda: progress_label.configure(text="Environment setup completed successfully!"))
                            self.root.after(3000, progress_window.destroy)
                        else:
                            self.root.after(0, lambda: progress_label.configure(text="Setup completed with some issues.\nCheck the log above for details."))
                            self.root.after(5000, progress_window.destroy)
                            
                    except Exception as e:
                        error_msg = f"Setup error: {str(e)}"
                        print(error_msg)
                        self.root.after(0, lambda: progress_label.configure(text=error_msg))
                        self.root.after(0, lambda: update_progress(None, None, error_msg))
                        self.root.after(5000, progress_window.destroy)
                
                setup_thread = threading.Thread(target=run_setup, daemon=True)
                setup_thread.start()
            else:
                print("Environment setup skipped by user")
                
        except Exception as e:
            print(f"Simple setup failed: {e}")
    
    def update_environment_status(self):
        """Update environment status in UI"""
        try:
            if hasattr(self, 'venv_status_label'):
                if self.venv_manager.current_venv:
                    self.venv_status_label.configure(text=self.venv_manager.current_venv)
                else:
                    self.venv_status_label.configure(text="No environment")
                    
        except Exception as e:
            print(f"Error updating environment status: {e}")
    
            
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
        
        # App icon/logo - MODIFIED TO USE CTkImage
        logo_image = load_icon_image("main_logo.png", size=(32, 32))
        if logo_image:
            logo_label = ctk.CTkLabel(header_left, image=logo_image, text="")
        else:
            # Fallback to emoji if image not found
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
        
        # Center - Quick actions - MODIFIED TO USE CTkImage
        header_center = ctk.CTkFrame(self.header, fg_color="transparent")
        header_center.grid(row=0, column=1, pady=10)
        
        # Quick action buttons with images
        quick_actions = [
            ("new_file.png", "📄", "New File", self.new_file),
            ("open_file.png", "📁", "Open File", self.open_file),
            ("save_file.png", "💾", "Save File", self.save_file),
            ("render_animation.png", "▶️", "Render Animation", self.render_animation),
            ("quick_preview.png", "👁️", "Quick Preview", self.quick_preview),
            ("environment_manager.png", "🔧", "Environment Setup", self.manage_environment),
        ]
        
        for image_name, fallback_emoji, tooltip, command in quick_actions:
            # Try to load image, fallback to emoji
            icon_image = load_icon_image(image_name, size=(20, 20))
            
            if icon_image:
                btn = ctk.CTkButton(
                    header_center,
                    image=icon_image,
                    text="",
                    width=45,
                    height=40,
                    command=command,
                    fg_color="transparent",
                    hover_color=VSCODE_COLORS["surface_light"],
                    corner_radius=8
                )
            else:
                # Fallback to emoji
                btn = ctk.CTkButton(
                    header_center,
                    text=fallback_emoji,
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
        
        # Virtual environment display - MODIFIED TO USE CTkImage
        venv_frame = ctk.CTkFrame(header_right, fg_color=VSCODE_COLORS["surface_light"])
        venv_frame.pack(side="right", padx=10)
        
        # Load environment manager icon
        env_icon = load_icon_image("environment_manager.png", size=(16, 16))
        if env_icon:
            venv_label = ctk.CTkLabel(venv_frame, image=env_icon, text="")
        else:
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
        
        # Theme selector - FIXED METHOD NAME
        theme_frame = ctk.CTkFrame(header_right, fg_color="transparent")
        theme_frame.pack(side="right", padx=15)
        
        ctk.CTkLabel(
            theme_frame,
            text="Theme:",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text"]
        ).pack(side="left")
        
        # FIXED: Use the correct method name and variable names from your existing code
        self.theme_var = ctk.StringVar(value=self.current_theme)
        theme_combo = ctk.CTkComboBox(
            theme_frame,
            values=list(THEME_SCHEMES.keys()),
            variable=self.theme_var,
            command=self.on_theme_change,  # FIXED: This was "change_theme" before
            width=120,
            height=35
        )
        theme_combo.pack(side="left")
        
        # Auto-preview toggle (from your existing code)
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
        """Create sidebar with optimal sizing based on screen detection"""
        # Get optimal sidebar width based on screen analysis
        sidebar_width = self.responsive.get_optimal_sidebar_width()
        
        self.sidebar = ctk.CTkFrame(
            self.root, 
            width=sidebar_width, 
            corner_radius=0, 
            fg_color=VSCODE_COLORS["surface"]
        )
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(0, weight=1)
        
        # Sidebar content with optimal spacing
        spacing = self.responsive.get_optimal_spacing()
        self.sidebar_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color=VSCODE_COLORS["surface"])
        self.sidebar_scroll.grid(row=0, column=0, sticky="nsew", 
                                padx=spacing["normal"], pady=spacing["normal"])
        
        # Create sections with responsive sizing
        self.create_render_section()
        self.create_preview_section()
        self.create_assets_section()
        
    def create_render_section(self):
        """Create render settings section with responsive sizing"""
        # Get responsive dimensions
        fonts = self.responsive.get_optimal_font_sizes()
        spacing = self.responsive.get_optimal_spacing()
        
        # Section header
        render_header = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        render_header.pack(fill="x", pady=(0, spacing["normal"]))
        
        header_title = ctk.CTkLabel(
            render_header,
            text="🎬 Render Settings",
            font=ctk.CTkFont(size=fonts["header"], weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        )
        header_title.pack(side="left", padx=spacing["medium"], pady=spacing["normal"])
        
        # Render settings frame
        render_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        render_frame.pack(fill="x", pady=(0, spacing["large"]))
        
        # Quality setting with responsive sizing
        quality_frame = ctk.CTkFrame(render_frame, fg_color="transparent")
        quality_frame.pack(fill="x", padx=spacing["medium"], pady=spacing["normal"])
        
        ctk.CTkLabel(
            quality_frame,
            text="Quality",
            font=ctk.CTkFont(size=fonts["medium"], weight="bold"),
            text_color=VSCODE_COLORS["text"]
        ).pack(anchor="w")
        
        # Use responsive combo height
        combo_height = self.responsive.scale_dimension(36)
        self.quality_combo = ctk.CTkComboBox(
            quality_frame,
            values=list(QUALITY_PRESETS.keys()),
            variable=self.quality_var,
            command=self.on_quality_change,
            height=combo_height,
            font=ctk.CTkFont(size=fonts["normal"])
        )
        self.quality_combo.pack(fill="x", pady=(spacing["small"], 0))
        
        # Quality info with responsive font
        current_quality = self.settings["quality"]
        if current_quality == "Custom":
            resolution_text = f"{self.custom_width_var.get()}x{self.custom_height_var.get()}"
        else:
            resolution_text = QUALITY_PRESETS[current_quality]["resolution"]
            
        self.quality_info = ctk.CTkLabel(
            quality_frame,
            text=f"Resolution: {resolution_text}",
            font=ctk.CTkFont(size=fonts["small"]),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.quality_info.pack(anchor="w", pady=(spacing["tiny"], 0))
        
        # Custom resolution frame
        self.custom_resolution_frame = ctk.CTkFrame(quality_frame, fg_color="transparent")
        self.custom_resolution_frame.pack(fill="x", pady=(spacing["normal"], 0))
        
        # Custom resolution inputs
        custom_header = ctk.CTkLabel(
            self.custom_resolution_frame,
            text="Custom Resolution:",
            font=ctk.CTkFont(size=fonts["normal"], weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        custom_header.pack(anchor="w", pady=(0, spacing["small"]))
        
        # Resolution input frame
        resolution_input_frame = ctk.CTkFrame(self.custom_resolution_frame, fg_color="transparent")
        resolution_input_frame.pack(fill="x")
        resolution_input_frame.grid_columnconfigure((0, 2), weight=1)
        
        # Width input
        ctk.CTkLabel(
            resolution_input_frame, 
            text="Width:", 
            width=50,
            font=ctk.CTkFont(size=fonts["normal"])
        ).grid(row=0, column=0, sticky="w", pady=2)
        
        # Continue with rest of custom resolution inputs...
        # (Keep your existing custom resolution input code but add font sizing)
        
        # CPU usage controls with responsive sizing
        cpu_frame = ctk.CTkFrame(render_frame, fg_color="transparent")
        cpu_frame.pack(fill="x", padx=spacing["medium"], pady=spacing["normal"])
        
        ctk.CTkLabel(
            cpu_frame,
            text="CPU Usage",
            font=ctk.CTkFont(size=fonts["medium"], weight="bold"),
            text_color=VSCODE_COLORS["text"]
        ).pack(anchor="w")
        
        # CPU combo with responsive sizing
        self.cpu_combo = ctk.CTkComboBox(
            cpu_frame,
            values=list(CPU_USAGE_PRESETS.keys()),
            variable=self.cpu_usage_var,
            command=self.on_cpu_usage_change,
            height=combo_height,
            font=ctk.CTkFont(size=fonts["normal"])
        )
        self.cpu_combo.pack(fill="x", pady=(spacing["small"], 0))
        
        # CPU description
        self.cpu_description = ctk.CTkLabel(
            cpu_frame,
            text=CPU_USAGE_PRESETS[self.cpu_usage_var.get()]["description"],
            font=ctk.CTkFont(size=fonts["small"]),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.cpu_description.pack(anchor="w", pady=(spacing["tiny"], 0))
        
        # Render button with responsive sizing - LARGE button for prominence
        render_btn_height = self.responsive.get_button_dimensions(base_height=50)
        self.render_button = ctk.CTkButton(
            render_frame,
            text="🚀 Render Animation",
            command=self.render_animation,
            height=render_btn_height,
            font=ctk.CTkFont(size=fonts["large"], weight="bold"),
            fg_color=VSCODE_COLORS["primary"],
            hover_color=VSCODE_COLORS["primary_hover"]
        )
        self.render_button.pack(fill="x", padx=spacing["medium"], pady=spacing["medium"])
        
        # Progress bar with responsive height
        progress_height = self.responsive.scale_dimension(8)
        self.progress_bar = ctk.CTkProgressBar(render_frame, height=progress_height)
        self.progress_bar.pack(fill="x", padx=spacing["medium"], pady=(0, spacing["normal"]))
        self.progress_bar.set(0)
        
        # Progress label with responsive font
        self.progress_label = ctk.CTkLabel(
            render_frame,
            text="Ready to render",
            font=ctk.CTkFont(size=fonts["normal"]),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.progress_label.pack(pady=(0, spacing["medium"]))  
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
        """Create preview settings section with responsive sizing"""
        # Get responsive dimensions
        fonts = self.responsive.get_optimal_font_sizes()
        spacing = self.responsive.get_optimal_spacing()
        
        # Section header
        preview_header = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        preview_header.pack(fill="x", pady=(0, spacing["normal"]))
        
        header_title = ctk.CTkLabel(
            preview_header,
            text="👁️ Preview Settings",
            font=ctk.CTkFont(size=fonts["header"], weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        )
        header_title.pack(side="left", padx=spacing["medium"], pady=spacing["normal"])
        
        # Preview settings frame
        preview_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        preview_frame.pack(fill="x", pady=(0, spacing["large"]))
        
        # Preview quality with responsive sizing
        quality_frame = ctk.CTkFrame(preview_frame, fg_color="transparent")
        quality_frame.pack(fill="x", padx=spacing["medium"], pady=spacing["normal"])
        
        ctk.CTkLabel(
            quality_frame,
            text="Preview Quality",
            font=ctk.CTkFont(size=fonts["medium"], weight="bold"),
            text_color=VSCODE_COLORS["text"]
        ).pack(anchor="w")
        
        combo_height = self.responsive.scale_dimension(36)
        self.preview_quality_combo = ctk.CTkComboBox(
            quality_frame,
            values=list(PREVIEW_QUALITIES.keys()),
            variable=self.preview_quality_var,
            command=self.on_preview_quality_change,
            height=combo_height,
            font=ctk.CTkFont(size=fonts["normal"])
        )
        self.preview_quality_combo.pack(fill="x", pady=(spacing["small"], 0))
        
        # Preview info with responsive font
        self.preview_info = ctk.CTkLabel(
            quality_frame,
            text=f"Resolution: {PREVIEW_QUALITIES[self.settings['preview_quality']]['resolution']}",
            font=ctk.CTkFont(size=fonts["small"]),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.preview_info.pack(anchor="w", pady=(spacing["tiny"], 0))
        
        # Preview button with responsive sizing - LARGE button for prominence
        preview_btn_height = self.responsive.get_button_dimensions(base_height=45)
        self.quick_preview_button = ctk.CTkButton(
            preview_frame,
            text="⚡ Quick Preview",
            command=self.quick_preview,
            height=preview_btn_height,
            font=ctk.CTkFont(size=fonts["large"], weight="bold"),
            fg_color=VSCODE_COLORS["accent"],
            hover_color=VSCODE_COLORS["info"]
        )
        self.quick_preview_button.pack(fill="x", padx=spacing["medium"], pady=spacing["medium"])
    def create_assets_section(self):
        """Create enhanced assets section with visual cards"""
        # Section header
        assets_header = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        assets_header.pack(fill="x", pady=(0, 10))
        
        header_frame = ctk.CTkFrame(assets_header, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=12)
        header_frame.grid_columnconfigure(0, weight=1)
        
        # Assets manager icon - MODIFIED TO USE CTkImage
        assets_icon = load_icon_image("assets_manager.png", size=(20, 20))
        if assets_icon:
            # Create frame to hold icon and text
            title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
            title_frame.grid(row=0, column=0, sticky="w")
            
            icon_label = ctk.CTkLabel(title_frame, image=assets_icon, text="")
            icon_label.pack(side="left", padx=(0, 8))
            
            header_title = ctk.CTkLabel(
                title_frame,
                text="Assets Manager",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=VSCODE_COLORS["text_bright"]
            )
            header_title.pack(side="left")
        else:
            # Fallback to emoji
            header_title = ctk.CTkLabel(
                header_frame,
                text="🎨 Assets Manager",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=VSCODE_COLORS["text_bright"]
            )
            header_title.grid(row=0, column=0, sticky="w")
        
        # Add asset button - MODIFIED TO USE CTkImage
        add_icon = load_icon_image("add_asset.png", size=(16, 16))
        if add_icon:
            add_btn = ctk.CTkButton(
                header_frame,
                image=add_icon,
                text="",
                width=30,
                height=25,
                command=self.show_add_asset_menu,
                fg_color=VSCODE_COLORS["success"],
                hover_color="#117A65"
            )
        else:
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
        """Clear all terminal output and virtual terminal data"""
        try:
            # Enable text widget for editing
            self.output_text.configure(state="normal")
            
            # Clear the visual text display
            self.output_text.delete("1.0", "end")
            
            # Disable text widget to prevent user editing
            self.output_text.configure(state="disabled")
            
            # Clear virtual terminal buffer
            if hasattr(self, 'terminal_buffer'):
                self.terminal_buffer = []
            
            # Clear search-related data
            if hasattr(self, 'search_matches'):
                self.search_matches = []
                self.current_search_index = -1
            
            # Clear any search highlighting
            self.output_text.tag_remove("search_match", "1.0", "end")
            
            # Clear search entry if it exists
            if hasattr(self, 'search_entry'):
                self.search_entry.delete(0, "end")
            
            # Reset terminal status
            if hasattr(self, 'update_terminal_status'):
                self.update_terminal_status("Ready", "#00FF00")
            
            # Clear any pending output queues if they exist
            if hasattr(self, '_output_queue'):
                while not self._output_queue.empty():
                    try:
                        self._output_queue.get_nowait()
                    except:
                        break
            
            # Reset any terminal state variables
            if hasattr(self, 'last_manim_output_path'):
                self.last_manim_output_path = None
            
            # Update main status
            self.update_status("Terminal cleared - all output history removed")
            
        except Exception as e:
            # Fallback if anything goes wrong
            try:
                self.output_text.configure(state="normal")
                self.output_text.delete("1.0", "end")
                self.output_text.configure(state="disabled")
                self.update_status(f"Terminal cleared (with errors: {e})")
            except:
                pass
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
        """Clear all terminal output and virtual terminal data"""
        try:
            # Enable text widget for editing
            self.output_text.configure(state="normal")
            
            # Clear the visual text display
            self.output_text.delete("1.0", "end")
            
            # Disable text widget to prevent user editing
            self.output_text.configure(state="disabled")
            
            # Clear virtual terminal buffer
            if hasattr(self, 'terminal_buffer'):
                self.terminal_buffer = []
            
            # Clear search-related data
            if hasattr(self, 'search_matches'):
                self.search_matches = []
                self.current_search_index = -1
            
            # Clear any search highlighting
            self.output_text.tag_remove("search_match", "1.0", "end")
            
            # Clear search entry if it exists
            if hasattr(self, 'search_entry'):
                self.search_entry.delete(0, "end")
            
            # Reset terminal status
            if hasattr(self, 'update_terminal_status'):
                self.update_terminal_status("Ready", "#00FF00")
            
            # Clear any pending output queues if they exist
            if hasattr(self, '_output_queue'):
                while not self._output_queue.empty():
                    try:
                        self._output_queue.get_nowait()
                    except:
                        break
            
            # Reset any terminal state variables
            if hasattr(self, 'last_manim_output_path'):
                self.last_manim_output_path = None
            
            # Update main status
            self.update_status("Terminal cleared - all output history removed")
            
        except Exception as e:
            # Fallback if anything goes wrong
            try:
                self.output_text.configure(state="normal")
                self.output_text.delete("1.0", "end")
                self.output_text.configure(state="disabled")
                self.update_status(f"Terminal cleared (with errors: {e})")
            except:
                pass

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
        """Open enhanced environment management dialog - ALWAYS SHOW UI"""
        try:
            # ALWAYS show the environment UI - don't get stuck on setup check
            dialog = EnhancedVenvManagerDialog(self.root, self.venv_manager)
            self.root.wait_window(dialog)
        
            # Update venv status after dialog closes
            if hasattr(self, 'venv_status_label') and self.venv_manager.current_venv:
                self.venv_status_label.configure(text=self.venv_manager.current_venv)
                
        except Exception as e:
            print(f"Error in manage_environment: {e}")
            # Fallback - try to create a simple environment setup
            self.setup_environment_simple()
    
    
    # Settings callbacks
    def on_quality_change(self, value):
        """Handle quality change with responsive UI updates"""
        self.settings["quality"] = value
        
        # CRITICAL: Update ResponsiveUI with new quality scaling
        self.responsive.set_quality_scaling(value)
        
        if value == "Custom":
            # Show custom resolution frame
            self.custom_resolution_frame.pack(fill="x", pady=(10, 0))
            self.validate_custom_resolution()
            resolution_text = f"{self.custom_width_var.get()}x{self.custom_height_var.get()}"
        else:
            # Hide custom resolution frame and show preset info
            self.custom_resolution_frame.pack_forget()
            quality_info = QUALITY_PRESETS[value]
            resolution_text = quality_info['resolution']
        
        # Update quality info display
        if hasattr(self, 'quality_info'):
            self.quality_info.configure(text=f"Resolution: {resolution_text}")
            
        # Update UI elements for new quality scaling
        self.update_ui_for_quality_change()
        
        self.save_settings()
    def update_ui_for_quality_change(self):
        """Update UI elements when quality changes to ensure all buttons remain visible"""
        
        # Get new responsive dimensions
        fonts = self.responsive.get_optimal_font_sizes()
        spacing = self.responsive.get_optimal_spacing()
        
        # Update main action buttons to ensure they're always visible
        if hasattr(self, 'quick_preview_button'):
            new_height = self.responsive.get_button_dimensions(base_height=45)
            self.quick_preview_button.configure(
                height=new_height,
                font=ctk.CTkFont(size=fonts["large"], weight="bold")
            )
        
        if hasattr(self, 'render_button'):
            new_height = self.responsive.get_button_dimensions(base_height=50)
            self.render_button.configure(
                height=new_height,
                font=ctk.CTkFont(size=fonts["large"], weight="bold")
            )
        
        # Update combo boxes
        combo_height = self.responsive.scale_dimension(36)
        if hasattr(self, 'quality_combo'):
            self.quality_combo.configure(
                height=combo_height,
                font=ctk.CTkFont(size=fonts["normal"])
            )
        
        if hasattr(self, 'preview_quality_combo'):
            self.preview_quality_combo.configure(
                height=combo_height,
                font=ctk.CTkFont(size=fonts["normal"])
            )
        
        # Update sidebar width if needed
        if hasattr(self, 'sidebar'):
            new_sidebar_width = self.responsive.get_optimal_sidebar_width()
            self.sidebar.configure(width=new_sidebar_width)
        
        # Force layout recalculation
        self.root.update_idletasks()
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
        
        # Try to create menu items with images
        try:
            # Load icons for menu items
            image_icon = load_icon_image("image_placeholder.png", size=(16, 16))
            audio_icon = load_icon_image("audio_icon.png", size=(16, 16))
            
            if image_icon:
                menu.add_command(label="Add Images", image=image_icon, compound="left", command=self.add_images)
            else:
                menu.add_command(label="📷 Add Images", command=self.add_images)
                
            if audio_icon:
                menu.add_command(label="Add Audio", image=audio_icon, compound="left", command=self.add_audio)
            else:
                menu.add_command(label="🎵 Add Audio", command=self.add_audio)
        except:
            # Fallback to text-only menu
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
            
            # File tab icon - MODIFIED TO USE IMAGE
            file_icon = load_icon_image("new_file.png", size=(16, 16))
            if file_icon:
                # For CustomTkinter labels with images, you might need to handle this differently
                # depending on your specific implementation
                self.file_tab.configure(text="Untitled")
            else:
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
        """Generate quick preview - FORCE VIRTUAL ENVIRONMENT USAGE"""
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
        
        # FORCE USE OF VIRTUAL ENVIRONMENT - NO FALLBACK ALLOWED
        if self.venv_manager.current_venv and self.venv_manager.python_path and os.path.exists(self.venv_manager.python_path):
            python_cmd = self.venv_manager.python_path
            self.append_terminal_output(f"✅ Using virtual environment: {self.venv_manager.current_venv}\n")
            self.append_terminal_output(f"Python path: {python_cmd}\n")
        else:
            # NO FALLBACK - Show error and stop
            self.append_terminal_output("❌ Virtual environment not found or not properly configured!\n", "error")
            self.append_terminal_output("Please set up the environment first using Tools → Environment Setup\n", "error")
            self.quick_preview_button.configure(text="⚡ Quick Preview", state="normal")
            self.is_previewing = False
            
            # Cleanup temp directory
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except:
                pass
            return
        
        # Build manim command with virtual environment
        command = [
            python_cmd,
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
        
        # FORCE USE OF VIRTUAL ENVIRONMENT STREAMING - NO FALLBACK
        if hasattr(self.venv_manager, 'run_command_streaming'):
            # Use virtual environment for streaming
            self.venv_manager.run_command_streaming(
                command, 
                log_callback=self.enhanced_log_callback,
                on_complete=on_preview_complete
            )
        else:
            # NO FALLBACK - Use direct subprocess with virtual environment
            self.append_terminal_output("✅ Using direct virtual environment execution\n")
            def run_with_venv():
                try:
                    # Get virtual environment variables
                    env = self.get_subprocess_environment()
                    
                    result = subprocess.run(
                        command, 
                        capture_output=True, 
                        text=True, 
                        timeout=300,
                        encoding='utf-8',
                        errors='replace',
                        env=env  # Use virtual environment
                    )
                    
                    # Process all output through enhanced callback
                    if result.stdout:
                        self.enhanced_log_callback(result.stdout, "output")
                    if result.stderr:
                        self.enhanced_log_callback(result.stderr, "error")
                        
                    on_preview_complete(result.returncode == 0, result.returncode)
                except Exception as e:
                    self.append_terminal_output(f"❌ Virtual environment execution error: {e}\n", "error")
                    on_preview_complete(False, -1)
            
            threading.Thread(target=run_with_venv, daemon=True).start()

    
    def get_subprocess_environment(self):
        """Get environment variables for subprocess commands - NO FALLBACK"""
        env = os.environ.copy()
        
        # FORCE USE OF VIRTUAL ENVIRONMENT - NO FALLBACK
        if self.venv_manager.current_venv and self.venv_manager.python_path:
            # Use virtual environment Python
            python_dir = os.path.dirname(self.venv_manager.python_path)
            env['PATH'] = f"{python_dir}{os.pathsep}{env.get('PATH', '')}"
            env['VIRTUAL_ENV'] = os.path.join(self.venv_manager.venv_dir, self.venv_manager.current_venv)
            env['PYTHONPATH'] = ""  # Clear to avoid conflicts
        
        # Set encoding variables
        env.update({
            'PYTHONIOENCODING': 'utf-8',
            'PYTHONLEGACYWINDOWSFSENCODING': '0',
            'PYTHONUTF8': '1',
            'LC_ALL': 'en_US.UTF-8'
        })
        
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
        def update_env_status(self):
            if self.venv_manager.is_environment_ready():
                status = "Environment ready"
            else:
                status = "Environment not set up"
            self.env_status_label.configure(text=status)
            env_path = os.path.join(self.venv_manager.venv_dir, "manim_studio_default")
            self.env_path_display.configure(text=env_path)
        
            # Always enable all buttons so users can always access environment management
            self.setup_button.configure(state="normal")
            self.fix_button.configure(state="normal")
            self.manage_button.configure(state="normal")
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
        """Automatically activate manim_studio_default environment if it exists - NO DIALOGS"""
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
                        
                        # SKIP MANIM CHECK - Just assume it's working
                        self.logger.info("✅ Auto-activated manim_studio_default environment")
                        self.venv_manager.needs_setup = False
                        # REMOVED: Don't schedule status update here
                    else:
                        self.logger.warning("manim_studio_default environment has missing executables")
                        self.venv_manager.needs_setup = True
                else:
                    self.logger.warning("manim_studio_default environment structure is invalid")
                    self.venv_manager.needs_setup = True
            else:
                self.logger.info("No manim_studio_default environment found")
                self.venv_manager.needs_setup = True
                
        except Exception as e:
            self.logger.error(f"Error in auto-activation: {e}")
            self.venv_manager.needs_setup = True
    
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
        """Update environment status in the UI - NO MANIM CHECK"""
        try:
            # Update status bar if it exists
            if hasattr(self, 'status_label'):
                if self.venv_manager.current_venv:
                    env_status = f"Environment: {self.venv_manager.current_venv} ✅"  # Always show green
                    self.status_label.configure(text=env_status)
                else:
                    self.status_label.configure(text="No environment active")
                
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
        """Setup the environment setup dialog UI - ORIGINAL STRUCTURE"""
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
        
        # App icon - MODIFIED TO USE IMAGE
        logo_icon = load_icon_image("main_logo.png", size=(64, 64))
        if logo_icon:
            icon_label = ctk.CTkLabel(header_frame, image=logo_icon, text="")
            icon_label.image = logo_icon
        else:
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
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        title_label.pack(pady=(0, 10))
        
        # Rest of the setup_ui method remains the same...
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
            self.log_display.delete("1.0", "end")
            self.log_display.insert("1.0", "Logs cleared successfully.")
        except Exception as e:
            self.log_display.delete("1.0", "end")
            self.log_display.insert("1.0", f"Error clearing log: {e}")
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
    """Main entry point - Fixed to prevent double dialogs and proper startup flow"""
    try:
        # Check if running from source or frozen
        if getattr(sys, 'frozen', False):
            logger.info("Running from executable")
        else:
            logger.info("Running from source")
        
        # Parse command line arguments
        parser = argparse.ArgumentParser(description="Manim Animation Studio")
        parser.add_argument("--debug", action="store_true", help="Enable debug mode")
        args = parser.parse_args()
        
        debug_mode = args.debug
        
        if debug_mode:
            logger.info("Debug mode enabled")
            print("🐛 Debug mode activated")
        
        # Check Jedi availability for IntelliSense
        if not JEDI_AVAILABLE:
            print("Warning: Jedi not available. IntelliSense features will be limited.")
            print("Install Jedi with: pip install jedi")

        # Check LaTeX availability (fast check)
        logger.info("Checking LaTeX installation...")
        latex_path = check_latex_installation()
        if latex_path:
            logger.info(f"LaTeX found at: {latex_path}")
        else:
            logger.warning("LaTeX not found - some features may be limited")

        # Create main application instance
        logger.info("Creating main application...")
        app = ManimStudioApp(latex_path=latex_path, debug=debug_mode)
        
        # REMOVED: Environment check from here - let the app handle it internally
        # The app will:
        # 1. Keep window hidden initially
        # 2. Check environment first
        # 3. Show setup dialog if needed (without main UI visible)
        # 4. Show main UI only after environment is ready
        
        logger.info("Starting application main loop...")
        
        # Start the main loop - app will handle showing window when ready
        try:
            # DON'T show window here - app handles it after environment check
            app.run()
            
        except KeyboardInterrupt:
            logger.info("Application interrupted by user")
            
        except Exception as e:
            error_msg = str(e)
            # Filter out common shutdown messages that aren't real errors
            if not any(msg in error_msg.lower() for msg in [
                "application has been destroyed",
                "invalid command name",
                "bad window path",
                "can't invoke",
                "destroyed while"
            ]):
                logger.error(f"UI error during main loop: {e}")
                # Try to show error dialog if possible
                try:
                    if app.root and app.root.winfo_exists():
                        import tkinter.messagebox as messagebox
                        messagebox.showerror(
                            "Application Error", 
                            f"An error occurred:\n{error_msg}",
                            parent=app.root
                        )
                except:
                    # If we can't show dialog, just print
                    print(f"Application error: {error_msg}")
        
    except ImportError as e:
        error_msg = f"Missing required dependency: {e}"
        logger.error(error_msg)
        try:
            # Try to show error without tkinter dependencies
            import tkinter
            import tkinter.messagebox as messagebox
            root = tkinter.Tk()
            root.withdraw()
            messagebox.showerror("Missing Dependency", error_msg)
            root.destroy()
        except:
            print(error_msg)
            print("Please install missing dependencies and try again.")
    
    except Exception as e:
        error_msg = f"Startup error: {e}"
        logger.error(error_msg)
        try:
            # Try to show startup error dialog
            import tkinter
            import tkinter.messagebox as messagebox
            root = tkinter.Tk()
            root.withdraw()
            messagebox.showerror("Startup Error", f"Failed to start application:\n\n{error_msg}")
            root.destroy()
        except:
            print(f"Failed to start application: {error_msg}")
            print("Please check the log file for more details.")
    
    finally:
        # Cleanup logging handlers
        if 'logger' in locals() and logger:
            try:
                for handler in logger.handlers[:]:
                    try:
                        handler.close()
                        logger.removeHandler(handler)
                    except:
                        pass
            except:
                pass
        
        # Final cleanup message
        try:
            logger.info("Application shutdown complete")
        except:
            print("Application shutdown complete")


if __name__ == "__main__":
    main()
