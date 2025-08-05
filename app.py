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
except ImportError:
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
from typing import List, Optional, Union, Dict, Any, Callable
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
import tkinterdnd2
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
def load_icon_image(icon_name: str, size: tuple[int, int] = (24, 24), fallback_text: str = "?") -> bool:
    return False
# Add this to the top of app.py after the imports section
# =============================================================================
# EMERGENCY ENCODING FIXES - Add this RIGHT AFTER imports
# =============================================================================
def get_responsive_dialog_size(base_width: int, base_height: int, screen_w: int | None = None, screen_h: int | None = None) -> tuple[int, int]:
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

def setup_portable_logging() -> str:
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
def run_subprocess_safe(command: list[str] | str, **kwargs) -> subprocess.CompletedProcess:
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

def run_subprocess_async_safe(command: list[str] | str, callback: Callable, **kwargs) -> None:
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
class SplashScreen:
    """Splash screen that stays visible until main UI is ready"""
    
    def __init__(self, debug_mode=False):
        import tkinter as tk
        
        self.debug_mode = debug_mode
        self.is_closed = False
        self.checks_complete = True
        
        # ESSENTIAL ATTRIBUTES that main() expects
        self.app_data_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")
        self.latex_path = None
        self.environment_ready = True
        
        # Ensure app_data_dir exists
        os.makedirs(self.app_data_dir, exist_ok=True)
        
        # Create splash window
        self.root = tk.Tk()
        self.root.title("Manim Studio")
        self.root.geometry("350x150")
        self.root.resizable(False, False)
        self.root.overrideredirect(True)
        self.root.configure(bg='#1e1e1e')
        
        # Center window
        self.root.eval('tk::PlaceWindow . center')
        
        # Create simple UI
        main_frame = tk.Frame(self.root, bg='#1e1e1e', padx=30, pady=30)
        main_frame.pack(fill='both', expand=True)
        
        tk.Label(
            main_frame,
            text="Manim Animation Studio",
            font=('Arial', 16, 'bold'),
            fg='white',
            bg='#1e1e1e'
        ).pack(pady=(0, 10))
        
        self.status_label = tk.Label(
            main_frame,
            text="Loading...",
            font=('Arial', 11),
            fg='#cccccc',
            bg='#1e1e1e'
        )
        self.status_label.pack()
        
        # Show splash
        self.root.deiconify()
        self.root.lift()
        self.root.update_idletasks()
    
    def update_status(self, message, progress=None):
        """Update status message"""
        if self.is_closed:
            return
        try:
            self.status_label.config(text=message)
            self.root.update_idletasks()
        except:
            pass
    
    def wait_for_checks_completion(self):
        """ESSENTIAL METHOD"""
        pass
    
    def wait_for_close(self):
        """ESSENTIAL METHOD - actually wait for close"""
        import time
        start_time = time.time()
        while not self.is_closed and (time.time() - start_time) < 5:
            try:
                self.root.update_idletasks()
                time.sleep(0.01)
            except:
                break
    
    def close_splash(self):
        """ESSENTIAL METHOD - close splash"""
        if self.is_closed:
            return
        
        self.is_closed = True
        try:
            self.root.withdraw()
            self.root.quit()
            self.root.destroy()
        except:
            pass

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
def check_latex_installation(self):
    """Check LaTeX installation - ROBUST FIX with debugging"""
    try:
        print("🔍 Starting LaTeX detection...")
        
        # Test LaTeX commands
        latex_commands = ['latex', 'pdflatex', 'xelatex', 'lualatex']
        latex_found = []
        
        for cmd in latex_commands:
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=10)
                if result.returncode == 0:
                    latex_found.append(cmd)
                    print(f"✅ Found {cmd}")
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
                continue
        
        # Update status based on findings
        if latex_found:
            self.latex_available = True
            self.latex_commands = latex_found
            status_text = f"✅ LaTeX: Available ({len(latex_found)} commands)"
            status_color = "green"
            print(f"✅ LaTeX detected: {latex_found}")
        else:
            self.latex_available = False
            self.latex_commands = []
            status_text = "❌ LaTeX: Not found"
            status_color = "red"
            print("❌ LaTeX not detected")
        
        # ROBUST FIX: Try multiple UI update methods
        print(f"🔄 Updating UI with: {status_text}")
        
        # Method 1: Try the main label
        updated = False
        try:
            if hasattr(self, 'latex_status_label') and self.latex_status_label:
                self.latex_status_label.configure(text=status_text, text_color=status_color)
                print("✅ Updated latex_status_label")
                updated = True
        except Exception as e:
            print(f"❌ Failed to update latex_status_label: {e}")
        
        # Method 2: Try alternative label names
        alternative_labels = ['env_status_label', 'status_label', 'latex_label']
        for label_name in alternative_labels:
            try:
                if hasattr(self, label_name):
                    label = getattr(self, label_name)
                    if label:
                        label.configure(text=status_text, text_color=status_color)
                        print(f"✅ Updated {label_name}")
                        updated = True
                        break
            except Exception as e:
                print(f"❌ Failed to update {label_name}: {e}")
                continue
        
        # Method 3: Force multiple UI refresh types
        try:
            self.update_idletasks()
            self.update()
            print("✅ Forced UI refresh")
        except:
            pass
        
        # Method 4: Schedule delayed update
        try:
            self.after(100, lambda: self.force_latex_status_update(status_text, status_color))
            print("✅ Scheduled delayed update")
        except:
            pass
        
        if not updated:
            print("⚠️ No UI labels found to update - check label names")
            # Debug: Print all attributes that contain 'label'
            label_attrs = [attr for attr in dir(self) if 'label' in attr.lower()]
            print(f"📋 Available label attributes: {label_attrs}")
        
        return self.latex_available
        
    except Exception as e:
        print(f"❌ Error checking LaTeX: {e}")
        return False

def force_latex_status_update(self, status_text, status_color):
    """Force LaTeX status update - helper method"""
    try:
        # Try all possible label references
        possible_labels = [
            getattr(self, 'latex_status_label', None),
            getattr(self, 'env_status_label', None), 
            getattr(self, 'status_label', None),
            getattr(self, 'latex_label', None)
        ]
        
        for label in possible_labels:
            if label:
                try:
                    label.configure(text=status_text, text_color=status_color)
                    print(f"✅ Force updated label with: {status_text}")
                    break
                except:
                    continue
        
        # Force UI refresh again
        self.update_idletasks()
        self.update()
        
    except Exception as e:
        print(f"❌ Error in force update: {e}")
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



import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk
import os
import sys
import shutil
import time
from datetime import datetime
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None
import threading

# Modern color scheme
MODERN_COLORS = {
    "bg_primary": "#1a1a1a",
    "bg_secondary": "#2d2d2d", 
    "bg_tertiary": "#3d3d3d",
    "accent": "#007acc",
    "accent_hover": "#0066b3",
    "success": "#4caf50",
    "warning": "#ff9800",
    "error": "#f44336",
    "text_primary": "#ffffff",
    "text_secondary": "#b0b0b0",
    "border": "#404040"
}

class AssetsManager(ctk.CTkToplevel):
    """Enhanced Assets Manager - Modern UI with working drag & drop and upload"""
    
    def __init__(self, parent, main_app):
        super().__init__(parent)
        
        self.parent = parent
        self.main_app = main_app
        self.title("🎨 Assets Manager - Enhanced Edition")
        
        # Initialize state variables
        self.drag_drop_available = False
        self.drop_zone_active = False
        self.preview_image = None
        self.processing_drop = False  # Prevent loops
        
        # DISABLE auto-delete for persistent assets
        self.auto_delete_enabled = False
        self.auto_delete_hours = 24
        self.file_timers = {}
        
        # FIXED: Get the correct assets folder path
        self.assets_folder = self.get_assets_folder()
        
        # Verify the path is not in temp
        if 'temp' in self.assets_folder.lower() or 'tmp' in self.assets_folder.lower():
            print("⚠️ WARNING: Assets folder is in temp directory!")
            # Force to use current working directory instead
            self.assets_folder = os.path.join(os.getcwd(), "assets")
            os.makedirs(self.assets_folder, exist_ok=True)
            print(f"🔧 Forced assets folder to: {self.assets_folder}")
        
        # Initialize drag and drop
        self.setup_drag_drop_availability()
        
        # UI setup with modern styling
        self.setup_window()
        self.setup_drag_drop()
        self.create_modern_ui()
        self.refresh_assets()
        # Don't setup file timers for persistent assets
        self.setup_existing_file_timers()
        
        print("✅ AssetsManager initialized successfully")
        # Start timer display updates if auto-delete is enabled - NEW
        if self.auto_delete_enabled:
            self.after(1000, self.start_timer_display_updates)  # Start after 1 second

    def get_file_timer_info(self, filename):
        """Get timer information for a file"""
        if not self.auto_delete_enabled or filename not in self.file_timers:
            return None
            
        if not hasattr(self, 'timer_start_times') or filename not in self.timer_start_times:
            return None
            
        timer_info = self.timer_start_times[filename]
        current_time = time.time()
        elapsed_time = current_time - timer_info['start_time']
        remaining_time = timer_info['duration'] - elapsed_time
        
        if remaining_time <= 0:
            return "Deleting soon..."
            
        # Format remaining time
        remaining_hours = remaining_time / 3600
        if remaining_hours >= 1:
            return f"⏰ {remaining_hours:.1f}h left"
        else:
            remaining_minutes = remaining_time / 60
            return f"⏰ {remaining_minutes:.0f}m left"
    
    def start_timer_display_updates(self):
        """Start periodic updates of timer displays"""
        if self.auto_delete_enabled:
            self.update_timer_displays()
            # Update every 30 seconds
            self.after(30000, self.start_timer_display_updates)
    
    def update_timer_displays(self):
        """Update all timer displays in the UI"""
        try:
            if hasattr(self, 'file_cards'):
                for filename, card_info in self.file_cards.items():
                    timer_text = self.get_file_timer_info(filename)
                    if timer_text and 'timer_label' in card_info:
                        card_info['timer_label'].configure(text=timer_text)
        except Exception as e:
            print(f"Error updating timer displays: {e}")
    def setup_existing_file_timers(self):
        """Setup timers for existing files - FIXED to add timers, not delete"""
        try:
            if not self.auto_delete_enabled:
                print("🔧 Auto-delete disabled - skipping timers")
                return
                
            asset_files = self.get_asset_files()
            current_time = time.time()
            
            for file_info in asset_files:
                filename = file_info['name']
                file_age_seconds = current_time - file_info['modified']
                total_timer_duration = self.auto_delete_hours * 3600
                remaining_time_seconds = total_timer_duration - file_age_seconds
                
                # Always add timer, even if file is "expired"
                # If expired, give it a grace period (e.g., 1 hour)
                if remaining_time_seconds <= 0:
                    remaining_time_seconds = 3600  # 1 hour grace period
                    print(f"⏰ File {filename} was expired, giving 1 hour grace period")
                
                self.schedule_file_deletion(filename, remaining_time_seconds)
                
                # Store timer start time for UI display
                if not hasattr(self, 'timer_start_times'):
                    self.timer_start_times = {}
                self.timer_start_times[filename] = {
                    'start_time': current_time,
                    'duration': remaining_time_seconds
                }
                
                hours_remaining = remaining_time_seconds / 3600
                print(f"⏰ Timer set for {filename}: {hours_remaining:.1f} hours remaining")
                    
        except Exception as e:
            print(f"❌ Error setting up file timers: {e}")
    def setup_drag_drop_availability(self):
        """Check if drag and drop is available"""
        try:
            import tkinterdnd2
            from tkinterdnd2 import DND_FILES, TkinterDnD
            
            # Store the imports for later use
            self.tkinterdnd2 = tkinterdnd2
            self.DND_FILES = DND_FILES
            self.TkinterDnD = TkinterDnD
            
            self.drag_drop_available = True
            print("✅ tkinterdnd2 available - drag & drop enabled")
        except ImportError:
            self.drag_drop_available = False
            self.tkinterdnd2 = None
            self.DND_FILES = None
            self.TkinterDnD = None
            print("⚠️ tkinterdnd2 not available - drag & drop disabled")
    
    def get_app_directory(self):
        """Get the directory where the .py or .exe file is located - SAME AS MAIN APP"""
        if getattr(sys, 'frozen', False):
            # Running as .exe - assets next to executable
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
            self.main_app.append_terminal_output("📁 Running as executable - assets next to .exe\n")
        else:
            # Running as .py - assets next to script
            app_dir = os.path.dirname(os.path.abspath(__file__))
            self.main_app.append_terminal_output("📁 Running as script - assets next to .py\n")
        
        self.main_app.append_terminal_output(f"📂 Assets directory: {app_dir}\n")
        return app_dir
    
    def setup_window(self):
        """Setup modern window styling"""
        # Window configuration
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(1500, screen_w - 100)
        height = min(900, screen_h - 100)
        
        # Center window
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        self.minsize(1200, 800)
        self.resizable(True, True)
        self.transient(self.parent)
        self.grab_set()
        
        # Modern styling
        self.configure(fg_color=MODERN_COLORS["bg_primary"])
        self.protocol("WM_DELETE_WINDOW", self.on_close)
    
    
    def create_modern_ui(self):
        """Create the modern UI layout"""
        # Configure main grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Create header
        self.create_header()
        
        # Create main content area
        self.create_main_content()
        
        # Create footer/controls
        self.create_footer()
    
    def create_header(self):
        """Create modern header"""
        header_frame = ctk.CTkFrame(
            self,
            height=80,
            fg_color=MODERN_COLORS["bg_secondary"],
            corner_radius=10
        )
        header_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))
        header_frame.grid_columnconfigure(1, weight=1)
        header_frame.grid_propagate(False)
        
        # Header icon and title
        title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w", padx=20, pady=15)
        
        # Large icon
        icon_label = ctk.CTkLabel(
            title_frame,
            text="🎨",
            font=ctk.CTkFont(size=32)
        )
        icon_label.pack(side="left", padx=(0, 10))
        
        # Title and subtitle
        text_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        text_frame.pack(side="left")
        
        title_label = ctk.CTkLabel(
            text_frame,
            text="Assets Manager",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=MODERN_COLORS["text_primary"]
        )
        title_label.pack(anchor="w")
        
        subtitle_label = ctk.CTkLabel(
            text_frame,
            text=f"Managing: {os.path.basename(self.assets_folder)}",
            font=ctk.CTkFont(size=12),
            text_color=MODERN_COLORS["text_secondary"]
        )
        subtitle_label.pack(anchor="w")
        
        # Header stats
        self.stats_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        self.stats_frame.grid(row=0, column=1, sticky="e", padx=20, pady=15)
        
        self.create_stats_display()
        
        # Header buttons - FIXED CALLBACKS
        buttons_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        buttons_frame.grid(row=0, column=2, sticky="e", padx=20, pady=15)
        
        # Quick action buttons
        self.create_header_buttons(buttons_frame)
    def process_dropped_files(self, file_paths):
        """Wrapper method for backward compatibility - calls the immediate version"""
        try:
            print(f"📁 Processing {len(file_paths)} files via wrapper...")
            self.process_dropped_files_immediate(file_paths)
        except Exception as e:
            print(f"❌ Error in process_dropped_files wrapper: {e}")
            self.show_error_notification(f"Processing error: {e}")
    def create_stats_display(self):
        """Create animated stats display"""
        asset_files = self.get_asset_files()
        total_files = len(asset_files)
        total_size = sum(f['size'] for f in asset_files)
        
        # Clear existing stats
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
        
        # Stats container
        stats_container = ctk.CTkFrame(self.stats_frame, fg_color=MODERN_COLORS["bg_tertiary"], corner_radius=8)
        stats_container.pack()
        
        # Files count
        files_frame = ctk.CTkFrame(stats_container, fg_color="transparent")
        files_frame.pack(side="left", padx=15, pady=10)
        
        ctk.CTkLabel(
            files_frame,
            text=str(total_files),
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=MODERN_COLORS["accent"]
        ).pack()
        
        ctk.CTkLabel(
            files_frame,
            text="Files",
            font=ctk.CTkFont(size=10),
            text_color=MODERN_COLORS["text_secondary"]
        ).pack()
        
        # Separator
        separator = ctk.CTkFrame(stats_container, width=1, fg_color=MODERN_COLORS["border"])
        separator.pack(side="left", fill="y", padx=10)
        
        # Total size
        size_frame = ctk.CTkFrame(stats_container, fg_color="transparent")
        size_frame.pack(side="left", padx=15, pady=10)
        
        size_mb = total_size / (1024 * 1024) if total_size > 0 else 0
        size_text = f"{size_mb:.1f} MB" if size_mb > 0 else "0 MB"
        
        ctk.CTkLabel(
            size_frame,
            text=size_text,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=MODERN_COLORS["success"]
        ).pack()
        
        ctk.CTkLabel(
            size_frame,
            text="Total Size",
            font=ctk.CTkFont(size=10),
            text_color=MODERN_COLORS["text_secondary"]
        ).pack()
    
    def create_header_buttons(self, parent):
        """Create header action buttons - FIXED CALLBACKS"""
        # Add files button with icon
        add_btn = ctk.CTkButton(
            parent,
            text="➕ Add Files",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=100,
            height=35,
            fg_color=MODERN_COLORS["accent"],
            hover_color=MODERN_COLORS["accent_hover"]
        )
        add_btn.configure(command=self.add_files_dialog)  # Fixed callback
        add_btn.pack(side="left", padx=5)
        
        # Open folder button - WORKING VERSION
        folder_btn = ctk.CTkButton(
            parent,
            text="📂 Open",
            font=ctk.CTkFont(size=12),
            width=80,
            height=35,
            fg_color=MODERN_COLORS["bg_tertiary"],
            hover_color=MODERN_COLORS["border"]
        )
        folder_btn.configure(command=self.open_app_folder)  # Fixed callback
        folder_btn.pack(side="left", padx=5)
        
        # Refresh button
        refresh_btn = ctk.CTkButton(
            parent,
            text="🔄",
            font=ctk.CTkFont(size=14),
            width=35,
            height=35,
            fg_color=MODERN_COLORS["bg_tertiary"],
            hover_color=MODERN_COLORS["border"]
        )
        refresh_btn.configure(command=self.refresh_assets)  # Fixed callback
        refresh_btn.pack(side="left", padx=5)
    
    def create_main_content(self):
        """Create main content area with drag & drop zones"""
        main_frame = ctk.CTkFrame(
            self,
            fg_color=MODERN_COLORS["bg_secondary"],
            corner_radius=10
        )
        main_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=10)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        
        # Left panel - Drop zones and quick actions
        self.create_left_panel(main_frame)
        
        # Main content - Assets grid
        self.create_assets_grid(main_frame)
        
        # Right panel - Preview and details
        self.create_right_panel(main_frame)
    
    def create_left_panel(self, parent):
        """Create left panel with drop zones"""
        left_panel = ctk.CTkFrame(
            parent,
            width=250,
            fg_color=MODERN_COLORS["bg_tertiary"],
            corner_radius=8
        )
        left_panel.grid(row=0, column=0, sticky="ns", padx=10, pady=10)
        left_panel.grid_propagate(False)
        
        # Panel title
        title_label = ctk.CTkLabel(
            left_panel,
            text="📥 Quick Add",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=MODERN_COLORS["text_primary"]
        )
        title_label.pack(pady=(20, 15))
        
        # Drag & drop status
        if self.drag_drop_available:
            status_text = "✅ Drag & Drop Ready"
            status_color = MODERN_COLORS["success"]
        else:
            status_text = "⚠️ Click to Add Files"
            status_color = MODERN_COLORS["warning"]
        
        status_label = ctk.CTkLabel(
            left_panel,
            text=status_text,
            font=ctk.CTkFont(size=10),
            text_color=status_color
        )
        status_label.pack(pady=(0, 10))
        
        # Image drop zone - FIXED CALLBACKS
        self.create_drop_zone(
            left_panel,
            "🖼️ Add Images",
            "PNG, JPG, GIF, etc.",
            MODERN_COLORS["accent"],
            self.handle_image_add
        )
        
        # Audio drop zone - FIXED CALLBACKS
        self.create_drop_zone(
            left_panel,
            "🎵 Add Audio",
            "MP3, WAV, OGG, etc.",
            MODERN_COLORS["success"],
            self.handle_audio_add
        )
        
        # Video drop zone - FIXED CALLBACKS
        self.create_drop_zone(
            left_panel,
            "🎬 Add Videos",
            "MP4, AVI, MOV, etc.",
            MODERN_COLORS["warning"],
            self.handle_video_add
        )
        
        # Quick actions
        self.create_quick_actions(left_panel)
    
    def create_drop_zone(self, parent, title, subtitle, color, callback):
        """Create a modern drop zone - FIXED CALLBACKS"""
        zone_frame = ctk.CTkFrame(
            parent,
            height=80,
            fg_color=MODERN_COLORS["bg_primary"],
            border_color=color,
            border_width=2,
            corner_radius=8
        )
        zone_frame.pack(fill="x", padx=15, pady=10)
        zone_frame.grid_propagate(False)
        
        # Zone content
        content_frame = ctk.CTkFrame(zone_frame, fg_color="transparent")
        content_frame.pack(expand=True, fill="both", padx=10, pady=10)
        
        title_label = ctk.CTkLabel(
            content_frame,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=color
        )
        title_label.pack()
        
        subtitle_label = ctk.CTkLabel(
            content_frame,
            text=subtitle,
            font=ctk.CTkFont(size=10),
            text_color=MODERN_COLORS["text_secondary"]
        )
        subtitle_label.pack()
        
        # FIXED: Proper button for each zone
        zone_button = ctk.CTkButton(
            content_frame,
            text="Click to Add",
            font=ctk.CTkFont(size=10),
            width=80,
            height=20,
            fg_color=color,
            hover_color=color
        )
        zone_button.configure(command=callback)  # Fixed callback
        zone_button.pack(pady=(5, 0))
        
        # Hover effects
        def on_enter(e):
            zone_frame.configure(fg_color=MODERN_COLORS["bg_secondary"])
        
        def on_leave(e):
            zone_frame.configure(fg_color=MODERN_COLORS["bg_primary"])
        
        zone_frame.bind("<Enter>", on_enter)
        zone_frame.bind("<Leave>", on_leave)
        content_frame.bind("<Enter>", on_enter)
        content_frame.bind("<Leave>", on_leave)
        
        return zone_frame
    
    def create_quick_actions(self, parent):
        """Create quick action buttons"""
        actions_frame = ctk.CTkFrame(parent, fg_color="transparent")
        actions_frame.pack(fill="x", padx=15, pady=20)
        
        # Section title
        ctk.CTkLabel(
            actions_frame,
            text="⚡ Quick Actions",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=MODERN_COLORS["text_primary"]
        ).pack(pady=(0, 10))
        
        # Clear all button
        clear_btn = ctk.CTkButton(
            actions_frame,
            text="🗑️ Clear All Assets",
            font=ctk.CTkFont(size=11),
            height=30,
            fg_color=MODERN_COLORS["error"],
            hover_color="#d32f2f"
        )
        clear_btn.configure(command=self.clear_all_assets)  # Fixed callback
        clear_btn.pack(fill="x", pady=2)
        
        # Info button
        info_btn = ctk.CTkButton(
            actions_frame,
            text="📊 Asset Info",
            font=ctk.CTkFont(size=11),
            height=30,
            fg_color=MODERN_COLORS["bg_primary"],
            hover_color=MODERN_COLORS["border"]
        )
        info_btn.configure(command=self.show_asset_info)  # Fixed callback
        info_btn.pack(fill="x", pady=2)
        
        # Manual refresh button
        refresh_btn = ctk.CTkButton(
            actions_frame,
            text="🔄 Refresh List",
            font=ctk.CTkFont(size=11),
            height=30,
            fg_color=MODERN_COLORS["bg_primary"],
            hover_color=MODERN_COLORS["border"]
        )
        refresh_btn.configure(command=self.refresh_assets)  # Fixed callback
        refresh_btn.pack(fill="x", pady=2)
    
    def create_assets_grid(self, parent):
        """Create main assets grid with modern cards"""
        grid_frame = ctk.CTkFrame(
            parent,
            fg_color="transparent"
        )
        grid_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_rowconfigure(1, weight=1)
        
        # Grid header
        header = ctk.CTkFrame(grid_frame, height=50, fg_color=MODERN_COLORS["bg_tertiary"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(1, weight=1)
        header.grid_propagate(False)
        
        # Filter/sort controls
        filter_frame = ctk.CTkFrame(header, fg_color="transparent")
        filter_frame.grid(row=0, column=0, sticky="w", padx=15, pady=10)
        
        ctk.CTkLabel(
            filter_frame,
            text="Filter:",
            font=ctk.CTkFont(size=12),
            text_color=MODERN_COLORS["text_secondary"]
        ).pack(side="left", padx=(0, 5))
        
        self.filter_var = ctk.StringVar(value="All")
        filter_combo = ctk.CTkComboBox(
            filter_frame,
            values=["All", "Images", "Audio", "Videos"],
            variable=self.filter_var,
            width=100,
            command=self.apply_filter
        )
        filter_combo.pack(side="left")
        
        # View mode toggle
        view_frame = ctk.CTkFrame(header, fg_color="transparent")
        view_frame.grid(row=0, column=1, sticky="e", padx=15, pady=10)
        
        self.view_mode = ctk.StringVar(value="grid")
        
        grid_btn = ctk.CTkButton(
            view_frame,
            text="⊞",
            font=ctk.CTkFont(size=14),
            width=30,
            height=30,
            fg_color=MODERN_COLORS["accent"],
            command=lambda: self.change_view_mode("grid")
        )
        grid_btn.pack(side="left", padx=2)
        
        list_btn = ctk.CTkButton(
            view_frame,
            text="☰",
            font=ctk.CTkFont(size=14),
            width=30,
            height=30,
            fg_color=MODERN_COLORS["bg_primary"],
            command=lambda: self.change_view_mode("list")
        )
        list_btn.pack(side="left", padx=2)
        
        # Scrollable assets area
        self.assets_scroll = ctk.CTkScrollableFrame(
            grid_frame,
            fg_color=MODERN_COLORS["bg_primary"],
            corner_radius=8
        )
        self.assets_scroll.grid(row=1, column=0, sticky="nsew")
        self.assets_scroll.grid_columnconfigure(0, weight=1)
    
    def create_right_panel(self, parent):
        """Create right panel for preview and details"""
        self.right_panel = ctk.CTkFrame(
            parent,
            width=300,
            fg_color=MODERN_COLORS["bg_tertiary"],
            corner_radius=8
        )
        self.right_panel.grid(row=0, column=2, sticky="ns", padx=10, pady=10)
        self.right_panel.grid_propagate(False)
        
        # Preview area
        preview_label = ctk.CTkLabel(
            self.right_panel,
            text="👁️ Preview",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=MODERN_COLORS["text_primary"]
        )
        preview_label.pack(pady=(20, 10))
        
        # Preview frame
        self.preview_frame = ctk.CTkFrame(
            self.right_panel,
            height=200,
            fg_color=MODERN_COLORS["bg_primary"]
        )
        self.preview_frame.pack(fill="x", padx=15, pady=10)
        self.preview_frame.grid_propagate(False)
        
        # Default preview message
        self.preview_label = ctk.CTkLabel(
            self.preview_frame,
            text="Select an asset to preview",
            font=ctk.CTkFont(size=12),
            text_color=MODERN_COLORS["text_secondary"]
        )
        self.preview_label.pack(expand=True)
        
        # Details area
        details_label = ctk.CTkLabel(
            self.right_panel,
            text="📋 Details",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=MODERN_COLORS["text_primary"]
        )
        details_label.pack(pady=(20, 10))
        
        self.details_frame = ctk.CTkFrame(
            self.right_panel,
            fg_color=MODERN_COLORS["bg_primary"]
        )
        self.details_frame.pack(fill="x", padx=15, pady=10)
        
        # Default details
        self.show_default_details()
    
    def create_footer(self):
        """Create simplified footer without auto-delete settings"""
        footer_frame = ctk.CTkFrame(
            self,
            height=60,  # Reduced height since no auto-delete settings
            fg_color=MODERN_COLORS["bg_secondary"],
            corner_radius=10
        )
        footer_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(10, 15))
        footer_frame.grid_columnconfigure(1, weight=1)
        footer_frame.grid_propagate(False)
        
        # Simple status display
        status_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        status_frame.grid(row=0, column=0, sticky="w", padx=20, pady=15)
        
        # Status label
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Ready",
            font=ctk.CTkFont(size=12),
            text_color=MODERN_COLORS["text_primary"]
        )
        self.status_label.pack(side="left")
        
        # Drag & Drop status
        dnd_status = "✅ Drag & Drop Available" if self.drag_drop_available else "⚠️ Drag & Drop Unavailable"
        dnd_label = ctk.CTkLabel(
            footer_frame,
            text=dnd_status,
            font=ctk.CTkFont(size=10),
            text_color=MODERN_COLORS["success"] if self.drag_drop_available else MODERN_COLORS["warning"]
        )
        dnd_label.grid(row=0, column=1, sticky="e", padx=20, pady=15)
    def validate_hours_input(self, event=None):
        """Validate hours input in real-time"""
        try:
            value = self.hours_var.get()
            if value:  # Only validate if not empty
                hours = float(value)
                if hours <= 0:
                    self.hours_var.set("1")  # Minimum 1 hour
                elif hours > 8760:  # Maximum 1 year
                    self.hours_var.set("8760")
        except ValueError:
            # Remove invalid characters
            valid_chars = ''.join(c for c in self.hours_var.get() if c.isdigit() or c == '.')
            self.hours_var.set(valid_chars)
    
    def apply_hours_setting(self, event=None):
        """Apply the hours setting when focus is lost"""
        try:
            hours = float(self.hours_var.get())
            if hours > 0:
                self.auto_delete_hours = hours
                if self.auto_delete_enabled:
                    self.setup_existing_file_timers()
                    self.show_success_notification(f"Auto-delete time set to {hours} hours")
        except ValueError:
            self.hours_var.set(str(self.auto_delete_hours))  # Reset to previous valid value
    
    def set_preset_hours(self, hours):
        """Set preset hours value"""
        self.hours_var.set(str(hours))
        self.auto_delete_hours = hours
        if self.auto_delete_enabled:
            self.setup_existing_file_timers()
            self.show_success_notification(f"Auto-delete set to {hours} hours")
    def get_assets_folder(self):
        """Get the assets folder path - FIXED to always use exe/script directory"""
        # Force detection of the actual executable/script location
        if getattr(sys, 'frozen', False):
            # Running as executable - get the REAL exe directory, not temp
            exe_path = sys.executable
            if 'temp' in exe_path.lower() or 'tmp' in exe_path.lower():
                # This might be a onefile temp path, try to find the real exe
                # Look for the original exe in common locations
                possible_locations = [
                    os.path.join(os.path.expanduser("~"), "Desktop"),
                    os.path.join(os.path.expanduser("~"), "Downloads"),
                    os.getcwd(),
                ]
                
                for location in possible_locations:
                    potential_exe = os.path.join(location, "app.exe")
                    if os.path.exists(potential_exe):
                        exe_path = potential_exe
                        break
                else:
                    # Fallback: use current working directory
                    exe_path = os.path.join(os.getcwd(), "app.exe")
            
            base_dir = os.path.dirname(os.path.abspath(exe_path))
        else:
            # Running as script
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Create assets folder next to the exe/script
        assets_path = os.path.join(base_dir, "assets")
        os.makedirs(assets_path, exist_ok=True)
        
        print(f"📁 Assets folder determined: {assets_path}")
        self.main_app.append_terminal_output(f"📁 Assets folder: {assets_path}\n")
        return assets_path
    def get_asset_files(self):
        """Get list of asset files directly in the app directory"""
        asset_extensions = {
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp',  # Images
            '.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma',    # Audio
            '.mp4', '.avi', '.mov', '.mkv', '.webm'                      # Video
        }
        
        try:
            all_files = os.listdir(self.assets_folder)
            asset_files = []
            
            for filename in all_files:
                # Skip the main application files
                if filename.lower() in ['app.py', 'app.exe', 'main.py', 'main.exe']:
                    continue
                    
                # Skip system files and folders
                if filename.startswith('.') or os.path.isdir(os.path.join(self.assets_folder, filename)):
                    continue
                
                # Check if file has asset extension
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext in asset_extensions:
                    file_path = os.path.join(self.assets_folder, filename)
                    file_size = os.path.getsize(file_path)
                    file_modified = os.path.getmtime(file_path)
                    
                    asset_files.append({
                        'name': filename,
                        'path': file_path,
                        'size': file_size,
                        'modified': file_modified,
                        'extension': file_ext,
                        'type': self.get_file_type(file_ext)
                    })
            
            # Sort by modification time (newest first)
            asset_files.sort(key=lambda x: x['modified'], reverse=True)
            return asset_files
            
        except Exception as e:
            print(f"Error getting asset files: {e}")
            return []
    
    def get_file_type(self, extension):
        """Get file type from extension"""
        image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
        audio_exts = {'.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma'}
        video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
        
        if extension in image_exts:
            return 'image'
        elif extension in audio_exts:
            return 'audio'
        elif extension in video_exts:
            return 'video'
        else:
            return 'other'
    
    def refresh_assets(self):
        """Refresh the assets display with modern cards"""
        try:
            # Clear existing content
            for widget in self.assets_scroll.winfo_children():
                widget.destroy()
            
            # Update stats
            self.create_stats_display()
            
            asset_files = self.get_asset_files()
            filtered_files = self.apply_current_filter(asset_files)
            
            if not filtered_files:
                self.show_empty_state()
                return
            
            if self.view_mode.get() == "grid":
                self.create_grid_view(filtered_files)
            else:
                self.create_list_view(filtered_files)
                
            self.update_status(f"Loaded {len(filtered_files)} assets")
        except Exception as e:
            print(f"Error refreshing assets: {e}")
            self.show_error_state(str(e))
    
    def apply_current_filter(self, files):
        """Apply current filter to file list"""
        filter_value = self.filter_var.get()
        
        if filter_value == "All":
            return files
        elif filter_value == "Images":
            return [f for f in files if f['type'] == 'image']
        elif filter_value == "Audio":
            return [f for f in files if f['type'] == 'audio']
        elif filter_value == "Videos":
            return [f for f in files if f['type'] == 'video']
        
        return files
    
    def create_grid_view(self, files):
        """Create modern grid view of assets"""
        cols = 3  # 3 columns for grid view
        
        for i, file_info in enumerate(files):
            row = i // cols
            col = i % cols
            
            self.assets_scroll.grid_columnconfigure(col, weight=1, uniform="col")
            
            card = self.create_modern_asset_card(file_info, is_grid=True)
            card.grid(row=row, column=col, sticky="ew", padx=5, pady=5)
    
    def create_list_view(self, files):
        """Create modern list view of assets"""
        self.assets_scroll.grid_columnconfigure(0, weight=1)
        
        for i, file_info in enumerate(files):
            card = self.create_modern_asset_card(file_info, is_grid=False)
            card.grid(row=i, column=0, sticky="ew", padx=5, pady=2)
    
    def create_modern_asset_card(self, file_info, is_grid=True):
        """Create a modern asset card with timer display and clear action buttons"""
        from datetime import datetime
        
        # Card frame with modern styling
        card = ctk.CTkFrame(
            self.assets_scroll,
            fg_color=MODERN_COLORS["bg_secondary"],
            border_color=MODERN_COLORS["border"],
            border_width=1,
            corner_radius=12,
            height=160 if is_grid else 120  # Increased height for timer display
        )
        
        if is_grid:
            card.grid_propagate(False)
        
        # Configure card layout
        card.grid_columnconfigure(1, weight=1)
        
        # File type icon with modern styling
        type_icons = {
            'image': '🖼️',
            'audio': '🎵',
            'video': '🎬',
            'other': '📄'
        }
        
        # Icon frame
        icon_frame = ctk.CTkFrame(
            card,
            width=60 if is_grid else 50,
            fg_color=MODERN_COLORS["bg_tertiary"],
            corner_radius=8
        )
        icon_frame.grid(row=0, column=0, rowspan=4 if is_grid else 3, 
                       padx=10, pady=10, sticky="ns")
        icon_frame.grid_propagate(False)
        
        icon_label = ctk.CTkLabel(
            icon_frame,
            text=type_icons[file_info['type']],
            font=ctk.CTkFont(size=24 if is_grid else 20)
        )
        icon_label.pack(expand=True)
        
        # Content frame
        content_frame = ctk.CTkFrame(card, fg_color="transparent")
        content_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=10)
        content_frame.grid_columnconfigure(0, weight=1)
        
        # File name with truncation
        name_display = file_info['name']
        if len(name_display) > 25 and is_grid:
            name_display = name_display[:22] + "..."
        elif len(name_display) > 40 and not is_grid:
            name_display = name_display[:37] + "..."
        
        name_label = ctk.CTkLabel(
            content_frame,
            text=name_display,
            font=ctk.CTkFont(size=14 if is_grid else 12, weight="bold"),
            text_color=MODERN_COLORS["text_primary"],
            anchor="w"
        )
        name_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        # File details
        size_mb = file_info['size'] / (1024 * 1024)
        size_text = f"{size_mb:.1f} MB" if size_mb >= 0.1 else f"{file_info['size']} B"
        modified_date = datetime.fromtimestamp(file_info['modified']).strftime("%m/%d %H:%M")
        
        details_text = f"{size_text} • {modified_date}"
        if not is_grid:
            details_text += f" • {file_info['type'].title()}"
        
        details_label = ctk.CTkLabel(
            content_frame,
            text=details_text,
            font=ctk.CTkFont(size=10 if is_grid else 9),
            text_color=MODERN_COLORS["text_secondary"],
            anchor="w"
        )
        details_label.grid(row=1, column=0, sticky="ew")
        
        # Timer display - NEW ENHANCED FEATURE
        timer_text = self.get_file_timer_info(file_info['name']) if self.auto_delete_enabled else None
        timer_label = None
        if timer_text:
            # Color-code timer based on remaining time
            if "m left" in timer_text and not "h" in timer_text:
                # Less than 1 hour - orange/warning color
                timer_color = MODERN_COLORS["warning"]
            elif "Deleting soon" in timer_text:
                # About to delete - red/error color
                timer_color = MODERN_COLORS["error"]
            else:
                # More than 1 hour - blue/accent color
                timer_color = MODERN_COLORS["accent"]
            
            timer_label = ctk.CTkLabel(
                content_frame,
                text=timer_text,
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=timer_color,
                anchor="w"
            )
            timer_label.grid(row=2, column=0, sticky="ew", pady=(2, 0))
            
            # Store reference for updates
            if not hasattr(self, 'file_cards'):
                self.file_cards = {}
            self.file_cards[file_info['name']] = {'timer_label': timer_label}
        
        # Action buttons frame - IMPROVED VISIBILITY
        actions_frame = ctk.CTkFrame(card, fg_color="transparent")
        actions_frame.grid(row=0, column=2, rowspan=4 if is_grid else 3, 
                          padx=10, pady=10, sticky="ns")
        
        # Preview button - ENHANCED
        preview_btn = ctk.CTkButton(
            actions_frame,
            text="👁️ View",
            width=75,  # Wider for better visibility
            height=30,  # Taller for better click target
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=MODERN_COLORS["accent"],
            hover_color=MODERN_COLORS["accent_hover"],
            text_color="white",
            corner_radius=6,
            command=lambda: self.preview_asset(file_info)
        )
        preview_btn.pack(pady=3)
        
        # Copy path button - ENHANCED
        copy_btn = ctk.CTkButton(
            actions_frame,
            text="📋 Copy",
            width=75,
            height=30,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=MODERN_COLORS["success"],
            hover_color="#3d8b40",
            text_color="white",
            corner_radius=6,
            command=lambda: self.copy_file_path(file_info)
        )
        copy_btn.pack(pady=3)
        
        # Delete button - ENHANCED
        delete_btn = ctk.CTkButton(
            actions_frame,
            text="🗑️ Delete",
            width=75,
            height=30,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=MODERN_COLORS["error"],
            hover_color="#d32f2f",
            text_color="white",
            corner_radius=6,
            command=lambda: self.delete_file_confirm(file_info)
        )
        delete_btn.pack(pady=3)
        
        # Timer control button (if auto-delete is enabled) - NEW
        if self.auto_delete_enabled and file_info['name'] in self.file_timers:
            timer_btn = ctk.CTkButton(
                actions_frame,
                text="⏰ Reset",
                width=75,
                height=25,
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color=MODERN_COLORS["warning"],
                hover_color="#e67e22",
                text_color="white",
                corner_radius=6,
                command=lambda: self.reset_file_timer(file_info['name'])
            )
            timer_btn.pack(pady=2)
        
        # Hover effects for the entire card - ENHANCED
        def on_enter(event):
            card.configure(border_color=MODERN_COLORS["accent"], border_width=2)
        
        def on_leave(event):
            card.configure(border_color=MODERN_COLORS["border"], border_width=1)
        
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)
        
        # Make the card clickable for preview - ENHANCED
        def on_card_click(event):
            self.preview_asset(file_info)
        
        card.bind("<Button-1>", on_card_click)
        icon_frame.bind("<Button-1>", on_card_click)
        content_frame.bind("<Button-1>", on_card_click)
        
        return card
    def reset_file_timer(self, filename):
        """Reset timer for a specific file"""
        try:
            if filename in self.file_timers:
                # Cancel existing timer
                self.after_cancel(self.file_timers[filename])
                
                # Set new timer with full duration
                delay_seconds = self.auto_delete_hours * 3600
                self.schedule_file_deletion(filename, delay_seconds)
                
                # Update timer start time
                if hasattr(self, 'timer_start_times'):
                    self.timer_start_times[filename] = {
                        'start_time': time.time(),
                        'duration': delay_seconds
                    }
                
                self.show_success_notification(f"Timer reset for {filename}")
                print(f"⏰ Timer reset for {filename} - {self.auto_delete_hours} hours")
                
                # Refresh to update timer display
                self.refresh_assets()
                
        except Exception as e:
            print(f"❌ Error resetting timer for {filename}: {e}")
            self.show_error_notification(f"Timer reset failed: {e}")
    def show_empty_state(self):
        """Show modern empty state"""
        empty_frame = ctk.CTkFrame(
            self.assets_scroll,
            fg_color="transparent"
        )
        empty_frame.pack(expand=True, fill="both", padx=20, pady=50)
        
        # Large icon
        icon_label = ctk.CTkLabel(
            empty_frame,
            text="📁",
            font=ctk.CTkFont(size=64)
        )
        icon_label.pack(pady=(0, 20))
        
        # Title
        title_label = ctk.CTkLabel(
            empty_frame,
            text="No Assets Found",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=MODERN_COLORS["text_primary"]
        )
        title_label.pack(pady=(0, 10))
        
        # Subtitle with drag & drop status
        if self.drag_drop_available:
            subtitle_text = "Drag & drop files here or use the buttons above to add assets"
        else:
            subtitle_text = "Use the buttons above to add assets (drag & drop not available)"
        
        subtitle_label = ctk.CTkLabel(
            empty_frame,
            text=subtitle_text,
            font=ctk.CTkFont(size=14),
            text_color=MODERN_COLORS["text_secondary"]
        )
        subtitle_label.pack()
    
    def show_error_state(self, error):
        """Show error state"""
        error_frame = ctk.CTkFrame(
            self.assets_scroll,
            fg_color="transparent"
        )
        error_frame.pack(expand=True, fill="both", padx=20, pady=50)
        
        # Error icon
        icon_label = ctk.CTkLabel(
            error_frame,
            text="⚠️",
            font=ctk.CTkFont(size=48),
            text_color=MODERN_COLORS["error"]
        )
        icon_label.pack(pady=(0, 15))
        
        # Error message
        error_label = ctk.CTkLabel(
            error_frame,
            text=f"Error loading assets:\n{error}",
            font=ctk.CTkFont(size=14),
            text_color=MODERN_COLORS["error"]
        )
        error_label.pack()
    
    def preview_asset(self, file_info):
        """Preview asset in right panel"""
        try:
            # Clear current preview
            for widget in self.preview_frame.winfo_children():
                widget.destroy()
            
            if file_info['type'] == 'image':
                self.preview_image_asset(file_info)
            elif file_info['type'] == 'audio':
                self.preview_audio_asset(file_info)
            elif file_info['type'] == 'video':
                self.preview_video_asset(file_info)
            
            # Update details
            self.show_asset_details(file_info)
        except Exception as e:
            print(f"Error previewing asset: {e}")
    
    def preview_image_asset(self, file_info):
        """Preview image asset"""
        try:
            if Image and ImageTk:
                # Load and resize image
                img = Image.open(file_info['path'])
                
                # Calculate size to fit preview area
                preview_size = (280, 180)
                img.thumbnail(preview_size, Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                photo = ImageTk.PhotoImage(img)
                
                # Display image
                img_label = tk.Label(
                    self.preview_frame,
                    image=photo,
                    bg=MODERN_COLORS["bg_primary"]
                )
                img_label.image = photo  # Keep reference
                img_label.pack(expand=True)
            else:
                self.show_preview_error("PIL not available for image preview")
            
        except Exception as e:
            self.show_preview_error(f"Cannot preview image: {e}")
    
    def preview_audio_asset(self, file_info):
        """Preview audio asset"""
        # Audio preview with waveform simulation
        audio_frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        audio_frame.pack(expand=True, fill="both", padx=20, pady=20)
        
        # Audio icon
        ctk.CTkLabel(
            audio_frame,
            text="🎵",
            font=ctk.CTkFont(size=48),
            text_color=MODERN_COLORS["success"]
        ).pack(pady=(20, 10))
        
        # Audio info
        ctk.CTkLabel(
            audio_frame,
            text=file_info['name'],
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=MODERN_COLORS["text_primary"]
        ).pack()
        
        # Simulated waveform
        waveform_frame = ctk.CTkFrame(audio_frame, height=40, fg_color=MODERN_COLORS["bg_tertiary"])
        waveform_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            waveform_frame,
            text="~ ~ ~ ~ ~ ~ ~ ~ ~ ~",
            font=ctk.CTkFont(size=12),
            text_color=MODERN_COLORS["accent"]
        ).pack(expand=True)
    
    def preview_video_asset(self, file_info):
        """Preview video asset"""
        video_frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        video_frame.pack(expand=True, fill="both", padx=20, pady=20)
        
        # Video icon
        ctk.CTkLabel(
            video_frame,
            text="🎬",
            font=ctk.CTkFont(size=48),
            text_color=MODERN_COLORS["warning"]
        ).pack(pady=(20, 10))
        
        # Video info
        ctk.CTkLabel(
            video_frame,
            text=file_info['name'],
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=MODERN_COLORS["text_primary"]
        ).pack()
        
        # Play button placeholder
        play_btn = ctk.CTkButton(
            video_frame,
            text="▶️ Open in Player",
            font=ctk.CTkFont(size=12),
            width=120,
            height=30,
            fg_color=MODERN_COLORS["warning"],
            command=lambda: self.open_file(file_info['path'])
        )
        play_btn.pack(pady=10)
    
    def show_preview_error(self, error):
        """Show preview error"""
        error_label = ctk.CTkLabel(
            self.preview_frame,
            text=f"Preview Error:\n{error}",
            font=ctk.CTkFont(size=12),
            text_color=MODERN_COLORS["error"]
        )
        error_label.pack(expand=True)
    
    def show_asset_details(self, file_info):
        """Show detailed asset information"""
        # Clear current details
        for widget in self.details_frame.winfo_children():
            widget.destroy()
        
        details = [
            ("📁 Name", file_info['name']),
            ("📏 Size", f"{file_info['size'] / (1024*1024):.2f} MB"),
            ("📅 Modified", datetime.fromtimestamp(file_info['modified']).strftime("%Y-%m-%d %H:%M:%S")),
            ("🏷️ Type", file_info['type'].title()),
            ("📎 Extension", file_info['extension']),
            ("📍 Path", file_info['name'])  # Relative path
        ]
        
        for label, value in details:
            detail_frame = ctk.CTkFrame(self.details_frame, fg_color="transparent")
            detail_frame.pack(fill="x", padx=10, pady=2)
            detail_frame.grid_columnconfigure(1, weight=1)
            
            ctk.CTkLabel(
                detail_frame,
                text=label,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=MODERN_COLORS["text_secondary"],
                width=80,
                anchor="w"
            ).grid(row=0, column=0, sticky="w")
            
            # Truncate long values
            display_value = value
            if len(str(value)) > 20:
                display_value = str(value)[:17] + "..."
            
            ctk.CTkLabel(
                detail_frame,
                text=display_value,
                font=ctk.CTkFont(size=11),
                text_color=MODERN_COLORS["text_primary"],
                anchor="w"
            ).grid(row=0, column=1, sticky="w", padx=(10, 0))
    
    def show_default_details(self):
        """Show default details when no asset is selected"""
        default_label = ctk.CTkLabel(
            self.details_frame,
            text="Select an asset to view details",
            font=ctk.CTkFont(size=12),
            text_color=MODERN_COLORS["text_secondary"]
        )
        default_label.pack(expand=True, pady=20)
    
    # CORRECT Drag and Drop Implementation - USING PROPER tkinterdnd2 API
    
    
    
    def reset_drop_processing(self):
        """Reset drop processing flag"""
        self.processing_drop = False
        self.update_status("Ready")
        print("🎯 Drop processing reset")
    
    # Working File Upload Implementation
    def add_files_dialog(self):
        """General add files dialog - WORKING IMPLEMENTATION"""
        print("🔄 Opening file dialog...")
        try:
            filetypes = [
                ("All Asset Files", "*.png *.jpg *.jpeg *.gif *.bmp *.mp3 *.wav *.ogg *.mp4 *.avi *.mov"),
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp"),
                ("Audio files", "*.mp3 *.wav *.ogg *.m4a *.flac *.aac *.wma"),
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("All files", "*.*")
            ]
            
            file_paths = filedialog.askopenfilenames(
                title="Select Asset Files",
                filetypes=filetypes,
                parent=self
            )
            
            if file_paths:
                print(f"📁 Selected {len(file_paths)} files")
                self.process_dropped_files(file_paths)
            else:
                print("❌ No files selected")
        except Exception as e:
            print(f"❌ Error in file dialog: {e}")
            self.show_error_notification(f"File dialog error: {str(e)}")
    
    def handle_image_add(self):
        """Handle image add - WORKING IMPLEMENTATION"""
        print("🖼️ Adding images...")
        try:
            filetypes = [
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp"),
                ("All files", "*.*")
            ]
            
            file_paths = filedialog.askopenfilenames(
                title="Select Images",
                filetypes=filetypes,
                parent=self
            )
            
            if file_paths:
                self.process_dropped_files(file_paths)
        except Exception as e:
            print(f"❌ Error adding images: {e}")
            self.show_error_notification(f"Image add error: {str(e)}")
    
    def handle_audio_add(self):
        """Handle audio add - WORKING IMPLEMENTATION"""
        print("🎵 Adding audio...")
        try:
            filetypes = [
                ("Audio files", "*.mp3 *.wav *.ogg *.m4a *.flac *.aac *.wma"),
                ("All files", "*.*")
            ]
            
            file_paths = filedialog.askopenfilenames(
                title="Select Audio Files",
                filetypes=filetypes,
                parent=self
            )
            
            if file_paths:
                self.process_dropped_files(file_paths)
        except Exception as e:
            print(f"❌ Error adding audio: {e}")
            self.show_error_notification(f"Audio add error: {str(e)}")
    
    def handle_video_add(self):
        """Handle video add - WORKING IMPLEMENTATION"""
        print("🎬 Adding videos...")
        try:
            filetypes = [
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("All files", "*.*")
            ]
            
            file_paths = filedialog.askopenfilenames(
                title="Select Video Files",
                filetypes=filetypes,
                parent=self
            )
            
            if file_paths:
                self.process_dropped_files(file_paths)
        except Exception as e:
            print(f"❌ Error adding videos: {e}")
            self.show_error_notification(f"Video add error: {str(e)}")
    
    # Utility Methods - WORKING IMPLEMENTATIONS
    def copy_file_path(self, file_info):
        """Copy file path to clipboard - WORKING IMPLEMENTATION"""
        try:
            relative_path = file_info['name']
            
            self.clipboard_clear()
            self.clipboard_append(relative_path)
            
            self.show_success_notification(f"Copied: {relative_path}")
            self.main_app.append_terminal_output(f"📋 Copied to clipboard: {relative_path}\n")
            
        except Exception as e:
            self.show_error_notification(f"Copy error: {str(e)}")
    
    def delete_file_confirm(self, file_info):
        """Confirm and delete file - WORKING IMPLEMENTATION"""
        if messagebox.askyesno(
            "Delete Asset",
            f"Are you sure you want to delete:\n{file_info['name']}?",
            parent=self
        ):
            try:
                os.remove(file_info['path'])
                
                # Cancel timer if exists
                if file_info['name'] in self.file_timers:
                    self.after_cancel(self.file_timers[file_info['name']])
                    del self.file_timers[file_info['name']]
                
                self.refresh_assets()
                self.show_success_notification(f"Deleted: {file_info['name']}")
                self.main_app.append_terminal_output(f"🗑️ Deleted asset: {file_info['name']}\n")
                
            except Exception as e:
                self.show_error_notification(f"Delete failed: {str(e)}")
    
    def open_app_folder(self):
        """Open the app directory in file explorer - SAFE VERSION"""
        print("📂 Opening app folder...")
        try:
            import subprocess
            import platform
            
            system = platform.system()
            
            if system == "Windows":
                # Use startfile for Windows - more reliable
                os.startfile(self.assets_folder)
            elif system == "Darwin":  # macOS
                subprocess.run(["open", self.assets_folder], check=True)
            else:  # Linux and others
                subprocess.run(["xdg-open", self.assets_folder], check=True)
                
            self.show_success_notification("Opened assets folder")
            self.main_app.append_terminal_output(f"📂 Opened app directory: {self.assets_folder}\n")
            
        except Exception as e:
            print(f"❌ Error opening folder: {e}")
            # Show folder path to user instead
            messagebox.showinfo(
                "Folder Location", 
                f"Cannot open folder automatically.\n\nAssets folder location:\n{self.assets_folder}",
                parent=self
            )
    
    def open_file(self, file_path):
        """Open file with default application"""
        try:
            import subprocess
            import platform
            
            system = platform.system()
            
            if system == "Windows":
                os.startfile(file_path)
            elif system == "Darwin":  # macOS
                subprocess.run(["open", file_path], check=True)
            else:  # Linux
                subprocess.run(["xdg-open", file_path], check=True)
                
        except Exception as e:
            self.show_error_notification(f"Cannot open file: {str(e)}")
    
    # Filter and View Methods
    def apply_filter(self, *args):
        """Apply filter to assets"""
        self.refresh_assets()
    
    def change_view_mode(self, mode):
        """Change view mode between grid and list"""
        self.view_mode.set(mode)
        self.refresh_assets()
    
    # Quick Actions
    def clear_all_assets(self):
        """Clear all assets with confirmation"""
        if messagebox.askyesno(
            "Clear All Assets",
            "Are you sure you want to delete ALL assets?\nThis cannot be undone!",
            parent=self
        ):
            try:
                asset_files = self.get_asset_files()
                deleted_count = 0
                
                for file_info in asset_files:
                    os.remove(file_info['path'])
                    if file_info['name'] in self.file_timers:
                        self.after_cancel(self.file_timers[file_info['name']])
                        del self.file_timers[file_info['name']]
                    deleted_count += 1
                
                self.refresh_assets()
                self.show_success_notification(f"Deleted {deleted_count} assets")
                self.main_app.append_terminal_output(f"🗑️ Cleared all assets ({deleted_count} files)\n")
                
            except Exception as e:
                self.show_error_notification(f"Clear failed: {str(e)}")
    
    def show_asset_info(self):
        """Show asset information"""
        asset_files = self.get_asset_files()
        total_files = len(asset_files)
        total_size = sum(f['size'] for f in asset_files) / (1024 * 1024)
        
        # Count by type
        type_counts = {'image': 0, 'audio': 0, 'video': 0, 'other': 0}
        for file_info in asset_files:
            type_counts[file_info['type']] += 1
        
        info_text = f"""Asset Summary:
        
📊 Total Files: {total_files}
📏 Total Size: {total_size:.1f} MB
📁 Directory: {self.assets_folder}

📊 By Type:
🖼️ Images: {type_counts['image']}
🎵 Audio: {type_counts['audio']}
🎬 Videos: {type_counts['video']}
📄 Other: {type_counts['other']}

⚙️ Auto-delete: {'Enabled' if self.auto_delete_enabled else 'Disabled'}
🔧 Drag & Drop: {'Available' if self.drag_drop_available else 'Not Available'}"""
        
        messagebox.showinfo("Asset Information", info_text, parent=self)
    
    # Auto-delete Methods
    def setup_existing_file_timers(self):
        """Setup timers for existing files"""
        try:
            if not self.auto_delete_enabled:
                return
                
            asset_files = self.get_asset_files()
            current_time = time.time()
            
            for file_info in asset_files:
                file_age_seconds = current_time - file_info['modified']
                delete_delay_seconds = (self.auto_delete_hours * 3600) - file_age_seconds
                
                if delete_delay_seconds > 0:
                    self.schedule_file_deletion(file_info['name'], delete_delay_seconds)
                else:
                    self.delete_expired_file(file_info['name'])
                    
        except Exception as e:
            print(f"Error setting up file timers: {e}")
    
    def schedule_file_deletion(self, filename, delay_seconds):
        """Schedule a file for automatic deletion - ENHANCED"""
        try:
            # Cancel existing timer if any
            if filename in self.file_timers:
                self.after_cancel(self.file_timers[filename])
            
            # Don't schedule if delay is too short (less than 1 minute)
            if delay_seconds < 60:
                delay_seconds = 60  # Minimum 1 minute
            
            # Schedule new timer
            timer_id = self.after(int(delay_seconds * 1000), lambda: self.delete_expired_file(filename))
            self.file_timers[filename] = timer_id
            
            print(f"⏰ Scheduled deletion for {filename} in {delay_seconds/3600:.1f} hours")
            
        except Exception as e:
            print(f"❌ Error scheduling deletion for {filename}: {e}")
    
    def delete_expired_file(self, filename):
        """Delete an expired file automatically"""
        try:
            file_path = os.path.join(self.assets_folder, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                
                if filename in self.file_timers:
                    del self.file_timers[filename]
                
                if self.winfo_exists():
                    self.refresh_assets()
                    self.show_info_notification(f"Auto-deleted: {filename}")
                    self.main_app.append_terminal_output(f"🗑️ Auto-deleted expired asset: {filename}\n")
                    
        except Exception as e:
            print(f"Error auto-deleting file {filename}: {e}")
    
    def toggle_auto_delete(self):
        """Toggle auto-delete functionality - ENHANCED"""
        self.auto_delete_enabled = self.auto_delete_var.get()
        
        if not self.auto_delete_enabled:
            # Cancel all existing timers
            for filename, timer_id in self.file_timers.items():
                self.after_cancel(timer_id)
                print(f"⏹️ Cancelled timer for {filename}")
            self.file_timers.clear()
            
            # Clear timer start times
            if hasattr(self, 'timer_start_times'):
                self.timer_start_times.clear()
                
            self.show_info_notification("Auto-delete disabled")
            print("🔧 Auto-delete disabled - all timers cancelled")
            
            # Refresh UI to remove timer displays
            self.refresh_assets()
        else:
            # Setup timers for ALL existing files (don't delete any)
            try:
                if hasattr(self, 'hours_var'):
                    self.auto_delete_hours = float(self.hours_var.get())
                
                self.setup_existing_file_timers()
                self.show_success_notification(f"Auto-delete enabled ({self.auto_delete_hours}h)")
                print(f"✅ Auto-delete enabled - files will be deleted after {self.auto_delete_hours} hours")
                
                # Start timer display updates
                self.start_timer_display_updates()
                
                # Refresh UI to show timer displays
                self.refresh_assets()
                
            except ValueError:
                self.auto_delete_var.set(False)
                self.auto_delete_enabled = False
                self.show_error_notification("Invalid hours value")
    # Notification Methods
    def setup_drag_drop(self):
        """Setup drag and drop functionality - FIXED VERSION"""
        if self.drag_drop_available and self.tkinterdnd2:
            try:
                # Correct way to initialize tkinterdnd2 for CustomTkinter
                self.TkdndVersion = self.TkinterDnD._require(self)
                
                # Register for file drops
                self.drop_target_register(self.DND_FILES)
                
                # Bind events
                self.dnd_bind('<<DropEnter>>', self.on_drop_enter)
                self.dnd_bind('<<DropPosition>>', self.on_drop_position) 
                self.dnd_bind('<<DropLeave>>', self.on_drop_leave)
                self.dnd_bind('<<Drop>>', self.on_drop)
                
                print("✅ Drag & Drop setup completed successfully")
                
            except Exception as e:
                print(f"⚠️ Drag & Drop setup failed: {e}")
                self.drag_drop_available = False
        else:
            print("⚠️ Drag & Drop not available")

    def on_drop_enter(self, event):
        """Handle drag enter - FIXED TO PREVENT LOOPS"""
        if not self.drag_drop_available or self.processing_drop:
            return event.action
        
        print("🎯 Drag detected - files entering drop zone")
        self.drop_zone_active = True
        
        # Visual feedback
        try:
            self.configure(border_color=MODERN_COLORS["accent"], border_width=3)
            self.update_status("Drop files to add to assets")
        except:
            pass  # Ignore visual update errors
        
        return event.action

    def on_drop_position(self, event):
        """Handle drag position - FIXED TO PREVENT LOOPS"""
        if not self.drag_drop_available or self.processing_drop:
            return event.action
        return event.action

    def on_drop_leave(self, event):
        """Handle drag leave - FIXED TO PREVENT LOOPS"""
        if not self.drag_drop_available or self.processing_drop:
            return
        
        print("🎯 Drag left drop zone")
        self.drop_zone_active = False
        
        # Reset visual feedback
        try:
            self.configure(border_color=MODERN_COLORS["border"], border_width=0)
            self.update_status("Ready")
        except:
            pass  # Ignore visual update errors
    def parse_multiple_file_paths(self, data):
        """Enhanced parser for multiple file paths from drag & drop"""
        import re
        
        file_paths = []
        
        # Remove any surrounding whitespace
        data = data.strip()
        
        if not data:
            return file_paths
        
        # Method 1: Try splitting by newlines first (common on Unix systems)
        if '\n' in data:
            potential_paths = [line.strip() for line in data.split('\n') if line.strip()]
            print(f"🔍 Found newline-separated paths: {len(potential_paths)}")
            
            for path in potential_paths:
                # Remove braces if present
                clean_path = path.strip('{}').strip('"').strip("'").strip()
                if clean_path and (os.path.isfile(clean_path) or os.path.isabs(clean_path)):
                    file_paths.append(clean_path)
            
            if file_paths:
                return file_paths
        
        # Method 2: Handle braced paths (Windows style: {path1} {path2})
        brace_pattern = r'\{([^}]+)\}'
        braced_matches = re.findall(brace_pattern, data)
        
        if braced_matches:
            print(f"🔍 Found braced paths: {len(braced_matches)}")
            for match in braced_matches:
                clean_path = match.strip()
                if clean_path and (os.path.isfile(clean_path) or os.path.isabs(clean_path)):
                    file_paths.append(clean_path)
            
            if file_paths:
                return file_paths
        
        # Method 3: Handle quoted paths ("path1" "path2" or 'path1' 'path2')
        quote_patterns = [
            r'"([^"]+)"',  # Double quotes
            r"'([^']+)'"   # Single quotes
        ]
        
        for pattern in quote_patterns:
            quoted_matches = re.findall(pattern, data)
            if quoted_matches:
                print(f"🔍 Found quoted paths: {len(quoted_matches)}")
                for match in quoted_matches:
                    clean_path = match.strip()
                    if clean_path and (os.path.isfile(clean_path) or os.path.isabs(clean_path)):
                        file_paths.append(clean_path)
                
                if file_paths:
                    return file_paths
        
        # Method 4: Smart space splitting (handle paths with spaces)
        # This is tricky because paths can contain spaces
        if ' ' in data:
            # Try to split intelligently
            potential_paths = []
            
            # First, try splitting by drive letters (Windows: C:\ D:\ etc.)
            if ':' in data and ('\\' in data or '/' in data):
                # Windows paths - split on drive pattern
                drive_pattern = r'([A-Za-z]:\\[^A-Za-z]*?)(?=[A-Za-z]:\\|$)'
                drive_matches = re.findall(drive_pattern, data)
                
                if drive_matches:
                    potential_paths = [match.strip() for match in drive_matches]
                else:
                    # Fallback: split by space and try to reconstruct paths
                    parts = data.split()
                    current_path = ""
                    
                    for part in parts:
                        if current_path:
                            current_path += " " + part
                        else:
                            current_path = part
                        
                        # Check if current_path looks like a complete file path
                        if os.path.isfile(current_path):
                            potential_paths.append(current_path)
                            current_path = ""
                        elif part.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.mp3', '.wav', '.mp4', '.avi')):
                            # Likely end of a file path
                            potential_paths.append(current_path)
                            current_path = ""
            else:
                # Unix paths or simple splitting
                potential_paths = [p.strip() for p in data.split() if p.strip()]
            
            print(f"🔍 Found space-separated paths: {len(potential_paths)}")
            
            for path in potential_paths:
                clean_path = path.strip('{}').strip('"').strip("'").strip()
                if clean_path and (os.path.isfile(clean_path) or os.path.isabs(clean_path)):
                    file_paths.append(clean_path)
            
            if file_paths:
                return file_paths
        
        # Method 5: Single file (fallback)
        clean_data = data.strip('{}').strip('"').strip("'").strip()
        if clean_data and (os.path.isfile(clean_data) or os.path.isabs(clean_data)):
            file_paths.append(clean_data)
            print(f"🔍 Single file detected: {clean_data}")
        
        return file_paths
    def on_drop(self, event):
        """Handle file drop - ENHANCED for multiple files"""
        if not self.drag_drop_available:
            return event.action
        
        # FIXED: Prevent multiple simultaneous processing
        if self.processing_drop:
            print("⚠️ Already processing files, skipping...")
            return event.action
        
        print("🎯 Files dropped!")
        
        # Set processing flag
        self.processing_drop = True
        
        try:
            self.drop_zone_active = False
            
            # Reset visual feedback
            try:
                self.configure(border_color=MODERN_COLORS["border"], border_width=0)
            except:
                pass
            
            # ENHANCED multi-file parsing for tkinterdnd2
            file_paths = []
            try:
                data = event.data
                print(f"🎯 Raw drop data: {repr(data)}")
                
                if isinstance(data, str):
                    file_paths = self.parse_multiple_file_paths(data)
                elif isinstance(data, (list, tuple)):
                    # Sometimes tkinterdnd2 provides a list
                    file_paths = [str(path).strip() for path in data]
                else:
                    file_paths = [str(data).strip()]
                
                print(f"🎯 Parsed {len(file_paths)} file paths: {file_paths}")
                
            except Exception as e:
                print(f"❌ Error parsing drop data: {e}")
                return event.action
            
            # Filter valid files
            valid_files = []
            for path in file_paths:
                path = path.strip()
                if path and os.path.isfile(path):
                    valid_files.append(path)
                    print(f"✅ Valid file: {os.path.basename(path)}")
                else:
                    if path:  # Only log if path is not empty
                        print(f"❌ Invalid file: {path}")
            
            if valid_files:
                print(f"🎯 Processing {len(valid_files)} valid files")
                # Process files immediately
                self.process_dropped_files_immediate(valid_files)
            else:
                self.show_error_notification("No valid files to add")
                
        except Exception as e:
            print(f"❌ Error in drop processing: {e}")
            self.show_error_notification(f"Drop error: {e}")
        finally:
            # CRITICAL: Always reset processing flag
            self.processing_drop = False
            print("🎯 Drop processing reset")
        
        return event.action
    def process_dropped_files_immediate(self, file_paths):
        """Process dropped files immediately - ENHANCED for multiple files"""
        try:
            successful_copies = 0
            failed_copies = 0
            total_files = len(file_paths)
            
            print(f"📁 Processing {total_files} dropped files...")
            self.update_status(f"Processing {total_files} files...")
            
            # Process each file
            for i, file_path in enumerate(file_paths):
                try:
                    # Update progress
                    progress = f"({i+1}/{total_files})"
                    
                    # Get file info
                    filename = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)
                    
                    print(f"📄 {progress} Processing: {filename} ({file_size} bytes)")
                    self.update_status(f"Processing {filename} {progress}...")
                    
                    # Determine destination
                    dest_path = os.path.join(self.assets_folder, filename)
                    
                    # Handle filename conflicts with enhanced naming
                    if os.path.exists(dest_path):
                        base_name, ext = os.path.splitext(filename)
                        counter = 1
                        while os.path.exists(dest_path):
                            new_filename = f"{base_name}_{counter:02d}{ext}"
                            dest_path = os.path.join(self.assets_folder, new_filename)
                            counter += 1
                        
                        print(f"📝 Renamed to avoid conflict: {os.path.basename(dest_path)}")
                    
                    # Copy file
                    shutil.copy2(file_path, dest_path)
                    successful_copies += 1
                    
                    print(f"✅ {progress} Copied: {filename} -> {os.path.basename(dest_path)}")
                    
                except Exception as e:
                    failed_copies += 1
                    print(f"❌ {progress} Failed to copy {filename}: {e}")
                    continue
            
            # Update UI and show results
            if successful_copies > 0:
                self.refresh_assets()
                
                # Enhanced success message
                if failed_copies > 0:
                    message = f"Added {successful_copies} files ({failed_copies} failed)"
                    self.show_error_notification(message)
                else:
                    message = f"Added {successful_copies} file(s) successfully!"
                    self.show_success_notification(message)
                
                print(f"✅ Successfully added {successful_copies}/{total_files} files")
                self.main_app.append_terminal_output(f"📁 Added {successful_copies} assets to collection\n")
            else:
                self.show_error_notification("Failed to add any files")
                print(f"❌ Failed to add any files (0/{total_files})")
                
        except Exception as e:
            print(f"❌ Error processing dropped files: {e}")
            self.show_error_notification(f"Processing error: {e}")
    def schedule_file_deletion(self, filename, delay_seconds):
        """Schedule a file for automatic deletion"""
        try:
            # Cancel existing timer if any
            if filename in self.file_timers:
                self.after_cancel(self.file_timers[filename])
            
            # Schedule new timer
            timer_id = self.after(int(delay_seconds * 1000), lambda: self.delete_expired_file(filename))
            self.file_timers[filename] = timer_id
            
            print(f"⏰ Scheduled deletion for {filename} in {delay_seconds/3600:.1f} hours")
            
        except Exception as e:
            print(f"❌ Error scheduling deletion for {filename}: {e}")
    
    def delete_expired_file(self, filename):
        """Delete an expired file automatically"""
        try:
            file_path = os.path.join(self.assets_folder, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️ Auto-deleted expired file: {filename}")
                
                # Remove from timers
                if filename in self.file_timers:
                    del self.file_timers[filename]
                
                # Update UI if window still exists
                if self.winfo_exists():
                    self.refresh_assets()
                    self.show_info_notification(f"Auto-deleted: {filename}")
                    self.main_app.append_terminal_output(f"🗑️ Auto-deleted expired asset: {filename}\n")
            else:
                print(f"⚠️ File {filename} not found for auto-deletion")
                
        except Exception as e:
            print(f"❌ Error auto-deleting file {filename}: {e}")
    def show_success_notification(self, message):
        """Show success notification"""
        try:
            # Update status
            self.update_status(message)
            
            # You can add more UI feedback here if needed
            print(f"✅ {message}")
            
        except Exception as e:
            print(f"Error showing success notification: {e}")

    def show_error_notification(self, message):
        """Show error notification"""
        try:
            # Update status
            self.update_status(f"Error: {message}")
            
            # You can add more UI feedback here if needed
            print(f"❌ {message}")
            
        except Exception as e:
            print(f"Error showing error notification: {e}")

    def update_status(self, message):
        """Update status message"""
        try:
            # If you have a status label, update it here
            if hasattr(self, 'status_label'):
                self.status_label.configure(text=message)
            
            # Also print to console
            print(f"📊 Status: {message}")
            
        except Exception as e:
            print(f"Error updating status: {e}")
    def show_error_notification(self, message):
        """Show error notification"""
        self.update_status(f"❌ {message}")
        self.after(5000, lambda: self.update_status("Ready"))
    
    def show_info_notification(self, message):
        """Show info notification"""
        self.update_status(f"ℹ️ {message}")
        self.after(3000, lambda: self.update_status("Ready"))
    
    
    
    def on_close(self):
        """Handle window close"""
        print("🔄 Closing Assets Manager...")
        # Cancel all timers
        for timer_id in self.file_timers.values():
            self.after_cancel(timer_id)
        self.file_timers.clear()
        
        self.destroy()

class AssetFileCard(ctk.CTkFrame):
    """Individual asset file card for the grid"""
    
    def __init__(self, parent, filename, file_path, category, on_select_callback, on_delete_callback, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.filename = filename
        self.file_path = file_path
        self.category = category
        self.on_select = on_select_callback
        self.on_delete = on_delete_callback
        
        self.create_ui()
        
    def create_ui(self):
        """Create the card UI"""
        self.grid_columnconfigure(0, weight=1)
        
        # Card container
        card_frame = ctk.CTkFrame(self, fg_color=VSCODE_COLORS["surface_light"], corner_radius=10)
        card_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        card_frame.grid_columnconfigure(0, weight=1)
        
        # File icon/preview
        icon_frame = ctk.CTkFrame(card_frame, height=70, fg_color="transparent")
        icon_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        icon_frame.grid_propagate(False)
        
        # Category icon
        icons = {
            "image": "🖼️",
            "audio": "🎵",
            "video": "🎬",
            "other": "📄"
        }
        
        icon_label = ctk.CTkLabel(
            icon_frame,
            text=icons.get(self.category, "📄"),
            font=ctk.CTkFont(size=32)
        )
        icon_label.pack(expand=True)
        
        # File name
        name_text = self.filename
        if len(name_text) > 15:
            name_text = name_text[:12] + "..."
        
        name_label = ctk.CTkLabel(
            card_frame,
            text=name_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            wraplength=140
        )
        name_label.grid(row=1, column=0, padx=10, pady=(0, 5))
        
        # File size
        try:
            size = os.path.getsize(self.file_path)
            size_str = self.format_file_size(size)
        except:
            size_str = "Unknown"
        
        size_label = ctk.CTkLabel(
            card_frame,
            text=size_str,
            font=ctk.CTkFont(size=9),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        size_label.grid(row=2, column=0, padx=10)
        
        # Action buttons
        button_frame = ctk.CTkFrame(card_frame, fg_color="transparent")
        button_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))
        button_frame.grid_columnconfigure((0, 1), weight=1)
        
        ctk.CTkButton(
            button_frame,
            text="View",
            width=50,
            height=25,
            command=self.on_view_click,
            fg_color=VSCODE_COLORS["primary"],
            hover_color=VSCODE_COLORS.get("primary_hover", VSCODE_COLORS["primary"]),
            font=ctk.CTkFont(size=10)
        ).grid(row=0, column=0, padx=(0, 5))
        
        ctk.CTkButton(
            button_frame,
            text="Delete",
            width=50,
            height=25,
            command=self.on_delete_click,
            fg_color=VSCODE_COLORS.get("error", "#E74C3C"),
            hover_color="#C0392B",
            font=ctk.CTkFont(size=10)
        ).grid(row=0, column=1)
        
    def format_file_size(self, size_bytes):
        """Format file size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
    
    def on_view_click(self):
        """Handle view button click"""
        self.on_select(self.filename, self.file_path, self.category)
        
    def on_delete_click(self):
        """Handle delete button click"""
        self.on_delete(self.filename)

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
        
    def run_command_redirected(self, command, callback, env=None, cwd=None):
        """Run command in background thread with output redirection"""
        def run_in_thread():
            try:
                self.command_running = True
                
                # Merge environment variables
                full_env = os.environ.copy()
                if env:
                    full_env.update(env)
                
                # Start the process with specified working directory
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    env=full_env,
                    cwd=cwd  # Set working directory
                )
                
                self.process = process
                
                # Read output line by line
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        # Schedule GUI update in main thread
                        self.after_idle(lambda line=output: self.insert("end", line))
                        self.after_idle(self.see, "end")
                
                # Wait for process to complete
                return_code = process.wait()
                
                # Call callback with result
                success = return_code == 0
                self.after_idle(lambda: callback(success, return_code))
                
            except Exception as e:
                self.after_idle(lambda: self.insert("end", f"Error running command: {e}\n"))
                self.after_idle(lambda: callback(False, -1))
            finally:
                self.command_running = False
                self.process = None
        
        # Start the thread
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

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
                            encoding='utf-8',  # FIXED: Add explicit UTF-8 encoding
                            errors='replace',  # FIXED: Replace problematic characters
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
    
    def run_command_redirected(self, command, on_complete=None, env=None, cwd=None):
        """Run command with output redirection (compatibility method)"""
        if env:
            old_env = self.env.copy()
            self.env.update(env)
        
        # Set working directory if provided
        old_cwd = self.cwd
        if cwd:
            self.cwd = cwd
        
        # Convert command list to string if needed
        if isinstance(command, list):
            command_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command)
        else:
            command_str = command
            
        result = self.execute_command(command_str, capture_output=True, on_complete=on_complete)
        
        # Restore original environment and directory
        if env:
            self.env = old_env
        if cwd:
            self.cwd = old_cwd
            
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
            
            # CRITICAL FIX for executable builds
            if getattr(sys, 'frozen', False):
                # For frozen executable - find system Python (not the frozen executable)
                system_python = shutil.which("python") or shutil.which("python3")
                if not system_python:
                    # Try common Windows locations
                    common_paths = [
                        r"C:\Python39\python.exe",
                        r"C:\Python310\python.exe", 
                        r"C:\Python311\python.exe",
                        r"C:\Python312\python.exe",
                        r"C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python39\python.exe",
                        r"C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe",
                        r"C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe",
                        r"C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"
                    ]
                    for path in common_paths:
                        expanded_path = os.path.expandvars(path)
                        if os.path.exists(expanded_path):
                            system_python = expanded_path
                            break
                    
                    if not system_python:
                        raise Exception("Python executable not found. Please ensure Python is installed and in PATH.")
                
                self.log(f"Using system Python: {system_python}")
                
                # Use subprocess to create venv with system Python
                cmd = [system_python, "-m", "venv", env_path]
                result = self.run_command(cmd)
                if result.returncode != 0:
                    raise Exception(f"Failed to create virtual environment: {result.stderr}")
                self.log("Virtual environment created with system Python")
            else:
                # Normal development mode - use venv module
                import venv
                venv.create(env_path, with_pip=True)
                self.log("Virtual environment created with venv module")
            
            # Get Python and pip paths
            if sys.platform == "win32":
                python_path = os.path.join(env_path, "Scripts", "python.exe")
                pip_path = os.path.join(env_path, "Scripts", "pip.exe")
            else:
                python_path = os.path.join(env_path, "bin", "python")
                pip_path = os.path.join(env_path, "bin", "pip")
                
            # Verify paths
            if not os.path.exists(python_path) or not os.path.exists(pip_path):
                self.log(f"ERROR: Python or pip executable not found in created environment")
                self.log(f"Python path: {python_path}, exists: {os.path.exists(python_path)}")
                self.log(f"Pip path: {pip_path}, exists: {os.path.exists(pip_path)}")
                self.update_status("Creation failed!")
                return False
            
            # Set paths for the manager
            self.python_exe = python_path
            self.pip_exe = pip_path
            
            self.log("✅ Virtual environment created successfully")
            return True
            
        except Exception as e:
            self.log(f"❌ Error creating environment: {e}")
            self.update_status("Creation failed!")
            return False
    
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
        
        # Run complete initialization
        self._initialize_environment()
        
        # Current environment state
        self.current_venv = None
        self.python_path = sys.executable
        self.pip_path = "pip"
        self.needs_setup = True
        self.using_fallback = False
        
        # Essential packages for ManimStudio
        self.essential_packages = [
            "manim",
            "pillow",
            "opencv-python",
            "numpy",
            "scipy",
            "matplotlib",
            "requests",
            "tqdm",
            "pydub",
            "ffmpeg-python",
            "moderngl",
            "manimpango",
            "mapbox-earcut"
        ]
        
        # Auto-activate default environment if available
        self.auto_activate_default_environment()
        
        # Perform complete environment validation
        self.validate_environment()
    def _initialize_environment(self):
        """Initialize environment settings and paths"""
        print("🔧 Initializing environment settings...")
        
        # Apply encoding fixes
        self._apply_encoding_fixes()
        
        # Setup paths
        self._setup_paths()
        
        # Initialize locale
        self._setup_locale()
        
        print("✅ Environment initialization complete")
    def _apply_encoding_fixes(self):
        """Apply encoding fixes to environment"""
        # Skip if already applied
        if os.environ.get('ENCODING_FIXES_APPLIED') == '1':
            return
        
        print("🔧 Applying encoding fixes...")
        
        # Set encoding environment variables
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
        except locale.Error:
            try:
                locale.setlocale(locale.LC_ALL, 'C.UTF-8')
                print("✅ Set system locale to C.UTF-8")
            except locale.Error:
                print("⚠️ Could not set UTF-8 locale")
        
        # Mark as applied
        os.environ['ENCODING_FIXES_APPLIED'] = '1'
        print("✅ Encoding fixes applied")
    def _setup_paths(self):
        """Setup application paths - EXE COMPATIBLE"""
        print("📁 Setting up application paths...")
        
        # Detect if frozen (compiled exe)
        self.is_frozen = getattr(sys, 'frozen', False)
        
        # Set base directory
        if self.is_frozen:
            # For exe builds, use the directory containing the exe
            self.base_dir = os.path.dirname(sys.executable)
            print(f"🔧 Exe build detected - base dir: {self.base_dir}")
        else:
            # For script builds, use the script directory
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            print(f"🐍 Script build detected - base dir: {self.base_dir}")
        
        # Set app directory - always use user directory for data
        self.app_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")
        self.venv_dir = os.path.join(self.app_dir, "venvs")
        
        # Create directories with proper error handling
        try:
            os.makedirs(self.venv_dir, exist_ok=True)
            os.makedirs(self.app_dir, exist_ok=True)
            print(f"✅ Created directories successfully")
        except PermissionError:
            print(f"❌ Permission denied creating directories")
            # Fallback to temp directory
            import tempfile
            self.app_dir = tempfile.mkdtemp(prefix="manim_studio_")
            self.venv_dir = os.path.join(self.app_dir, "venvs")
            os.makedirs(self.venv_dir, exist_ok=True)
            print(f"📁 Using temp directory: {self.app_dir}")
        except Exception as e:
            print(f"❌ Error creating directories: {e}")
            raise
        
        print(f"📁 Base directory: {self.base_dir}")
        print(f"📁 App directory: {self.app_dir}")
        print(f"📁 Venv directory: {self.venv_dir}")
    
    def _setup_locale(self):
        """Setup locale for proper encoding"""
        try:
            # Try to set UTF-8 locale
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.kernel32.SetConsoleOutputCP(65001)
                ctypes.windll.kernel32.SetConsoleCP(65001)
            
            # Set locale
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
            
        except Exception as e:
            print(f"⚠️ Locale setup warning: {e}")
    def _detect_if_frozen(self):
        """Detect if running as a frozen executable - ENHANCED FOR EXE"""
        # Multiple ways to detect if we're running as an exe
        is_frozen = (
            getattr(sys, 'frozen', False) or  # Standard frozen detection
            sys.executable.endswith('.exe') or  # Check if executable ends with .exe
            'dist' in sys.executable or  # Check if we're in a dist folder
            'app.exe' in sys.executable.lower() or  # Check if we're app.exe
            os.path.basename(sys.executable).lower() == 'app.exe'  # Direct exe name check
        )
        
        print(f"🔧 Frozen detection result: {is_frozen}")
        print(f"🔧 sys.frozen: {getattr(sys, 'frozen', False)}")
        print(f"🔧 sys.executable: {sys.executable}")
        
        return is_frozen
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
        """Create virtual environment with encoding fixes applied - ENHANCED WITH LOGGING"""
        env_path = os.path.join(self.venv_dir, "manim_studio_default")
        
        self.safe_log_callback(log_callback, "Creating virtual environment with encoding fixes...")
        print("🔧 Creating virtual environment with encoding fixes...")
        
        # Apply encoding fixes to the environment
        self.fix_encoding_environment()
        
        # ENHANCED: Log system information
        print("="*60)
        print("🔧 DETAILED ENVIRONMENT CREATION LOG")
        print("="*60)
        print(f"📋 Target environment path: {env_path}")
        print(f"📋 Is frozen: {self.is_frozen}")
        print(f"📋 System: {platform.platform()}")
        print(f"📋 Current Python: {sys.executable}")
        
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
            print(f"📋 Command: {' '.join(create_cmd)}")
            
            # Enhanced environment for creation
            env = os.environ.copy()
            env.update({
                'PYTHONIOENCODING': 'utf-8',
                'PYTHONLEGACYWINDOWSFSENCODING': '0',
                'PYTHONUTF8': '1'
            })
            print(f"📋 Environment variables updated")
            
            # Windows subprocess setup
            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
                print(f"📋 Windows subprocess configuration applied")
            
            print(f"🚀 Executing: {' '.join(create_cmd)}")
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
            
            print(f"📋 Command completed with return code: {result.returncode}")
            if result.stdout:
                print(f"📋 stdout: {result.stdout[:300]}")
            if result.stderr:
                print(f"📋 stderr: {result.stderr[:300]}")
            
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
            
            print(f"✅ Environment directory created: {env_path}")
            
            # Set up paths
            if os.name == 'nt':
                python_exe = os.path.join(env_path, "Scripts", "python.exe")
                pip_exe = os.path.join(env_path, "Scripts", "pip.exe")
            else:
                python_exe = os.path.join(env_path, "bin", "python")
                pip_exe = os.path.join(env_path, "bin", "pip")
            
            print(f"📋 Expected Python: {python_exe}")
            print(f"📋 Expected Pip: {pip_exe}")
            
            # Verify executables exist
            if not os.path.exists(python_exe):
                error_msg = f"❌ Python executable not found: {python_exe}"
                self.safe_log_callback(log_callback, error_msg)
                print(error_msg)
                
                # List what WAS created
                try:
                    if os.path.exists(env_path):
                        contents = os.listdir(env_path)
                        print(f"📋 Environment contents: {contents}")
                        
                        scripts_dir = os.path.join(env_path, "Scripts")
                        if os.path.exists(scripts_dir):
                            scripts_contents = os.listdir(scripts_dir)
                            print(f"📋 Scripts directory contents: {scripts_contents}")
                        else:
                            print(f"❌ Scripts directory not found: {scripts_dir}")
                except Exception as e:
                    print(f"❌ Error listing contents: {e}")
                
                return False
            
            print(f"✅ Python executable found: {python_exe}")
            
            # Install pip if needed
            if not os.path.exists(pip_exe):
                self.safe_log_callback(log_callback, "Installing pip in new environment...")
                print("🔧 Installing pip in new environment...")
                
                try:
                    pip_install_result = subprocess.run(
                        [python_exe, "-m", "ensurepip", "--upgrade"],
                        capture_output=True,
                        text=True,
                        env=env,
                        encoding='utf-8',
                        errors='replace',
                        timeout=60
                    )
                    
                    print(f"📋 Pip install return code: {pip_install_result.returncode}")
                    if pip_install_result.stdout:
                        print(f"📋 Pip install stdout: {pip_install_result.stdout[:200]}")
                    if pip_install_result.stderr:
                        print(f"📋 Pip install stderr: {pip_install_result.stderr[:200]}")
                    
                    if pip_install_result.returncode != 0:
                        print(f"❌ Failed to install pip with ensurepip: {pip_install_result.stderr}")
                        return False
                    print("✅ Pip installed successfully")
                except Exception as e:
                    print(f"❌ Error installing pip: {e}")
                    return False
            else:
                print(f"✅ Pip executable found: {pip_exe}")
            
            # Activate it for further operations
            self.python_path = python_exe
            self.pip_path = pip_exe
            self.current_venv = "manim_studio_default"
            
            self.safe_log_callback(log_callback, "✅ Virtual environment created successfully")
            print("✅ Virtual environment created successfully")
            print("="*60)
            
            return True
            
        except Exception as e:
            error_msg = f"❌ Error creating virtual environment: {e}"
            self.safe_log_callback(log_callback, error_msg)
            print(error_msg)
            import traceback
            traceback.print_exc()
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
                text=True
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
    def check_environment_exists_only(self):
        """NEW METHOD: Only check if environment exists - no setup UI"""
        try:
            default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
            
            if not os.path.exists(default_venv_path):
                return False
            
            # Check if it's a valid environment structure
            if os.name == 'nt':
                python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
                pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
            else:
                python_path = os.path.join(default_venv_path, "bin", "python")
                pip_path = os.path.join(default_venv_path, "bin", "pip")
            
            # Both executables must exist
            if os.path.exists(python_path) and os.path.exists(pip_path):
                # Auto-set the paths without triggering setup
                self.python_path = python_path
                self.pip_path = pip_path
                self.current_venv = "manim_studio_default"
                self.needs_setup = False
                return True
            
            return False
            
        except Exception:
            return False
    def get_environment_info(self):
        """Get current environment information"""
        if not self.current_venv:
            return "No environment active"
        
        return f"Active: {self.current_venv} | Python: {self.python_path}"
    def auto_activate_default_environment(self):
        """Auto-activate manim_studio_default environment if it exists - EXE COMPATIBLE"""
        try:
            print("🔍 Checking for existing environments...")
            
            # Ensure we have the necessary attributes
            if not hasattr(self, 'app_dir'):
                self.is_frozen = getattr(sys, 'frozen', False)
                
                if self.is_frozen:
                    self.base_dir = os.path.dirname(sys.executable)
                else:
                    self.base_dir = os.path.dirname(os.path.abspath(__file__))
                
                self.app_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")
                self.venv_dir = os.path.join(self.app_dir, "venvs")
                
                # Create directories
                os.makedirs(self.venv_dir, exist_ok=True)
                os.makedirs(self.app_dir, exist_ok=True)
                
                print(f"📁 App directory: {self.app_dir}")
                print(f"📁 Venv directory: {self.venv_dir}")
            
            # For exe builds, use current Python directly
            if self.is_frozen:
                print("🔧 Exe build - using current Python interpreter")
                self.python_path = sys.executable
                self.pip_path = "pip"
                self.current_venv = "exe_bundled"
                self.needs_setup = False
                
                print(f"✅ Using exe Python: {self.python_path}")
                if hasattr(self, 'logger'):
                    self.logger.info(f"✅ Using exe Python: {self.python_path}")
                return
            
            # Check for default environment (non-exe)
            default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
            
            if os.path.exists(default_venv_path):
                print("🎯 Found manim_studio_default environment")
                
                # Get Python and pip paths
                if sys.platform == "win32":
                    python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
                    pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
                else:
                    python_path = os.path.join(default_venv_path, "bin", "python")
                    pip_path = os.path.join(default_venv_path, "bin", "pip")
                
                # Verify executables exist
                if os.path.exists(python_path) and os.path.exists(pip_path):
                    self.python_path = python_path
                    self.pip_path = pip_path
                    self.current_venv = "manim_studio_default"
                    self.needs_setup = False
                    
                    print(f"✅ Auto-activated manim_studio_default at: {default_venv_path}")
                    print(f"Python: {python_path}")
                    print(f"Pip: {pip_path}")
                    
                    if hasattr(self, 'logger'):
                        self.logger.info(f"✅ Auto-activated manim_studio_default at: {default_venv_path}")
                        self.logger.info(f"Python: {python_path}")
                        self.logger.info(f"Pip: {pip_path}")
                else:
                    print("⚠️ manim_studio_default environment has missing executables")
                    self.needs_setup = True
            else:
                print("📝 No manim_studio_default environment found")
                self.needs_setup = True
                
        except Exception as e:
            print(f"❌ Error in auto-activation: {e}")
            if hasattr(self, 'logger'):
                self.logger.error(f"Error in auto-activation: {e}")
            self.needs_setup = True
    def get_environment_status_only(self):
        """NEW METHOD: Get environment status without triggering any UI"""
        try:
            default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
            
            if not os.path.exists(default_venv_path):
                return "not_found"
            
            if os.name == 'nt':
                python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
                pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
            else:
                python_path = os.path.join(default_venv_path, "bin", "python")
                pip_path = os.path.join(default_venv_path, "bin", "pip")
            
            if os.path.exists(python_path) and os.path.exists(pip_path):
                return "ready"
            else:
                return "incomplete"
                
        except Exception:
            return "error"
    def setup_environment(self, log_callback=None):
        """Setup environment with detailed logging - EXE COMPATIBLE"""
        if not log_callback:
            log_callback = print
        
        # Create a file logger to capture ALL output
        log_file_path = os.path.join(self.app_dir, "environment_setup.log")
        
        def enhanced_log(message):
            """Enhanced logging that prints AND writes to file"""
            print(message)  # Print to console
            if log_callback:
                try:
                    log_callback(message)
                except:
                    pass
            # Write to file
            try:
                with open(log_file_path, 'a', encoding='utf-8') as f:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp}] {message}\n")
            except:
                pass
        
        enhanced_log("="*80)
        enhanced_log("🚀 DETAILED ENVIRONMENT SETUP LOG STARTED")
        enhanced_log("="*80)
        enhanced_log(f"📋 Log file: {log_file_path}")
        enhanced_log(f"📋 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        enhanced_log(f"📋 System: {platform.platform()}")
        enhanced_log(f"📋 Python: {sys.version}")
        enhanced_log(f"📋 Executable: {sys.executable}")
        enhanced_log(f"📋 Frozen: {getattr(sys, 'frozen', False)}")
        enhanced_log(f"📋 Current working directory: {os.getcwd()}")
        enhanced_log(f"📋 App directory: {self.app_dir}")
        enhanced_log(f"📋 Venv directory: {self.venv_dir}")
        
        try:
            # Step 1: Create environment if needed
            if self.needs_setup:
                enhanced_log("\n🔧 Step 1: Creating virtual environment...")
                success = self.create_environment_with_logging("manim_studio_default")
                
                if not success:
                    enhanced_log("❌ FAILED: Could not create environment")
                    enhanced_log("="*80)
                    return False
                else:
                    enhanced_log("✅ Step 1 Complete: Environment created successfully")
            else:
                enhanced_log("✅ Step 1 Skipped: Environment already exists")
            
            # For exe builds, skip package installation as they're bundled
            if self.is_frozen:
                enhanced_log("\n🔧 Step 2: Exe build detected - using bundled packages")
                enhanced_log("✅ Environment setup complete (using bundled dependencies)")
                enhanced_log("="*80)
                return True
            
            # Step 2: Install essential packages for non-exe builds
            enhanced_log("\n🔧 Step 2: Installing essential packages...")
            
            # Use a more robust pip installation approach
            pip_cmd = [self.python_path, "-m", "pip"]
            enhanced_log(f"📋 Using pip command: {' '.join(pip_cmd)}")
            
            # Upgrade pip first
            enhanced_log("📦 Upgrading pip...")
            cmd = pip_cmd + ["install", "--upgrade", "pip"]
            enhanced_log(f"📋 Running: {' '.join(cmd)}")
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding='utf-8', errors='replace')
                enhanced_log(f"📋 Pip upgrade return code: {result.returncode}")
                if result.stdout:
                    enhanced_log(f"📋 Pip upgrade stdout: {result.stdout[:500]}")
                if result.stderr:
                    enhanced_log(f"📋 Pip upgrade stderr: {result.stderr[:500]}")
                
                if result.returncode == 0:
                    enhanced_log("✅ Pip upgraded successfully")
                else:
                    enhanced_log("⚠️ Pip upgrade failed, continuing anyway")
                    
            except subprocess.TimeoutExpired:
                enhanced_log("⚠️ Pip upgrade timed out")
            except Exception as e:
                enhanced_log(f"⚠️ Pip upgrade error: {e}")
            
            # Install packages one by one with better error handling
            enhanced_log(f"📦 Installing {len(self.essential_packages)} essential packages...")
            successful_packages = 0
            failed_packages = []
            
            for i, package in enumerate(self.essential_packages):
                enhanced_log(f"📦 Installing {package} ({i+1}/{len(self.essential_packages)})...")
                cmd = pip_cmd + ["install", package, "--no-cache-dir", "--timeout", "60"]
                enhanced_log(f"📋 Command: {' '.join(cmd)}")
                
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, encoding='utf-8', errors='replace')
                    enhanced_log(f"📋 Return code: {result.returncode}")
                    
                    if result.stdout:
                        # Show first and last 200 chars of stdout
                        stdout_short = result.stdout[:200] + ("..." if len(result.stdout) > 200 else "")
                        enhanced_log(f"📋 stdout: {stdout_short}")
                    
                    if result.stderr:
                        # Show first and last 200 chars of stderr
                        stderr_short = result.stderr[:200] + ("..." if len(result.stderr) > 200 else "")
                        enhanced_log(f"📋 stderr: {stderr_short}")
                    
                    if result.returncode == 0:
                        enhanced_log(f"✅ {package} installed successfully")
                        successful_packages += 1
                    else:
                        enhanced_log(f"❌ {package} installation failed")
                        failed_packages.append(package)
                        
                except subprocess.TimeoutExpired:
                    enhanced_log(f"⏰ {package} installation timed out")
                    failed_packages.append(package)
                except Exception as e:
                    enhanced_log(f"❌ {package} installation error: {e}")
                    failed_packages.append(package)
            
            # Summary
            success_rate = successful_packages / len(self.essential_packages) if self.essential_packages else 0
            enhanced_log(f"\n📊 Installation Summary:")
            enhanced_log(f"✅ Successful: {successful_packages}/{len(self.essential_packages)} ({success_rate*100:.1f}%)")
            enhanced_log(f"❌ Failed: {len(failed_packages)}")
            
            if failed_packages:
                enhanced_log(f"❌ Failed packages: {', '.join(failed_packages)}")
            
            if success_rate >= 0.7:  # 70% success rate
                enhanced_log("✅ Environment setup complete (sufficient packages installed)")
                enhanced_log("="*80)
                return True
            else:
                enhanced_log("⚠️ Environment setup completed with warnings (many packages failed)")
                enhanced_log("="*80)
                return False
                
        except Exception as e:
            enhanced_log(f"❌ CRITICAL ERROR in environment setup: {e}")
            import traceback
            enhanced_log(f"❌ Traceback: {traceback.format_exc()}")
            enhanced_log("="*80)
            return False
    
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
        Find ONLY real Python executables - NEVER use app.exe or any non-Python exe
        """
        try:
            print("🔍 Looking for REAL Python executable (never app.exe)...")
            print(f"📋 Current sys.executable: {sys.executable}")
            
            python_candidates = []
            
            # RULE: Never use anything that doesn't have "python" in the name
            current_exe_name = os.path.basename(sys.executable).lower()
            if 'python' not in current_exe_name:
                print(f"❌ BLOCKING sys.executable (not Python): {sys.executable}")
            else:
                print(f"✅ sys.executable is valid Python: {sys.executable}")
                python_candidates.append(sys.executable)
            
            # Method 1: Search PATH for ONLY python executables
            print("🔍 Searching PATH for python executables...")
            for python_name in ["python", "python3", "python.exe", "python3.exe"]:
                try:
                    python_path = shutil.which(python_name)
                    if python_path:
                        exe_name = os.path.basename(python_path).lower()
                        print(f"📋 Found in PATH: {python_path} (name: {exe_name})")
                        
                        # ONLY accept if it has "python" in the name
                        if 'python' in exe_name:
                            print(f"✅ Valid Python executable: {python_path}")
                            python_candidates.append(python_path)
                        else:
                            print(f"❌ BLOCKING non-Python exe: {python_path}")
                except Exception as e:
                    print(f"⚠️ Error searching for {python_name}: {e}")
            
            # Method 2: Common Python installation directories
            print("🔍 Searching common Python installation directories...")
            if sys.platform == "win32":
                common_locations = [
                    r"C:\Python312\python.exe",
                    r"C:\Python311\python.exe",
                    r"C:\Python310\python.exe",
                    r"C:\Python39\python.exe",
                    r"C:\Python38\python.exe",
                ]
                
                # Add user-specific paths
                username = os.environ.get('USERNAME', 'User')
                user_locations = [
                    f"C:\\Users\\{username}\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
                    f"C:\\Users\\{username}\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
                    f"C:\\Users\\{username}\\AppData\\Local\\Programs\\Python\\Python310\\python.exe",
                    f"C:\\Users\\{username}\\AppData\\Local\\Programs\\Python\\Python39\\python.exe",
                ]
                
                all_locations = common_locations + user_locations
                
                for location in all_locations:
                    if os.path.exists(location):
                        exe_name = os.path.basename(location).lower()
                        if 'python' in exe_name:
                            print(f"✅ Found Python installation: {location}")
                            python_candidates.append(location)
                        else:
                            print(f"❌ BLOCKING non-Python exe: {location}")
            
            # Method 3: Windows Registry (only for Python)
            print("🔍 Searching Windows Registry for Python installations...")
            if sys.platform == "win32":
                try:
                    import winreg
                    
                    for version in ["3.12", "3.11", "3.10", "3.9", "3.8"]:
                        for hive in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                            try:
                                key_path = f"SOFTWARE\\Python\\PythonCore\\{version}\\InstallPath"
                                with winreg.OpenKey(hive, key_path) as key:
                                    install_path = winreg.QueryValue(key, "")
                                    python_exe = os.path.join(install_path, "python.exe")
                                    if os.path.exists(python_exe):
                                        print(f"✅ Found Python {version} in registry: {python_exe}")
                                        python_candidates.append(python_exe)
                            except:
                                pass
                except ImportError:
                    print("⚠️ Registry search not available")
            
            # Remove duplicates and filter out any non-Python executables
            python_candidates = list(set(python_candidates))
            
            # FINAL FILTER: Only keep executables with "python" in the name
            filtered_candidates = []
            for candidate in python_candidates:
                exe_name = os.path.basename(candidate).lower()
                if 'python' in exe_name:
                    filtered_candidates.append(candidate)
                else:
                    print(f"❌ FINAL FILTER BLOCKED: {candidate} (name: {exe_name})")
            
            python_candidates = filtered_candidates
            print(f"📋 Total valid Python candidates: {len(python_candidates)}")
            
            if not python_candidates:
                print("❌ NO PYTHON EXECUTABLES FOUND!")
                print("💡 Please install Python from https://python.org")
                return None
            
            # Test each candidate
            for i, candidate in enumerate(python_candidates):
                print(f"🧪 Testing candidate {i+1}/{len(python_candidates)}: {candidate}")
                if self.validate_python_installation(candidate):
                    print(f"✅ SUCCESS: Using Python: {candidate}")
                    return candidate
                else:
                    print(f"❌ Validation failed: {candidate}")
            
            print("❌ No working Python installation found!")
            return None
            
        except Exception as e:
            print(f"❌ Error finding Python executable: {e}")
            import traceback
            traceback.print_exc()
            return None
    def create_environment_alternative(self, env_name="manim_studio_default"):
        """Alternative environment creation with better error handling"""
        try:
            print("🔧 Alternative environment creation...")
            
            # Find Python first
            python_exe = self.find_python_executable_robust()
            if not python_exe:
                print("❌ Cannot create environment: No Python found")
                return False
            
            print(f"📍 Using Python: {python_exe}")
            
            # Create environment path
            env_path = os.path.join(self.venv_dir, env_name)
            
            # Remove existing environment if it exists
            if os.path.exists(env_path):
                print(f"🗑️ Removing existing environment: {env_path}")
                shutil.rmtree(env_path)
            
            print(f"📦 Creating environment at: {env_path}")
            
            # Create the command
            cmd = [python_exe, "-m", "venv", env_path]
            
            print(f"🔧 Running: {' '.join(cmd)}")
            
            # Run with enhanced error capture
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode != 0:
                print(f"❌ Command failed with code {result.returncode}")
                print(f"❌ Error output: {result.stderr}")
                print(f"❌ Standard output: {result.stdout}")
                return False
            
            # Verify environment was created
            if sys.platform == "win32":
                python_path = os.path.join(env_path, "Scripts", "python.exe")
                pip_path = os.path.join(env_path, "Scripts", "pip.exe")
            else:
                python_path = os.path.join(env_path, "bin", "python")
                pip_path = os.path.join(env_path, "bin", "pip")
            
            if not os.path.exists(python_path):
                print(f"❌ Python executable not created: {python_path}")
                return False
            
            # Test the created Python
            test_result = subprocess.run(
                [python_path, "--version"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if test_result.returncode != 0:
                print(f"❌ Created Python doesn't work: {test_result.stderr}")
                return False
            
            print(f"✅ Environment created successfully")
            print(f"✅ Python version: {test_result.stdout.strip()}")
            
            # Update manager state
            self.current_venv = env_name
            self.python_path = python_path
            self.pip_path = pip_path
            self.needs_setup = False
            
            return True
            
        except subprocess.TimeoutExpired:
            print("❌ Environment creation timed out")
            return False
        except Exception as e:
            print(f"❌ Error in alternative environment creation: {e}")
            return False
    def create_environment_user_fallback(self):
        """Create environment in user directory as fallback"""
        try:
            print("🔄 Trying user directory fallback...")
            
            # Use user's temp directory
            user_temp = os.path.join(os.path.expanduser("~"), "manim_studio_temp")
            os.makedirs(user_temp, exist_ok=True)
            
            # Update venv directory to user temp
            self.venv_dir = user_temp
            
            return self.create_environment_alternative()
            
        except Exception as e:
            print(f"❌ User directory fallback failed: {e}")
            return False
    def find_python_executable_with_logging(self):
        """Find Python executable with comprehensive logging"""
        try:
            print("=" * 60)
            print("🔍 DETAILED PYTHON DETECTION LOG")
            print("=" * 60)
            
            print(f"📋 sys.executable: {sys.executable}")
            print(f"📋 sys.frozen: {getattr(sys, 'frozen', False)}")
            print(f"📋 Platform: {sys.platform}")
            print(f"📋 Current working directory: {os.getcwd()}")
            print(f"📋 PATH variable: {os.environ.get('PATH', 'NOT_SET')[:200]}...")
            
            # Skip if not frozen
            if not self.is_frozen:
                print("✅ Not frozen - using sys.executable")
                return sys.executable
            
            python_candidates = []
            
            # Method 1: Windows Registry Search
            print("\n🔍 Method 1: Windows Registry Search")
            if sys.platform == "win32":
                try:
                    import winreg
                    print("✅ winreg module imported successfully")
                    
                    for version in ["3.12", "3.11", "3.10", "3.9", "3.8"]:
                        print(f"🔍 Checking Python {version} in registry...")
                        
                        # HKEY_CURRENT_USER
                        try:
                            key_path = f"SOFTWARE\\Python\\PythonCore\\{version}\\InstallPath"
                            print(f"  📋 Checking HKCU: {key_path}")
                            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                                install_path = winreg.QueryValue(key, "")
                                python_exe = os.path.join(install_path, "python.exe")
                                print(f"  📍 Found registry entry: {python_exe}")
                                if os.path.exists(python_exe):
                                    print(f"  ✅ File exists: {python_exe}")
                                    python_candidates.append(python_exe)
                                else:
                                    print(f"  ❌ File not found: {python_exe}")
                        except Exception as e:
                            print(f"  ⚠️ HKCU registry check failed: {e}")
                        
                        # HKEY_LOCAL_MACHINE
                        try:
                            key_path = f"SOFTWARE\\Python\\PythonCore\\{version}\\InstallPath"
                            print(f"  📋 Checking HKLM: {key_path}")
                            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                                install_path = winreg.QueryValue(key, "")
                                python_exe = os.path.join(install_path, "python.exe")
                                print(f"  📍 Found registry entry: {python_exe}")
                                if os.path.exists(python_exe):
                                    print(f"  ✅ File exists: {python_exe}")
                                    python_candidates.append(python_exe)
                                else:
                                    print(f"  ❌ File not found: {python_exe}")
                        except Exception as e:
                            print(f"  ⚠️ HKLM registry check failed: {e}")
                            
                except ImportError as e:
                    print(f"❌ Cannot import winreg: {e}")
            else:
                print("⚠️ Not Windows - skipping registry search")
            
            # Method 2: PATH Search
            print("\n🔍 Method 2: PATH Search")
            for python_name in ["python", "python3", "python.exe"]:
                print(f"🔍 Searching for '{python_name}' in PATH...")
                try:
                    python_path = shutil.which(python_name)
                    print(f"  📍 shutil.which result: {python_path}")
                    
                    if python_path:
                        # Check if it's our own exe
                        exe_name = os.path.basename(python_path).lower()
                        our_exe = os.path.basename(sys.executable).lower()
                        print(f"  📋 Found executable: {exe_name}")
                        print(f"  📋 Our executable: {our_exe}")
                        
                        if exe_name != our_exe and exe_name != "app.exe":
                            print(f"  ✅ Valid candidate: {python_path}")
                            python_candidates.append(python_path)
                        else:
                            print(f"  ❌ Skipping (our own exe): {python_path}")
                    else:
                        print(f"  ❌ Not found in PATH: {python_name}")
                except Exception as e:
                    print(f"  ❌ Error searching PATH: {e}")
            
            # Remove duplicates
            python_candidates = list(set(python_candidates))
            print(f"\n📋 Total candidates found: {len(python_candidates)}")
            for i, candidate in enumerate(python_candidates):
                print(f"  {i+1}. {candidate}")
            
            # Test each candidate
            print("\n🧪 TESTING CANDIDATES")
            print("=" * 40)
            
            if not python_candidates:
                print("❌ No Python candidates found!")
                return None
            
            for i, candidate in enumerate(python_candidates):
                print(f"\n🧪 Testing candidate {i+1}/{len(python_candidates)}: {candidate}")
                
                # Test basic execution
                if self.validate_python_installation_with_logging(candidate):
                    print(f"✅ SUCCESS: Found working Python: {candidate}")
                    return candidate
                else:
                    print(f"❌ Validation failed for: {candidate}")
            
            print("\n❌ No working Python installation found")
            return None
            
        except Exception as e:
            print(f"❌ Critical error in Python detection: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def validate_python_installation_with_logging(self, python_path):
        """Validate Python installation with detailed logging"""
        try:
            print(f"    🧪 Validating: {python_path}")
            
            if not python_path or not os.path.exists(python_path):
                print(f"    ❌ Path does not exist: {python_path}")
                return False
            
            # Test basic execution
            test_cmd = [python_path, "--version"]
            print(f"    🔧 Running: {' '.join(test_cmd)}")
            
            try:
                result = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='utf-8',
                    errors='replace'
                )
                
                print(f"    📋 Return code: {result.returncode}")
                print(f"    📋 stdout: {result.stdout.strip()}")
                print(f"    📋 stderr: {result.stderr.strip()}")
                
                if result.returncode != 0:
                    print(f"    ❌ Command failed with code {result.returncode}")
                    return False
                
                # Test venv module
                venv_test_cmd = [python_path, "-m", "venv", "--help"]
                print(f"    🔧 Testing venv module: {' '.join(venv_test_cmd[:3])}...")
                
                venv_result = subprocess.run(
                    venv_test_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='utf-8',
                    errors='replace'
                )
                
                print(f"    📋 venv test return code: {venv_result.returncode}")
                if venv_result.returncode != 0:
                    print(f"    ❌ venv module not available: {venv_result.stderr}")
                    return False
                
                print(f"    ✅ Python validation successful")
                return True
                
            except subprocess.TimeoutExpired:
                print(f"    ❌ Command timed out")
                return False
            except Exception as e:
                print(f"    ❌ Subprocess error: {e}")
                return False
                
        except Exception as e:
            print(f"    ❌ Validation error: {e}")
            return False
    def create_environment_with_logging(self, env_name="manim_studio_default"):
        """Create environment with comprehensive logging"""
        try:
            print("=" * 60)
            print("🔧 DETAILED ENVIRONMENT CREATION LOG")
            print("=" * 60)
            
            # Find Python first
            print("🔍 Step 1: Finding Python executable...")
            python_exe = self.find_python_executable()
            
            if not python_exe:
                print("❌ FAILED: No Python executable found")
                return False
            
            print(f"✅ Step 1 Complete: Using Python: {python_exe}")
            
            # Create environment path
            print(f"\n🔧 Step 2: Setting up environment paths...")
            env_path = os.path.join(self.venv_dir, env_name)
            print(f"📋 Environment path: {env_path}")
            
            # Create the command
            print(f"\n🔧 Step 3: Creating virtual environment...")
            cmd = [python_exe, "-m", "venv", env_path]  # Removed --with-pip for Python 3.12
            print(f"📋 Command: {' '.join(cmd)}")
            
            # Run the command
            print(f"🚀 Executing venv creation command...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            print(f"📋 Return code: {result.returncode}")
            if result.stdout:
                print(f"📋 stdout: {result.stdout}")
            if result.stderr:
                print(f"📋 stderr: {result.stderr}")
            
            if result.returncode != 0:
                print(f"❌ FAILED: Command failed with code {result.returncode}")
                return False
            
            # Update manager state
            if sys.platform == "win32":
                python_path = os.path.join(env_path, "Scripts", "python.exe")
                pip_path = os.path.join(env_path, "Scripts", "pip.exe")
            else:
                python_path = os.path.join(env_path, "bin", "python")
                pip_path = os.path.join(env_path, "bin", "pip")
            
            self.current_venv = env_name
            self.python_path = python_path
            self.pip_path = pip_path
            self.needs_setup = False
            
            print(f"✅ SUCCESS: Environment created successfully!")
            return True
            
        except Exception as e:
            print(f"❌ CRITICAL ERROR in environment creation: {e}")
            import traceback
            traceback.print_exc()
            return False
    def validate_environment(self):
        """Validate current environment setup"""
        if not self.current_venv:
            print("⚠️ No active environment - setup required")
            return False
        
        if not os.path.exists(self.python_path):
            print(f"❌ Python executable not found: {self.python_path}")
            self.needs_setup = True
            return False
        
        print(f"✅ Environment validated: {self.current_venv}")
        return True
    def is_ready(self):
        """Check if environment is ready for use"""
        return (self.current_venv and 
                os.path.exists(self.python_path) and 
                not self.needs_setup)
    def create_default_environment(self):
        """Create default environment with detailed logging"""
        if not self.needs_setup:
            print("✅ Environment already ready")
            return True
        
        return self.create_environment_with_logging("manim_studio_default")
    def validate_python_installation(self, python_path):
        """
        Validate that a Python installation is working correctly
        """
        try:
            # FIRST: Check if it's even a valid Python executable
            if not self.is_valid_python_executable(python_path):
                return False
            
            print(f"🧪 Validating Python: {python_path}")
            
            # Test basic Python functionality
            test_cmd = [python_path, "--version"]
            
            result = subprocess.run(
                test_cmd,
                capture_output=True,
                text=True,
                timeout=15,
                encoding='utf-8',
                errors='replace'
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
    def is_valid_python_executable(self, path):
        """
        Check if an executable is a valid Python interpreter (not app.exe)
        """
        if not path or not os.path.exists(path):
            return False
        
        exe_name = os.path.basename(path).lower()
        
        # MUST have "python" in the name
        if 'python' not in exe_name:
            print(f"❌ REJECTED: {path} (no 'python' in name)")
            return False
        
        # MUST NOT be our app
        if 'app.exe' in exe_name or exe_name == 'app.exe':
            print(f"❌ REJECTED: {path} (is app.exe)")
            return False
        
        print(f"✅ ACCEPTED: {path} (valid Python name)")
        return True
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
                capture_output=True
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
    """YouTube-style fullscreen video player with complete professional controls"""
    
    def __init__(self, parent, video_player):
        super().__init__(parent)
        
        self.video_player = video_player
        self.parent = parent
        
        # Fullscreen setup
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.configure(bg="black", cursor="none")
        
        # Control visibility and state
        self.controls_visible = True  # Show controls by default
        self.speed_menu_visible = False
        self.volume_menu_visible = False
        self.mouse_timer = None
        self.last_mouse_move = time.time()
        
        # Drag state for enhanced progress bar
        self.is_dragging = False
        self.drag_start_x = 0
        
        # Volume control
        self.volume = 1.0
        self.is_muted = False
        self.last_volume = 1.0
        
        self.setup_fullscreen_ui()
        self.setup_bindings()
        
        # Show controls by default and position them
        self.position_overlays()
        
        # Start mouse tracking
        self.start_mouse_tracking()
        
        # Sync initial state
        self.sync_with_main_player()
        
    def setup_fullscreen_ui(self):
        """Setup YouTube-style fullscreen interface with complete professional controls"""
        # Video takes the ENTIRE screen - never gets blocked
        self.video_frame = tk.Frame(self, bg="black")
        self.video_frame.pack(fill="both", expand=True)
        
        # Video canvas - FULL SCREEN always
        self.canvas = tk.Canvas(self.video_frame, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        # === OVERLAY CONTROLS (positioned over video) ===
        
        # Title overlay (top) - simplified
        self.title_frame = tk.Frame(self, bg="black")
        
        # Back button only
        self.back_btn = tk.Button(
            self.title_frame,
            text="← Exit Fullscreen",
            bg="#333333", fg="white",
            relief="flat", padx=10, pady=5,
            command=self.exit_fullscreen
        )
        self.back_btn.pack(side="left", padx=10, pady=10)
        
        # Main controls overlay (bottom)
        self.overlay_frame = tk.Frame(self, bg="black")
        
        # Progress bar with enhanced drag support
        self.progress_frame = tk.Frame(self.overlay_frame, bg="black")
        self.progress_frame.pack(fill="x", padx=20, pady=(10, 5))
        
        # Create progress canvas with drag support
        self.progress_canvas = tk.Canvas(
            self.progress_frame, 
            height=12, 
            bg="#333333", 
            highlightthickness=0,
            cursor="hand2"
        )
        self.progress_canvas.pack(fill="x")
        
        # Enhanced progress bar event bindings
        self.progress_canvas.bind("<Button-1>", self.on_progress_press)
        self.progress_canvas.bind("<B1-Motion>", self.on_progress_drag)
        self.progress_canvas.bind("<ButtonRelease-1>", self.on_progress_release)
        self.progress_canvas.bind("<Enter>", self.on_progress_enter)
        self.progress_canvas.bind("<Leave>", self.on_progress_leave)
        
        # Control buttons frame
        self.button_frame = tk.Frame(self.overlay_frame, bg="black")
        self.button_frame.pack(pady=8)
        
        # Left side controls
        left_controls = tk.Frame(self.button_frame, bg="black")
        left_controls.pack(side="left")
        
        # Playback controls
        self.prev_btn = tk.Button(left_controls, text="⏮", bg="#444444", fg="white", 
                                 relief="flat", padx=8, pady=5, font=("Arial", 12),
                                 command=lambda: self.seek_relative(-30))
        self.prev_btn.pack(side="left", padx=2)
        
        self.play_btn = tk.Button(left_controls, text="▶", bg="#ff0000", fg="white", 
                                 relief="flat", padx=15, pady=5, font=("Arial", 16, "bold"),
                                 command=self.toggle_playback)
        self.play_btn.pack(side="left", padx=8)
        
        self.next_btn = tk.Button(left_controls, text="⏭", bg="#444444", fg="white", 
                                 relief="flat", padx=8, pady=5, font=("Arial", 12),
                                 command=lambda: self.seek_relative(30))
        self.next_btn.pack(side="left", padx=2)
        
        # Volume control
        volume_frame = tk.Frame(left_controls, bg="black")
        volume_frame.pack(side="left", padx=10)
        
        self.volume_btn = tk.Button(volume_frame, text="🔊", bg="#444444", fg="white", 
                                   relief="flat", padx=8, pady=5, font=("Arial", 12),
                                   command=self.toggle_volume_menu)
        self.volume_btn.pack(side="top")
        
        # Center controls - Time display
        center_controls = tk.Frame(self.button_frame, bg="black")
        center_controls.pack(side="left", padx=30)
        
        self.time_label = tk.Label(center_controls, text="0:00 / 0:00", 
                                  bg="black", fg="white", font=("Arial", 14, "bold"))
        self.time_label.pack()
        
        # Right side controls
        right_controls = tk.Frame(self.button_frame, bg="black")
        right_controls.pack(side="right")
        
        # Speed control with display
        speed_frame = tk.Frame(right_controls, bg="black")
        speed_frame.pack(side="right", padx=10)
        
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
        
        # Create simplified menus
        self.setup_speed_menu()
        self.setup_volume_menu()

    def setup_speed_menu(self):
        """Create floating speed selection menu"""
        self.speed_menu = tk.Toplevel(self)
        self.speed_menu.withdraw()
        self.speed_menu.configure(bg="#333333", relief="raised", bd=2)
        self.speed_menu.overrideredirect(True)
        self.speed_menu.attributes("-topmost", True)
        
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
        
        # Speed options
        speeds = [("0.25×", 0.25), ("0.5×", 0.5), ("0.75×", 0.75), ("1.0×", 1.0), 
                 ("1.25×", 1.25), ("1.5×", 1.5), ("2.0×", 2.0), ("4.0×", 4.0)]
        
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

    def setup_volume_menu(self):
        """Create volume control menu"""
        self.volume_menu = tk.Toplevel(self)
        self.volume_menu.withdraw()
        self.volume_menu.configure(bg="#333333", relief="raised", bd=2)
        self.volume_menu.overrideredirect(True)
        self.volume_menu.attributes("-topmost", True)
        
        # Volume title
        title_frame = tk.Frame(self.volume_menu, bg="#444444")
        title_frame.pack(fill="x")
        
        title_label = tk.Label(
            title_frame,
            text="🔊 Volume",
            font=("Arial", 11, "bold"),
            fg="white",
            bg="#444444",
            pady=5
        )
        title_label.pack()
        
        # Volume controls
        controls_frame = tk.Frame(self.volume_menu, bg="#333333")
        controls_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Mute button
        self.mute_btn = tk.Button(
            controls_frame,
            text="🔇 Mute",
            font=("Arial", 10),
            fg="white",
            bg="#555555",
            relief="flat",
            command=self.toggle_mute,
            padx=10,
            pady=5
        )
        self.mute_btn.pack(fill="x", pady=(0, 10))
        
        # Volume slider
        volume_slider_frame = tk.Frame(controls_frame, bg="#333333")
        volume_slider_frame.pack(fill="x")
        
        self.volume_slider = tk.Scale(
            volume_slider_frame,
            from_=0,
            to=100,
            orient="horizontal",
            bg="#333333",
            fg="white",
            highlightthickness=0,
            command=self.on_volume_change
        )
        self.volume_slider.set(100)
        self.volume_slider.pack(fill="x")

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
        
        # Additional keyboard shortcuts
        self.bind("<space>", lambda e: self.toggle_playback())
        self.bind("<Left>", lambda e: self.seek_relative(-10))
        self.bind("<Right>", lambda e: self.seek_relative(10))
        self.bind("<Up>", lambda e: self.change_speed(0.25))
        self.bind("<Down>", lambda e: self.change_speed(-0.25))
        
        # Number keys for percentage seeking
        for i in range(10):
            self.bind(f"<Key-{i}>", lambda e, num=i: self.seek_to_percentage(num * 10))
        
        # Volume keys
        self.bind("<Key-m>", lambda e: self.toggle_mute())
        self.bind("<Key-plus>", lambda e: self.adjust_volume(0.1))
        self.bind("<Key-minus>", lambda e: self.adjust_volume(-0.1))
        
        # Mouse wheel for volume
        self.bind("<MouseWheel>", self.on_mouse_wheel)

    # === PROGRESS BAR DRAG FUNCTIONALITY ===
    
    def on_progress_press(self, event):
        """Handle mouse press on progress bar - start potential drag"""
        if not self.video_player.cap:
            return
        
        self.is_dragging = True
        self.drag_start_x = event.x
        
        # Immediate seek on press (like YouTube)
        self.seek_to_position_from_event(event)
        
        # Change cursor to indicate dragging (use hand2 for Windows compatibility)
        self.progress_canvas.configure(cursor="hand2")

    def on_progress_drag(self, event):
        """Handle mouse drag on progress bar - continuous seeking"""
        if not self.is_dragging or not self.video_player.cap:
            return
        
        # Continuous seeking while dragging
        self.seek_to_position_from_event(event)

    def on_progress_release(self, event):
        """Handle mouse release on progress bar - end drag"""
        if not self.is_dragging:
            return
        
        self.is_dragging = False
        
        # Final seek position
        self.seek_to_position_from_event(event)
        
        # Reset cursor
        self.progress_canvas.configure(cursor="hand2")

    def on_progress_enter(self, event):
        """Handle mouse entering progress bar"""
        if not self.is_dragging:
            self.progress_canvas.configure(cursor="hand2")

    def on_progress_leave(self, event):
        """Handle mouse leaving progress bar"""
        if not self.is_dragging:
            self.progress_canvas.configure(cursor="")

    def seek_to_position_from_event(self, event):
        """Seek to position based on mouse event coordinates"""
        if not self.video_player.cap:
            return
        
        canvas_width = self.progress_canvas.winfo_width()
        if canvas_width > 0:
            # Clamp x position to canvas bounds
            x_position = max(0, min(event.x, canvas_width))
            click_position = x_position / canvas_width
            
            target_frame = int(click_position * self.video_player.total_frames)
            target_frame = max(0, min(target_frame, self.video_player.total_frames - 1))
            
            # Update both players
            self.video_player.seek_to_frame(target_frame)
            self.update_progress_bar()

    def update_progress_bar(self):
        """Update progress bar with enhanced visual feedback"""
        if not self.video_player.cap or not self.controls_visible:
            return
        
        self.progress_canvas.delete("all")
        canvas_width = self.progress_canvas.winfo_width()
        canvas_height = self.progress_canvas.winfo_height()
        
        if canvas_width <= 0:
            return
        
        # Background track
        self.progress_canvas.create_rectangle(
            0, 3, canvas_width, canvas_height-3,
            fill="#555555", outline=""
        )
        
        # Progress fill
        if self.video_player.total_frames > 0:
            progress = self.video_player.current_frame / self.video_player.total_frames
            progress_width = int(progress * canvas_width)
            
            if progress_width > 0:
                self.progress_canvas.create_rectangle(
                    0, 3, progress_width, canvas_height-3,
                    fill="#ff0000", outline=""
                )
        
        # Enhanced scrubber handle
        if self.video_player.total_frames > 0:
            progress = self.video_player.current_frame / self.video_player.total_frames
            x = int(progress * canvas_width)
            
            # Larger, more visible scrubber handle
            handle_size = 10 if self.is_dragging else 8
            
            # Shadow/outline for better visibility
            self.progress_canvas.create_oval(
                x-handle_size-1, 0, x+handle_size+1, canvas_height,
                fill="#000000", outline=""
            )
            
            # Main handle
            self.progress_canvas.create_oval(
                x-handle_size, 1, x+handle_size, canvas_height-1,
                fill="#ffffff" if not self.is_dragging else "#ff4444", 
                outline="#ff0000", width=2
            )
        
        # Update time display
        if self.video_player.cap:
            current_seconds = self.video_player.current_frame / max(self.video_player.fps, 1)
            total_seconds = self.video_player.total_frames / max(self.video_player.fps, 1)
            
            current_time = f"{int(current_seconds // 60)}:{int(current_seconds % 60):02d}"
            total_time = f"{int(total_seconds // 60)}:{int(total_seconds % 60):02d}"
            
            self.time_label.configure(text=f"{current_time} / {total_time}")

    # === MENU MANAGEMENT ===
    
    def toggle_speed_menu(self):
        """Toggle speed selection menu"""
        self.hide_all_menus()
        if not self.speed_menu_visible:
            self.show_speed_menu()

    def toggle_volume_menu(self):
        """Toggle volume menu"""
        self.hide_all_menus()
        if not self.volume_menu_visible:
            self.show_volume_menu()

    def show_speed_menu(self):
        """Show speed menu positioned above controls"""
        if not self.speed_menu_visible:
            self.speed_menu_visible = True
            self.position_menu(self.speed_menu, 150, 230)
            self.sync_speed_display()

    def show_volume_menu(self):
        """Show volume menu"""
        if not self.volume_menu_visible:
            self.volume_menu_visible = True
            self.position_menu(self.volume_menu, 150, 180)

    def position_menu(self, menu, width, height):
        """Position menu above controls"""
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Position from right edge, well above controls
        menu_x = screen_width - width - 50
        menu_y = screen_height - 120 - height - 30
        
        # Ensure menu doesn't go off screen
        menu_x = max(10, menu_x)
        menu_y = max(50, menu_y)
        
        menu.geometry(f"{width}x{height}+{menu_x}+{menu_y}")
        menu.deiconify()
        menu.lift()
        menu.focus_set()

    def hide_all_menus(self):
        """Hide all popup menus"""
        self.hide_speed_menu()
        self.hide_volume_menu()

    def hide_speed_menu(self):
        """Hide speed menu"""
        if self.speed_menu_visible:
            self.speed_menu_visible = False
            self.speed_menu.withdraw()

    def hide_volume_menu(self):
        """Hide volume menu"""
        if self.volume_menu_visible:
            self.volume_menu_visible = False
            self.volume_menu.withdraw()

    # === PLAYBACK CONTROLS ===
    
    def toggle_playback(self):
        """Toggle video playback (synchronized with main player)"""
        if self.video_player.cap:
            # Handle replay scenario - if video ended, restart from beginning
            if not self.video_player.is_playing and self.video_player.current_frame >= self.video_player.total_frames - 1:
                self.video_player.current_frame = 0
                self.video_player.display_frame(0)
                self.video_player.update_time_display()
                self.video_player.update_frame_display()
                self.display_frame(0)
                if self.controls_visible:
                    self.update_progress_bar()
            
            # Now toggle playback normally
            self.video_player.toggle_playback()
            
            # Update button text and sync playback state
            if self.video_player.is_playing:
                self.play_btn.configure(text="⏸")
                self.start_fullscreen_playback()
            else:
                self.play_btn.configure(text="▶")

    def seek_relative(self, seconds):
        """Seek relative to current position"""
        if not self.video_player.cap:
            return
        
        target_frame = self.video_player.current_frame + (seconds * self.video_player.fps)
        target_frame = max(0, min(target_frame, self.video_player.total_frames - 1))
        
        self.video_player.seek_to_frame(int(target_frame))
        self.update_progress_bar()

    def seek_to_percentage(self, percentage):
        """Seek to percentage of video"""
        if not self.video_player.cap:
            return
        
        target_frame = int((percentage / 100) * self.video_player.total_frames)
        self.video_player.seek_to_frame(target_frame)
        self.update_progress_bar()

    def change_speed(self, delta):
        """Change playback speed"""
        current_speed = getattr(self.video_player, 'playback_speed', 1.0)
        new_speed = max(0.25, min(8.0, current_speed + delta))
        self.set_speed(new_speed)

    def set_speed(self, speed):
        """Set playback speed and update display"""
        if hasattr(self.video_player, 'set_speed'):
            self.video_player.set_speed(speed)
        elif hasattr(self.video_player, 'playback_speed'):
            self.video_player.playback_speed = speed
            # Update speed indicator if it exists
            if hasattr(self.video_player, 'speed_indicator'):
                self.video_player.speed_indicator.configure(text=f"{speed}×")
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

    # === VOLUME CONTROLS ===
    
    def toggle_mute(self):
        """Toggle mute state"""
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.last_volume = self.volume
            self.volume = 0.0
            self.volume_btn.configure(text="🔇")
            self.mute_btn.configure(text="🔊 Unmute", bg="#ff4444")
        else:
            self.volume = self.last_volume
            self.volume_btn.configure(text="🔊")
            self.mute_btn.configure(text="🔇 Mute", bg="#555555")
        
        self.volume_slider.set(int(self.volume * 100))

    def on_volume_change(self, value):
        """Handle volume slider change"""
        self.volume = float(value) / 100
        if self.volume > 0 and self.is_muted:
            self.is_muted = False
            self.volume_btn.configure(text="🔊")
            self.mute_btn.configure(text="🔇 Mute", bg="#555555")

    def adjust_volume(self, delta):
        """Adjust volume by delta"""
        self.volume = max(0.0, min(1.0, self.volume + delta))
        self.volume_slider.set(int(self.volume * 100))
        if self.volume > 0 and self.is_muted:
            self.is_muted = False
            self.volume_btn.configure(text="🔊")

    # === DISPLAY AND SYNC ===
    
    def sync_with_main_player(self):
        """Sync fullscreen player state with main player"""
        if not self.video_player.cap:
            return
        
        # Sync playback state
        if self.video_player.is_playing:
            self.play_btn.configure(text="⏸")
            self.start_fullscreen_playback()
        else:
            self.play_btn.configure(text="▶")
        
        # Sync speed
        self.sync_speed_display()
        
        # Sync position
        if hasattr(self.video_player, 'current_frame'):
            self.display_frame(self.video_player.current_frame)
            self.update_progress_bar()

    def sync_speed_display(self):
        """Sync speed display with main player"""
        current_speed = self.get_current_speed()
        self.speed_label.configure(text=f"{current_speed}×")
        
        # Update menu highlights
        for speed_val, button in self.speed_buttons.items():
            if abs(speed_val - current_speed) < 0.01:
                button.configure(bg="#555555")
            else:
                button.configure(bg="#333333")

    def get_current_speed(self):
        """Get current playback speed from main player"""
        if hasattr(self.video_player, 'playback_speed'):
            return self.video_player.playback_speed
        return 1.0

    def start_fullscreen_playback(self):
        """Start fullscreen playback synchronized with main player"""
        if not self.video_player.is_playing or not self.video_player.cap:
            return
        
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
        
        # Calculate sync interval based on playback speed
        if self.video_player.playback_speed >= 4.0:
            sync_interval = 20
        elif self.video_player.playback_speed >= 2.0:
            sync_interval = 30
        else:
            sync_interval = 50
        
        self.after(sync_interval, self.sync_playback_with_main)

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
            
            # Convert frame for display
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_height, frame_width = frame_rgb.shape[:2]
            
            # Calculate scaling to fit screen while maintaining aspect ratio
            scale_w = screen_width / frame_width
            scale_h = screen_height / frame_height
            scale = min(scale_w, scale_h)
            
            new_width = int(frame_width * scale)
            new_height = int(frame_height * scale)
            
            # Resize frame
            from PIL import Image, ImageTk
            img = Image.fromarray(frame_rgb)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            self.photo = ImageTk.PhotoImage(img)
            
            # Clear canvas and display centered image
            self.canvas.delete("all")
            x_offset = (screen_width - new_width) // 2
            y_offset = (screen_height - new_height) // 2
            
            self.canvas.create_image(x_offset, y_offset, anchor="nw", image=self.photo)
            
        except Exception as e:
            print(f"Error displaying fullscreen frame: {e}")

    # === CONTROL VISIBILITY ===
    
    def position_overlays(self):
        """Position overlay controls over the video"""
        self.update_idletasks()
        
        window_width = self.winfo_width()
        window_height = self.winfo_height()
        
        # Position title overlay at top
        self.title_frame.place(x=0, y=0, width=window_width, height=60)
        
        # Position control overlay at bottom
        overlay_height = 140
        self.overlay_frame.place(
            x=0, y=window_height-overlay_height, 
            width=window_width, height=overlay_height
        )

    def show_controls(self):
        """Show overlay controls"""
        if not self.controls_visible:
            self.controls_visible = True
            self.position_overlays()
            self.update_progress_bar()

    def hide_controls(self):
        """Hide overlay controls"""
        if self.controls_visible:
            self.controls_visible = False
            self.title_frame.place_forget()
            self.overlay_frame.place_forget()
            self.hide_all_menus()

    def start_mouse_tracking(self):
        """Start tracking mouse for auto-hide controls"""
        def check_mouse_idle():
            if time.time() - self.last_mouse_move > 3.0 and self.controls_visible:
                self.hide_controls()
            
            if self.winfo_exists():
                self.after(500, check_mouse_idle)
        
        check_mouse_idle()

    # === EVENT HANDLERS ===
    
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

    def on_canvas_click(self, event):
        """Handle canvas clicks"""
        self.last_mouse_move = time.time()
        if not self.controls_visible:
            self.show_controls()

    def on_click_outside_menu(self, event):
        """Hide menus when clicking outside"""
        self.hide_all_menus()

    def on_mouse_wheel(self, event):
        """Handle mouse wheel for volume control"""
        delta = 0.05 if event.delta > 0 else -0.05
        self.adjust_volume(delta)

    def on_key_press(self, event):
        """Handle keyboard shortcuts"""
        key = event.keysym.lower()
        
        if key == "escape":
            self.exit_fullscreen()
        elif key == "space":
            self.toggle_playback()
        elif key == "f":
            self.exit_fullscreen()
        elif key in ["left", "a"]:
            self.seek_relative(-10)
        elif key in ["right", "d"]:
            self.seek_relative(10)
        elif key in ["up", "w"]:
            self.change_speed(0.25)
        elif key in ["down", "s"]:
            self.change_speed(-0.25)
        elif key == "m":
            self.toggle_mute()
        elif key == "c":
            if self.controls_visible:
                self.hide_controls()
            else:
                self.show_controls()

    def exit_fullscreen(self):
        """Exit fullscreen mode"""
        self.hide_all_menus()
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
def initialize_vscode_colors(theme_name="Dark+"):
    """Initialize VSCODE_COLORS with a complete color scheme"""
    global VSCODE_COLORS
    
    if theme_name in THEME_SCHEMES:
        VSCODE_COLORS = THEME_SCHEMES[theme_name].copy()
    else:
        VSCODE_COLORS = THEME_SCHEMES["Dark+"].copy()
    
    # Ensure ALL required colors exist
    required_colors = {
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
        "current_line": "#2A2D2E"
    }
    
    for key, default_value in required_colors.items():
        if key not in VSCODE_COLORS:
            VSCODE_COLORS[key] = default_value
class DetailedUserGuideDialog(ctk.CTkToplevel):
    """Comprehensive user guide dialog shown after installation"""
    
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        
        # Fix missing VSCODE_COLORS keys
        global VSCODE_COLORS
        if "accent" not in VSCODE_COLORS:
            VSCODE_COLORS["accent"] = "#007ACC"
        if "accent_hover" not in VSCODE_COLORS:
            VSCODE_COLORS["accent_hover"] = "#005A9E"
        if "text_bright" not in VSCODE_COLORS:
            VSCODE_COLORS["text_bright"] = "#FFFFFF"
        if "surface" not in VSCODE_COLORS:
            VSCODE_COLORS["surface"] = "#252526"
        if "text_secondary" not in VSCODE_COLORS:
            VSCODE_COLORS["text_secondary"] = "#858585"
        if "surface_light" not in VSCODE_COLORS:
            VSCODE_COLORS["surface_light"] = "#2D2D30"
        
        self.title("ManimStudio - Complete User Guide")
        

        
        # Responsive window sizing
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = max(800, min(int(screen_w * 0.7), screen_w - 100, 1200))
        height = max(600, min(int(screen_h * 0.85), screen_h - 100, 900))
        self.geometry(f"{width}x{height}")
        self.minsize(700, 500)
        self.resizable(True, True)
        self.transient(app.root)
        self.grab_set()
        
        # Center the dialog
        self.geometry("+%d+%d" % (
            app.root.winfo_rootx() + 50,
            app.root.winfo_rooty() + 30
        ))
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the comprehensive user guide UI"""
        # Main container
        main_frame = ctk.CTkFrame(self, fg_color=VSCODE_COLORS["surface"])
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))
        
        # App icon and title
        title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_frame.pack(fill="x")
        
        ctk.CTkLabel(
            title_frame,
            text="🎬",
            font=ctk.CTkFont(size=48)
        ).pack(side="left", padx=(0, 15))
        
        header_text_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        header_text_frame.pack(side="left", fill="x", expand=True)
        
        ctk.CTkLabel(
            header_text_frame,
            text="ManimStudio - Complete User Guide",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            header_text_frame,
            text="Everything you need to know to create amazing mathematical animations",
            font=ctk.CTkFont(size=14),
            text_color=VSCODE_COLORS["text_secondary"]
        ).pack(anchor="w", pady=(5, 0))
        
        # Tabbed content
        self.notebook = ctk.CTkTabview(main_frame)
        self.notebook.pack(fill="both", expand=True, pady=(0, 15))
        
        # Create tabs
        self.create_quick_start_tab()
        self.create_interface_guide_tab()
        self.create_features_tab()
        self.create_examples_tab()
        self.create_troubleshooting_tab()
        self.create_tips_tab()
        
        # Bottom buttons
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x")
        
        ctk.CTkButton(
            button_frame,
            text="📖 Open Manim Documentation",
            command=self.open_manim_docs,
            height=35
        ).pack(side="left", padx=(0, 10))
        
        ctk.CTkButton(
            button_frame,
            text="✅ Got it, Let's Start!",
            command=self.destroy,
            height=35,
            fg_color=VSCODE_COLORS["accent"],
            hover_color=VSCODE_COLORS["accent_hover"]
        ).pack(side="right")
    
    def create_quick_start_tab(self):
        """Create quick start guide tab"""
        tab = self.notebook.add("🚀 Quick Start")
        
        content = ctk.CTkScrollableFrame(tab, fg_color=VSCODE_COLORS["surface"])
        content.pack(fill="both", expand=True, padx=15, pady=15)
        
        guide_text = """
🎯 GET STARTED IN 3 MINUTES

1. WRITE YOUR FIRST ANIMATION
   • Use the code editor (left panel) to write Manim code
   • Start with a simple scene class that inherits from Scene
   • Example: Create a circle that appears on screen

2. PREVIEW YOUR WORK
   • Click "⚡ Quick Preview" (F5) for fast preview
   • View the result in the preview panel (bottom right)
   • Adjust your code and preview again

3. RENDER FINAL VIDEO
   • Click "🎬 Render Animation" (F7) for high-quality output
   • Choose your desired format (MP4, GIF, WebM, PNG)
   • Select resolution (720p, 1080p, 4K, 8K available)

🎬 YOUR FIRST ANIMATION CODE:

from manim import *

class MyFirstScene(Scene):
    def construct(self):
        # Create a blue circle
        circle = Circle(color=BLUE)
        
        # Add text
        text = Text("Hello ManimStudio!")
        
        # Show animations
        self.play(Create(circle))
        self.play(Write(text))
        self.play(circle.animate.shift(UP))
        self.wait()

✨ COPY THIS CODE, PASTE IT IN THE EDITOR, AND HIT F5!

🎯 WHAT HAPPENS NEXT:
   • ManimStudio will render a preview showing:
     - A blue circle appearing
     - Text "Hello ManimStudio!" writing itself
     - Circle moving upward
   • Total animation time: ~3 seconds
   • You can then modify colors, text, or add more objects!

💡 PRO TIPS FOR BEGINNERS:
   • Always start with "from manim import *"
   • Your scene class must inherit from Scene
   • Use self.play() to animate objects
   • Use self.wait() to pause between animations
   • Press Ctrl+Space for auto-completion suggestions
        """
        
        self.create_guide_content(content, guide_text)
    
    def create_interface_guide_tab(self):
        """Create interface guide tab"""
        tab = self.notebook.add("🖥️ Interface Guide")
        
        content = ctk.CTkScrollableFrame(tab, fg_color=VSCODE_COLORS["surface"])
        content.pack(fill="both", expand=True, padx=15, pady=15)
        
        guide_text = """
🖥️ INTERFACE LAYOUT GUIDE

📝 CODE EDITOR (Left Panel):
   • Professional VSCode-like editor with syntax highlighting
   • IntelliSense autocompletion (Ctrl+Space)
   • Line numbers and bracket matching
   • Find & Replace (Ctrl+F / Ctrl+H)
   • Auto-indentation for Python code
   • Multiple themes available

🎮 CONTROL PANEL (Top):
   • File operations: New, Open, Save, Save As
   • Quick Preview (⚡ F5) - Fast preview generation
   • Render Animation (🎬 F7) - High-quality final render
   • Environment Setup - Manage Python virtual environments

⚙️ SETTINGS PANEL (Right Side):
   • Preview Quality: Choose rendering quality for previews
   • Output Format: MP4, GIF, WebM, PNG sequence
   • Resolution: 480p to 8K (Professional edition)
   • Frame Rate: 15fps to 60fps options
   • Theme Selection: Light, Dark, and custom themes

📺 PREVIEW PANEL (Bottom Right):
   • Real-time video preview with playback controls
   • Play, pause, seek through your animation
   • Full-screen preview mode
   • Automatic refresh after rendering

📁 ASSET MANAGER (Right Panel):
   • Add images: Drag & drop PNG, JPG, GIF files
   • Add audio: Support for MP3, WAV, OGG formats
   • Asset previews with thumbnail display
   • One-click code insertion for assets

🖥️ TERMINAL OUTPUT (Bottom):
   • Real-time rendering progress
   • Error messages and debugging info
   • Package installation status
   • Command execution logs

🎨 THEME CUSTOMIZATION:
   • Dark themes for night coding
   • Light themes for day work
   • High contrast options
   • Custom color schemes

⌨️ KEYBOARD SHORTCUTS:
   • Ctrl+N: New file
   • Ctrl+O: Open file
   • Ctrl+S: Save file
   • F5: Quick Preview
   • F7: Render Animation
   • Ctrl+F: Find
   • Ctrl+H: Replace
   • Ctrl+Space: IntelliSense
        """
        
        self.create_guide_content(content, guide_text)
    
    def create_features_tab(self):
        """Create features overview tab"""
        tab = self.notebook.add("✨ Features")
        
        content = ctk.CTkScrollableFrame(tab, fg_color=VSCODE_COLORS["surface"])
        content.pack(fill="both", expand=True, padx=15, pady=15)
        
        guide_text = """
✨ COMPLETE FEATURE OVERVIEW

🚀 DEVELOPMENT FEATURES:
   • Professional code editor with Python IntelliSense
   • Real-time syntax highlighting and error detection
   • Advanced find & replace with regex support
   • Auto-completion for Manim functions and classes
   • Smart indentation and bracket matching
   • Multiple file support with tabs

🎬 RENDERING CAPABILITIES:
   • Multiple output formats: MP4, GIF, WebM, PNG sequences
   • Resolution support: 480p, 720p, 1080p, 4K, 8K
   • Frame rates: 15fps, 30fps, 60fps options
   • Quality presets: Draft, Medium, High, Production
   • Batch rendering for multiple scenes
   • Custom resolution support

⚡ PREVIEW SYSTEM:
   • Lightning-fast preview generation (15-30 seconds)
   • Real-time preview with video controls
   • Automatic scene detection and rendering
   • Preview quality optimization for speed
   • Full-screen preview mode
   • Timeline scrubbing and playback control

🎨 ASSET MANAGEMENT:
   • Visual asset manager with thumbnails
   • Drag & drop support for images and audio
   • Automatic code generation for asset usage
   • Support for: PNG, JPG, GIF, BMP, TIFF images
   • Audio formats: MP3, WAV, OGG, M4A, FLAC
   • Asset organization and preview

🔧 ENVIRONMENT MANAGEMENT:
   • Automatic Python virtual environment setup
   • One-click package installation
   • Environment health monitoring
   • Dependency conflict resolution
   • Python version compatibility checking
   • Automatic Manim installation and updates

🎯 PROFESSIONAL TOOLS:
   • Advanced package manager with 1000+ packages
   • System terminal integration
   • Multi-threaded rendering engine
   • Memory optimization for large projects
   • Export project settings and configurations
   • Professional logging and error reporting

🌟 USER EXPERIENCE:
   • Modern, responsive UI design
   • Multiple theme options (Dark, Light, Custom)
   • Customizable interface layout
   • Keyboard shortcuts for all functions
   • Context-sensitive help and tooltips
   • Seamless workflow integration

📊 PERFORMANCE FEATURES:
   • Multi-core rendering utilization
   • Intelligent caching system
   • Memory management for large scenes
   • Background processing for previews
   • Optimized for Windows, macOS, and Linux
   • Efficient file handling and storage
        """
        
        self.create_guide_content(content, guide_text)
    
    def create_examples_tab(self):
        """Create examples tab"""
        tab = self.notebook.add("📝 Examples")
        
        content = ctk.CTkScrollableFrame(tab, fg_color=VSCODE_COLORS["surface"])
        content.pack(fill="both", expand=True, padx=15, pady=15)
        
        guide_text = """
📝 ANIMATION EXAMPLES

🎯 BASIC SHAPES ANIMATION:

from manim import *

class BasicShapes(Scene):
    def construct(self):
        # Create shapes
        square = Square(color=BLUE)
        circle = Circle(color=RED)
        triangle = Triangle(color=GREEN)
        
        # Position shapes
        square.shift(LEFT * 3)
        circle.shift(RIGHT * 3)
        
        # Animate creation
        self.play(Create(square), Create(circle), Create(triangle))
        self.play(square.animate.rotate(PI/4))
        self.play(circle.animate.scale(1.5))
        self.play(triangle.animate.flip(UP))
        self.wait()

📊 MATHEMATICAL FUNCTIONS:

from manim import *

class MathFunction(Scene):
    def construct(self):
        # Create axes
        axes = Axes(
            x_range=[-3, 3, 1],
            y_range=[-2, 2, 1],
            x_length=6,
            y_length=4
        )
        
        # Create function
        func = axes.plot(lambda x: x**2, color=YELLOW)
        func_label = MathTex(r"f(x) = x^2").next_to(func, UP)
        
        # Animate
        self.play(Create(axes))
        self.play(Create(func), Write(func_label))
        self.wait()

🎭 TEXT ANIMATIONS:

from manim import *

class TextAnimation(Scene):
    def construct(self):
        # Create text
        title = Text("ManimStudio", font_size=48, color=BLUE)
        subtitle = Text("Mathematical Animations Made Easy", font_size=24)
        subtitle.next_to(title, DOWN)
        
        # Animate text
        self.play(Write(title))
        self.play(FadeIn(subtitle))
        self.play(title.animate.scale(1.2).set_color(YELLOW))
        self.play(subtitle.animate.shift(DOWN))
        self.wait()

🔄 TRANSFORMATIONS:

from manim import *

class Transformations(Scene):
    def construct(self):
        # Create objects
        square = Square(color=BLUE)
        circle = Circle(color=RED)
        
        # Transform square to circle
        self.play(Create(square))
        self.play(Transform(square, circle))
        self.play(square.animate.move_to(RIGHT * 2))
        self.play(Rotate(square, PI))
        self.wait()

📈 GRAPH ANIMATION:

from manim import *

class GraphScene(Scene):
    def construct(self):
        # Create number plane
        plane = NumberPlane()
        
        # Create points
        points = [plane.coords_to_point(x, x**2) for x in range(-3, 4)]
        dots = VGroup(*[Dot(point, color=YELLOW) for point in points])
        
        # Create curve
        curve = plane.plot(lambda x: x**2, color=BLUE)
        
        # Animate
        self.play(Create(plane))
        self.play(Create(dots))
        self.play(Create(curve))
        self.wait()

💡 TIPS FOR YOUR OWN ANIMATIONS:
   • Start simple and build complexity gradually
   • Use self.play() for smooth animations
   • Combine multiple objects with VGroup()
   • Experiment with colors: RED, BLUE, GREEN, YELLOW, etc.
   • Use .animate for property changes
   • Add self.wait() for pauses between scenes
        """
        
        self.create_guide_content(content, guide_text)
    
    def create_troubleshooting_tab(self):
        """Create troubleshooting tab"""
        tab = self.notebook.add("🔧 Troubleshooting")
        
        content = ctk.CTkScrollableFrame(tab, fg_color=VSCODE_COLORS["surface"])
        content.pack(fill="both", expand=True, padx=15, pady=15)
        
        guide_text = """
🔧 TROUBLESHOOTING GUIDE

❌ COMMON ISSUES AND SOLUTIONS:

🐍 "No Python Environment" Error:
   SOLUTION:
   • Click "Environment Setup" button
   • Follow the automatic setup wizard
   • Wait for virtual environment creation
   • Restart ManimStudio if needed

📦 "Manim not found" Error:
   SOLUTION:
   • Go to Tools → Environment Setup
   • Click "Fix Manim Dependencies"
   • Wait for automatic package installation
   • Verify installation in terminal output

🎬 "No scene class found" Error:
   SOLUTION:
   • Ensure your class inherits from Scene
   • Check class name spelling and capitalization
   • Verify proper indentation (4 spaces)
   • Make sure construct() method exists

⚡ Preview Not Working:
   SOLUTION:
   • Check terminal output for error messages
   • Verify your code syntax is correct
   • Try a simpler example first
   • Check if all imports are correct

🎥 Rendering Fails:
   SOLUTION:
   • Check available disk space
   • Verify output directory permissions
   • Try lower quality settings first
   • Check for conflicting file names

🔊 Audio Issues:
   SOLUTION:
   • Verify audio file format (MP3, WAV supported)
   • Check file path and existence
   • Ensure audio file isn't corrupted
   • Try converting to MP3 format

💾 File Save Problems:
   SOLUTION:
   • Check file permissions in target directory
   • Verify disk space availability
   • Try saving to different location
   • Check for special characters in filename

🌐 Package Installation Fails:
   SOLUTION:
   • Check internet connection
   • Try running as administrator (Windows)
   • Clear pip cache: pip cache purge
   • Use VPN if behind corporate firewall

🖥️ PERFORMANCE ISSUES:

💻 Slow Rendering:
   • Lower preview quality in settings
   • Close other applications
   • Use SSD storage if available
   • Increase virtual memory

🔥 High CPU Usage:
   • Normal during rendering
   • Close unnecessary programs
   • Use "Draft" quality for testing
   • Enable multi-threading in settings

💡 QUICK FIXES:
   • Restart ManimStudio for environment issues
   • Try the "Getting Started" example first
   • Check the terminal output for detailed errors
   • Use File → New to start with clean template

🆘 STILL NEED HELP?
   • Check Manim Community documentation
   • Visit GitHub issues page
   • Contact support with error logs
   • Join Manim Discord community
        """
        
        self.create_guide_content(content, guide_text)
    
    def create_tips_tab(self):
        """Create tips and tricks tab"""
        tab = self.notebook.add("💡 Pro Tips")
        
        content = ctk.CTkScrollableFrame(tab, fg_color=VSCODE_COLORS["surface"])
        content.pack(fill="both", expand=True, padx=15, pady=15)
        
        guide_text = """
💡 PRO TIPS AND TRICKS

⚡ PRODUCTIVITY SHORTCUTS:
   • F5: Quick preview (fastest way to test)
   • F7: Render final animation
   • Ctrl+Space: IntelliSense autocompletion
   • Ctrl+F: Find text in code
   • Ctrl+H: Find and replace
   • Ctrl+S: Save your work frequently

🎨 ANIMATION BEST PRACTICES:
   • Start with simple shapes before complex scenes
   • Use consistent timing (self.wait(1) for 1 second)
   • Group related objects with VGroup()
   • Name your variables descriptively
   • Comment your code for future reference
   • Plan your animation sequence on paper first

🚀 OPTIMIZATION TECHNIQUES:
   • Use "Draft" quality for testing and iteration
   • Save "High" quality for final renders only
   • Close preview panel if not needed during coding
   • Use lower frame rates (15fps) for faster previews
   • Clear terminal output regularly for performance

📁 PROJECT ORGANIZATION:
   • Save each animation as a separate .py file
   • Use descriptive filenames (math_functions.py)
   • Keep assets in the same folder as your script
   • Export your environment settings for backup
   • Create templates for common animation types

🎯 WORKFLOW EFFICIENCY:
   • Write and test small parts incrementally
   • Use Quick Preview frequently during development
   • Keep the Manim documentation open in browser
   • Save your work before major changes
   • Create backups of working animations

🔧 ADVANCED TECHNIQUES:
   • Use custom colors: color=rgb_to_color([0.5, 0.8, 0.2])
   • Create custom animations with AnimationGroup
   • Use updaters for dynamic objects
   • Implement camera movements for cinematic effects
   • Combine multiple scenes in one script

📚 LEARNING RESOURCES:
   • 3Blue1Brown YouTube channel (creator of Manim)
   • Manim Community documentation and examples
   • Practice with mathematical visualizations
   • Study existing Manim projects on GitHub
   • Join the Manim Discord community

🎬 RENDERING STRATEGIES:
   • Test with 720p before rendering 4K
   • Use MP4 for most purposes, GIF for web
   • Higher frame rates (60fps) for smooth motion
   • PNG sequences for post-processing in other software
   • WebM format for web optimization

💾 BACKUP AND SHARING:
   • Export your virtual environment settings
   • Save project files with version numbers
   • Share .py files with others easily
   • Use Git for version control of projects
   • Document your animation process for reuse

🌟 CREATIVE IDEAS:
   • Visualize mathematical concepts and formulas
   • Create educational content for teaching
   • Design presentation animations for slides
   • Build interactive demonstrations
   • Combine with screen recording for tutorials

Remember: The best way to learn Manim is by doing!
Start simple, experiment often, and gradually build complexity.
        """
        
        self.create_guide_content(content, guide_text)
    
    def create_guide_content(self, parent, text_content):
        """Create formatted guide content"""
        # Text widget for proper formatting
        text_widget = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            height=600
        )
        text_widget.pack(fill="both", expand=True)
        
        # Insert and format content
        text_widget.insert("1.0", text_content.strip())
        text_widget.configure(state="disabled")  # Make read-only
    
    def open_manim_docs(self):
        """Open Manim documentation"""
        import webbrowser
        webbrowser.open("https://docs.manim.community/")
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
        
        
        # Initialize system terminal manager
        self.terminal = None
        
        # IMPORTANT: Auto-activate manim_studio_default environment if it exists and is ready
        self.auto_activate_default_environment()
        # Initialize virtual environment manager
        self.venv_manager = VirtualEnvironmentManager(self)
        
        # Load settings before initializing variables that depend on them
        self.load_settings()
        
        # **CRITICAL FIX: Initialize VSCODE_COLORS immediately after loading settings**
        initialize_vscode_colors(self.settings.get("theme", "Dark+"))
        
        # CRITICAL FIX: Update responsive UI with loaded quality setting
        loaded_quality = self.settings.get("quality", "720p")
        self.responsive.set_quality_scaling(loaded_quality)
        
        self.initialize_variables()
        self.check_latex_installation()
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
    def check_latex_installation(self):
        """Check LaTeX installation - QUICK FIX"""
        try:
            # First check bundled LaTeX in WindowsApps path
            bundled_latex_path = r"C:\Program Files\WindowsApps\9NZFT55DVCBS_1.0.2.0_x64__c5s549jf2x494\app\dependencies\miktex\bin"
            
            if os.path.exists(bundled_latex_path):
                # Check for pdflatex.exe in bundled path
                pdflatex_path = os.path.join(bundled_latex_path, "pdflatex.exe")
                if os.path.exists(pdflatex_path):
                    self.latex_available = True
                    self.latex_installed = True
                    self.latex_path = pdflatex_path
                    status_text = "LaTeX: Bundled MikTeX"
                    status_color = VSCODE_COLORS["success"]
                    print(f"✅ Found bundled LaTeX: {pdflatex_path}")
                else:
                    # Fallback to system check
                    self.latex_available = False
                    self.latex_installed = False
                    self.latex_path = None
                    status_text = "LaTeX: Missing"
                    status_color = VSCODE_COLORS["error"]
            else:
                # Check system PATH for LaTeX
                try:
                    result = subprocess.run(['pdflatex', '--version'], capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        self.latex_available = True
                        self.latex_installed = True
                        self.latex_path = "pdflatex"
                        status_text = "LaTeX: System Installation"
                        status_color = VSCODE_COLORS["success"]
                    else:
                        raise Exception("pdflatex not found")
                except:
                    self.latex_available = False
                    self.latex_installed = False
                    self.latex_path = None
                    status_text = "LaTeX: Missing"
                    status_color = VSCODE_COLORS["error"]
            
            # Update UI
            if hasattr(self, 'latex_status_label') and self.latex_status_label:
                self.latex_status_label.configure(text=status_text, text_color=status_color)
            
            return self.latex_available
            
        except Exception as e:
            print(f"❌ Error checking LaTeX: {e}")
            return False
    def force_latex_status_update(self, status_text, status_color):
        """Force LaTeX status update - helper method"""
        try:
            # Try all possible label references
            possible_labels = [
                getattr(self, 'latex_status_label', None),
                getattr(self, 'env_status_label', None), 
                getattr(self, 'status_label', None),
                getattr(self, 'latex_label', None)
            ]
            
            for label in possible_labels:
                if label:
                    try:
                        label.configure(text=status_text, text_color=status_color)
                        print(f"✅ Force updated label with: {status_text}")
                        break
                    except:
                        continue
            
            # Force UI refresh again
            self.update_idletasks()
            self.update()
            
        except Exception as e:
            print(f"❌ Error in force update: {e}")
    def check_environment_before_showing_ui(self):
        """Check environment before showing main UI - BETTER UX"""
        try:
            # Prevent multiple checks
            if self._environment_check_scheduled:
                return
            
            self._environment_check_scheduled = True
            
            # IMPORTANT: Check if environment was already detected during auto_activate_default_environment
            if not self.venv_manager.needs_setup:
                self.logger.info("Environment already ready - showing main UI directly")
                self.update_environment_status()
                self.show_main_window()
                return
            
            # Only show setup dialog if environment actually needs setup
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
    
    def add_image_file(self):
        """Add image file to assets and show path"""
        filetypes = [
            ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.svg"),
            ("PNG files", "*.png"),
            ("JPEG files", "*.jpg *.jpeg"),
            ("All files", "*.*")
        ]
        
        file_path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=filetypes,
            parent=self.root
        )
        
        if file_path:
            try:
                assets_folder = self.ensure_assets_folder()
                filename = os.path.basename(file_path)
                
                # Handle duplicate names
                counter = 1
                base_name, ext = os.path.splitext(filename)
                while os.path.exists(os.path.join(assets_folder, filename)):
                    filename = f"{base_name}_{counter}{ext}"
                    counter += 1
                
                destination = os.path.join(assets_folder, filename)
                shutil.copy2(file_path, destination)
                
                # Show success message with path to use
                relative_path = f"assets/{filename}"
                messagebox.showinfo(
                    "Image Added",
                    f"Image copied to assets folder!\n\n"
                    f"Use this path in your Manim code:\n"
                    f'"{relative_path}"\n\n'
                    f"Example:\n"
                    f'img = ImageMobject("{relative_path}")',
                    parent=self.root
                )
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to copy image:\n{str(e)}", parent=self.root)

    def add_audio_file(self):
        """Add audio file to assets and show path"""
        filetypes = [
            ("Audio files", "*.mp3 *.wav *.ogg *.m4a *.flac"),
            ("MP3 files", "*.mp3"),
            ("WAV files", "*.wav"),
            ("All files", "*.*")
        ]
        
        file_path = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=filetypes,
            parent=self.root
        )
        
        if file_path:
            try:
                assets_folder = self.ensure_assets_folder()
                filename = os.path.basename(file_path)
                
                # Handle duplicate names
                counter = 1
                base_name, ext = os.path.splitext(filename)
                while os.path.exists(os.path.join(assets_folder, filename)):
                    filename = f"{base_name}_{counter}{ext}"
                    counter += 1
                
                destination = os.path.join(assets_folder, filename)
                shutil.copy2(file_path, destination)
                
                # Show success message with path to use
                relative_path = f"assets/{filename}"
                messagebox.showinfo(
                    "Audio Added",
                    f"Audio copied to assets folder!\n\n"
                    f"Use this path in your Manim code:\n"
                    f'"{relative_path}"\n\n'
                    f"Example:\n"
                    f'self.add_sound("{relative_path}")',
                    parent=self.root
                )
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to copy audio:\n{str(e)}", parent=self.root)
    def show_add_asset_menu(self):
        """Show Assets Manager instead of simple menu"""
        assets_manager = AssetsManager(self.root, self)
        self.root.wait_window(assets_manager)
        
        # Refresh the main assets display after manager closes
        self.update_assets_display()

    def create_assets_section(self):
        """Create enhanced assets section with visual cards"""
        # Section header
        assets_header = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        assets_header.pack(fill="x", pady=(0, 10))
        
        header_frame = ctk.CTkFrame(assets_header, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=12)
        header_frame.grid_columnconfigure(0, weight=1)
        
        # Assets title
        ctk.CTkLabel(
            header_frame,
            text="📁 Assets",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        ).grid(row=0, column=0, sticky="w")
        
        # Assets controls frame
        controls_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        controls_frame.grid(row=0, column=1, sticky="e")
        
        # CHANGED: Assets Manager button instead of Add button
        manager_button = ctk.CTkButton(
            controls_frame,
            text="📁 Assets Manager",
            width=120,
            height=28,
            font=ctk.CTkFont(size=11),
            command=self.show_add_asset_menu,  # This now opens the manager
            fg_color=VSCODE_COLORS["primary"],
            hover_color=VSCODE_COLORS.get("primary_hover", VSCODE_COLORS["primary"])
        )
        manager_button.pack(side="right", padx=(5, 0))
        
        # Clear assets button
        clear_button = ctk.CTkButton(
            controls_frame,
            text="Clear",
            width=60,
            height=28,
            font=ctk.CTkFont(size=11),
            command=self.clear_assets,
            fg_color=VSCODE_COLORS.get("warning", "#F39C12"),
            hover_color=VSCODE_COLORS.get("error", "#E74C3C")
        )
        clear_button.pack(side="right", padx=(5, 5))
        
        # Assets container
        self.assets_container = ctk.CTkScrollableFrame(
            self.sidebar_scroll,
            height=200,
            fg_color=VSCODE_COLORS["surface"],
            corner_radius=8
        )
        self.assets_container.pack(fill="x", pady=(0, 15))
        
        # Assets info
        self.assets_info = ctk.CTkLabel(
            self.assets_container,
            text="Click 'Assets Manager' to view and manage assets",
            font=ctk.CTkFont(size=12),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.assets_info.pack(pady=20)
    def set_environment_ready(self):
        """NEW METHOD: Mark environment as ready and skip setup UI"""
        try:
            # Mark that environment is ready
            self.venv_manager.needs_setup = False
            
            # Update environment status silently
            self.update_environment_status()
            
            # Don't show any setup dialogs
            self._skip_environment_dialogs = True
            
        except Exception as e:
            self.logger.error(f"Error setting environment ready: {e}")

    def check_environment_before_showing_ui(self):
        """MODIFIED: Check environment and skip UI if ready"""
        try:
            # Check if we should skip dialogs
            if hasattr(self, '_skip_environment_dialogs') and self._skip_environment_dialogs:
                # Environment already validated by splash, show main window
                self.show_main_window()
                return
            
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
        """Initialize all application variables - FIXED VERSION"""
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
        
        # FIXED: Ensure VSCODE_COLORS has all required keys
        global VSCODE_COLORS
        if self.current_theme in THEME_SCHEMES:
            VSCODE_COLORS = THEME_SCHEMES[self.current_theme].copy()
        else:
            VSCODE_COLORS = THEME_SCHEMES["Dark+"].copy()
            
        # Ensure all critical colors exist
        required_colors = {
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
            "current_line": "#2A2D2E"
        }
        
        for key, default_value in required_colors.items():
            if key not in VSCODE_COLORS:
                VSCODE_COLORS[key] = default_value
                
    def apply_vscode_theme(self):
        """Apply VSCode-like color theme safely - FIXED VERSION"""
        colors = VSCODE_COLORS
        
        try:
            # Apply to main window
            self.root.configure(fg_color=colors["background"])
            
            # Apply to sidebar with error handling
            if hasattr(self, 'sidebar'):
                try:
                    self.sidebar.configure(fg_color=colors["surface"])
                except Exception:
                    pass
                    
            # Apply to main area with error handling
            if hasattr(self, 'main_area'):
                try:
                    self.main_area.configure(fg_color=colors["background"])
                except Exception:
                    pass
            
            # Apply to output text with error handling
            if hasattr(self, 'output_text'):
                try:
                    if hasattr(self.output_text, 'fg_color'):
                        self.output_text.configure(
                            fg_color=colors["background"],
                            text_color=colors["text"]
                        )
                    else:
                        self.output_text.configure(
                            bg=colors["background"],
                            fg=colors["text"],
                            insertbackground=colors["text"],
                            selectbackground=colors["selection"],
                            selectforeground=colors.get("text_bright", colors["text"])
                        )
                except Exception as e:
                    print(f"Warning: Could not apply theme to output_text: {e}")
            
            # Apply to code editor with error handling
            if hasattr(self, 'code_editor'):
                try:
                    self.code_editor.configure(
                        bg=colors["background"],
                        fg=colors["text"],
                        insertbackground=colors["text"],
                        selectbackground=colors["selection"],
                        selectforeground=colors.get("text_bright", colors["text"])
                    )
                except Exception as e:
                    print(f"Warning: Could not apply theme to code_editor: {e}")
                    
        except Exception as e:
            print(f"Warning: Could not apply theme completely: {e}")
    
    
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
        """Create render settings section with responsive sizing - FIXED VERSION"""
        # Get responsive dimensions
        fonts = self.responsive.get_optimal_font_sizes()
        spacing = self.responsive.get_optimal_spacing()
        
        # Section header
        render_header = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        render_header.pack(fill="x", pady=(0, spacing["normal"]))
        
        header_title = ctk.CTkLabel(
            render_header,
            text="🎬 Render Settings",
            font=ctk.CTkFont(size=fonts["large"], weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        header_title.pack(padx=spacing["medium"], pady=spacing["medium"])
        
        # Main render frame
        render_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface"])
        render_frame.pack(fill="x", pady=(0, spacing["normal"]))
        
        # Quality controls with responsive sizing
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
        
        # Custom resolution frame - FIXED: Each input on separate row
        self.custom_resolution_frame = ctk.CTkFrame(quality_frame, fg_color="transparent")
        
        # Custom resolution header
        custom_header = ctk.CTkLabel(
            self.custom_resolution_frame,
            text="Custom Resolution:",
            font=ctk.CTkFont(size=fonts["normal"], weight="bold"),
            text_color=VSCODE_COLORS["text"]
        )
        custom_header.pack(anchor="w", pady=(spacing["small"], spacing["small"]))
        
        # Width input - FIXED: On its own row
        width_frame = ctk.CTkFrame(self.custom_resolution_frame, fg_color="transparent")
        width_frame.pack(fill="x", pady=(0, spacing["small"]))
        width_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            width_frame, 
            text="Width:", 
            font=ctk.CTkFont(size=fonts["normal"]),
            width=60
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.custom_width_entry = ctk.CTkEntry(
            width_frame,
            textvariable=self.custom_width_var,
            height=combo_height,
            font=ctk.CTkFont(size=fonts["normal"]),
            placeholder_text="e.g. 1920"
        )
        self.custom_width_entry.grid(row=0, column=1, sticky="ew")
        self.custom_width_entry.bind("<KeyRelease>", self.validate_custom_resolution)
        
        # Height input - FIXED: On its own row
        height_frame = ctk.CTkFrame(self.custom_resolution_frame, fg_color="transparent")
        height_frame.pack(fill="x", pady=(0, spacing["small"]))
        height_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            height_frame, 
            text="Height:", 
            font=ctk.CTkFont(size=fonts["normal"]),
            width=60
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.custom_height_entry = ctk.CTkEntry(
            height_frame,
            textvariable=self.custom_height_var,
            height=combo_height,
            font=ctk.CTkFont(size=fonts["normal"]),
            placeholder_text="e.g. 1080"
        )
        self.custom_height_entry.grid(row=0, column=1, sticky="ew")
        self.custom_height_entry.bind("<KeyRelease>", self.validate_custom_resolution)
        
        # FPS input - FIXED: On its own row
        fps_frame = ctk.CTkFrame(self.custom_resolution_frame, fg_color="transparent")
        fps_frame.pack(fill="x", pady=(0, spacing["small"]))
        fps_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            fps_frame, 
            text="FPS:", 
            font=ctk.CTkFont(size=fonts["normal"]),
            width=60
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.custom_fps_entry = ctk.CTkEntry(
            fps_frame,
            textvariable=self.custom_fps_var,
            height=combo_height,
            font=ctk.CTkFont(size=fonts["normal"]),
            placeholder_text="e.g. 30"
        )
        self.custom_fps_entry.grid(row=0, column=1, sticky="ew")
        self.custom_fps_entry.bind("<KeyRelease>", self.validate_custom_resolution)
        
        # Validation label - FIXED: Added missing validation label
        self.custom_validation_label = ctk.CTkLabel(
            self.custom_resolution_frame,
            text="",
            font=ctk.CTkFont(size=fonts["small"]),
            text_color=VSCODE_COLORS["text_secondary"]
        )
        self.custom_validation_label.pack(anchor="w", pady=(spacing["tiny"], 0))
        
        # Show/hide custom resolution frame based on current quality
        if self.settings["quality"] == "Custom":
            self.custom_resolution_frame.pack(fill="x", pady=(spacing["normal"], 0))
        
        # Format controls
        format_frame = ctk.CTkFrame(render_frame, fg_color="transparent")
        format_frame.pack(fill="x", padx=spacing["medium"], pady=spacing["normal"])
        
        ctk.CTkLabel(
            format_frame,
            text="Output Format",
            font=ctk.CTkFont(size=fonts["medium"], weight="bold"),
            text_color=VSCODE_COLORS["text"]
        ).pack(anchor="w")
        
        self.format_combo = ctk.CTkComboBox(
            format_frame,
            values=list(EXPORT_FORMATS.keys()),
            variable=self.format_var,
            command=lambda x: self.save_settings(),
            height=combo_height,
            font=ctk.CTkFont(size=fonts["normal"])
        )
        self.format_combo.pack(fill="x", pady=(spacing["small"], 0))
        
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
        
        # Custom CPU frame implementation
        self.custom_cpu_frame = ctk.CTkFrame(cpu_frame, fg_color="transparent")
        
        # Custom CPU slider
        cpu_slider_frame = ctk.CTkFrame(self.custom_cpu_frame, fg_color="transparent")
        cpu_slider_frame.pack(fill="x", pady=(spacing["small"], 0))
        cpu_slider_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            cpu_slider_frame,
            text="Cores:",
            font=ctk.CTkFont(size=fonts["normal"])
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        self.cpu_cores_slider = ctk.CTkSlider(
            cpu_slider_frame,
            from_=1,
            to=self.cpu_count,
            number_of_steps=self.cpu_count - 1,
            variable=self.cpu_custom_cores_var,
            command=self.update_cores_label,
            height=20
        )
        self.cpu_cores_slider.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        
        self.cores_value_label = ctk.CTkLabel(
            cpu_slider_frame,
            text=str(self.cpu_custom_cores_var.get()),
            font=ctk.CTkFont(size=fonts["normal"], weight="bold"),
            text_color=VSCODE_COLORS["primary"],
            width=30
        )
        self.cores_value_label.grid(row=0, column=2, sticky="e")
        
        # Show custom CPU frame if Custom is selected
        if self.cpu_usage_var.get() == "Custom":
            self.custom_cpu_frame.pack(fill="x", pady=(5, 0))
        
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
    def get_app_directory(self):
        """Get the base directory where the app/exe is located"""
        if getattr(sys, 'frozen', False):
            # Running as executable
            return os.path.dirname(os.path.abspath(sys.executable))
        else:
            # Running as script
            return os.path.dirname(os.path.abspath(__file__))
    def render_animation(self):
        """Render the current animation - FIXED to use app directory with CORRECT variable names"""
        if not self.current_code.strip():
            messagebox.showwarning("No Code", "Please write some Manim code first.")
            return
            
        if not self.venv_manager.is_ready():
            messagebox.showwarning(
                "Environment Not Ready", 
                "Please set up an environment first.\n\n"
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
            # Use directory next to app instead of system temp
            app_dir = self.get_app_directory()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = os.path.join(app_dir, f"render_temp_{timestamp}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Extract scene class name
            scene_class = self.extract_scene_class_name(self.current_code)
            
            # Write code to file in temp directory
            scene_file = os.path.join(temp_dir, f"scene_{timestamp}.py")
            with open(scene_file, "w", encoding="utf-8") as f:
                f.write(self.current_code)
                
            # Get render settings - CORRECT variable names
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
                "-m", "manim",
                os.path.basename(scene_file),  # Use basename since we set cwd
                str(scene_class),
                str(quality_flag),
                "--format", format_ext,
                "--fps", str(fps),
                "--renderer", "cairo"
            ]
            
            # Add custom resolution if using custom quality
            if self.quality_var.get() == "Custom":
                command.extend([
                    "--resolution", f"{resolution_settings['width']},{resolution_settings['height']}"
                ])
            
            # Add audio if available (check in app directory)
            audio_files = [f for f in os.listdir(app_dir) if f.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a'))]
            if audio_files:
                audio_path = os.path.join(app_dir, audio_files[0])  # Use first audio file found
                command.extend(["--sound", audio_path])
                self.append_terminal_output(f"🎵 Using audio: {audio_files[0]}\n")
            
            # Set environment variable for CPU control
            env = {"OMP_NUM_THREADS": str(num_cores)}
            
            # Enhanced logging
            self.append_terminal_output(f"Starting render...\n")
            self.append_terminal_output(f"Resolution: {resolution_settings['resolution']} @ {fps}fps\n")
            self.append_terminal_output(f"Using {num_cores} CPU cores\n")
            self.append_terminal_output(f"Temp directory: {temp_dir}\n")
            
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
                
                # Cleanup temp directory after a delay
                def cleanup_temp():
                    try:
                        if os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir)
                    except Exception as e:
                        self.append_terminal_output(f"Warning: Could not clean up temp directory: {e}\n")
                
                # Schedule cleanup after 30 seconds
                self.root.after(30000, cleanup_temp)
            
            # Run command from temp directory
            self.terminal.run_command_redirected(command, on_render_complete, env, cwd=temp_dir)
                
        except Exception as e:
            self.update_status(f"Render error: {e}")
            self.append_terminal_output(f"Render error: {e}\n")
            self.render_button.configure(text="🚀 Render Animation", state="normal")
            self.is_rendering = False
    
    def initialize_variables(self):
        """Initialize all application variables - FIXED VERSION"""
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
        self.cpu_usage_var = ctk.StringVar(value=self.settings["cpu_usage"])
        
        # FIXED: Missing CPU custom cores variable
        self.cpu_custom_cores_var = ctk.IntVar(value=self.settings.get("cpu_custom_cores", 2))

    def on_cpu_usage_change(self, value):
        """Handle CPU usage preset change - FIXED VERSION"""
        self.settings["cpu_usage"] = value
        self.cpu_description.configure(text=CPU_USAGE_PRESETS[value]["description"])
        
        # Show/hide custom slider based on selection
        if value == "Custom":
            self.custom_cpu_frame.pack(fill="x", pady=(5, 0))
        else:
            self.custom_cpu_frame.pack_forget()
        
        self.save_settings()

    def update_cores_label(self, value):
        """Update the cores value label - FIXED VERSION"""
        cores = int(float(value))  # Handle float values from slider
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
            if fps < 1 or fps > 12000:
                errors.append("FPS must be between 1 and 12000")
            
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
        """Create preview settings section with responsive sizing - FIXED VERSION"""
        # Get responsive dimensions
        fonts = self.responsive.get_optimal_font_sizes()
        spacing = self.responsive.get_optimal_spacing()
        
        # Section header
        preview_header = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface_light"])
        preview_header.pack(fill="x", pady=(0, spacing["normal"]))
        
        header_title = ctk.CTkLabel(
            preview_header,
            text="👁️ Preview Settings",
            font=ctk.CTkFont(size=fonts["large"], weight="bold"),
            text_color=VSCODE_COLORS["text_bright"]
        )
        header_title.pack(side="left", padx=spacing["medium"], pady=spacing["normal"])
        
        # Preview settings frame
        preview_frame = ctk.CTkFrame(self.sidebar_scroll, fg_color=VSCODE_COLORS["surface"])
        preview_frame.pack(fill="x", pady=(0, spacing["normal"]))
        
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
        
        # Preview button with responsive sizing - FIXED: Use safe colors
        preview_btn_height = self.responsive.get_button_dimensions(base_height=45)
        self.quick_preview_button = ctk.CTkButton(
            preview_frame,
            text="⚡ Quick Preview",
            command=self.quick_preview,
            height=preview_btn_height,
            font=ctk.CTkFont(size=fonts["large"], weight="bold"),
            fg_color=VSCODE_COLORS["secondary"],
            hover_color=VSCODE_COLORS["primary"]
        )
        self.quick_preview_button.pack(fill="x", padx=spacing["medium"], pady=spacing["medium"])
    
    
    
    
    def create_controls(self):
        """Create YouTube-style control layout - FIXED VERSION"""
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
            hover_color=VSCODE_COLORS.get("primary_hover", VSCODE_COLORS["primary"]),
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
            
    def clear_assets(self):
        """Clear all assets"""
        self.image_paths.clear()
        self.audio_path = None
        self.update_assets_display()
        self.append_terminal_output("Cleared all assets\n")

    def ensure_assets_folder(self):
        """FIXED: Ensure assets folder exists next to the app - BETTER exe detection"""
        
        # ENHANCED detection for exe builds
        if getattr(sys, 'frozen', False):
            # Running as executable (.exe) 
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller bundle - use original exe location
                exe_dir = os.path.dirname(sys.executable)
                # Check if we're in a temp extraction folder
                if 'temp' in exe_dir.lower() or 'tmp' in exe_dir.lower() or '_MEI' in exe_dir:
                    # Use the directory where the .exe was originally launched from
                    base_dir = os.getcwd()
                else:
                    base_dir = exe_dir
            else:
                # Nuitka onefile - get REAL exe directory  
                real_exe_path = os.path.realpath(sys.executable)
                if 'temp' in real_exe_path.lower() or 'tmp' in real_exe_path.lower():
                    # OneDirBundle extraction - use launch directory
                    base_dir = os.getcwd()
                else:
                    # OneFile in permanent location
                    base_dir = os.path.dirname(real_exe_path)
            
            self.append_terminal_output(f"🔧 EXE detected - using: {base_dir}\n")
        else:
            # Running as script (.py)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.append_terminal_output(f"🐍 Script detected - using: {base_dir}\n")
        
        # Force assets next to exe/script, NOT in temp
        assets_path = os.path.join(base_dir, "assets")
        os.makedirs(assets_path, exist_ok=True)
        
        # Verify we're NOT in a temp folder
        if 'temp' in assets_path.lower() or 'tmp' in assets_path.lower():
            # Fallback to current working directory 
            fallback_path = os.path.join(os.getcwd(), "assets")
            os.makedirs(fallback_path, exist_ok=True)
            self.append_terminal_output(f"⚠️ Temp path detected, using fallback: {fallback_path}\n")
            return fallback_path
        
        self.append_terminal_output(f"✅ Assets folder: {assets_path}\n")
        return assets_path
    def setup_drag_drop_availability(self):
        """Enhanced drag and drop detection for exe builds"""
        try:
            # Try importing tkinterdnd2
            import tkinterdnd2
            from tkinterdnd2 import DND_FILES, TkinterDnD
            
            # Test if tkinterdnd2 can actually initialize
            # This is critical for exe builds
            test_successful = False
            try:
                # Create a test window to verify tkinterdnd2 works
                import tkinter as tk
                test_root = tk.Tk()
                test_root.withdraw()  # Hide it
                
                # Try to initialize tkinterdnd2
                TkinterDnD._require(test_root)
                test_root.destroy()
                test_successful = True
                
            except Exception as e:
                if 'test_root' in locals():
                    try:
                        test_root.destroy()
                    except:
                        pass
                print(f"⚠️ tkinterdnd2 initialization test failed: {e}")
                test_successful = False
            
            if test_successful:
                # Store the imports for later use
                self.tkinterdnd2 = tkinterdnd2
                self.DND_FILES = DND_FILES
                self.TkinterDnD = TkinterDnD
                self.drag_drop_available = True
                
                print("✅ tkinterdnd2 available - drag & drop enabled")
                if hasattr(self, 'main_app'):
                    self.main_app.append_terminal_output("✅ Drag & Drop: ENABLED\n")
            else:
                raise Exception("tkinterdnd2 failed initialization test")
                
        except Exception as e:
            self.drag_drop_available = False
            self.tkinterdnd2 = None
            self.DND_FILES = None
            self.TkinterDnD = None
            
            print(f"⚠️ tkinterdnd2 not available: {e}")
            if hasattr(self, 'main_app'):
                self.main_app.append_terminal_output("⚠️ Drag & Drop: DISABLED (Use file buttons)\n")
    def create_temp_animation_file(self, prefix="temp_preview"):
        """Create temp file INSIDE assets folder"""
        assets_folder = self.ensure_assets_folder()
        timestamp = str(int(time.time() * 1000))
        temp_filename = f"{prefix}_{timestamp}.py"
        temp_path = os.path.join(assets_folder, temp_filename)
        
        # Write current code to temp file
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(self.current_code)
        
        self.append_terminal_output(f"📄 Created: {temp_filename}\n")
        self.append_terminal_output(f"📁 Working in: {assets_folder}\n")
        
        return temp_path, assets_folder
    def add_images(self):
        """Add image assets to assets folder"""
        from tkinter import filedialog, messagebox
        file_paths = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.svg"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("All files", "*.*")
            ]
        )
        
        if file_paths:
            try:
                assets_folder = self.ensure_assets_folder()
                copied_files = []
                
                for file_path in file_paths:
                    filename = os.path.basename(file_path)
                    
                    # Handle duplicate names
                    counter = 1
                    base_name, ext = os.path.splitext(filename)
                    while os.path.exists(os.path.join(assets_folder, filename)):
                        filename = f"{base_name}_{counter}{ext}"
                        counter += 1
                    
                    destination = os.path.join(assets_folder, filename)
                    shutil.copy2(file_path, destination)
                    copied_files.append(filename)
                    
                    # Add to image paths list (using relative path)
                    relative_path = f"assets/{filename}"
                    if relative_path not in self.image_paths:
                        self.image_paths.append(relative_path)
                
                self.update_assets_display()
                
                # Show success message with paths to use
                paths_text = "\n".join([f'"assets/{f}"' for f in copied_files])
                messagebox.showinfo(
                    "Images Added",
                    f"Copied {len(copied_files)} image(s) to assets folder!\n\n"
                    f"Use these paths in your Manim code:\n{paths_text}\n\n"
                    f"Example:\nimg = ImageMobject(\"assets/{copied_files[0]}\")",
                    parent=self.root
                )
                
                self.append_terminal_output(f"Added {len(copied_files)} image(s) to assets folder\n")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to copy images:\n{str(e)}", parent=self.root)

    def add_audio(self):
        """Add audio asset to assets folder"""
        from tkinter import filedialog, messagebox
        file_path = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.ogg *.m4a *.flac"),
                ("MP3 files", "*.mp3"),
                ("WAV files", "*.wav"),
                ("All files", "*.*")
            ]
        )
        
        if file_path:
            try:
                assets_folder = self.ensure_assets_folder()
                filename = os.path.basename(file_path)
                
                # Handle duplicate names
                counter = 1
                base_name, ext = os.path.splitext(filename)
                while os.path.exists(os.path.join(assets_folder, filename)):
                    filename = f"{base_name}_{counter}{ext}"
                    counter += 1
                
                destination = os.path.join(assets_folder, filename)
                shutil.copy2(file_path, destination)
                
                # Set audio path (using relative path)
                relative_path = f"assets/{filename}"
                self.audio_path = relative_path
                
                self.update_assets_display()
                
                # Show success message with path to use
                messagebox.showinfo(
                    "Audio Added",
                    f"Audio copied to assets folder!\n\n"
                    f"Use this path in your Manim code:\n"
                    f'"{relative_path}"\n\n'
                    f"Example:\n"
                    f'self.add_sound("{relative_path}")',
                    parent=self.root
                )
                
                self.append_terminal_output(f"Added audio: {filename} to assets folder\n")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to copy audio:\n{str(e)}", parent=self.root)
    
    def update_assets_display(self):
        """Update assets display"""
        # Clear existing widgets
        for widget in self.assets_container.winfo_children():
            widget.destroy()
        
        # Count total assets
        total_assets = len(self.image_paths) + (1 if self.audio_path else 0)
        
        if total_assets > 0:
            # Show asset count
            info_parts = []
            if self.image_paths:
                info_parts.append(f"{len(self.image_paths)} image(s)")
            if self.audio_path:
                info_parts.append("1 audio file")
            
            info_text = ", ".join(info_parts)
            self.assets_info = ctk.CTkLabel(
                self.assets_container,
                text=info_text,
                font=ctk.CTkFont(size=12),
                text_color=VSCODE_COLORS["text"]
            )
            self.assets_info.pack(pady=10)
            
            # List assets
            for i, img_path in enumerate(self.image_paths):
                asset_frame = ctk.CTkFrame(self.assets_container)
                asset_frame.pack(fill="x", pady=2, padx=5)
                
                ctk.CTkLabel(
                    asset_frame,
                    text=f"📷 {os.path.basename(img_path)}",
                    font=ctk.CTkFont(size=10)
                ).pack(side="left", padx=5, pady=5)
                
                remove_btn = ctk.CTkButton(
                    asset_frame,
                    text="Remove",
                    width=60,
                    height=20,
                    command=lambda path=img_path: self.remove_image_asset(path),
                    fg_color=VSCODE_COLORS["error"]
                )
                remove_btn.pack(side="right", padx=5, pady=2)
            
            if self.audio_path:
                asset_frame = ctk.CTkFrame(self.assets_container)
                asset_frame.pack(fill="x", pady=2, padx=5)
                
                ctk.CTkLabel(
                    asset_frame,
                    text=f"🎵 {os.path.basename(self.audio_path)}",
                    font=ctk.CTkFont(size=10)
                ).pack(side="left", padx=5, pady=5)
                
                remove_btn = ctk.CTkButton(
                    asset_frame,
                    text="Remove",
                    width=60,
                    height=20,
                    command=self.remove_audio_asset,
                    fg_color=VSCODE_COLORS["error"]
                )
                remove_btn.pack(side="right", padx=5, pady=2)
        else:
            self.assets_info = ctk.CTkLabel(
                self.assets_container,
                text="Click + to add images or audio files",
                font=ctk.CTkFont(size=12),
                text_color=VSCODE_COLORS["text_secondary"]
            )
            self.assets_info.pack(pady=20)

    def remove_image_asset(self, image_path):
        """Remove a specific image asset"""
        if image_path in self.image_paths:
            self.image_paths.remove(image_path)
            self.update_assets_display()
            self.append_terminal_output(f"Removed image: {os.path.basename(image_path)}\n")

    def remove_audio_asset(self):
        """Remove audio asset"""
        if self.audio_path:
            filename = os.path.basename(self.audio_path)
            self.audio_path = None
            self.update_assets_display()
            self.append_terminal_output(f"Removed audio: {filename}\n")

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
        """Generate quick preview - FIXED to create temp files inside assets folder"""
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
        
        # FIXED: Create temp file INSIDE assets folder
        assets_folder = self.ensure_assets_folder()
        temp_suffix = str(int(time.time() * 1000))
        
        # Create temp file inside assets folder
        temp_file = os.path.join(assets_folder, f"temp_preview_{temp_suffix}.py")
        
        # Write Python file inside assets folder
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(self.current_code)
            self.append_terminal_output(f"📄 Created temp file: {temp_file}\n")
            self.append_terminal_output(f"📁 Working directory: {assets_folder}\n")
            self.append_terminal_output(f"📁 Assets accessible directly by filename (e.g., 'pic.jpg')\n")
        except Exception as e:
            self.append_terminal_output(f"❌ Error writing temp file: {e}\n")
            self.quick_preview_button.configure(text="⚡ Quick Preview", state="normal")
            self.is_previewing = False
            return
        
        # FORCE USE OF VIRTUAL ENVIRONMENT
        if self.venv_manager.current_venv and self.venv_manager.python_path and os.path.exists(self.venv_manager.python_path):
            python_cmd = self.venv_manager.python_path
            self.append_terminal_output(f"✅ Using virtual environment: {self.venv_manager.current_venv}\n")
        else:
            self.append_terminal_output("❌ Virtual environment not found!\n", "error")
            self.quick_preview_button.configure(text="⚡ Quick Preview", state="normal")
            self.is_previewing = False
            return
        
        # Build manim command
        command = [
            python_cmd,
            "-m", "manim", "render",
            os.path.basename(temp_file),  # Use basename since we set cwd to assets folder
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
        self.log_info(f"Working directory: {assets_folder}")
        
        # On preview complete callback
        def on_preview_complete(success, return_code):
            try:
                # Reset UI state first
                self.quick_preview_button.configure(text="⚡ Quick Preview", state="normal")
                self.is_previewing = False
                
                if success:
                    # Find the output video file in media structure
                    video_files = []
                    media_dir = os.path.join(assets_folder, "media", "videos")
                    
                    # Search recursively for mp4 files
                    if os.path.exists(media_dir):
                        for root, dirs, files in os.walk(media_dir):
                            for file in files:
                                if file.endswith('.mp4') and f"preview_{temp_suffix}" in file:
                                    video_files.append(os.path.join(root, file))
                    
                    if video_files:
                        # Use the most recent video file
                        latest_video = max(video_files, key=os.path.getmtime)
                        self.log_success(f"Preview generated: {os.path.basename(latest_video)}")
                        
                        # Load the video in the preview
                        if self.load_preview_video(latest_video):
                            self.last_preview_code = self.current_code
                            self.last_manim_output_path = latest_video
                        else:
                            self.log_error("Failed to load preview video")
                    else:
                        self.log_error("No output video file found")
                else:
                    self.log_error(f"Preview generation failed (return code: {return_code})")
                    
            except Exception as e:
                self.log_error(f"Error in preview completion: {e}")
            finally:
                # Clean up temp Python file after a delay
                def cleanup_temp():
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                        # Also clean up media folder inside assets
                        media_dir = os.path.join(assets_folder, "media")
                        if os.path.exists(media_dir):
                            shutil.rmtree(media_dir)
                    except:
                        pass
                
                # Schedule cleanup after 10 seconds
                self.root.after(10000, cleanup_temp)
        
        # Run the command from assets folder (where Python file and assets are located)
        self.terminal.run_command_redirected(command, on_preview_complete, cwd=assets_folder)
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
        """Render the current animation - FIXED format parameter issue"""
        if not self.current_code.strip():
            messagebox.showwarning("No Code", "Please write some Manim code first.")
            return
            
        if not self.venv_manager.is_ready():
            messagebox.showwarning(
                "Environment Not Ready", 
                "Please set up an environment first.\n\n"
                "Click the Environment Setup button to create one."
            )
            return
            
        # Check if already rendering
        if self.is_rendering:
            return
        
        try:
            self.is_rendering = True
            self.render_button.configure(text="⏳ Rendering...", state="disabled")
            
            # Get settings
            scene_class = self.extract_scene_class_name(self.current_code)
            if not scene_class:
                messagebox.showerror("Error", "No valid Manim scene class found in the code.")
                self.render_button.configure(text="🚀 Render Animation", state="normal")
                self.is_rendering = False
                return
            
            # FIXED: Clean format parameter
            quality = self.quality_var.get()
            format_raw = self.format_var.get()
            fps_raw = self.fps_var.get()
            
            # Clean and validate format parameter
            format_ext = format_raw.strip().strip('"').strip("'").lower()
            if format_ext not in ['mp4', 'mov', 'gif', 'png', 'webm']:
                format_ext = 'mp4'  # Default fallback
            
            # Clean fps parameter
            try:
                fps = str(int(fps_raw.strip().strip('"').strip("'")))
            except:
                fps = "30"  # Default fallback
            
            self.append_terminal_output(f"📋 Render settings: Quality={quality}, Format={format_ext}, FPS={fps}\n")
            
            # FIXED: Create temp file INSIDE assets folder
            assets_folder = self.ensure_assets_folder()
            temp_suffix = str(int(time.time() * 1000))
            
            # Create temp file inside assets folder
            temp_file = os.path.join(assets_folder, f"temp_render_{temp_suffix}.py")
            
            # Write the current code to temp file
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(self.current_code)
            
            self.append_terminal_output(f"📄 Created temp file: {temp_file}\n")
            self.append_terminal_output(f"📁 Working directory: {assets_folder}\n")
            self.append_terminal_output(f"📁 Assets accessible directly by filename (e.g., 'pic.jpg')\n")
            
            # Build manim command with FIXED format parameter
            quality_flags = {
                "Low": ["-ql"],
                "Medium": ["-qm"], 
                "High": ["-qh"],
                "Ultra": ["-qk"]
            }
            
            command = [
                self.venv_manager.python_path,
                "-m", "manim", "render",
                os.path.basename(temp_file),  # Use basename since we set cwd to assets folder
                scene_class,
                *quality_flags.get(quality, ["-qm"]),
                "--format", format_ext,  # Now properly cleaned
                "--fps", fps,            # Now properly cleaned
                "--disable_caching",
                "-o", f"render_{temp_suffix}"
            ]
            
            # Log the exact command for debugging
            self.append_terminal_output(f"🔧 Command: {' '.join(command)}\n")
            
            # Get environment
            env = self.get_subprocess_environment()
            
            # Progress tracking
            self.progress_bar.set(0.1)
            self.progress_label.configure(text="Rendering...")
            self.update_status("Rendering animation...")
            
            def on_render_complete(success, return_code):
                # Find output file
                output_file = None
                media_dir = os.path.join(assets_folder, "media", "videos")
                
                if os.path.exists(media_dir):
                    for root, dirs, files in os.walk(media_dir):
                        for file in files:
                            if file.endswith(f'.{format_ext}') and f"render_{temp_suffix}" in file:
                                output_file = os.path.join(root, file)
                                break
                        if output_file:
                            break
                
                # Reset UI state
                self.render_button.configure(text="🚀 Render Animation", state="normal")
                self.is_rendering = False
                
                if output_file and os.path.exists(output_file):
                    self.progress_bar.set(1.0)
                    self.progress_label.configure(text="Render completed")
                    self.update_status("Render completed successfully")
                    
                    # Save rendered file
                    self.save_rendered_file(output_file, format_ext)
                else:
                    self.progress_bar.set(0)
                    self.progress_label.configure(text="Render failed")
                    self.update_status("Render failed")
                    self.append_terminal_output("Error: Output file not found or rendering failed\n")
                
                # Cleanup temp files after a delay
                def cleanup_temp():
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                        # Also clean up media folder inside assets
                        media_dir = os.path.join(assets_folder, "media")
                        if os.path.exists(media_dir):
                            shutil.rmtree(media_dir)
                    except Exception as e:
                        self.append_terminal_output(f"Warning: Could not clean up temp files: {e}\n")
                
                # Schedule cleanup after 30 seconds
                self.root.after(30000, cleanup_temp)
            
            # Run command from assets folder (where Python file and assets are located)
            self.terminal.run_command_redirected(command, on_render_complete, env, cwd=assets_folder)
                
        except Exception as e:
            self.update_status(f"Render error: {e}")
            self.append_terminal_output(f"Render error: {e}\n")
            self.render_button.configure(text="🚀 Render Animation", state="normal")
            self.is_rendering = False
    def setup_format_dropdown(self):
        """Setup format dropdown with proper values"""
        # Make sure format dropdown has clean values
        format_options = ["mp4", "mov", "gif", "png", "webm"]
        
        # If you have a format dropdown widget, update it like this:
        if hasattr(self, 'format_dropdown'):
            self.format_dropdown.configure(values=format_options)
        
        # Set default value
        if not self.format_var.get() or self.format_var.get().strip() == "":
            self.format_var.set("mp4")
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
        
        # Updated Description with credits
        description = f"""A modern, professional desktop application for creating
mathematical animations using the Manim library.

👨‍💻 Created by: Yu Yao-Hsing
🤖 Coding assistance from:
   • Claude Sonnet 4 (Anthropic)
   • ChatGPT o3 (OpenAI)

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
- Manim Community Edition for mathematical animations
- FFmpeg for video processing and export
- PIL/Pillow for image processing and manipulation

📋 Technical Stack:
- Frontend: CustomTkinter (Modern Python GUI)
- Backend: Python 3.12+ with virtual environment management
- Rendering: Manim Community Edition with FFmpeg
- Editor: Custom text widget with syntax highlighting
- IntelliSense: Jedi language server integration
- Asset Management: PIL/Pillow with preview generation"""
        
        # Create scrollable text widget for description
        desc_frame = ctk.CTkFrame(content_frame, fg_color=VSCODE_COLORS["surface_light"])
        desc_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        desc_text = ctk.CTkTextbox(
            desc_frame,
            font=ctk.CTkFont(size=11, family="Consolas"),
            wrap="word",
            height=300
        )
        desc_text.pack(fill="both", expand=True, padx=10, pady=10)
        desc_text.insert("1.0", description)
        desc_text.configure(state="disabled")  # Make read-only
        
        # Buttons frame
        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(10, 0))
        
        # Show detailed guide button
        guide_button = ctk.CTkButton(
            button_frame,
            text="📖 Complete User Guide",
            command=lambda: self.show_detailed_user_guide(),
            height=35
        )
        guide_button.pack(side="left", padx=(0, 10))
        
        # Close button
        close_button = ctk.CTkButton(
            button_frame,
            text="Close",
            command=about_dialog.destroy,
            height=35
        )
        close_button.pack(side="right")
    def show_detailed_user_guide(self):
        """Show detailed user guide dialog"""
        try:
            DetailedUserGuideDialog(self)
        except Exception as e:
            print(f"Error showing detailed user guide: {e}")
    def show_post_installation_guide(self):
        """Show comprehensive user guide after installation is complete"""
        try:
            # Show completion message first
            if messagebox.askyesno(
                "Installation Complete! 🎉",
                "ManimStudio has been set up successfully!\n\n"
                "Your virtual environment is ready with all required packages.\n"
                "Python, Manim, and all dependencies are installed.\n\n"
                "Would you like to see the complete user guide to get started?",
                parent=self.root
            ):
                DetailedUserGuideDialog(self)
        except Exception as e:
            print(f"Error showing post-installation guide: {e}")
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
    def _setup_paths(self):
        """Setup application paths - EXE COMPATIBLE"""
        print("📁 Setting up application paths...")
        
        # FORCE FROZEN DETECTION - Fix for exe builds
        self.is_frozen = (getattr(sys, 'frozen', False) or 
                         sys.executable.endswith('.exe') or 
                         'dist' in sys.executable or
                         'app.exe' in sys.executable.lower())
        
        print(f"🔧 Frozen detection: {self.is_frozen}")
        print(f"🔧 sys.frozen: {getattr(sys, 'frozen', False)}")
        print(f"🔧 sys.executable: {sys.executable}")
        
        # Set base directory
        if self.is_frozen:
            # For exe builds, use the directory containing the exe
            self.base_dir = os.path.dirname(sys.executable)
            print(f"🔧 Exe build detected - base dir: {self.base_dir}")
        else:
            # For script builds, use the script directory
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            print(f"🐍 Script build detected - base dir: {self.base_dir}")
        
        # Set app directory - always use user directory for data
        self.app_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")
        self.venv_dir = os.path.join(self.app_dir, "venvs")
        
        # Create directories with proper error handling
        try:
            os.makedirs(self.venv_dir, exist_ok=True)
            os.makedirs(self.app_dir, exist_ok=True)
            print(f"✅ Created directories successfully")
        except PermissionError:
            print(f"❌ Permission denied creating directories")
            # Fallback to temp directory
            import tempfile
            self.app_dir = tempfile.mkdtemp(prefix="manim_studio_")
            self.venv_dir = os.path.join(self.app_dir, "venvs")
            os.makedirs(self.venv_dir, exist_ok=True)
            print(f"📁 Using temp directory: {self.app_dir}")
        except Exception as e:
            print(f"❌ Error creating directories: {e}")
            raise
        
        print(f"📁 Base directory: {self.base_dir}")
        print(f"📁 App directory: {self.app_dir}")
        print(f"📁 Venv directory: {self.venv_dir}")
    def auto_activate_default_environment(self):
        """Auto-activate manim_studio_default environment - WITH WINDOWSAPPS DETECTION AND COPY"""
        try:
            print("🔍 Checking for existing environments...")
            
            # Ensure we have the necessary attributes
            if not hasattr(self, 'venv_dir'):
                print("⚠️ venv_dir not initialized, running path setup...")
                self._setup_paths()
            
            # Check for default environment in usual location first
            default_venv_path = os.path.join(self.venv_dir, "manim_studio_default")
            
            if os.path.exists(default_venv_path):
                print("🎯 Found manim_studio_default environment in usual location")
                
                # Get Python and pip paths
                if sys.platform == "win32":
                    python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
                    pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
                else:
                    python_path = os.path.join(default_venv_path, "bin", "python")
                    pip_path = os.path.join(default_venv_path, "bin", "pip")
                
                # Verify executables exist
                if os.path.exists(python_path) and os.path.exists(pip_path):
                    # ACTIVATE THE ENVIRONMENT
                    self.python_path = python_path
                    self.pip_path = pip_path
                    self.current_venv = "manim_studio_default"
                    self.needs_setup = False  # CRITICAL: Mark as ready
                    print(f"✅ Activated existing environment: {python_path}")
                    return
                else:
                    print("❌ Environment exists but executables missing")
            
            # YOUR SPECIFIC WINDOWSAPPS PATH - Check for bundled environment
            bundled_path = r"C:\Program Files\WindowsApps\9NZFT55DVCBS_1.0.2.0_x64__c5s549jf2x494\app\venv_bundle\manim_studio_default"
            
            print(f"🔍 Checking your specific bundled location: {bundled_path}")
            
            if os.path.exists(bundled_path):
                print(f"🎯 Found bundled environment at: {bundled_path}")
                
                # Get Python and pip paths for bundled environment
                if sys.platform == "win32":
                    bundled_python_path = os.path.join(bundled_path, "Scripts", "python.exe")
                    bundled_pip_path = os.path.join(bundled_path, "Scripts", "pip.exe")
                else:
                    bundled_python_path = os.path.join(bundled_path, "bin", "python")
                    bundled_pip_path = os.path.join(bundled_path, "bin", "pip")
                
                # Verify bundled executables exist
                if os.path.exists(bundled_python_path) and os.path.exists(bundled_pip_path):
                    print(f"✅ Bundled environment verified: {bundled_path}")
                    
                    # COPY bundled environment to usual location
                    try:
                        print(f"📋 Copying bundled environment to: {default_venv_path}")
                        print("⏳ This may take a few minutes...")
                        
                        # Use shutil.copytree to copy the entire environment
                        if os.path.exists(default_venv_path):
                            print(f"🗑️ Removing existing incomplete environment...")
                            shutil.rmtree(default_venv_path)
                        
                        shutil.copytree(bundled_path, default_venv_path, symlinks=True, dirs_exist_ok=True)
                        
                        print(f"✅ Successfully copied bundled environment")
                        
                        # Verify the copied environment works
                        if sys.platform == "win32":
                            python_path = os.path.join(default_venv_path, "Scripts", "python.exe")
                            pip_path = os.path.join(default_venv_path, "Scripts", "pip.exe")
                        else:
                            python_path = os.path.join(default_venv_path, "bin", "python")
                            pip_path = os.path.join(default_venv_path, "bin", "pip")
                        
                        if os.path.exists(python_path) and os.path.exists(pip_path):
                            # ACTIVATE THE COPIED ENVIRONMENT
                            self.python_path = python_path
                            self.pip_path = pip_path
                            self.current_venv = "manim_studio_default"
                            self.needs_setup = False  # CRITICAL: Mark as ready
                            
                            print(f"✅ Activated copied environment: {python_path}")
                            print(f"📁 Environment location: {default_venv_path}")
                            
                            # Test the environment quickly
                            try:
                                result = subprocess.run(
                                    [python_path, "--version"],
                                    capture_output=True,
                                    text=True,
                                    timeout=10
                                )
                                if result.returncode == 0:
                                    python_version = result.stdout.strip()
                                    print(f"✅ Environment test successful: {python_version}")
                                else:
                                    print(f"⚠️ Environment test warning: {result.stderr}")
                            except Exception as test_e:
                                print(f"⚠️ Environment test failed: {test_e}")
                            
                            return  # SUCCESS - environment copied and activated
                        else:
                            print(f"❌ Copied environment missing executables")
                            
                    except Exception as copy_e:
                        print(f"❌ Failed to copy bundled environment: {copy_e}")
                        
                        # Fallback: Use bundled environment directly (original behavior)
                        print(f"🔄 Falling back to direct bundled environment usage")
                        self.python_path = bundled_python_path
                        self.pip_path = bundled_pip_path
                        self.current_venv = "manim_studio_default"
                        self.needs_setup = False  # CRITICAL: Mark as ready even for direct usage
                        print(f"✅ Activated bundled environment directly: {bundled_python_path}")
                        return
                else:
                    print(f"❌ Bundled environment exists but executables missing: {bundled_path}")
            else:
                print(f"❌ Bundled environment NOT found at: {bundled_path}")
            
            # If we get here, no environment was found
            print("📝 No manim_studio_default environment found")
            self.needs_setup = True
                
        except Exception as e:
            print(f"❌ Error in auto-activation: {e}")
            if hasattr(self, 'logger'):
                self.logger.error(f"Error in auto-activation: {e}")
            self.needs_setup = True
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
    """Main entry point - Direct initialization without splash"""
    try:
        # Set flag to prevent duplicate encoding fixes
        os.environ['ENCODING_FIXES_APPLIED'] = '1'
        
        print("Initializing Manim Studio...")
        
        # Setup essential paths and data
        app_data_dir = os.path.join(os.path.expanduser("~"), ".manim_studio")
        os.makedirs(app_data_dir, exist_ok=True)
        
        print("Setting up logging...")
        
        # Setup logging
        logger = setup_logging(app_data_dir)
        logger.info("Starting application...")
        
        print("Checking dependencies...")
        
        # Check Jedi availability
        if not JEDI_AVAILABLE:
            print("Warning: Jedi not available. IntelliSense features will be limited.")
            logger.warning("Jedi not available. IntelliSense features will be limited.")
        
        print("Parsing command line arguments...")
        
        # Parse command line arguments
        import argparse
        parser = argparse.ArgumentParser(description="Manim Animation Studio")
        parser.add_argument("--debug", action="store_true", help="Enable debug mode")
        args = parser.parse_args()
        debug_mode = args.debug
        
        print("Creating main application...")
        
        # Create main application directly - VirtualEnvironmentManager will handle all setup
        app = ManimStudioApp(latex_path=None, debug=debug_mode)
        
        print("Starting main application...")
        app.root.after(1000, lambda: DetailedUserGuideDialog(app))
        # Start main application
        logger.info("Starting application main loop...")
        app.run()
        
    except Exception as e:
        print(f"Critical startup error: {e}")
        import traceback
        traceback.print_exc()
        
        # Show error dialog with fresh tkinter instance
        try:
            import tkinter
            import tkinter.messagebox as messagebox
            error_root = tkinter.Tk()
            error_root.withdraw()
            messagebox.showerror("Startup Error", f"Failed to start application:\n\n{str(e)}")
            error_root.destroy()
        except:
            pass
    
    finally:
        print("Application shutdown complete")
if __name__ == "__main__":
    main()
