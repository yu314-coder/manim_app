"""
Manim Studio - Native Desktop Application
Uses PyWebView to create a native desktop window with HTML/CSS/JS UI
Single executable with PyInstaller
"""
import webview
from webview import FileDialog
import os
import sys
import tempfile
import subprocess
import json
import threading
import time
from pathlib import Path
import re
import socket

# Fix encoding issues on Windows - ensure UTF-8 encoding for stdout/stderr
if sys.platform == 'win32':
    import io
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# App version
APP_VERSION = "1.1.1.0"

# Terminal emulation with PTY support
try:
    import winpty
    WINPTY_AVAILABLE = True
except ImportError:
    WINPTY_AVAILABLE = False
    print("[WARNING] pywinpty not available - terminal will use fallback mode")

# No AI/LLM imports - feature removed

# Determine base directory
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# User data directory (defined early for use in setup_venv)
# Force exact structure: C:\Users\<username>\.manim_studio
USER_DATA_DIR = os.path.join(os.path.expanduser('~'), '.manim_studio')
MEDIA_DIR = os.path.join(USER_DATA_DIR, 'media')  # Render output folder
ASSETS_DIR = os.path.join(USER_DATA_DIR, 'assets')
PREVIEW_DIR = os.path.join(USER_DATA_DIR, 'preview')  # Preview folder (cleared before each preview)
RENDER_DIR = os.path.join(USER_DATA_DIR, 'render')  # Render folder (for high-quality renders)
AUTOSAVE_DIR = os.path.join(USER_DATA_DIR, 'autosave')  # Auto-save directory

# Virtual environment directory - always at: ~/.manim_studio/venvs/manim_studio_default
VENV_DIR = os.path.join(USER_DATA_DIR, 'venvs', 'manim_studio_default')

# Set encoding environment variables (crucial for Windows)
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = '0'
os.environ['PYTHONUTF8'] = '1'

def get_clean_environment():
    """
    Get a clean environment for running Python subprocesses.
    This prevents the exe from accidentally being used as Python interpreter.
    Critical: Removes PYTHONPATH and PYTHONHOME to prevent circular execution.
    """
    env = os.environ.copy()

    # CRITICAL: REMOVE (not just clear) these variables to prevent exe interference
    # Setting to empty string can cause issues - we need to delete them
    keys_to_remove = ['PYTHONPATH', 'PYTHONHOME', '__PYVENV_LAUNCHER__']
    for key in keys_to_remove:
        if key in env:
            del env[key]
            print(f"[ENV] Removed {key} from environment")

    # Set encoding for proper UTF-8 handling
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONLEGACYWINDOWSFSENCODING'] = '0'
    env['PYTHONUTF8'] = '1'

    # Additional UTF-8 encoding for LaTeX and text rendering
    env['LANG'] = 'en_US.UTF-8'
    env['LC_ALL'] = 'en_US.UTF-8'
    env['LC_CTYPE'] = 'en_US.UTF-8'
    env['LC_MESSAGES'] = 'en_US.UTF-8'

    # Font configuration for Pango - ensure system fonts are accessible
    # DO NOT set these to empty strings - it breaks font rendering
    # Instead, ensure Windows font directory is accessible
    if os.name == 'nt':
        # Windows font directory (derived from system root, not hardcoded)
        windir = os.environ.get('SystemRoot', os.environ.get('WINDIR', r'C:\Windows'))
        windows_fonts = os.path.join(windir, 'Fonts')
        if os.path.exists(windows_fonts):
            # Set font config paths for Pango/fontconfig
            env['FONTCONFIG_PATH'] = windows_fonts
            env['FC_CONFIG_DIR'] = windows_fonts
            # Also ensure Pango can find fonts
            env['PANGO_RC_FILE'] = ''  # Let Pango use default
            print(f"[ENV] Set font paths to: {windows_fonts}")

        # Configure Pango for better Windows font rendering
        env['PANGOCAIRO_BACKEND'] = 'fontconfig'  # Use fontconfig for font lookup
        env['PANGO_ALIASING'] = 'enabled'  # Enable font aliasing
        # Force Pango to use specific fonts for ASCII characters
        env['PANGO_DEFAULT_FONT'] = 'Arial'  # Use Arial as fallback (has all ASCII chars)

        # Use custom fontconfig configuration file (fixes "Cannot load default config file" error)
        fontconfig_file = os.path.join(os.path.dirname(__file__), 'fonts.conf')
        if os.path.exists(fontconfig_file):
            env['FONTCONFIG_FILE'] = fontconfig_file
            env['FONTCONFIG_PATH'] = windows_fonts
            print(f"[ENV] Using fontconfig file: {fontconfig_file}")
        else:
            print(f"[ENV] Warning: fontconfig file not found at {fontconfig_file}")

        print(f"[ENV] Configured Pango backend and default font")

    # Ensure fontconfig can build cache (critical for Pango font discovery)
    # Don't set XDG paths to empty - let them use system defaults
    if 'XDG_CACHE_HOME' in env:
        # Keep existing cache location
        pass
    if 'XDG_DATA_HOME' in env:
        # Keep existing data location
        pass

    # Force LaTeX to use UTF-8 encoding (fixes subscript rendering issues)
    env['latex_encoding'] = 'utf-8'
    env['MANIM_TEX_TEMPLATE'] = 'default'  # Use Manim's default UTF-8 template

    # Ensure console uses UTF-8 on Windows
    if os.name == 'nt':
        env['PYTHONLEGACYSTDIO'] = '0'
        # Windows console code page for UTF-8
        env['PYTHONIOENCODING'] = 'utf-8:replace'

    # Force tqdm and other progress bars to display
    # Make Python think it's running in a terminal with TTY
    env['TERM'] = 'xterm-256color'  # Indicate we support ANSI colors
    env['COLORTERM'] = 'truecolor'  # Indicate we support true color
    # Force progress bars to show (tqdm checks these)
    env['FORCE_COLOR'] = '1'
    env['PYTHONUNBUFFERED'] = '1'  # Disable Python output buffering

    # If frozen, ensure exe directory is not interfering
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        print(f"[ENV] Running as frozen EXE from: {exe_dir}")

        # Remove exe directory from PATH if present
        if 'PATH' in env:
            path_parts = env['PATH'].split(os.pathsep)
            original_count = len(path_parts)
            path_parts = [p for p in path_parts if os.path.normpath(p) != os.path.normpath(exe_dir)]
            if len(path_parts) < original_count:
                print(f"[ENV] Removed EXE directory from PATH")
            env['PATH'] = os.pathsep.join(path_parts)

        # Ensure system Python paths are available
        # This helps the venv Python find system DLLs
        windir = os.environ.get('SystemRoot', os.environ.get('WINDIR', r'C:\Windows'))
        system_paths = [
            os.path.join(windir, 'System32'),
            windir,
            os.path.join(windir, 'System32', 'Wbem'),
            os.path.join(windir, 'System32', 'WindowsPowerShell', 'v1.0'),
        ]

        current_paths = env.get('PATH', '').split(os.pathsep)
        for sys_path in system_paths:
            if os.path.exists(sys_path) and sys_path not in current_paths:
                current_paths.append(sys_path)

        env['PATH'] = os.pathsep.join(current_paths)
        print(f"[ENV] PATH configured with {len(current_paths)} entries")

    return env

# Function to check GPU detection dependencies (no auto-install)
def check_gpu_detection_packages():
    """
    Check if PyOpenGL and pygame are installed in the venv for GPU detection.
    These packages are needed by detect_gpu() function.
    Returns: (all_installed: bool, missing_packages: list)
    """
    print("[GPU PACKAGES] Checking GPU detection dependencies...")

    missing_packages = []

    # Check PyOpenGL
    try:
        import OpenGL
        print(f"[GPU PACKAGES] ✓ PyOpenGL version: {OpenGL.__version__}")
    except ImportError:
        print("[GPU PACKAGES] ✗ PyOpenGL not found")
        missing_packages.append('PyOpenGL')

    # Check pygame
    try:
        import pygame
        print(f"[GPU PACKAGES] ✓ pygame version: {pygame.__version__}")
    except ImportError:
        print("[GPU PACKAGES] ✗ pygame not found")
        missing_packages.append('pygame')

    if missing_packages:
        print(f"[GPU PACKAGES] ✗ Missing packages: {', '.join(missing_packages)}")
        print(f"[GPU PACKAGES] GPU detection and acceleration features may not work correctly")
        print(f"[GPU PACKAGES] These packages should have been installed during venv creation")
        return False, missing_packages
    else:
        print("[GPU PACKAGES] ✓ All GPU detection packages are installed")
        return True, []

# Function to detect GPU availability
def detect_gpu():
    """
    Detect if the system has a GPU available for OpenGL rendering
    Prioritizes discrete GPUs (NVIDIA, AMD) over integrated GPUs (Intel)
    Returns: dict with 'available' (bool for OpenGL accel), 'gpu_present' (bool for any GPU), and 'info' (str) keys
    """
    gpu_info = {
        'available': False,       # True only for discrete GPUs (NVIDIA/AMD) - enables GPU acceleration
        'gpu_present': False,     # True for any GPU (including Intel) - for performance monitoring
        'info': 'No GPU detected',
        'vendor': '',
        'renderer': ''
    }

    discrete_gpu_keywords = ['nvidia', 'geforce', 'rtx', 'gtx', 'quadro', 'amd', 'radeon', 'rx']
    integrated_gpu_keywords = ['intel', 'uhd', 'iris', 'hd graphics']

    try:
        # Try to import OpenGL to test GPU availability
        try:
            from OpenGL import GL
            from OpenGL.GL import shaders
            import pygame

            print("[GPU DETECT] Testing OpenGL capability via pygame...")

            # Initialize pygame with OpenGL context
            pygame.init()
            pygame.display.set_mode((1, 1), pygame.OPENGL | pygame.HIDDEN)

            # Get GPU info
            vendor = GL.glGetString(GL.GL_VENDOR)
            renderer = GL.glGetString(GL.GL_RENDERER)
            version = GL.glGetString(GL.GL_VERSION)

            if vendor and renderer:
                vendor_str = vendor.decode('utf-8') if isinstance(vendor, bytes) else str(vendor)
                renderer_str = renderer.decode('utf-8') if isinstance(renderer, bytes) else str(renderer)
                version_str = version.decode('utf-8') if isinstance(version, bytes) else str(version)

                gpu_info['vendor'] = vendor_str
                gpu_info['renderer'] = renderer_str

                print(f"[GPU DETECT] OpenGL Vendor: {vendor_str}")
                print(f"[GPU DETECT] OpenGL Renderer: {renderer_str}")
                print(f"[GPU DETECT] OpenGL Version: {version_str}")

                # Check if it's a discrete GPU (NVIDIA/AMD) - these are preferred for OpenGL
                renderer_lower = renderer_str.lower()
                is_discrete = any(keyword in renderer_lower for keyword in discrete_gpu_keywords)
                is_integrated = any(keyword in renderer_lower for keyword in integrated_gpu_keywords)

                if is_discrete:
                    # Discrete GPU found - excellent for OpenGL
                    gpu_info['available'] = True
                    gpu_info['gpu_present'] = True
                    gpu_info['info'] = f"{vendor_str} - {renderer_str} (Recommended)"
                    print(f"[GPU DETECT] OK Discrete GPU detected (NVIDIA/AMD): {gpu_info['info']}")
                elif is_integrated:
                    # Integrated GPU - can use OpenGL but with reduced performance
                    gpu_info['available'] = True  # Changed from False - allow integrated GPU usage
                    gpu_info['gpu_present'] = True
                    gpu_info['info'] = f"Integrated GPU ({renderer_str}) - Performance may be limited"
                    print(f"[GPU DETECT] WARNING Integrated GPU detected (Intel): {renderer_str} - usable but discrete GPU recommended for better performance")
                else:
                    # Unknown GPU type - allow it
                    gpu_info['available'] = True
                    gpu_info['gpu_present'] = True
                    gpu_info['info'] = f"{vendor_str} - {renderer_str}"
                    print(f"[GPU DETECT] OK GPU detected: {gpu_info['info']}")

            pygame.quit()

        except ImportError:
            # OpenGL not installed, try alternative detection methods
            print("[GPU DETECT] OpenGL not available, trying alternative methods...")

            # Windows: Use wmic to detect GPU
            if os.name == 'nt':
                try:
                    result = subprocess.run(
                        ['wmic', 'path', 'win32_VideoController', 'get', 'name'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )

                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')
                        # First line is header "Name", rest are GPU names
                        gpu_names = [line.strip() for line in lines[1:] if line.strip()]

                        if gpu_names:
                            # Filter out Microsoft Basic Display Adapter (software renderer)
                            hardware_gpus = [gpu for gpu in gpu_names if 'basic display' not in gpu.lower()]

                            if hardware_gpus:
                                # Prioritize discrete GPUs
                                discrete_gpus = [gpu for gpu in hardware_gpus if any(keyword in gpu.lower() for keyword in discrete_gpu_keywords)]

                                if discrete_gpus:
                                    # Found discrete GPU (NVIDIA/AMD)
                                    gpu_info['available'] = True
                                    gpu_info['gpu_present'] = True
                                    gpu_info['renderer'] = discrete_gpus[0]
                                    gpu_info['info'] = discrete_gpus[0]
                                    print(f"[GPU DETECT] OK Discrete GPU found via wmic: {gpu_info['info']}")
                                else:
                                    # Only integrated GPU found
                                    integrated_gpus = [gpu for gpu in hardware_gpus if any(keyword in gpu.lower() for keyword in integrated_gpu_keywords)]
                                    if integrated_gpus:
                                        gpu_info['available'] = True  # Changed from False - allow integrated GPU usage
                                        gpu_info['gpu_present'] = True
                                        gpu_info['renderer'] = integrated_gpus[0]
                                        gpu_info['info'] = f"Integrated GPU ({integrated_gpus[0]}) - Performance may be limited"
                                        print(f"[GPU DETECT] WARNING Integrated GPU detected: {integrated_gpus[0]} - usable but discrete GPU recommended")
                                    else:
                                        # Unknown GPU type - allow it
                                        gpu_info['available'] = True
                                        gpu_info['gpu_present'] = True
                                        gpu_info['renderer'] = hardware_gpus[0]
                                        gpu_info['info'] = hardware_gpus[0]
                                        print(f"[GPU DETECT] GPU found via wmic: {gpu_info['info']}")
                            else:
                                gpu_info['info'] = 'Software renderer only'
                                print("[GPU DETECT] Only software renderer detected")
                        else:
                            gpu_info['info'] = 'No GPU found'
                            print("[GPU DETECT] No GPU detected via wmic")

                except Exception as e:
                    print(f"[GPU DETECT] wmic detection failed: {e}")
                    gpu_info['info'] = 'GPU detection failed'

            # Linux: Try lspci
            elif os.name == 'posix':
                try:
                    result = subprocess.run(
                        ['lspci'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    if result.returncode == 0:
                        # Look for VGA or 3D controller lines
                        for line in result.stdout.split('\n'):
                            if 'VGA' in line or '3D controller' in line:
                                gpu_info['available'] = True
                                gpu_info['info'] = line.split(': ', 1)[1] if ': ' in line else line
                                gpu_info['renderer'] = gpu_info['info']
                                print(f"[GPU DETECT] Found GPU via lspci: {gpu_info['info']}")
                                break

                except Exception as e:
                    print(f"[GPU DETECT] lspci detection failed: {e}")
                    gpu_info['info'] = 'GPU detection failed'

    except Exception as e:
        print(f"[GPU DETECT] Error during GPU detection: {e}")
        gpu_info['info'] = f'Detection error: {str(e)}'

    return gpu_info

# Function to get performance metrics
def get_performance_metrics():
    """
    Get current system performance metrics including CPU, GPU, RAM, and VRAM
    Returns: dict with performance data
    """
    metrics = {
        'cpu_percent': 0.0,
        'cpu_count': 0,
        'ram_used_gb': 0.0,
        'ram_total_gb': 0.0,
        'ram_percent': 0.0,
        'gpu_percent': 0.0,
        'vram_used_gb': 0.0,
        'vram_total_gb': 0.0,
        'vram_percent': 0.0,
        'gpu_name': 'N/A',
        'timestamp': time.time()
    }

    try:
        # CPU and RAM metrics using psutil
        try:
            import psutil

            # CPU usage
            metrics['cpu_percent'] = psutil.cpu_percent(interval=0.1)
            metrics['cpu_count'] = psutil.cpu_count()

            # RAM usage
            mem = psutil.virtual_memory()
            metrics['ram_used_gb'] = mem.used / (1024**3)
            metrics['ram_total_gb'] = mem.total / (1024**3)
            metrics['ram_percent'] = mem.percent

        except ImportError:
            print("[PERF] psutil not available, skipping CPU/RAM metrics")

        # GPU metrics
        try:
            # Try NVIDIA GPU first using nvidia-smi
            if os.name == 'nt':
                nvidia_smi = 'nvidia-smi'
            else:
                nvidia_smi = 'nvidia-smi'

            # Query GPU utilization and memory
            result = subprocess.run(
                [nvidia_smi, '--query-gpu=utilization.gpu,memory.used,memory.total,name', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if lines and lines[0]:
                    # Parse first GPU
                    parts = [p.strip() for p in lines[0].split(',')]
                    if len(parts) >= 4:
                        metrics['gpu_percent'] = float(parts[0])
                        metrics['vram_used_gb'] = float(parts[1]) / 1024  # Convert MB to GB
                        metrics['vram_total_gb'] = float(parts[2]) / 1024  # Convert MB to GB
                        metrics['vram_percent'] = (metrics['vram_used_gb'] / metrics['vram_total_gb'] * 100) if metrics['vram_total_gb'] > 0 else 0
                        metrics['gpu_name'] = parts[3]
                        print(f"[PERF] NVIDIA GPU detected: {metrics['gpu_name']}")

        except FileNotFoundError:
            # nvidia-smi not found, try AMD or Intel
            print("[PERF] nvidia-smi not found, trying alternative GPU detection")

            # Try Windows Performance Counter for GPU (works for Intel, AMD, NVIDIA)
            if os.name == 'nt':
                try:
                    # Use wmic to get GPU info
                    result = subprocess.run(
                        ['wmic', 'path', 'win32_VideoController', 'get', 'name,AdapterRAM'],
                        capture_output=True,
                        text=True,
                        timeout=2,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )

                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')
                        if len(lines) > 1:
                            # Parse GPU name and VRAM
                            for line in lines[1:]:
                                parts = line.strip().split()
                                if parts and 'basic display' not in line.lower():
                                    # Try to extract VRAM (last number in line)
                                    try:
                                        vram_bytes = int(parts[-1])
                                        metrics['vram_total_gb'] = vram_bytes / (1024**3)
                                        metrics['gpu_name'] = ' '.join(parts[:-1])
                                        print(f"[PERF] GPU detected via wmic: {metrics['gpu_name']}")
                                        break
                                    except (ValueError, IndexError):
                                        pass

                except Exception as e:
                    print(f"[PERF] wmic GPU detection failed: {e}")

        except Exception as e:
            print(f"[PERF] GPU metrics collection failed: {e}")

    except Exception as e:
        print(f"[PERF] Error collecting performance metrics: {e}")

    return metrics

# Function to find system Python using 'where python' command
def find_system_python():
    """
    Find Python interpreter using multiple methods:
    1. 'where python' command (PATH-based)
    2. Windows Registry (for Python installed via official installer)
    3. Common installation locations
    """
    print("\n[INFO] Searching for system Python...")

    # Get exe info to avoid using it
    is_frozen = getattr(sys, 'frozen', False)
    if is_frozen:
        exe_path = os.path.abspath(sys.executable).lower()
        exe_dir = os.path.dirname(exe_path).lower()
        print(f"[INFO] Running as exe: {exe_path}")
        print(f"[INFO] Will reject any Python in: {exe_dir}")
    else:
        exe_path = None
        exe_dir = None
        print("[INFO] Running as Python script")

    def is_valid_python(python_path):
        """Check if a Python path is valid and not the exe itself"""
        if not os.path.exists(python_path):
            return False

        abs_path = os.path.abspath(python_path).lower()
        dirname = os.path.dirname(abs_path)
        basename = os.path.basename(abs_path)

        # Skip if it's the exe itself or in exe directory
        if is_frozen:
            if abs_path == exe_path:
                print(f"  [SKIP] This is the exe itself: {python_path}")
                return False
            if dirname == exe_dir:
                print(f"  [SKIP] In exe directory: {python_path}")
                return False

        # Skip if in BASE_DIR
        if dirname == os.path.normpath(BASE_DIR).lower():
            print(f"  [SKIP] In BASE_DIR: {python_path}")
            return False

        # Skip if filename contains "manim" or "studio"
        if 'manim' in basename or 'studio' in basename:
            print(f"  [SKIP] Filename contains 'manim' or 'studio': {python_path}")
            return False

        # Skip paths containing "manim" UNLESS it's our venv
        if 'manim' in abs_path:
            venv_normalized = os.path.normpath(VENV_DIR).lower()
            if not abs_path.startswith(venv_normalized):
                print(f"  [SKIP] Path contains 'manim' (not our venv): {python_path}")
                return False

        # Verify it works
        try:
            env = get_clean_environment()
            test_result = subprocess.run(
                [python_path, '--version'],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            version = (test_result.stdout + test_result.stderr).strip()
            if 'python' in version.lower():
                print(f"  [SUCCESS] Valid Python: {version}")
                return True
            else:
                print(f"  [SKIP] Not Python: {version}")
                return False
        except Exception as e:
            print(f"  [SKIP] Version check failed: {e}")
            return False

    # Method 1: Try 'where python' command (PATH-based)
    print("\n[METHOD 1] Trying 'where python' command...")
    try:
        env = get_clean_environment()
        result = subprocess.run(
            ['where', 'python'],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        if result.returncode == 0:
            pythons = result.stdout.strip().split('\n')
            print(f"[INFO] Found {len(pythons)} Python installation(s) in PATH")

            for python_path in pythons:
                python_path = python_path.strip()
                if not python_path:
                    continue

                print(f"\n[CHECK] {python_path}")
                if is_valid_python(python_path):
                    return python_path
        else:
            print("[INFO] 'where python' found nothing in PATH")
    except Exception as e:
        print(f"[INFO] 'where python' failed: {e}")

    # Method 2: Check Windows Registry (only on Windows)
    if os.name == 'nt':
        print("\n[METHOD 2] Checking Windows Registry...")
        try:
            import winreg

            # Check both HKEY_CURRENT_USER and HKEY_LOCAL_MACHINE
            registry_keys = [
                (winreg.HKEY_CURRENT_USER, r"Software\Python\PythonCore"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Python\PythonCore"),
            ]

            for root_key, subkey_path in registry_keys:
                try:
                    with winreg.OpenKey(root_key, subkey_path) as key:
                        # Enumerate all Python versions
                        i = 0
                        while True:
                            try:
                                version = winreg.EnumKey(key, i)
                                print(f"[INFO] Found Python {version} in registry")

                                # Try to get install path
                                try:
                                    with winreg.OpenKey(key, f"{version}\\InstallPath") as install_key:
                                        install_path = winreg.QueryValue(install_key, None)
                                        python_exe = os.path.join(install_path, 'python.exe')

                                        print(f"[CHECK] {python_exe}")
                                        if is_valid_python(python_exe):
                                            return python_exe
                                except WindowsError:
                                    pass

                                i += 1
                            except WindowsError:
                                break
                except WindowsError:
                    pass
        except ImportError:
            print("[INFO] winreg not available (not on Windows)")
        except Exception as e:
            print(f"[INFO] Registry check failed: {e}")

    # Method 3: Check common installation locations
    print("\n[METHOD 3] Checking common installation paths...")
    common_paths = []

    if os.name == 'nt':
        # Windows common paths
        username = os.getenv('USERNAME', '')
        appdata = os.getenv('APPDATA', '')
        localappdata = os.getenv('LOCALAPPDATA', '')
        programfiles = os.getenv('ProgramFiles', 'C:\\Program Files')

        # Python.org installer locations
        sysdrive = os.environ.get('SystemDrive', 'C:')
        for version in ['312', '311', '310', '39', '38', '37']:
            common_paths.extend([
                os.path.join(sysdrive + os.sep, f'Python{version}', 'python.exe'),
                os.path.join(localappdata, 'Programs', 'Python', f'Python{version}', 'python.exe'),
            ])

        # Microsoft Store Python
        if localappdata:
            common_paths.append(f"{localappdata}\\Microsoft\\WindowsApps\\python.exe")

    for python_path in common_paths:
        if python_path and os.path.exists(python_path):
            print(f"[CHECK] {python_path}")
            if is_valid_python(python_path):
                return python_path

    # No Python found
    print("\n" + "=" * 60)
    print("[ERROR] Could not find Python on this system!")
    print("=" * 60)
    print("\nPlease ensure Python is installed:")
    print("1. Download Python from https://www.python.org/downloads/")
    print("2. Run the installer")
    print("3. IMPORTANT: Check 'Add Python to PATH' during installation")
    print("4. Restart this application after installing Python")
    print("=" * 60)
    return None

# Function to setup virtual environment with manim
def setup_venv(window=None):
    """
    Setup virtual environment in .manim_studio/venvs/manim_studio_default with manim installed.
    Returns path to venv Python executable.
    """
    import glob

    # Use the constant VENV_DIR for consistency
    venv_dir = VENV_DIR

    # Determine venv python path
    if os.name == 'nt':  # Windows
        venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe')
    else:  # Linux/Mac
        venv_python = os.path.join(venv_dir, 'bin', 'python')

    print(f"[INFO] Virtual environment path: {venv_dir}")
    print(f"[INFO] Virtual environment Python: {venv_python}")

    # If venv exists and has Python, use it
    if os.path.exists(venv_python):
        print(f"[INFO] Using existing venv at: {venv_dir}")
        return venv_python

    # Need to create venv - find system Python first
    print("[INFO] Virtual environment not found, creating one...")

    system_python = find_system_python()
    if not system_python:
        error_title = "Python Not Found!"
        error_msgs = [
            "Could not find Python on this system.",
            "",
            "To fix this:",
            "1. Download Python from https://python.org/downloads/",
            "2. Run the installer",
            "3. IMPORTANT: Check 'Add Python to PATH' during installation",
            "4. Restart this application",
            "",
            "If Python is already installed, make sure it's added to your system PATH."
        ]

        print(f"[ERROR] {error_title}")
        for msg in error_msgs:
            print(f"        {msg}")

        if window:
            # Show error in console
            for msg in error_msgs:
                if msg:  # Skip empty lines
                    safe_msg = msg.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
                    window.evaluate_js(f'if(window.appendConsole){{window.appendConsole("{safe_msg}", "error")}}')

            # Also show toast notification
            window.evaluate_js(f'if(window.toast){{window.toast("Python not found! Check console for details.", "error")}}')

        return None

    # CRITICAL SAFETY CHECK: Ensure we're NEVER using the exe itself
    if getattr(sys, 'frozen', False):
        exe_path = os.path.abspath(sys.executable)
        system_python_abs = os.path.abspath(system_python)
        if system_python_abs == exe_path:
            error_msg = f"CRITICAL ERROR: Attempted to use exe as Python! {system_python_abs}"
            print(f"[ERROR] {error_msg}")
            if window:
                window.evaluate_js(f'if(window.appendConsole){{window.appendConsole("{error_msg}", "error")}}')
            return None
        if 'manim' in os.path.basename(system_python_abs).lower():
            error_msg = f"CRITICAL ERROR: Python filename contains 'manim': {system_python_abs}"
            print(f"[ERROR] {error_msg}")
            if window:
                window.evaluate_js(f'if(window.appendConsole){{window.appendConsole("{error_msg}", "error")}}')
            return None

    print(f"[INFO] Found system Python: {system_python}")

    # Create venv
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    def log_output(msg, level='info'):
        """Log to console and UI"""
        print(f"[{level.upper()}] {msg}")
        if window:
            safe_msg = msg.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
            window.evaluate_js(f'if(window.appendConsole){{window.appendConsole("{safe_msg}", "{level}")}}')

    try:
        log_output("=" * 60)
        log_output("STARTING VIRTUAL ENVIRONMENT CREATION")
        log_output("=" * 60)
        log_output("")
        log_output("Step 1: Creating virtual environment...")
        log_output("")

        # Create venv using clean environment with streaming output
        venv_process = subprocess.Popen(
            [system_python, '-m', 'venv', venv_dir, '--without-pip'],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',  # Force UTF-8 encoding
            errors='replace',  # Replace invalid characters instead of crashing
            bufsize=1,
            universal_newlines=True,
            env=get_clean_environment(),  # Use clean environment
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        # Stream output
        for line in iter(venv_process.stdout.readline, ''):
            if line:
                line = line.rstrip()
                log_output(line)

        venv_process.wait()

        if venv_process.returncode != 0:
            log_output("")
            log_output("Failed to create virtual environment!", "error")
            log_output("=" * 60)
            return None

        log_output("")
        log_output("✓ Virtual environment created successfully!")
        log_output("")

        # Now install pip
        log_output("Step 2: Installing pip in virtual environment...")
        log_output("")

        venv_python_exe = os.path.join(venv_dir, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(venv_dir, 'bin', 'python')

        pip_install_process = subprocess.Popen(
            [venv_python_exe, '-m', 'ensurepip'],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',  # Force UTF-8 encoding
            errors='replace',  # Replace invalid characters instead of crashing
            bufsize=1,
            universal_newlines=True,
            env=get_clean_environment(),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        # Stream output
        for line in iter(pip_install_process.stdout.readline, ''):
            if line:
                line = line.rstrip()
                log_output(line)

        pip_install_process.wait()

        if pip_install_process.returncode != 0:
            log_output("")
            log_output("Failed to install pip!", "error")
            log_output("Trying alternative method...")
            log_output("")

        log_output("")
        log_output("✓ Pip installed successfully!")
        log_output("")

        # Install manim and manim-fonts
        log_output("Step 3: Installing Manim and fonts (this may take a few minutes)...")
        log_output("")

        # Use python -m pip instead of pip.exe directly for better compatibility
        install_process = subprocess.Popen(
            [venv_python_exe, '-m', 'pip', 'install', 'manim', 'manim-fonts', 'basedpyright'],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',  # Force UTF-8 encoding
            errors='replace',  # Replace invalid characters instead of crashing
            bufsize=1,
            universal_newlines=True,
            env=get_clean_environment(),  # Use clean environment
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        # Stream output to terminal
        for line in iter(install_process.stdout.readline, ''):
            if line:
                line = line.rstrip()
                log_output(line)

        install_process.wait()

        log_output("")
        if install_process.returncode == 0:
            log_output("✓ All packages installed successfully!", "success")
            log_output("")
            log_output("=" * 60)
            log_output("VIRTUAL ENVIRONMENT SETUP FINISHED!")
            log_output("=" * 60)
            log_output("")
            log_output("Summary:")
            log_output(f"  • Python: {system_python}")
            log_output(f"  • Venv location: {venv_dir}")
            log_output(f"  • Manim: Installed")
            log_output(f"  • Manim Fonts: Installed")
            log_output("")
            log_output("✓ Ready to render animations!")
            log_output("=" * 60)
            return venv_python
        else:
            log_output("✗ Failed to install packages", "error")
            log_output("=" * 60)
            return None

    except Exception as e:
        log_output(f"Error setting up environment: {e}", "error")
        return None

# Function to get the Python interpreter
def get_python_executable(window=None):
    """
    Get the Python executable path.
    Always uses venv in .manim_studio, creating it if needed.
    NEVER RETURNS THE EXE ITSELF!
    """
    # If not frozen (running as script), check for venv
    if not getattr(sys, 'frozen', False):
        # Still use venv if available for consistency
        venv_python = setup_venv(window)
        if venv_python:
            return venv_python
        # Fallback to current Python
        return sys.executable

    # If frozen (compiled exe), MUST use venv - NEVER sys.executable!
    print("[INFO] Running as compiled exe - NEVER using exe itself for Python")
    print(f"[INFO] Exe path (WILL NOT USE): {sys.executable}")

    venv_python = setup_venv(window)

    if venv_python:
        print(f"[SUCCESS] Using venv Python: {venv_python}")
        return venv_python

    # Fallback - try to use 'python' from PATH as last resort
    # But NEVER return sys.executable when frozen!
    print("[ERROR] Could not setup Python environment!")
    print("[ERROR] Will try 'python' command as fallback (NOT the exe)")
    return 'python'

# Function to verify venv setup
def verify_venv_setup(window=None):
    """
    Verify that venv exists in .manim_studio and has manim installed.
    This forces a check at startup and logs all findings.
    """
    def log_msg(msg, level='info'):
        """Log to console and optionally to UI"""
        print(f"[{level.upper()}] {msg}")
        if window:
            safe_msg = msg.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
            window.evaluate_js(f'if(window.appendConsole){{window.appendConsole("{safe_msg}", "{level}")}}')

    log_msg("=" * 60)
    log_msg("VIRTUAL ENVIRONMENT VERIFICATION")
    log_msg("=" * 60)

    # Check venv directory
    log_msg(f"Checking venv location: {VENV_DIR}")

    if os.name == 'nt':  # Windows
        venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
        venv_pip = os.path.join(VENV_DIR, 'Scripts', 'pip.exe')
    else:  # Linux/Mac
        venv_python = os.path.join(VENV_DIR, 'bin', 'python')
        venv_pip = os.path.join(VENV_DIR, 'bin', 'pip')

    # Check if venv exists
    if not os.path.exists(VENV_DIR):
        log_msg("Virtual environment NOT found", "warning")
        log_msg("Will create on first render/preview", "info")
        log_msg("=" * 60)
        return False

    log_msg("Virtual environment directory EXISTS", "success")

    # Check if Python executable exists
    if not os.path.exists(venv_python):
        log_msg(f"Python executable NOT found at: {venv_python}", "error")
        log_msg("Venv may be corrupted - will recreate on next render", "warning")
        log_msg("=" * 60)
        return False

    log_msg(f"Python executable found: {venv_python}", "success")

    # Check if manim is installed
    try:
        log_msg("Checking if manim is installed in venv...")
        result = subprocess.run(
            [venv_pip, 'show', 'manim'],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            env=get_clean_environment(),  # Use clean environment
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

        if result.returncode == 0:
            # Parse manim version from output
            version_line = [line for line in result.stdout.split('\n') if line.startswith('Version:')]
            version = version_line[0].replace('Version:', '').strip() if version_line else 'unknown'
            log_msg(f"Manim is installed (version {version})", "success")
            log_msg("=" * 60)
            log_msg("VENV READY TO USE")
            log_msg("=" * 60)
            return True
        else:
            log_msg("Manim NOT installed in venv", "warning")
            log_msg("Will install on first render/preview", "info")
            log_msg("=" * 60)
            return False

    except Exception as e:
        log_msg(f"Error checking manim installation: {e}", "error")
        log_msg("=" * 60)
        return False

# Get the Python executable to use for manim
# Note: Will be re-initialized when window is available
PYTHON_EXE = None

# Application state
app_state = {
    'current_code': '',
    'current_file_path': None,
    'is_rendering': False,
    'is_previewing': False,
    'render_process': None,
    'preview_process': None,
    'output_dir': MEDIA_DIR,
    'window': None,
    'generated_files': [],  # Track files generated this session for cleanup
    'preview_files_to_cleanup': set(),  # Track preview MP4 files copied to assets (kept after app closes)
    'terminal_process': None,  # Persistent cmd.exe session
    'terminal_thread': None,  # Thread for reading terminal output
    'terminal_output_buffer': [],  # Buffer for terminal output (gets cleared when sent to frontend)
    'terminal_error_buffer': [],  # Persistent buffer for error checking (keeps last 1000 lines)
    'dependency_cache': None,  # Cached dependency check results (python/latex/etc)
    'dependency_last_checked': 0.0,  # Unix timestamp of last completed check
    'dependency_check_in_progress': False,  # Prevent overlapping checks
    'dependency_check_error': None,  # Last dependency check error
    'dependency_check_lock': threading.Lock(),  # Synchronize dependency checker state
    'dependency_stop_event': threading.Event(),  # Stop signal for background checker
    'dependency_checker_thread': None,  # Background checker thread handle
    'settings': {
        'quality': '720p',
        'format': 'MP4 Video',
        'fps': 30,
        'preview_quality': 'Medium',
        'theme': 'Dark+',
        'font_size': 14,
        'intellisense_enabled': True
    },
    'lsp_process': None,    # basedpyright-langserver subprocess
    'lsp_running': False,   # LSP stdout reader thread active flag
}

# Quality presets
QUALITY_PRESETS = {
    "120p": ("-ql", 214, 120),      # Ultra low quality (214x120 15fps)
    "240p": ("-ql", 426, 240),      # Very low quality (426x240 15fps)
    "480p": ("-ql", 854, 480),      # Low quality (854x480 15fps)
    "720p": ("-qm", 1280, 720),     # Medium quality (1280x720 30fps)
    "1080p": ("-qh", 1920, 1080),   # High quality (1920x1080 60fps)
    "1440p": ("-qp", 2560, 1440),   # 1440p quality (2560x1440 60fps)
    "4K": ("-qk", 3840, 2160),      # 4K quality (3840x2160 60fps)
    "8K": ("-qk", 7680, 4320),      # 8K quality (7680x4320 60fps) - uses -qk flag
}

def safe_evaluate_js(window, js_code):
    """
    Safely evaluate JavaScript on a webview window.
    Returns True if successful, False if window is closed/disposed.
    """
    if not window:
        return False

    try:
        window.evaluate_js(js_code)
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if 'disposed' in error_msg or 'webview2' in error_msg:
            print(f"[WINDOW] Window has been closed/disposed - skipping JS evaluation")
            return False
        else:
            print(f"[WINDOW] Error evaluating JS: {e}")
            raise  # Re-raise if it's not a disposal error

def sanitize_code_for_latex(code):
    """
    Remove invisible Unicode characters that cause LaTeX rendering issues.

    These characters (like U+2068 FIRST STRONG ISOLATE) can corrupt LaTeX subscripts
    and cause them to display as garbled text showing Unicode code points.

    Removes:
    - U+200B-U+200D: Zero-width spaces
    - U+200E-U+200F: Text direction marks
    - U+202A-U+202E: Bidirectional formatting
    - U+202F: Narrow no-break space
    - U+2060-U+206F: Invisible operators, FSI, PDI, etc. (includes U+2068!)
    - U+FEFF: Zero-width no-break space (BOM)
    - U+00A0: No-break space (convert to regular space)
    - U+00AD: Soft hyphen
    """
    import re

    # First, scan for and log any problematic characters
    problematic_chars = []
    for i, char in enumerate(code):
        code_point = ord(char)
        if (0x200B <= code_point <= 0x200D or  # Zero-width spaces
            code_point in (0x200E, 0x200F) or   # LTR/RTL marks
            0x202A <= code_point <= 0x202E or   # Bidi formatting
            code_point == 0x202F or              # Narrow no-break space
            0x2060 <= code_point <= 0x206F or   # Invisible operators including U+2068
            code_point == 0xFEFF or              # BOM
            code_point == 0x00AD):               # Soft hyphen
            # Find context (20 chars before and after)
            start = max(0, i - 20)
            end = min(len(code), i + 20)
            context = code[start:end]
            context_display = context.replace('\n', '\\n').replace('\r', '\\r')
            problematic_chars.append({
                'char': char,
                'code_point': f'U+{code_point:04X}',
                'position': i,
                'context': context_display
            })

    if problematic_chars:
        print(f"[LATEX SANITIZE] ⚠️ Found {len(problematic_chars)} invisible Unicode characters:")
        for item in problematic_chars[:10]:  # Show first 10
            print(f"  - {item['code_point']} at position {item['position']}")
            print(f"    Context: ...{item['context']}...")

    # Pattern for all problematic invisible characters
    invisible_chars_pattern = re.compile(
        r'[\u200B-\u200D'  # Zero-width spaces
        r'\u200E\u200F'     # Left-to-right/right-to-left marks
        r'\u202A-\u202E'    # Bidirectional formatting
        r'\u202F'           # Narrow no-break space
        r'\u2060-\u206F'    # Invisible operators, FSI (U+2068), PDI, etc.
        r'\uFEFF'           # Zero-width no-break space (BOM)
        r'\u00AD]'          # Soft hyphen
    )

    # Remove invisible characters
    cleaned = invisible_chars_pattern.sub('', code)

    # Convert no-break spaces to regular spaces
    cleaned = cleaned.replace('\u00A0', ' ')

    # Count how many characters were removed for logging
    removed_count = len(code) - len(cleaned)
    if removed_count > 0:
        print(f"[LATEX SANITIZE] ✅ Removed {removed_count} invisible Unicode characters")
    else:
        print(f"[LATEX SANITIZE] No invisible characters found in code")

    return cleaned

def create_manim_config(script_dir):
    """Create manim.cfg in the script directory for proper asset path configuration"""
    config_path = os.path.join(script_dir, 'manim.cfg')

    # Use Manim's default template - don't override with custom template
    # The default template already has proper UTF-8 support
    config_content = f"""[CLI]
# Manim Studio Configuration
assets_dir = {ASSETS_DIR}
media_dir = {MEDIA_DIR}
# Unlimited cache - never delete partial movie files
max_files_cached = -1
# Ensure UTF-8 input encoding for LaTeX (critical for subscripts!)
input_file_encoding = utf-8
"""
    try:
        with open(config_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(config_content)
        print(f"[CONFIG] Created manim.cfg at: {config_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to create manim.cfg: {e}")
        return False

def clear_preview_folder():
    """Clear all files in the preview folder before each preview"""
    import shutil
    try:
        if os.path.exists(PREVIEW_DIR):
            # Remove all contents
            for item in os.listdir(PREVIEW_DIR):
                item_path = os.path.join(PREVIEW_DIR, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    print(f"[WARNING] Failed to delete {item_path}: {e}")
            print(f"[OK] Cleared preview folder: {PREVIEW_DIR}")
        else:
            # Create if doesn't exist
            os.makedirs(PREVIEW_DIR, exist_ok=True)
            print(f"[OK] Created preview folder: {PREVIEW_DIR}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to clear preview folder: {e}")
        return False

def clear_render_folder():
    """Clear all files in the render folder before each render"""
    import shutil
    try:
        if os.path.exists(RENDER_DIR):
            # Remove all contents
            for item in os.listdir(RENDER_DIR):
                item_path = os.path.join(RENDER_DIR, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    print(f"[WARNING] Failed to delete {item_path}: {e}")
            print(f"[OK] Cleared render folder: {RENDER_DIR}")
        else:
            # Create if doesn't exist
            os.makedirs(RENDER_DIR, exist_ok=True)
            print(f"[OK] Created render folder: {RENDER_DIR}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to clear render folder: {e}")
        return False

def load_settings():
    """Load settings from file"""
    settings_file = os.path.join(USER_DATA_DIR, 'settings.json')
    try:
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                saved = json.load(f)
                app_state['settings'].update(saved)
    except Exception as e:
        print(f"Error loading settings: {e}")

def save_settings():
    """Save settings to file"""
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    settings_file = os.path.join(USER_DATA_DIR, 'settings.json')
    try:
        with open(settings_file, 'w') as f:
            json.dump(app_state['settings'], f, indent=2)
    except Exception as e:
        print(f"Error saving settings: {e}")

def kill_process_tree(pid):
    """
    Kill a process AND all its children (ffmpeg, LaTeX, etc.).
    On Windows, taskkill /F /T kills the full tree.
    On Unix, SIGKILL is sent to the entire process group.
    """
    if os.name == 'nt':
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            print(f"[STOP] taskkill /F /T /PID {pid} completed")
        except Exception as e:
            print(f"[STOP] taskkill failed for PID {pid}: {e}")
    else:
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
            print(f"[STOP] Killed process group for PID {pid}")
        except Exception as e:
            print(f"[STOP] killpg failed: {e}")
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass


def check_terminal_output_for_errors():
    """
    Check terminal output buffer for error patterns that indicate manim/python failure.
    Returns (has_error, error_message) tuple.
    """
    # Use the persistent error buffer instead of the display buffer
    # The error buffer doesn't get cleared and keeps accumulating output
    output = ''.join(app_state['terminal_error_buffer'])

    # Debug: only print buffer size occasionally (reduced spam)
    # Uncomment for debugging:
    # print(f"[ERROR CHECK] Error buffer has {len(app_state['terminal_error_buffer'])} items, {len(output)} chars total")

    # Common error patterns - check in order of specificity
    error_patterns = [
        'SyntaxError:',
        'NameError:',
        'ImportError:',
        'ModuleNotFoundError:',
        'AttributeError:',
        'TypeError:',
        'ValueError:',
        'IndentationError:',
        'Traceback (most recent call last)',
        'manim.utils.module_ops.SceneNotFound',
        'FileNotFoundError:',
        'Exception:'
    ]

    for pattern in error_patterns:
        if pattern in output:
            print(f"[ERROR CHECK] Found error pattern: {pattern}")
            # Extract error message from the output
            lines = output.split('\n')
            error_msg = None
            for i, line in enumerate(lines):
                if pattern in line:
                    # Get this line and the next few lines for context
                    error_msg = line.strip()
                    # Get up to 2 more lines for context
                    for j in range(1, min(3, len(lines) - i)):
                        next_line = lines[i + j].strip()
                        if next_line:
                            error_msg += ' ' + next_line
                    break

            if not error_msg:
                error_msg = f"Error detected: {pattern}"

            print(f"[ERROR CHECK] Error message extracted: {error_msg[:100]}")
            return (True, error_msg[:200])  # Limit error message length

    return (False, None)


def extract_scene_name(code):
    """
    Extract the first Scene subclass name from code using regex only.
    Avoids executing user code in the main process (which is unsafe and
    fails anyway since Manim lives in the venv, not the host Python).
    Handles all standard Manim scene types: Scene, ThreeDScene,
    MovingCameraScene, ZoomedScene, VectorScene, etc.
    """
    # Priority 1: class that inherits from anything containing 'Scene'
    # Covers Scene, ThreeDScene, MovingCameraScene, ZoomedScene, etc.
    match = re.search(r'class\s+(\w+)\s*\([^)]*Scene[^)]*\):', code)
    if match:
        return match.group(1)

    # Priority 2: first class definition in the file as a last resort
    match = re.search(r'class\s+(\w+)\s*\([^)]*\):', code)
    return match.group(1) if match else None

class ManimAPI:
    """
    API class that exposes Python functions to JavaScript
    All methods in this class can be called from JS using: pywebview.api.method_name()
    """

    def __init__(self):
        """Initialize the API"""
        # AI/LLM feature removed

        # Start terminal automatically
        print("[API] Auto-starting persistent terminal...")
        try:
            self.start_persistent_terminal()
        except Exception as e:
            print(f"[API ERROR] Failed to auto-start terminal: {e}")

        # Start dependency checker in background (non-blocking startup)
        print("[API] Auto-starting dependency checker...")
        try:
            self.start_dependency_checker_background()
        except Exception as e:
            print(f"[API ERROR] Failed to start dependency checker: {e}")

    def get_code(self):
        """Get current code"""
        return {'code': app_state['current_code']}

    def set_code(self, code):
        """Set current code"""
        app_state['current_code'] = code
        return {'status': 'success'}

    def new_file(self):
        """Create a new file"""
        app_state['current_code'] = """from manim import *

class MyScene(Scene):
    def construct(self):
        # Your animation code here
        text = Text("Hello, Manim!")
        self.play(Write(text))
        self.wait()
"""
        app_state['current_file_path'] = None
        return {'status': 'success', 'code': app_state['current_code']}

    def save_screenshot(self, base64_data, suggested_name):
        """Save a screenshot from base64 PNG data using a native Save As dialog."""
        try:
            import base64

            print(f"[SCREENSHOT] Showing save dialog for: {suggested_name}")

            # Show native Save As dialog
            result = app_state['window'].create_file_dialog(
                dialog_type=webview.FileDialog.SAVE,
                save_filename=suggested_name,
                file_types=('PNG Image (*.png)', 'JPEG Image (*.jpg)', 'All Files (*.*)')
            )

            if not result:
                print("[SCREENSHOT] User cancelled save dialog")
                return {'status': 'cancelled'}

            # Extract path from result
            if isinstance(result, (list, tuple)) and len(result) > 0:
                save_path = result[0]
            else:
                save_path = result

            # Decode base64 and write to file
            image_data = base64.b64decode(base64_data)
            with open(save_path, 'wb') as f:
                f.write(image_data)

            print(f"[SCREENSHOT] Saved to: {save_path} ({len(image_data)} bytes)")
            return {
                'status': 'success',
                'path': save_path,
                'filename': os.path.basename(save_path),
                'size': len(image_data)
            }
        except Exception as e:
            print(f"[SCREENSHOT] Error: {e}")
            return {'status': 'error', 'message': str(e)}

    def open_file_by_path(self, file_path):
        """Open a file by its absolute path (for drag-drop support)"""
        try:
            if not os.path.exists(file_path):
                return {'status': 'error', 'message': 'File not found'}
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in ('.py', '.txt', '.pyw'):
                return {'status': 'error', 'message': f'Unsupported file type: {ext}'}
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            app_state['current_code'] = content
            app_state['current_file_path'] = file_path
            return {'status': 'success', 'code': content, 'path': file_path, 'filename': os.path.basename(file_path)}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def open_file_dialog(self):
        """Open file dialog and return file path"""
        result = app_state['window'].create_file_dialog(
            FileDialog.OPEN,
            allow_multiple=False,
            file_types=('Python Files (*.py)', 'All Files (*.*)')
        )

        if result and len(result) > 0:
            file_path = result[0]
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                app_state['current_code'] = content
                app_state['current_file_path'] = file_path
                return {'status': 'success', 'code': content, 'path': file_path, 'filename': os.path.basename(file_path)}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}

        return {'status': 'cancelled'}

    def save_file_dialog(self, code):
        """Save file dialog for code files"""
        print("[SAVE] save_file_dialog() called - showing file dialog")
        result = app_state['window'].create_file_dialog(
            dialog_type=webview.FileDialog.SAVE,
            save_filename='scene.py',
            file_types=('Python Files (*.py)', 'All Files (*.*)')
        )
        print(f"[SAVE] Dialog result: {result}")
        print(f"[SAVE] Dialog result type: {type(result)}")

        if result:
            # create_file_dialog returns a tuple/list even for SAVE, extract first element
            if isinstance(result, (list, tuple)) and len(result) > 0:
                file_path = result[0]
            else:
                file_path = result

            print(f"[SAVE] Extracted file_path: {file_path}")

            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(code)

                app_state['current_code'] = code
                app_state['current_file_path'] = file_path
                print(f"[SAVE] Successfully saved to: {file_path}")
                return {'status': 'success', 'path': file_path, 'filename': os.path.basename(file_path)}
            except Exception as e:
                print(f"[SAVE] Error saving file: {e}")
                return {'status': 'error', 'message': str(e)}

        print("[SAVE] Dialog was cancelled")
        return {'status': 'cancelled'}

    def save_file(self, code, file_path=None):
        """Save the current file"""
        print(f"[SAVE] save_file() called with file_path={file_path}")
        if not file_path:
            file_path = app_state.get('current_file_path')
            print(f"[SAVE] No file_path provided, got from app_state: {file_path}")

        if not file_path:
            print("[SAVE] No file_path available, calling save_file_dialog()")
            return self.save_file_dialog(code)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)

            app_state['current_code'] = code
            app_state['current_file_path'] = file_path
            return {'status': 'success', 'path': file_path, 'filename': os.path.basename(file_path)}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def autosave_code(self, code):
        """Auto-save code to temporary location"""
        try:
            import json
            from datetime import datetime

            # Create autosave directory
            os.makedirs(AUTOSAVE_DIR, exist_ok=True)

            # Generate timestamp-based filename (microseconds prevent same-second collisions)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            autosave_file = os.path.join(AUTOSAVE_DIR, f'autosave_{timestamp}.py')

            # Save code
            with open(autosave_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # Save metadata
            metadata = {
                'timestamp': timestamp,
                'file_path': app_state.get('current_file_path', ''),
                'autosave_file': autosave_file
            }

            metadata_file = os.path.join(AUTOSAVE_DIR, f'autosave_{timestamp}.json')
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)

            # Keep only last 5 autosaves
            self.cleanup_old_autosaves()

            print(f"[AUTOSAVE] Saved to {autosave_file}")

            return {'status': 'success', 'file': autosave_file, 'timestamp': timestamp}

        except Exception as e:
            print(f"[AUTOSAVE ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def cleanup_old_autosaves(self):
        """Keep only the last 5 autosaves"""
        try:
            # Get all autosave files
            autosave_files = []
            for filename in os.listdir(AUTOSAVE_DIR):
                if filename.startswith('autosave_') and filename.endswith('.py'):
                    filepath = os.path.join(AUTOSAVE_DIR, filename)
                    autosave_files.append((filepath, os.path.getmtime(filepath)))

            # Sort by modification time (newest first)
            autosave_files.sort(key=lambda x: x[1], reverse=True)

            # Delete old autosaves (keep only 5 newest)
            for filepath, _ in autosave_files[5:]:
                try:
                    os.remove(filepath)
                    # Also remove corresponding metadata file
                    metadata_file = filepath.replace('.py', '.json')
                    if os.path.exists(metadata_file):
                        os.remove(metadata_file)
                    print(f"[AUTOSAVE] Deleted old autosave: {filepath}")
                except Exception as e:
                    print(f"[AUTOSAVE] Error deleting {filepath}: {e}")

        except Exception as e:
            print(f"[AUTOSAVE CLEANUP ERROR] {e}")

    def get_autosave_files(self):
        """Get list of available autosave files"""
        try:
            import json

            if not os.path.exists(AUTOSAVE_DIR):
                return {'status': 'success', 'files': []}

            autosaves = []
            for filename in os.listdir(AUTOSAVE_DIR):
                if filename.startswith('autosave_') and filename.endswith('.json'):
                    metadata_file = os.path.join(AUTOSAVE_DIR, filename)
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)

                        # Check if corresponding .py file exists
                        py_file = metadata.get('autosave_file', '')
                        if os.path.exists(py_file):
                            autosaves.append(metadata)
                    except Exception as e:
                        print(f"[AUTOSAVE] Error reading metadata {filename}: {e}")

            # Sort by timestamp (newest first)
            autosaves.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

            return {'status': 'success', 'files': autosaves}

        except Exception as e:
            print(f"[AUTOSAVE ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def load_autosave(self, autosave_file):
        """Load code from an autosave file"""
        try:
            if not os.path.exists(autosave_file):
                return {'status': 'error', 'message': 'Autosave file not found'}

            with open(autosave_file, 'r', encoding='utf-8') as f:
                code = f.read()

            print(f"[AUTOSAVE] Loaded from {autosave_file}")
            return {'status': 'success', 'code': code}

        except Exception as e:
            print(f"[AUTOSAVE ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def delete_autosave(self, autosave_file):
        """Delete a specific autosave file"""
        try:
            if os.path.exists(autosave_file):
                os.remove(autosave_file)
                # Also remove metadata
                metadata_file = autosave_file.replace('.py', '.json')
                if os.path.exists(metadata_file):
                    os.remove(metadata_file)
                print(f"[AUTOSAVE] Deleted {autosave_file}")
                return {'status': 'success'}
            else:
                return {'status': 'error', 'message': 'File not found'}
        except Exception as e:
            print(f"[AUTOSAVE ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def delete_all_autosaves(self):
        """Delete all autosave files"""
        try:
            deleted_count = 0
            if os.path.exists(AUTOSAVE_DIR):
                for filename in os.listdir(AUTOSAVE_DIR):
                    filepath = os.path.join(AUTOSAVE_DIR, filename)
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                        deleted_count += 1
            print(f"[AUTOSAVE] Deleted {deleted_count} files")
            return {'status': 'success', 'deleted_count': deleted_count}
        except Exception as e:
            print(f"[AUTOSAVE ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def open_autosave_folder(self):
        """Open the autosave folder in file explorer"""
        try:
            if not os.path.exists(AUTOSAVE_DIR):
                os.makedirs(AUTOSAVE_DIR, exist_ok=True)

            if os.name == 'nt':
                os.startfile(AUTOSAVE_DIR)
            elif os.name == 'posix':
                subprocess.run(['xdg-open', AUTOSAVE_DIR])

            return {'status': 'success', 'path': AUTOSAVE_DIR}
        except Exception as e:
            print(f"[AUTOSAVE ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    # ── Render History ─────────────────────────────────────────────────────

    def _render_history_file(self):
        """Path to the render history JSON file."""
        return os.path.join(USER_DATA_DIR, 'render_history.json')

    def get_render_history(self):
        """Return the list of render history entries (newest first)."""
        try:
            path = self._render_history_file()
            if not os.path.exists(path):
                return {'status': 'success', 'entries': []}
            with open(path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
            # Mark entries whose output file no longer exists
            for entry in entries:
                entry['file_exists'] = os.path.exists(entry.get('output_path', ''))
            return {'status': 'success', 'entries': entries}
        except Exception as e:
            print(f"[HISTORY ERROR] {e}")
            return {'status': 'error', 'message': str(e), 'entries': []}

    def add_render_history(self, entry):
        """Append a render history entry and persist to disk.
        entry should be a dict with keys like:
            scene_name, quality, fps, format, mode (render|preview),
            output_path, timestamp, duration_seconds
        """
        try:
            path = self._render_history_file()
            entries = []
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    entries = json.load(f)

            # Deduplicate: remove older entries with the same output_path
            # since the file gets overwritten and only the latest content exists
            new_path = entry.get('output_path', '')
            if new_path:
                entries = [e for e in entries if e.get('output_path') != new_path]

            entries.insert(0, entry)
            # Keep at most 100 entries
            entries = entries[:100]

            os.makedirs(USER_DATA_DIR, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=2)

            print(f"[HISTORY] Added entry: {entry.get('scene_name', '?')} ({entry.get('mode', '?')})")
            return {'status': 'success'}
        except Exception as e:
            print(f"[HISTORY ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def clear_render_history(self):
        """Delete all render history entries."""
        try:
            path = self._render_history_file()
            if os.path.exists(path):
                os.remove(path)
            return {'status': 'success'}
        except Exception as e:
            print(f"[HISTORY ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def delete_render_history_entry(self, timestamp):
        """Delete a single render history entry by its timestamp."""
        try:
            path = self._render_history_file()
            if not os.path.exists(path):
                return {'status': 'success'}
            with open(path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
            entries = [e for e in entries if e.get('timestamp') != timestamp]
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=2)
            return {'status': 'success'}
        except Exception as e:
            print(f"[HISTORY ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def clear_manim_cache(self):
        """Clear Manim's cache directories (partial_movie_files and Tex)"""
        try:
            deleted_count = 0
            deleted_size = 0

            # Clear partial_movie_files from media directory
            partial_movies_dir = os.path.join(MEDIA_DIR, 'videos')
            if os.path.exists(partial_movies_dir):
                for root, dirs, files in os.walk(partial_movies_dir):
                    if 'partial_movie_files' in root:
                        for file in files:
                            filepath = os.path.join(root, file)
                            try:
                                file_size = os.path.getsize(filepath)
                                os.remove(filepath)
                                deleted_count += 1
                                deleted_size += file_size
                            except OSError:
                                pass

            # Clear Tex cache
            tex_dir = os.path.join(MEDIA_DIR, 'Tex')
            if os.path.exists(tex_dir):
                for root, dirs, files in os.walk(tex_dir):
                    for file in files:
                        filepath = os.path.join(root, file)
                        try:
                            file_size = os.path.getsize(filepath)
                            os.remove(filepath)
                            deleted_count += 1
                            deleted_size += file_size
                        except OSError:
                            pass

            # Convert bytes to MB
            deleted_size_mb = deleted_size / (1024 * 1024)

            print(f"[CACHE] Cleared {deleted_count} files ({deleted_size_mb:.2f} MB)")
            return {
                'status': 'success',
                'deleted_count': deleted_count,
                'deleted_size_mb': round(deleted_size_mb, 2)
            }
        except Exception as e:
            print(f"[CACHE ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def check_code_errors(self, code):
        """Check Python code for syntax errors using AST"""
        try:
            import ast
            import traceback

            errors = []

            if not code.strip():
                return {'status': 'success', 'errors': errors}

            try:
                # Try to parse the code
                ast.parse(code)
                # No errors found
                return {'status': 'success', 'errors': []}

            except SyntaxError as e:
                # Syntax error found
                error_info = {
                    'type': 'error',
                    'line': e.lineno if e.lineno else 0,
                    'column': e.offset if e.offset else 0,
                    'message': str(e.msg),
                    'text': e.text.strip() if e.text else ''
                }
                errors.append(error_info)

            except Exception as e:
                # Other parsing errors
                error_info = {
                    'type': 'error',
                    'line': 0,
                    'column': 0,
                    'message': str(e),
                    'text': ''
                }
                errors.append(error_info)

            return {'status': 'success', 'errors': errors}

        except Exception as e:
            print(f"[CODE CHECK ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def render_animation(self, code, quality='720p', fps=30, gpu_accelerate=False, format='mp4', width=None, height=None, scene_name=None):
        """Render the animation - same as preview but uses RENDER_DIR"""
        global PYTHON_EXE

        print("=" * 80)
        print(f"[RENDER] render_animation() called with parameters:")
        print(f"[RENDER]   quality: {quality}")
        print(f"[RENDER]   fps: {fps}")
        print(f"[RENDER]   gpu_accelerate: {gpu_accelerate} (type: {type(gpu_accelerate)})")
        print(f"[RENDER]   format: {format}")
        print("=" * 80)

        # Initialize Python executable if needed
        if PYTHON_EXE is None:
            PYTHON_EXE = get_python_executable(app_state['window'])
            if not PYTHON_EXE:
                return {'status': 'error', 'message': 'Python environment not available'}

        # Safety check: if is_rendering is stuck from a previous interrupted render
        # Check if there's actually a render process running
        if app_state['is_rendering']:
            # Check if render process exists and is actually running
            render_process_running = False
            if app_state.get('render_process'):
                try:
                    if hasattr(app_state['render_process'], 'poll'):
                        render_process_running = (app_state['render_process'].poll() is None)
                except OSError:
                    pass

            if not render_process_running:
                # Process not running but state is stuck - reset it
                print("[RENDER] Detected stuck render state - resetting")
                app_state['is_rendering'] = False
            else:
                return {'status': 'error', 'message': 'Already rendering'}

        if app_state['is_previewing']:
            return {'status': 'error', 'message': 'Cannot render while previewing. Please wait for preview to complete.'}

        try:
            # Clear render folder before rendering
            print("[RENDER] Clearing render folder...")
            clear_render_folder()

            # Create temporary file in render folder
            os.makedirs(RENDER_DIR, exist_ok=True)
            timestamp = int(time.time() * 1000)
            temp_file = os.path.join(RENDER_DIR, f'temp_render_{timestamp}.py')

            # Write file and ensure it's fully closed before proceeding
            # First, dump raw code for debugging
            print(f"[DEBUG] First 500 chars of code before sanitization:")
            print(f"[DEBUG] {repr(code[:500])}")

            # Sanitize code to remove invisible Unicode characters that corrupt LaTeX
            code = sanitize_code_for_latex(code)

            print(f"[DEBUG] First 500 chars of code AFTER sanitization:")
            print(f"[DEBUG] {repr(code[:500])}")

            # Add UTF-8 coding declaration if not present
            # Check first two lines for coding declaration (PEP 263)
            lines = code.split('\n', 2)
            has_coding = False
            for i in range(min(2, len(lines))):
                if 'coding' in lines[i] or 'encoding' in lines[i]:
                    has_coding = True
                    break

            if not has_coding:
                # Add both shebang-compatible and standard coding declarations
                code_with_encoding = '#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n' + code
            else:
                code_with_encoding = code

            # Write file
            with open(temp_file, 'w', encoding='utf-8', newline='\n', errors='replace') as f:
                f.write(code_with_encoding)

            # Also save a debug copy with hex dump
            debug_file = temp_file + '.debug.txt'
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write("=== ORIGINAL CODE (first 1000 chars) ===\n")
                f.write(code[:1000])
                f.write("\n\n=== HEX DUMP (first 500 bytes) ===\n")
                for i, byte in enumerate(code[:500].encode('utf-8')):
                    f.write(f"{byte:02X} ")
                    if (i + 1) % 16 == 0:
                        f.write("\n")
            print(f"[DEBUG] Saved debug file to: {debug_file}")

            # Ensure file is flushed to disk and fully closed
            time.sleep(0.2)  # Increased delay to ensure file is available

            # Verify file was created
            if not os.path.exists(temp_file):
                return {'status': 'error', 'message': f'Failed to create temporary file: {temp_file}'}

            print(f"[RENDER] Created temp file: {temp_file}")

            # Create manim.cfg in the render directory
            create_manim_config(RENDER_DIR)

            if not scene_name:
                scene_name = extract_scene_name(code)
            if not scene_name:
                return {'status': 'error', 'message': 'No scene class found'}

            # Get manim executable path (in venv Scripts folder)
            if os.name == 'nt':
                manim_exe = os.path.join(VENV_DIR, 'Scripts', 'manim.exe')
            else:
                manim_exe = os.path.join(VENV_DIR, 'bin', 'manim')

            # Fallback to python -m manim if executable not found
            if not os.path.exists(manim_exe):
                print(f"[WARNING] Manim executable not found at {manim_exe}, using python -m manim")
                cmd = [PYTHON_EXE, '-m', 'manim']
            else:
                cmd = [manim_exe]

            # Convert quality preset to flag
            quality_flag = self._get_quality_flag(quality)

            # Add file, scene, and quality flag
            cmd.extend([temp_file, scene_name, quality_flag])

            # Add render directory as media directory (output goes here)
            cmd.extend(['--media_dir', RENDER_DIR])

            # ALWAYS add FPS to allow user override (manim accepts --frame_rate even with preset flags)
            # This allows custom FPS with any quality setting
            cmd.extend(['--frame_rate', str(fps)])
            print(f"[RENDER] Using FPS: {fps}")

            # Add format if specified
            if format and format.lower() != 'mp4':
                cmd.extend(['--format', format.lower()])

            # Check settings for cache preference (default: enable caching)
            settings_file = os.path.join(USER_DATA_DIR, 'settings.json')
            disable_cache = False  # Default to enabled
            try:
                if os.path.exists(settings_file):
                    import json
                    with open(settings_file, 'r') as f:
                        settings = json.load(f)
                        disable_cache = settings.get('disableCache', False)
            except Exception as e:
                print(f"[RENDER] Could not load cache setting: {e}, using default (enabled)")

            if disable_cache:
                cmd.extend(['--disable_caching'])
                print(f"[RENDER] Caching DISABLED per user settings")
            else:
                print(f"[RENDER] Caching ENABLED per user settings")

            # Force progress bar display
            cmd.extend(['--progress_bar', 'display'])
            print(f"[RENDER] Progress bar ENABLED")

            # Add GPU acceleration (OpenGL renderer) if requested
            print(f"[GPU CHECK] Checking gpu_accelerate flag: {gpu_accelerate}")
            if gpu_accelerate:
                cmd.extend(['--renderer=opengl', '--write_to_movie'])
                print(f"[GPU] OK GPU acceleration ENABLED - adding --renderer=opengl --write_to_movie to command")
                print(f"[GPU] Note: OpenGL renderer requires --write_to_movie to save video files")
            else:
                cmd.extend(['--renderer=cairo'])
                print(f"[GPU] DISABLED GPU acceleration - using --renderer=cairo")

            print(f"[RENDER] Full command: {' '.join(cmd)}")

            # Send command to terminal PTY instead of running in subprocess
            # Terminal is in ASSETS_DIR, but render temp file is in RENDER_DIR, so we need full paths
            # Build command string with proper quoting
            cmd_parts = []
            for arg in cmd:
                # Quote arguments that have spaces or are paths
                if ' ' in arg or arg == temp_file or '\\' in arg:
                    cmd_parts.append(f'"{arg}"')
                else:
                    cmd_parts.append(arg)

            cmd_string = ' '.join(cmd_parts)
            print(f"[RENDER] Sending to terminal: {cmd_string}")

            if app_state['terminal_process'] is not None:
                try:
                    # Clear terminal before running new render to remove old errors
                    if WINPTY_AVAILABLE and hasattr(app_state['terminal_process'], 'write'):
                        app_state['terminal_process'].write('cls\r\n')
                        time.sleep(0.2)

                    # Clear error buffer for fresh error detection
                    app_state['terminal_error_buffer'] = []
                    print("[RENDER] Cleared error buffer for new render")

                    # Send command to terminal
                    if WINPTY_AVAILABLE and hasattr(app_state['terminal_process'], 'write'):
                        app_state['terminal_process'].write(cmd_string + '\r\n')
                    else:
                        app_state['terminal_process'].stdin.write(cmd_string + '\n')
                        app_state['terminal_process'].stdin.flush()

                    app_state['is_rendering'] = True

                    # Store temp file path for cleanup after render
                    render_temp_file = temp_file

                    # Start a background thread to watch for render file and handle it
                    def watch_render():
                        import time
                        import shutil
                        max_wait = 259200  # 72 hours for render (3 days for extremely complex animations)
                        start_time = time.time()

                        print(f"[RENDER WATCHER] Waiting for render to complete...")
                        print(f"[RENDER WATCHER] Temp file to clean up later: {render_temp_file}")

                        # Wait a bit for command to start executing before checking for errors
                        time.sleep(3)
                        print(f"[RENDER WATCHER] Starting error detection...")

                        # Wait for file to appear in render directory
                        error_check_count = 0
                        while time.time() - start_time < max_wait:
                            # Check terminal output for errors periodically (not every iteration)
                            # Only check every 5 iterations (every 10 seconds) to reduce spam
                            error_check_count += 1
                            if error_check_count % 5 == 0:
                                has_error, error_msg = check_terminal_output_for_errors()

                                # Check if user interrupted with Ctrl+C
                                output = ''.join(app_state['terminal_error_buffer'])
                                if 'KeyboardInterrupt' in output or '^C' in output or 'Interrupted' in output:
                                    print(f"[RENDER WATCHER] Detected Ctrl+C interrupt - stopping render")
                                    app_state['is_rendering'] = False
                                    return
                            else:
                                has_error = False
                                error_msg = None

                            # Additional check: if user manually changed the state (via stop button)
                            if not app_state['is_rendering']:
                                print(f"[RENDER WATCHER] Render stopped externally - exiting watcher")
                                return

                            if has_error:
                                print(f"[RENDER WATCHER] Error detected in terminal output: {error_msg}")
                                app_state['is_rendering'] = False

                                # Clean up temp file
                                try:
                                    if os.path.exists(render_temp_file):
                                        os.remove(render_temp_file)
                                        print(f"[RENDER WATCHER] Cleaned up temp file after error")
                                except Exception as cleanup_err:
                                    print(f"[RENDER WATCHER] Error cleaning temp file: {cleanup_err}")

                                # Notify frontend of failure
                                if app_state['window']:
                                    try:
                                        safe_error = error_msg.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
                                        safe_evaluate_js(
                                            app_state['window'],
                                            f'if(window.renderFailed){{window.renderFailed("{safe_error}")}}'
                                        )
                                    except Exception as js_err:
                                        print(f"[RENDER WATCHER] Error notifying frontend: {js_err}")

                                return

                            # Look for video files in render directory
                            # Search both in 'videos' subfolder and root RENDER_DIR
                            try:
                                # First, check the standard videos subdirectory
                                videos_dir = os.path.join(RENDER_DIR, 'videos')
                                search_paths = [videos_dir] if os.path.exists(videos_dir) else []

                                # Also check root RENDER_DIR every 30 seconds (15 iterations * 2s sleep)
                                if error_check_count % 15 == 0:
                                    search_paths.append(RENDER_DIR)
                                    print(f"[RENDER WATCHER] Expanded search to include root RENDER_DIR")

                                file_found = False
                                for search_dir in search_paths:
                                    if file_found:
                                        break
                                    # Log what we're searching for debugging
                                    if error_check_count % 15 == 0:  # Log every 30 seconds
                                        print(f"[RENDER WATCHER] Searching in: {search_dir}")

                                    for root, dirs, files in os.walk(search_dir):
                                        if file_found:
                                            break

                                        # Log all files found for debugging (every 30 seconds)
                                        if error_check_count % 15 == 0 and files:
                                            print(f"[RENDER WATCHER] Files in {root}: {files}")

                                        for file in files:
                                            # Skip partial movie files - look for video files (mp4, mov, webm, avi)
                                            # OpenGL renderer might output different formats than Cairo
                                            if file.endswith(('.mp4', '.mov', '.webm', '.avi')) and 'partial_movie_files' not in root:
                                                render_file = os.path.join(root, file)
                                                print(f"[RENDER WATCHER] ✅ Found render file: {render_file}")
                                                file_found = True

                                                # Wait a bit more to ensure manim has completely finished writing
                                                print(f"[RENDER WATCHER] Waiting for manim to finish completely...")
                                                time.sleep(3)  # Wait for manim to fully complete and release file

                                                # Verify file is not being written to
                                                file_size_1 = os.path.getsize(render_file)
                                                time.sleep(1)
                                                file_size_2 = os.path.getsize(render_file)

                                                if file_size_1 != file_size_2:
                                                    # File is still being written, wait more
                                                    print(f"[RENDER WATCHER] File still being written, waiting more...")
                                                    continue

                                                # Move MP4 directly to RENDER_DIR root
                                                try:
                                                    final_render_path = os.path.join(RENDER_DIR, file)

                                                    print(f"[RENDER WATCHER] Moving MP4 to root directory...")
                                                    shutil.move(render_file, final_render_path)
                                                    print(f"[RENDER WATCHER] Moved to: {final_render_path}")

                                                    # Remove the videos folder structure created by manim
                                                    print(f"[RENDER WATCHER] Removing manim folder structure...")
                                                    try:
                                                        if os.path.exists(videos_dir):
                                                            shutil.rmtree(videos_dir)
                                                            print(f"[RENDER WATCHER] Removed videos folder")
                                                    except Exception as rmdir_err:
                                                        print(f"[RENDER WATCHER] Could not remove videos dir: {rmdir_err}")

                                                    # Clean up temp file after successful render
                                                    try:
                                                        if os.path.exists(render_temp_file):
                                                            os.remove(render_temp_file)
                                                            print(f"[RENDER WATCHER] Cleaned up temp .py file")
                                                    except Exception as cleanup_err:
                                                        print(f"[RENDER WATCHER] Error cleaning temp file: {cleanup_err}")

                                                    app_state['is_rendering'] = False
                                                    print(f"[RENDER WATCHER] Render complete! File ready at: {final_render_path}")

                                                    # Show preview AND save dialog to user AFTER everything is done
                                                    try:
                                                        if app_state['window']:
                                                            # Small delay to ensure everything is settled
                                                            time.sleep(0.5)
                                                            # Get suggested filename from path
                                                            suggested_name = os.path.basename(final_render_path)
                                                            # Trigger renderCompleted with autoSave=true to show preview AND save dialog
                                                            escaped_path = final_render_path.replace('\\', '\\\\').replace('"', '\\"')
                                                            escaped_name = suggested_name.replace('\\', '\\\\').replace('"', '\\"')
                                                            safe_evaluate_js(
                                                                app_state['window'],
                                                                f'if(window.renderCompleted){{window.renderCompleted("{escaped_path}", true, "{escaped_name}")}}'
                                                            )
                                                            print(f"[RENDER WATCHER] Render completed - showing preview and save dialog")
                                                    except Exception as dialog_err:
                                                        print(f"[RENDER WATCHER] Error showing render completion: {dialog_err}")

                                                    return
                                                except Exception as move_err:
                                                    print(f"[RENDER WATCHER ERROR] Failed to move/cleanup: {move_err}")

                            except Exception as e:
                                print(f"[RENDER WATCHER] Error checking files: {e}")

                            # Sleep before next check
                            time.sleep(2)

                        # Timeout reached - do final thorough search before giving up
                        print(f"[RENDER WATCHER] Timeout reached ({max_wait}s) - performing final thorough search...")
                        found_file = None

                        try:
                            # Search entire RENDER_DIR recursively
                            for root, dirs, files in os.walk(RENDER_DIR):
                                print(f"[RENDER WATCHER] Searching: {root}")
                                for file in files:
                                    if file.endswith(('.mp4', '.mov', '.webm', '.avi', '.gif', '.png')) and 'partial_movie_files' not in root:
                                        file_path = os.path.join(root, file)
                                        file_size = os.path.getsize(file_path)
                                        print(f"[RENDER WATCHER] Found media file: {file} ({file_size} bytes) in {root}")
                                        # Accept any video format (mp4, mov, webm, avi) - OpenGL might use different formats
                                        if file.endswith(('.mp4', '.mov', '.webm', '.avi')):
                                            found_file = file_path
                                            print(f"[RENDER WATCHER] ✓ Found video file on final search: {found_file}")
                                            break
                                if found_file:
                                    break
                        except Exception as search_err:
                            print(f"[RENDER WATCHER] Error during final search: {search_err}")

                        if found_file:
                            # Found a file! Process it
                            try:
                                final_render_path = os.path.join(RENDER_DIR, os.path.basename(found_file))
                                if found_file != final_render_path:
                                    shutil.move(found_file, final_render_path)
                                print(f"[RENDER WATCHER] ✓ Recovered render file: {final_render_path}")

                                # Notify frontend - show preview AND save dialog
                                if app_state['window']:
                                    suggested_name = os.path.basename(final_render_path)
                                    escaped_path = final_render_path.replace('\\', '\\\\').replace('"', '\\"')
                                    escaped_name = suggested_name.replace('\\', '\\\\').replace('"', '\\"')
                                    safe_evaluate_js(
                                        app_state['window'],
                                        f'if(window.renderCompleted){{window.renderCompleted("{escaped_path}", true, "{escaped_name}")}}'
                                    )
                            except Exception as recovery_err:
                                print(f"[RENDER WATCHER] Error recovering file: {recovery_err}")
                        else:
                            print(f"[RENDER WATCHER] ✗ No render file found after final search")
                            # Notify frontend of timeout
                            if app_state['window']:
                                safe_evaluate_js(
                                    app_state['window'],
                                    f'if(window.renderFailed){{window.renderFailed("Render timeout: No output file found after {max_wait}s. Check terminal for errors.")}}'
                                )

                        app_state['is_rendering'] = False

                        # Clean up temp file even on timeout
                        try:
                            if os.path.exists(render_temp_file):
                                os.remove(render_temp_file)
                                print(f"[RENDER WATCHER] Cleaned up temp file after timeout: {render_temp_file}")
                        except Exception as cleanup_err:
                            print(f"[RENDER WATCHER] Error cleaning temp file: {cleanup_err}")

                    import threading
                    watcher_thread = threading.Thread(target=watch_render, daemon=True)
                    watcher_thread.start()

                    return {'status': 'started', 'message': 'Render command sent to terminal'}
                except Exception as e:
                    print(f"[RENDER ERROR] Failed to send to terminal: {e}")
                    app_state['is_rendering'] = False
                    return {'status': 'error', 'message': f'Failed to send command to terminal: {e}'}

            # Fallback to old subprocess method if terminal not available
            print("[RENDER] Terminal not available, using fallback subprocess method")

            # Start rendering in background thread
            def render_thread():
                app_state['is_rendering'] = True
                output_lines = []

                try:
                    process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding='utf-8',  # Force UTF-8 encoding
                        errors='replace',  # Replace invalid characters instead of crashing
                        bufsize=1,
                        universal_newlines=True,
                        env=get_clean_environment(),  # Use clean environment
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )

                    app_state['render_process'] = process

                    # Read output line by line
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            line = line.rstrip()
                            output_lines.append(line)
                            print(f"[Render] {line}")

                            # Send to UI using evaluate_js
                            if app_state['window']:
                                try:
                                    safe_line = line.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'").replace('\n', '\\n')
                                    app_state['window'].evaluate_js(
                                        f'if(window.updateRenderOutput){{window.updateRenderOutput("{safe_line}")}}'
                                    )
                                except Exception as e:
                                    # Ignore errors when window is disposed/closed
                                    if "disposed" not in str(e).lower():
                                        print(f"[RENDER] Error updating output: {e}")

                    process.wait()

                    print(f"Render process finished with code: {process.returncode}")

                    if process.returncode == 0:
                        # Wait a moment for filesystem to flush files to disk
                        print("[INFO] Waiting for files to be written to disk...")
                        time.sleep(2)  # Give OS time to flush buffers

                        # Find the rendered files
                        final_path = self.cleanup_after_render(scene_name)

                        # Verify file actually exists and is readable before proceeding
                        if final_path and os.path.exists(final_path):
                            try:
                                # Try to open and verify the file is accessible
                                with open(final_path, 'rb') as f:
                                    f.read(1)  # Read one byte to verify it's accessible
                                print(f"[OK] Verified file exists and is accessible: {final_path}")
                            except Exception as verify_error:
                                print(f"[ERROR] File exists but not accessible: {verify_error}")
                                final_path = None
                        else:
                            print(f"[WARNING] No output file found after render")

                        # Move to assets folder and trigger auto-save dialog
                        if final_path:
                            try:
                                import shutil
                                from datetime import datetime

                                # Create timestamp for unique filename
                                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                                original_name = os.path.basename(final_path)
                                name_without_ext = os.path.splitext(original_name)[0]
                                ext = os.path.splitext(original_name)[1]

                                # Create assets folder if it doesn't exist
                                os.makedirs(ASSETS_DIR, exist_ok=True)

                                # Move to assets with timestamp
                                assets_filename = f"{name_without_ext}_{timestamp}{ext}"
                                assets_path = os.path.join(ASSETS_DIR, assets_filename)

                                print(f"[INFO] Moving rendered file to assets folder...")
                                print(f"   From: {final_path}")
                                print(f"   To: {assets_path}")

                                shutil.move(final_path, assets_path)
                                print(f"[OK] File moved to assets!")

                                # Clean up temp folders now that file is safe in assets
                                print(f"[INFO] Cleaning up temp folders...")
                                videos_base = os.path.join(MEDIA_DIR, 'videos')
                                images_base = os.path.join(MEDIA_DIR, 'images')
                                folders_deleted = 0

                                # Delete temp folders from videos
                                if os.path.exists(videos_base):
                                    for folder in os.listdir(videos_base):
                                        if folder.startswith('temp_'):
                                            folder_path = os.path.join(videos_base, folder)
                                            try:
                                                shutil.rmtree(folder_path)
                                                folders_deleted += 1
                                                print(f"   [OK] Deleted: {folder}")
                                            except Exception as e:
                                                print(f"   [ERROR] Failed to delete {folder}: {e}")

                                # Delete temp folders from images
                                if os.path.exists(images_base):
                                    for folder in os.listdir(images_base):
                                        if folder.startswith('temp_'):
                                            folder_path = os.path.join(images_base, folder)
                                            try:
                                                shutil.rmtree(folder_path)
                                                folders_deleted += 1
                                                print(f"   [OK] Deleted: {folder}")
                                            except Exception as e:
                                                print(f"   [ERROR] Failed to delete {folder}: {e}")

                                print(f"[OK] Cleaned up {folders_deleted} temp folder(s)")

                                # Call renderCompleted with autoSave flag
                                if app_state['window']:
                                    safe_path = assets_path.replace('\\', '/').replace('"', '\\"')
                                    # Format: scene name with timestamp as suggested filename
                                    suggested_name = f"{scene_name}_{timestamp}.mp4"
                                    safe_name = suggested_name.replace('"', '\\"')
                                    app_state['window'].evaluate_js(
                                        f'if(window.renderCompleted){{window.renderCompleted("{safe_path}", true, "{safe_name}")}}'
                                    )
                            except Exception as move_error:
                                print(f"[ERROR] Failed to move file to assets: {move_error}")
                                # Fall back to old behavior if move fails
                                if app_state['window']:
                                    safe_path = final_path.replace('\\', '/').replace('"', '\\"')
                                    app_state['window'].evaluate_js(
                                        f'if(window.renderCompleted){{window.renderCompleted("{safe_path}")}}'
                                    )
                        else:
                            # No file found
                            if app_state['window']:
                                app_state['window'].evaluate_js(
                                    'if(window.renderCompleted){window.renderCompleted()}'
                                )

                        result = {
                            'status': 'success',
                            'message': 'Rendering completed',
                            'output': '\n'.join(output_lines)
                        }
                    else:
                        if app_state['window']:
                            error_msg = f"Render failed with code {process.returncode}".replace('"', '\\"')
                            app_state['window'].evaluate_js(
                                f'if(window.renderFailed){{window.renderFailed("{error_msg}")}}'
                            )
                        result = {
                            'status': 'error',
                            'message': f'Render failed with code {process.returncode}',
                            'output': '\n'.join(output_lines)
                        }

                except Exception as e:
                    print(f"Render error: {e}")
                    if app_state['window']:
                        safe_error = str(e).replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
                        app_state['window'].evaluate_js(
                            f'if(window.renderFailed){{window.renderFailed("{safe_error}")}}'
                        )
                    result = {
                        'status': 'error',
                        'message': str(e),
                        'output': '\n'.join(output_lines)
                    }
                finally:
                    app_state['is_rendering'] = False
                    # Clean up temp file
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                    except:
                        pass

            threading.Thread(target=render_thread, daemon=True).start()

            return {'status': 'started', 'message': 'Rendering started', 'scene': scene_name}

        except Exception as e:
            print(f"Error starting render: {e}")
            app_state['is_rendering'] = False
            return {'status': 'error', 'message': str(e)}

    def _get_quality_flag(self, quality):
        """Convert quality preset to manim flag or custom resolution"""
        if quality in QUALITY_PRESETS:
            return QUALITY_PRESETS[quality][0]  # Return the flag (e.g., '-ql', '-qm')
        else:
            # Validate custom resolution format: should be WIDTHxHEIGHT
            if 'x' in str(quality).lower():
                # Custom resolution like "1920x1080"
                return f'-r{quality}'
            else:
                # Invalid quality - fallback to 720p
                print(f"[WARNING] Invalid quality '{quality}', using 720p fallback")
                return QUALITY_PRESETS["720p"][0]

    def quick_preview(self, code, quality='480p', fps=15, gpu_accelerate=False, format='mp4', scene_name=None):
        """Quick preview the animation with customizable quality settings"""
        global PYTHON_EXE

        print("=" * 80)
        print(f"[PREVIEW] quick_preview() called with parameters:")
        print(f"[PREVIEW]   quality: {quality}")
        print(f"[PREVIEW]   fps: {fps}")
        print(f"[PREVIEW]   gpu_accelerate: {gpu_accelerate} (type: {type(gpu_accelerate)})")
        print(f"[PREVIEW]   format: {format}")
        print("=" * 80)

        # Initialize Python executable if needed
        if PYTHON_EXE is None:
            PYTHON_EXE = get_python_executable(app_state['window'])
            if not PYTHON_EXE:
                return {'status': 'error', 'message': 'Python environment not available'}

        # Safety check: if is_previewing is stuck from a previous interrupted preview
        # Check if there's actually a preview process running
        if app_state['is_previewing']:
            # Check if preview process exists and is actually running
            preview_process_running = False
            if app_state.get('preview_process'):
                try:
                    if hasattr(app_state['preview_process'], 'poll'):
                        preview_process_running = (app_state['preview_process'].poll() is None)
                except:
                    pass

            if not preview_process_running:
                # Process not running but state is stuck - reset it
                print("[PREVIEW] Detected stuck preview state - resetting")
                app_state['is_previewing'] = False
            else:
                return {'status': 'error', 'message': 'Already previewing'}

        if app_state['is_rendering']:
            return {'status': 'error', 'message': 'Cannot preview while rendering. Please wait for render to complete.'}

        try:
            # Clear preview folder before rendering
            print("[PREVIEW] Clearing preview folder...")
            clear_preview_folder()

            # Create temporary file in preview folder
            os.makedirs(PREVIEW_DIR, exist_ok=True)
            timestamp = int(time.time() * 1000)
            temp_file = os.path.join(PREVIEW_DIR, f'temp_preview_{timestamp}.py')

            # Write file and ensure it's fully closed before proceeding
            # First, dump raw code for debugging
            print(f"[DEBUG] First 500 chars of code before sanitization:")
            print(f"[DEBUG] {repr(code[:500])}")

            # Sanitize code to remove invisible Unicode characters that corrupt LaTeX
            code = sanitize_code_for_latex(code)

            print(f"[DEBUG] First 500 chars of code AFTER sanitization:")
            print(f"[DEBUG] {repr(code[:500])}")

            # Add UTF-8 coding declaration if not present
            # Check first two lines for coding declaration (PEP 263)
            lines = code.split('\n', 2)
            has_coding = False
            for i in range(min(2, len(lines))):
                if 'coding' in lines[i] or 'encoding' in lines[i]:
                    has_coding = True
                    break

            if not has_coding:
                # Add both shebang-compatible and standard coding declarations
                code_with_encoding = '#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n' + code
            else:
                code_with_encoding = code

            # Write file
            with open(temp_file, 'w', encoding='utf-8', newline='\n', errors='replace') as f:
                f.write(code_with_encoding)

            # Also save a debug copy with hex dump
            debug_file = temp_file + '.debug.txt'
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write("=== ORIGINAL CODE (first 1000 chars) ===\n")
                f.write(code[:1000])
                f.write("\n\n=== HEX DUMP (first 500 bytes) ===\n")
                for i, byte in enumerate(code[:500].encode('utf-8')):
                    f.write(f"{byte:02X} ")
                    if (i + 1) % 16 == 0:
                        f.write("\n")
            print(f"[DEBUG] Saved debug file to: {debug_file}")

            # Ensure file is flushed to disk and fully closed
            time.sleep(0.2)  # Increased delay to ensure file is available

            # Verify file was created
            if not os.path.exists(temp_file):
                return {'status': 'error', 'message': f'Failed to create temporary file: {temp_file}'}

            print(f"[PREVIEW] Created temp file: {temp_file}")

            # Create manim.cfg in the preview directory
            create_manim_config(PREVIEW_DIR)

            if not scene_name:
                scene_name = extract_scene_name(code)
            if not scene_name:
                return {'status': 'error', 'message': 'No scene class found'}

            # Get manim executable path (in venv Scripts folder)
            if os.name == 'nt':
                manim_exe = os.path.join(VENV_DIR, 'Scripts', 'manim.exe')
            else:
                manim_exe = os.path.join(VENV_DIR, 'bin', 'manim')

            # Fallback to python -m manim if executable not found
            if not os.path.exists(manim_exe):
                print(f"[WARNING] Manim executable not found at {manim_exe}, using python -m manim")
                cmd = [PYTHON_EXE, '-m', 'manim']
            else:
                cmd = [manim_exe]

            # Convert quality preset to flag or resolution
            quality_flag = self._get_quality_flag(quality)

            # Add file, scene, and quality flag
            cmd.extend([temp_file, scene_name, quality_flag])

            # Add preview directory as media directory (output goes here)
            cmd.extend(['--media_dir', PREVIEW_DIR])

            # ALWAYS add FPS to allow user override (manim accepts --frame_rate even with preset flags)
            # This allows custom FPS with any quality setting
            cmd.extend(['--frame_rate', str(fps)])
            print(f"[PREVIEW] Using FPS: {fps}")

            # Add format if specified
            if format and format.lower() != 'mp4':
                cmd.extend(['--format', format.lower()])

            # Check settings for cache preference (default: enable caching)
            settings_file = os.path.join(USER_DATA_DIR, 'settings.json')
            disable_cache = False  # Default to enabled
            try:
                if os.path.exists(settings_file):
                    import json
                    with open(settings_file, 'r') as f:
                        settings = json.load(f)
                        disable_cache = settings.get('disableCache', False)
            except Exception as e:
                print(f"[PREVIEW] Could not load cache setting: {e}, using default (enabled)")

            if disable_cache:
                cmd.extend(['--disable_caching'])
                print(f"[PREVIEW] Caching DISABLED per user settings")
            else:
                print(f"[PREVIEW] Caching ENABLED per user settings")

            # Force progress bar display
            cmd.extend(['--progress_bar', 'display'])
            print(f"[PREVIEW] Progress bar ENABLED")

            # Add GPU acceleration (OpenGL renderer) if requested
            print(f"[GPU CHECK] Checking gpu_accelerate flag: {gpu_accelerate}")
            if gpu_accelerate:
                cmd.extend(['--renderer=opengl', '--write_to_movie'])
                print(f"[GPU] OK GPU acceleration ENABLED - adding --renderer=opengl --write_to_movie to command")
                print(f"[GPU] Note: OpenGL renderer requires --write_to_movie to save video files")
            else:
                cmd.extend(['--renderer=cairo'])
                print(f"[GPU] DISABLED GPU acceleration - using --renderer=cairo")

            print(f"[PREVIEW] Full command: {' '.join(cmd)}")

            # Send command to terminal PTY instead of running in subprocess
            # Terminal is in ASSETS_DIR, but preview temp file is in PREVIEW_DIR, so we need full paths
            # Build command string with proper quoting
            cmd_parts = []
            for arg in cmd:
                # Quote arguments that have spaces or are paths
                if ' ' in arg or arg == temp_file or '\\' in arg:
                    cmd_parts.append(f'"{arg}"')
                else:
                    cmd_parts.append(arg)

            cmd_string = ' '.join(cmd_parts)
            print(f"[PREVIEW] Sending to terminal: {cmd_string}")

            if app_state['terminal_process'] is not None:
                try:
                    # Clear terminal before running new preview to remove old errors
                    if WINPTY_AVAILABLE and hasattr(app_state['terminal_process'], 'write'):
                        app_state['terminal_process'].write('cls\r\n')
                        time.sleep(0.2)

                    # Clear error buffer for fresh error detection
                    app_state['terminal_error_buffer'] = []
                    print("[PREVIEW] Cleared error buffer for new preview")

                    # Send command to terminal
                    if WINPTY_AVAILABLE and hasattr(app_state['terminal_process'], 'write'):
                        app_state['terminal_process'].write(cmd_string + '\r\n')
                    else:
                        app_state['terminal_process'].stdin.write(cmd_string + '\n')
                        app_state['terminal_process'].stdin.flush()

                    app_state['is_previewing'] = True

                    # Store temp file path for cleanup after preview
                    preview_temp_file = temp_file

                    # Start a background thread to watch for preview file and handle it
                    def watch_preview():
                        import time
                        import shutil
                        max_wait = 259200  # 72 hours for preview (3 days for extremely complex animations)
                        start_time = time.time()

                        print(f"[PREVIEW WATCHER] Waiting for preview to complete...")
                        print(f"[PREVIEW WATCHER] Temp file to clean up later: {preview_temp_file}")

                        # Wait a bit for command to start executing before checking for errors
                        time.sleep(3)
                        print(f"[PREVIEW WATCHER] Starting error detection...")

                        # Wait for file to appear in preview directory
                        error_check_count = 0
                        manim_reported_done = False
                        while time.time() - start_time < max_wait:
                            # Check terminal output for errors periodically (not every iteration)
                            # Only check every 5 iterations (every 10 seconds) to reduce spam
                            error_check_count += 1
                            if error_check_count % 5 == 0:
                                has_error, error_msg = check_terminal_output_for_errors()

                                # Also check if manim reported successful completion
                                output = ''.join(app_state['terminal_error_buffer'])
                                if 'Rendered ' in output and 'File ready at' in output:
                                    if not manim_reported_done:
                                        print(f"[PREVIEW WATCHER] Manim reported completion in terminal output")
                                        manim_reported_done = True

                                # Check if user interrupted with Ctrl+C
                                if 'KeyboardInterrupt' in output or '^C' in output or 'Interrupted' in output:
                                    print(f"[PREVIEW WATCHER] Detected Ctrl+C interrupt - stopping preview")
                                    app_state['is_previewing'] = False
                                    return
                            else:
                                has_error = False
                                error_msg = None

                            # Additional check: if user manually changed the state (via stop button)
                            if not app_state['is_previewing']:
                                print(f"[PREVIEW WATCHER] Preview stopped externally - exiting watcher")
                                return

                            if has_error:
                                print(f"[PREVIEW WATCHER] Error detected in terminal output: {error_msg}")
                                app_state['is_previewing'] = False

                                # Clean up temp file
                                try:
                                    if os.path.exists(preview_temp_file):
                                        os.remove(preview_temp_file)
                                        print(f"[PREVIEW WATCHER] Cleaned up temp file after error")
                                except Exception as cleanup_err:
                                    print(f"[PREVIEW WATCHER] Error cleaning temp file: {cleanup_err}")

                                # Notify frontend of failure
                                if app_state['window']:
                                    try:
                                        safe_error = error_msg.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
                                        safe_evaluate_js(
                                            app_state['window'],
                                            f'if(window.previewFailed){{window.previewFailed("{safe_error}")}}'
                                        )
                                    except Exception as js_err:
                                        print(f"[PREVIEW WATCHER] Error notifying frontend: {js_err}")

                                return

                            # Print progress every 30 seconds
                            elapsed = time.time() - start_time
                            if error_check_count % 15 == 0:  # Every 30 seconds (15 * 2 second sleep)
                                print(f"[PREVIEW WATCHER] Still waiting for preview... ({int(elapsed)}s elapsed)")

                            # Look for video files in preview directory
                            # Search both in 'videos' subfolder and root PREVIEW_DIR
                            try:
                                # First, check the standard videos subdirectory
                                videos_dir = os.path.join(PREVIEW_DIR, 'videos')
                                search_paths = [videos_dir] if os.path.exists(videos_dir) else []

                                # Also check root PREVIEW_DIR every 30 seconds (15 iterations * 2s sleep)
                                if error_check_count % 15 == 0:
                                    search_paths.append(PREVIEW_DIR)
                                    print(f"[PREVIEW WATCHER] Expanded search to include root PREVIEW_DIR")

                                file_found = False
                                for search_dir in search_paths:
                                    if file_found:
                                        break
                                    # Log what we're searching for debugging
                                    if error_check_count % 15 == 0:  # Log every 30 seconds
                                        print(f"[PREVIEW WATCHER] Searching in: {search_dir}")

                                    for root, dirs, files in os.walk(search_dir):
                                        if file_found:
                                            break

                                        # Log all files found for debugging (every 30 seconds)
                                        if error_check_count % 15 == 0 and files:
                                            print(f"[PREVIEW WATCHER] Files in {root}: {files}")

                                        for file in files:
                                            # Skip partial movie files - look for video files (mp4, mov, webm, avi)
                                            # OpenGL renderer might output different formats than Cairo
                                            if file.endswith(('.mp4', '.mov', '.webm', '.avi')) and 'partial_movie_files' not in root:
                                                preview_file = os.path.join(root, file)
                                                print(f"[PREVIEW WATCHER] ✅ Found preview file: {preview_file}")
                                                file_found = True

                                                # Process video with ffmpeg and copy to assets
                                                try:
                                                    os.makedirs(ASSETS_DIR, exist_ok=True)
                                                    assets_path = os.path.join(ASSETS_DIR, file)

                                                    # If file already exists, remove it first
                                                    if os.path.exists(assets_path):
                                                        os.remove(assets_path)

                                                    # Wait for file to be completely written
                                                    print(f"[PREVIEW WATCHER] Waiting for file to be fully written...")
                                                    time.sleep(1)  # Wait for filesystem flush

                                                    # Verify source file is valid and stable
                                                    prev_size = -1
                                                    stable_count = 0
                                                    for _ in range(10):  # Wait up to 5 seconds
                                                        try:
                                                            curr_size = os.path.getsize(preview_file)
                                                            if curr_size == prev_size and curr_size > 0:
                                                                stable_count += 1
                                                                if stable_count >= 2:  # Stable for 1 second
                                                                    break
                                                            else:
                                                                stable_count = 0
                                                            prev_size = curr_size
                                                            time.sleep(0.5)
                                                        except:
                                                            time.sleep(0.5)

                                                    print(f"[PREVIEW WATCHER] Source file stable at {prev_size} bytes")

                                                    # Use ffmpeg to process and copy (avoids corruption from shutil.copy2)
                                                    # This also enables fast-start in one step
                                                    if preview_file.endswith('.mp4'):
                                                        try:
                                                            print(f"[PREVIEW WATCHER] Processing MP4 with ffmpeg (fast-start + copy to assets)...")

                                                            # Use ffmpeg to move moov atom to beginning and copy to assets
                                                            ffmpeg_cmd = [
                                                                'ffmpeg',
                                                                '-y',  # Overwrite output
                                                                '-i', preview_file,  # Input from ORIGINAL preview file
                                                                '-c', 'copy',  # Copy streams without re-encoding
                                                                '-movflags', '+faststart',  # Move moov atom to beginning
                                                                assets_path  # Output directly to assets
                                                            ]

                                                            result = subprocess.run(
                                                                ffmpeg_cmd,
                                                                stdout=subprocess.PIPE,
                                                                stderr=subprocess.PIPE,
                                                                text=True,
                                                                timeout=60,
                                                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                                                            )

                                                            if result.returncode == 0 and os.path.exists(assets_path):
                                                                final_size = os.path.getsize(assets_path)
                                                                print(f"[PREVIEW WATCHER] ✅ Video processed successfully: {final_size} bytes")
                                                                print(f"[PREVIEW WATCHER] ✅ Fast-start enabled for web playback")
                                                            else:
                                                                print(f"[PREVIEW WATCHER] ⚠️ ffmpeg processing failed: {result.stderr}")
                                                                # Fallback: try direct copy
                                                                print(f"[PREVIEW WATCHER] Falling back to direct copy...")
                                                                shutil.copy2(preview_file, assets_path)
                                                                print(f"[PREVIEW WATCHER] File copied (without fast-start)")
                                                        except FileNotFoundError:
                                                            print(f"[PREVIEW WATCHER] ⚠️ ffmpeg not found, using direct copy")
                                                            shutil.copy2(preview_file, assets_path)
                                                        except Exception as ff_err:
                                                            print(f"[PREVIEW WATCHER] ⚠️ ffmpeg error: {ff_err}, using direct copy")
                                                            shutil.copy2(preview_file, assets_path)
                                                    else:
                                                        # Non-MP4 files: direct copy
                                                        print(f"[PREVIEW WATCHER] Copying non-MP4 file to assets...")
                                                        shutil.copy2(preview_file, assets_path)

                                                    # Also copy to a simple location for easy access (preserve extension)
                                                    file_ext = os.path.splitext(file)[1]  # Get extension (.mp4, .mov, etc)
                                                    simple_preview_path = os.path.join(PREVIEW_DIR, f'latest_preview{file_ext}')
                                                    try:
                                                        shutil.copy2(assets_path, simple_preview_path)
                                                        print(f"[PREVIEW WATCHER] ✅ Preview copied to easy-access location: {simple_preview_path}")
                                                    except Exception as simple_copy_err:
                                                        print(f"[PREVIEW WATCHER] Warning: Failed to copy to simple location: {simple_copy_err}")

                                                    # Track preview file (kept in assets folder even after app closes)
                                                    app_state['preview_files_to_cleanup'].add(assets_path)

                                                    print("=" * 80)
                                                    print(f"[PREVIEW WATCHER] ✅ PREVIEW COMPLETE!")
                                                    print(f"[PREVIEW WATCHER] 📁 Preview saved to:")
                                                    print(f"[PREVIEW WATCHER]    1. Easy access: {simple_preview_path}")
                                                    print(f"[PREVIEW WATCHER]    2. Assets folder: {assets_path}")
                                                    print(f"[PREVIEW WATCHER]    3. Original render: {preview_file}")
                                                    print(f"[PREVIEW WATCHER] ℹ️ Files will persist after app closes")
                                                    print("=" * 80)

                                                    # Notify frontend to load preview in preview box
                                                    if app_state['window']:
                                                        try:
                                                            # Escape the path for JavaScript
                                                            escaped_path = assets_path.replace('\\', '\\\\').replace('"', '\\"')
                                                            safe_evaluate_js(
                                                                app_state['window'],
                                                                f'if(window.previewCompleted){{window.previewCompleted("{escaped_path}")}}'
                                                            )
                                                            print(f"[PREVIEW WATCHER] Notified frontend to load preview")
                                                        except Exception as js_err:
                                                            print(f"[PREVIEW WATCHER] Error notifying frontend: {js_err}")

                                                    app_state['is_previewing'] = False

                                                    # Clean up temp file after successful preview
                                                    try:
                                                        if os.path.exists(preview_temp_file):
                                                            os.remove(preview_temp_file)
                                                            print(f"[PREVIEW WATCHER] Cleaned up temp file: {preview_temp_file}")
                                                    except Exception as cleanup_err:
                                                        print(f"[PREVIEW WATCHER] Error cleaning temp file: {cleanup_err}")

                                                    return
                                                except Exception as copy_err:
                                                    print(f"[PREVIEW WATCHER ERROR] Failed to copy preview file: {copy_err}")

                            except Exception as e:
                                print(f"[PREVIEW WATCHER] Error checking files: {e}")

                            # Check if preview process has finished (if using subprocess mode)
                            # In terminal mode, we rely on file detection instead
                            if app_state.get('preview_process') and hasattr(app_state['preview_process'], 'poll'):
                                if app_state['preview_process'].poll() is not None:
                                    # Process finished
                                    elapsed = time.time() - start_time
                                    print(f"[PREVIEW WATCHER] Preview process finished after {int(elapsed)}s, checking for output one more time...")
                                    # Give it one more chance to find files
                                    time.sleep(2)
                                    # Continue loop to check files one more time

                            # Sleep before next check
                            time.sleep(2)

                            # Safety: if manim reported done but we still haven't found the file after 30 seconds
                            if manim_reported_done and (time.time() - start_time) > 30:
                                print(f"[PREVIEW WATCHER] Manim reported completion but file not found. Checking manually...")
                                # Try one more thorough search
                                try:
                                    for root, dirs, files in os.walk(PREVIEW_DIR):
                                        print(f"[PREVIEW WATCHER] Checking directory: {root}")
                                        for file in files:
                                            if file.endswith('.mp4'):
                                                print(f"[PREVIEW WATCHER] Found MP4: {os.path.join(root, file)}")
                                except Exception as search_err:
                                    print(f"[PREVIEW WATCHER] Manual search error: {search_err}")

                                print(f"[PREVIEW WATCHER] Giving up - file not found despite completion report")
                                app_state['is_previewing'] = False
                                break

                        # Timeout reached - do final thorough search before giving up
                        print(f"[PREVIEW WATCHER] Timeout reached ({max_wait}s) - performing final thorough search...")
                        found_file = None

                        try:
                            # Search entire PREVIEW_DIR recursively
                            for root, dirs, files in os.walk(PREVIEW_DIR):
                                print(f"[PREVIEW WATCHER] Searching: {root}")
                                for file in files:
                                    if file.endswith(('.mp4', '.mov', '.webm', '.avi', '.gif', '.png')) and 'partial_movie_files' not in root:
                                        file_path = os.path.join(root, file)
                                        file_size = os.path.getsize(file_path)
                                        print(f"[PREVIEW WATCHER] Found media file: {file} ({file_size} bytes) in {root}")
                                        # Accept any video format (mp4, mov, webm, avi) - OpenGL might use different formats
                                        if file.endswith(('.mp4', '.mov', '.webm', '.avi')):
                                            found_file = file_path
                                            print(f"[PREVIEW WATCHER] ✓ Found video file on final search: {found_file}")
                                            break
                                if found_file:
                                    break
                        except Exception as search_err:
                            print(f"[PREVIEW WATCHER] Error during final search: {search_err}")

                        if found_file:
                            # Found a file! Process it to assets
                            try:
                                print(f"[PREVIEW WATCHER] ✓ Recovered preview file, copying to assets...")
                                assets_path = os.path.join(ASSETS_DIR, os.path.basename(found_file))

                                # Remove existing file if present
                                if os.path.exists(assets_path):
                                    os.remove(assets_path)

                                # Copy to assets
                                shutil.copy2(found_file, assets_path)
                                print(f"[PREVIEW WATCHER] ✓ Copied to assets: {assets_path}")

                                # Also copy to a simple location for easy access (preserve extension)
                                file_ext = os.path.splitext(found_file)[1]  # Get extension (.mp4, .mov, etc)
                                simple_preview_path = os.path.join(PREVIEW_DIR, f'latest_preview{file_ext}')
                                try:
                                    shutil.copy2(assets_path, simple_preview_path)
                                    print(f"[PREVIEW WATCHER] ✅ Preview copied to easy-access location: {simple_preview_path}")
                                except Exception as simple_copy_err:
                                    print(f"[PREVIEW WATCHER] Warning: Failed to copy to simple location: {simple_copy_err}")

                                # Track preview file (kept in assets folder even after app closes)
                                app_state['preview_files_to_cleanup'].add(assets_path)

                                print("=" * 80)
                                print(f"[PREVIEW WATCHER] ✅ PREVIEW COMPLETE (timeout recovery)!")
                                print(f"[PREVIEW WATCHER] 📁 Preview saved to:")
                                print(f"[PREVIEW WATCHER]    1. Easy access: {simple_preview_path}")
                                print(f"[PREVIEW WATCHER]    2. Assets folder: {assets_path}")
                                print(f"[PREVIEW WATCHER] ℹ️ Files will persist after app closes")
                                print("=" * 80)

                                # Notify frontend
                                if app_state['window']:
                                    escaped_path = assets_path.replace('\\', '\\\\').replace('"', '\\"')
                                    safe_evaluate_js(
                                        app_state['window'],
                                        f'if(window.previewCompleted){{window.previewCompleted("{escaped_path}")}}'
                                    )
                                    print(f"[PREVIEW WATCHER] ✓ Notified frontend to load preview")
                            except Exception as recovery_err:
                                print(f"[PREVIEW WATCHER] Error recovering file: {recovery_err}")
                        else:
                            print(f"[PREVIEW WATCHER] ✗ No preview file found after final search")
                            # Notify frontend of timeout
                            if app_state['window']:
                                safe_evaluate_js(
                                    app_state['window'],
                                    f'if(window.previewFailed){{window.previewFailed("Preview timeout: No output file found after {max_wait}s. Check terminal for errors.")}}'
                                )

                        app_state['is_previewing'] = False

                        # Clean up temp file even on timeout
                        try:
                            if os.path.exists(preview_temp_file):
                                os.remove(preview_temp_file)
                                print(f"[PREVIEW WATCHER] Cleaned up temp file after timeout: {preview_temp_file}")
                        except Exception as cleanup_err:
                            print(f"[PREVIEW WATCHER] Error cleaning temp file: {cleanup_err}")

                    import threading
                    watcher_thread = threading.Thread(target=watch_preview, daemon=True)
                    watcher_thread.start()

                    return {'status': 'started', 'message': 'Preview command sent to terminal'}
                except Exception as e:
                    print(f"[PREVIEW ERROR] Failed to send to terminal: {e}")
                    app_state['is_previewing'] = False
                    return {'status': 'error', 'message': f'Failed to send command to terminal: {e}'}

            # Fallback to old subprocess method if terminal not available
            print("[PREVIEW] Terminal not available, using fallback subprocess method")

            def preview_thread():
                app_state['is_previewing'] = True
                output_lines = []

                try:
                    process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding='utf-8',  # Force UTF-8 encoding
                        errors='replace',  # Replace invalid characters instead of crashing
                        bufsize=1,
                        universal_newlines=True,
                        env=get_clean_environment(),  # Use clean environment
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )

                    app_state['preview_process'] = process

                    # Read output
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            line = line.rstrip()
                            output_lines.append(line)
                            print(f"[Preview] {line}")

                            if app_state['window']:
                                try:
                                    safe_line = line.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'").replace('\n', '\\n')
                                    app_state['window'].evaluate_js(
                                        f'if(window.updateRenderOutput){{window.updateRenderOutput("{safe_line}")}}'
                                    )
                                except Exception as e:
                                    # Ignore errors when window is disposed/closed
                                    if "disposed" not in str(e).lower():
                                        print(f"[PREVIEW] Error updating output: {e}")

                    process.wait()

                    print(f"Preview finished with code: {process.returncode}")

                    if process.returncode == 0:
                        # Wait a moment for filesystem to flush files to disk
                        print("[INFO] Waiting for files to be written to disk...")
                        time.sleep(2)  # Give OS time to flush buffers

                        # Find the rendered files in preview directory
                        final_path = self.cleanup_after_render(scene_name, media_dir=PREVIEW_DIR)

                        # Verify file actually exists and is readable before proceeding
                        if final_path and os.path.exists(final_path):
                            try:
                                # Try to open and verify the file is accessible
                                with open(final_path, 'rb') as f:
                                    f.read(1)  # Read one byte to verify it's accessible
                                print(f"[OK] Verified file exists and is accessible: {final_path}")
                                print(f"[OK] Preview file ready in preview folder: {final_path}")

                                # Copy preview file to assets and track for cleanup on exit
                                import shutil
                                os.makedirs(ASSETS_DIR, exist_ok=True)
                                assets_path = os.path.join(ASSETS_DIR, os.path.basename(final_path))

                                # If file already exists, remove it first
                                if os.path.exists(assets_path):
                                    os.remove(assets_path)

                                print(f"[PREVIEW] Copying to assets: {assets_path}")
                                shutil.copy2(final_path, assets_path)
                                print(f"[PREVIEW] Preview file copied to assets!")

                                # Also copy to a simple location for easy access (preserve extension)
                                file_ext = os.path.splitext(final_path)[1]  # Get extension (.mp4, .mov, etc)
                                simple_preview_path = os.path.join(PREVIEW_DIR, f'latest_preview{file_ext}')
                                try:
                                    shutil.copy2(assets_path, simple_preview_path)
                                    print(f"[PREVIEW] ✅ Preview copied to easy-access location: {simple_preview_path}")
                                except Exception as simple_copy_err:
                                    print(f"[PREVIEW] Warning: Failed to copy to simple location: {simple_copy_err}")

                                # Track preview file (kept in assets folder even after app closes)
                                app_state['preview_files_to_cleanup'].add(assets_path)

                                print("=" * 80)
                                print(f"[PREVIEW] ✅ PREVIEW COMPLETE!")
                                print(f"[PREVIEW] 📁 Preview saved to:")
                                print(f"[PREVIEW]    1. Easy access: {simple_preview_path}")
                                print(f"[PREVIEW]    2. Assets folder: {assets_path}")
                                print(f"[PREVIEW] ℹ️ Files will persist after app closes")
                                print("=" * 80)

                                # Use assets path for frontend notification
                                final_path = assets_path

                            except Exception as verify_error:
                                print(f"[ERROR] Failed to verify/copy preview file: {verify_error}")
                                final_path = None
                        else:
                            print(f"[WARNING] No output file found after preview")

                        if app_state['window']:
                            if final_path:
                                safe_path = final_path.replace('\\', '/').replace('"', '\\"')
                                app_state['window'].evaluate_js(
                                    f'if(window.previewCompleted){{window.previewCompleted("{safe_path}")}}'
                                )
                            else:
                                app_state['window'].evaluate_js(
                                    'if(window.previewCompleted){window.previewCompleted()}'
                                )
                    else:
                        if app_state['window']:
                            error_msg = f"Preview failed with code {process.returncode}".replace('"', '\\"')
                            app_state['window'].evaluate_js(
                                f'if(window.previewFailed){{window.previewFailed("{error_msg}")}}'
                            )

                except Exception as e:
                    print(f"Preview error: {e}")
                    if app_state['window']:
                        safe_error = str(e).replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
                        app_state['window'].evaluate_js(
                            f'if(window.previewFailed){{window.previewFailed("{safe_error}")}}'
                        )
                finally:
                    app_state['is_previewing'] = False
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                    except:
                        pass

            threading.Thread(target=preview_thread, daemon=True).start()

            return {'status': 'started', 'message': 'Preview started', 'scene': scene_name}

        except Exception as e:
            print(f"Error starting preview: {e}")
            app_state['is_previewing'] = False
            return {'status': 'error', 'message': str(e)}

    def stop_render(self):
        """Stop current render or preview"""
        try:
            # Stop render process and its entire child tree (ffmpeg, LaTeX, etc.)
            if app_state['render_process']:
                try:
                    kill_process_tree(app_state['render_process'].pid)
                    app_state['is_rendering'] = False
                    print("[STOP] Render process tree killed")
                except Exception as e:
                    print(f"[STOP] Error killing render process tree: {e}")

            # Stop preview process and its entire child tree
            if app_state['preview_process']:
                try:
                    kill_process_tree(app_state['preview_process'].pid)
                    app_state['is_previewing'] = False
                    print("[STOP] Preview process tree killed")
                except Exception as e:
                    print(f"[STOP] Error killing preview process tree: {e}")

            # If using terminal mode, send Ctrl+C
            if app_state['terminal_process']:
                try:
                    if WINPTY_AVAILABLE and hasattr(app_state['terminal_process'], 'write'):
                        # Send Ctrl+C to terminal
                        app_state['terminal_process'].write('\x03')
                        print("[STOP] Sent Ctrl+C to terminal")
                    else:
                        # For subprocess mode, send Ctrl+C
                        import signal
                        if hasattr(app_state['terminal_process'], 'send_signal'):
                            app_state['terminal_process'].send_signal(signal.SIGINT)
                            print("[STOP] Sent SIGINT to terminal")
                except Exception as e:
                    print(f"[STOP] Error sending interrupt to terminal: {e}")

            # Always reset states
            app_state['is_rendering'] = False
            app_state['is_previewing'] = False
            print("[STOP] Reset render and preview states")

            return {'status': 'success', 'message': 'Stopped active processes'}

        except Exception as e:
            print(f"[STOP] Error in stop_render: {e}")
            # Always reset states even on error
            app_state['is_rendering'] = False
            app_state['is_previewing'] = False
            return {'status': 'error', 'message': str(e)}

    def cleanup_after_render(self, scene_name, temp_filename=None, media_dir=None):
        """Find rendered files and return path - DO NOT auto-save, let user choose location"""
        try:
            import shutil

            # Use provided media_dir or default to MEDIA_DIR
            if media_dir is None:
                media_dir = MEDIA_DIR

            print("=" * 60)
            print(f"[CLEANUP] FINDING RENDERED FILES for scene: {scene_name}")
            print(f"[DIR] Media directory: {media_dir}")
            print("=" * 60)

            # Determine temp files directory (ASSETS_DIR for render, PREVIEW_DIR for preview)
            temp_files_dir = PREVIEW_DIR if media_dir == PREVIEW_DIR else ASSETS_DIR

            # Ensure temp files directory exists
            try:
                os.makedirs(temp_files_dir, exist_ok=True)
            except Exception as e:
                print(f"[ERROR] Failed to create temp directory: {e}")

            # 1. Delete temp .py files from temp directory
            print(f"\n[STEP 1] Deleting temp .py files from {temp_files_dir}...")
            temp_deleted = 0
            if os.path.exists(temp_files_dir):
                for file in os.listdir(temp_files_dir):
                    if file.startswith('temp_') and file.endswith('.py'):
                        try:
                            temp_file = os.path.join(temp_files_dir, file)
                            os.remove(temp_file)
                            temp_deleted += 1
                            print(f"   [OK] Deleted: {file}")
                        except Exception as e:
                            print(f"   [ERROR] Error deleting {file}: {e}")
            print(f"   Deleted {temp_deleted} temp file(s)")

            # 2. Find rendered media files
            print("\n[STEP 2] Finding rendered media files...")

            # IMPORTANT: Manim creates folders based on the .py filename, NOT the scene name
            # Structure: media/videos/{python_filename_without_ext}/{quality}/SceneName.mp4
            # We need to search ALL folders in media/videos/ and media/images/

            videos_base = os.path.join(media_dir, 'videos')
            images_base = os.path.join(media_dir, 'images')

            print(f"   Videos base: {videos_base}")
            print(f"   Videos base exists: {os.path.exists(videos_base)}")
            print(f"   Images base: {images_base}")
            print(f"   Images base exists: {os.path.exists(images_base)}")

            final_path = None
            found_files = []  # List of dicts: {'path': path, 'size': size_mb}
            folders_to_delete = []

            # Process videos folder - search ALL subdirectories recursively
            if os.path.exists(videos_base):
                print(f"\n   [SCAN] Scanning ALL videos folders recursively...")

                # Walk through ALL subfolders
                for root, dirs, files in os.walk(videos_base):
                    # Track temp folders for deletion
                    if 'temp_' in root:
                        # Mark entire temp folder tree for deletion
                        parent_folder = root
                        while os.path.dirname(parent_folder) != videos_base:
                            parent_folder = os.path.dirname(parent_folder)
                        if parent_folder not in folders_to_delete:
                            folders_to_delete.append(parent_folder)

                    if files:
                        print(f"\n      [DIR] Checking: {root}")
                        print(f"      Found {len(files)} file(s)")

                        for file in files:
                            print(f"         - {file}")

                            if file.endswith(('.mp4', '.mov', '.webm', '.avi')):
                                source_file = os.path.join(root, file)
                                print(f"         [OK] Video file found!")
                                print(f"            Path: {source_file}")

                                # Verify file exists and has content
                                try:
                                    if os.path.exists(source_file):
                                        size_bytes = os.path.getsize(source_file)
                                        if size_bytes > 0:
                                            size_mb = size_bytes / (1024 * 1024)
                                            print(f"            Size: {size_mb:.2f} MB")

                                            # Store path AND size together
                                            found_files.append({
                                                'path': source_file,
                                                'size': size_mb,
                                                'name': file
                                            })

                                            # Set as final path (most recent video) - this will be returned for preview
                                            if not final_path:
                                                final_path = source_file
                                                print(f"            [FINAL] Set as preview path")
                                        else:
                                            print(f"            [WARNING] File is empty")
                                    else:
                                        print(f"            [WARNING] File doesn't exist")
                                except Exception as e:
                                    print(f"            [ERROR] Error checking file: {e}")
            else:
                print(f"   [WARNING] Videos base folder does not exist: {videos_base}")

            # Process images folder (for still frames/images) - search ALL subdirectories
            if os.path.exists(images_base):
                print(f"\n   [SCAN] Scanning ALL images folders recursively...")

                for root, dirs, files in os.walk(images_base):
                    # Track temp folders for deletion
                    if 'temp_' in root:
                        parent_folder = root
                        while os.path.dirname(parent_folder) != images_base:
                            parent_folder = os.path.dirname(parent_folder)
                        if parent_folder not in folders_to_delete:
                            folders_to_delete.append(parent_folder)

                    if files:
                        print(f"\n      [DIR] Checking: {root}")
                        print(f"      Found {len(files)} file(s)")

                        for file in files:
                            print(f"         - {file}")

                            if file.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                                source_file = os.path.join(root, file)
                                print(f"         [OK] Image file found!")
                                print(f"            Path: {source_file}")

                                # Verify file exists and has content
                                try:
                                    if os.path.exists(source_file):
                                        size_bytes = os.path.getsize(source_file)
                                        if size_bytes > 0:
                                            size_mb = size_bytes / (1024 * 1024)
                                            print(f"            Size: {size_mb:.2f} MB")

                                            # Store path AND size together
                                            found_files.append({
                                                'path': source_file,
                                                'size': size_mb,
                                                'name': file
                                            })

                                            # Set as final path if no video was found
                                            if not final_path:
                                                final_path = source_file
                                                print(f"            [FINAL] Set as preview path")
                                        else:
                                            print(f"            [WARNING] File is empty")
                                    else:
                                        print(f"            [WARNING] File doesn't exist")
                                except Exception as e:
                                    print(f"            [ERROR] Error checking file: {e}")
            else:
                print(f"   [WARNING] Images base folder does not exist: {images_base}")

            # 3. Do NOT delete temp folders yet - user needs to save first!
            # Temp folders will be cleaned up after successful save or at app shutdown
            print("\n[STEP 3] Temp folders preserved until after save...")
            if folders_to_delete:
                print(f"   Found {len(folders_to_delete)} temp folder(s) to clean later")
            else:
                print(f"   No temp folders found")

            print("\n" + "=" * 60)
            print(f"[OK] FILE SEARCH COMPLETE!")
            print(f"   Found {len(found_files)} rendered file(s)")

            # Show list of found files (using stored size data)
            if found_files:
                print(f"\n   Rendered files (in MEDIA_DIR):")
                for file_info in found_files:
                    filename = file_info['name']
                    size_mb = file_info['size']
                    print(f"      - {filename} ({size_mb:.2f} MB)")
                print(f"\n   [INFO] Files will remain in MEDIA_DIR until you save them")

            if final_path:
                print(f"\n   Preview path: {final_path}")
            else:
                print(f"\n   [WARNING] No output file found - check render logs above")
            print("=" * 60 + "\n")

            # Note: Temp folders are cleaned up after successful save,
            # or at app shutdown for unsaved renders (via cleanup_on_exit)

            return final_path

        except Exception as e:
            print(f"[ERROR] CLEANUP ERROR: {e}")
            import traceback
            traceback.print_exc()
            return None

    def save_rendered_file(self, source_path, suggested_name):
        """
        Show save dialog and move rendered file from assets to user's chosen location.

        Args:
            source_path: Path to the file in assets folder
            suggested_name: Suggested filename for save dialog

        Returns:
            dict with status and message
        """
        try:
            import shutil
            from datetime import datetime

            print("=" * 60)
            print(f"[SAVE] Showing save dialog...")
            print(f"   Source: {source_path}")
            print(f"   Suggested name: {suggested_name}")
            print("=" * 60)

            # Verify source file exists
            if not os.path.exists(source_path):
                print(f"[ERROR] Source file not found: {source_path}")
                return {
                    'status': 'error',
                    'message': 'Source file not found'
                }

            # Show save dialog
            result = app_state['window'].create_file_dialog(
                dialog_type=webview.FileDialog.SAVE,
                save_filename=suggested_name,
                file_types=('Video Files (*.mp4;*.mov;*.webm)', 'All Files (*.*)')
            )

            if not result:
                print("[INFO] User cancelled save dialog")
                # Don't delete file from assets - user might want to save later
                return {
                    'status': 'cancelled',
                    'message': 'Save cancelled by user'
                }

            # Get save path
            save_path = result[0] if isinstance(result, tuple) else result
            print(f"[OK] User chose: {save_path}")

            # Ensure file has proper extension
            if not save_path.endswith(('.mp4', '.mov', '.webm', '.avi')):
                save_path += '.mp4'

            # Copy file to user's location (use copy instead of move so we can clean up render folder properly)
            print(f"[INFO] Copying file...")
            print(f"   From: {source_path}")
            print(f"   To: {save_path}")

            shutil.copy2(source_path, save_path)

            print(f"[OK] File copied successfully!")

            # Open the folder where the file was saved
            folder_path = os.path.dirname(save_path)
            print(f"\n[INFO] Opening folder: {folder_path}")
            try:
                if sys.platform == 'win32':
                    os.startfile(folder_path)
                elif sys.platform == 'darwin':
                    subprocess.run(['open', folder_path])
                else:
                    subprocess.run(['xdg-open', folder_path])
                print(f"[OK] Folder opened successfully")
            except Exception as folder_err:
                print(f"[WARNING] Could not open folder: {folder_err}")

            # Don't clear render folder after save - keep the rendered video
            # User can access it later from RENDER_DIR
            if source_path.startswith(RENDER_DIR):
                print(f"\n[INFO] Rendered video kept in: {RENDER_DIR}")
                print(f"[INFO] Video will be cleared on next render")
                print("=" * 60)
            else:
                # For other locations (assets/media), clean up temp folders as before
                print(f"\n[INFO] Cleaning up temp folders...")
                videos_base = os.path.join(MEDIA_DIR, 'videos')
                images_base = os.path.join(MEDIA_DIR, 'images')
                folders_deleted = 0

                # Delete temp folders from videos
                if os.path.exists(videos_base):
                    for folder in os.listdir(videos_base):
                        if folder.startswith('temp_'):
                            folder_path = os.path.join(videos_base, folder)
                            try:
                                shutil.rmtree(folder_path)
                                folders_deleted += 1
                                print(f"   [OK] Deleted: {folder}")
                            except Exception as e:
                                print(f"   [ERROR] Failed to delete {folder}: {e}")

                # Delete temp folders from images
                if os.path.exists(images_base):
                    for folder in os.listdir(images_base):
                        if folder.startswith('temp_'):
                            folder_path = os.path.join(images_base, folder)
                            try:
                                shutil.rmtree(folder_path)
                                folders_deleted += 1
                                print(f"   [OK] Deleted: {folder}")
                            except Exception as e:
                                print(f"   [ERROR] Failed to delete {folder}: {e}")

                print(f"[OK] Cleaned up {folders_deleted} temp folder(s)")
                print("=" * 60)

            return {
                'status': 'success',
                'message': f'File saved to {save_path}',
                'path': save_path
            }

        except Exception as e:
            print(f"[ERROR] Save error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'message': str(e)
            }

    def get_settings(self):
        """Get application settings"""
        return app_state['settings']

    def update_settings(self, settings):
        """Update application settings"""
        app_state['settings'].update(settings)
        save_settings()
        return {'status': 'success', 'settings': app_state['settings']}

    def list_media_files(self):
        """List media files from assets directory only"""
        print("\n" + "="*60)
        print("[ASSETS] list_media_files() called")
        print("="*60)

        # Show files from ASSETS_DIR (not nested MEDIA_DIR folders)
        assets_dir = ASSETS_DIR
        print(f"[ASSETS] Looking in directory: {assets_dir}")
        print(f"[ASSETS] Directory exists: {os.path.exists(assets_dir)}")

        if not os.path.exists(assets_dir):
            print("[ASSETS] Creating assets directory...")
            os.makedirs(assets_dir)
            return {'files': []}

        files = []
        all_items = os.listdir(assets_dir)
        print(f"[ASSETS] Found {len(all_items)} items in directory:")
        for item in all_items:
            print(f"  - {item}")

        # Only list files directly in ASSETS_DIR (no subdirectories)
        for filename in os.listdir(assets_dir):
            file_path = os.path.join(assets_dir, filename)
            print(f"[ASSETS] Checking: {filename}")
            print(f"  - Is file: {os.path.isfile(file_path)}")

            # Include all asset types: videos, images, fonts, audio, subtitles
            # Skip temp .py files, .pyc, and hidden files
            if os.path.isfile(file_path) and not filename.startswith('.') and not filename.endswith(('.py', '.pyc')):
                # Supported extensions
                video_exts = ('.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv', '.m4v')
                image_exts = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.bmp', '.webp', '.ico')
                font_exts = ('.ttf', '.otf', '.woff', '.woff2', '.ttc', '.eot')
                audio_exts = ('.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.wma')
                subtitle_exts = ('.srt', '.vtt', '.ass', '.ssa', '.sub')
                text_exts = ('.txt', '.md', '.json', '.xml', '.csv')

                if filename.lower().endswith(video_exts + image_exts + font_exts + audio_exts + subtitle_exts + text_exts):
                    file_info = {
                        'name': filename,
                        'path': file_path,
                        'size': os.path.getsize(file_path),
                        'mtime': os.path.getmtime(file_path)
                    }
                    files.append(file_info)
                    print(f"  [OK] Added to list: {filename} ({file_info['size']} bytes)")
                else:
                    print(f"  [SKIP] Unsupported file type: {filename}")
            else:
                if filename.startswith('.'):
                    print(f"  [SKIP] Hidden file: {filename}")
                elif filename.endswith(('.py', '.pyc')):
                    print(f"  [SKIP] Python file: {filename}")
                else:
                    print(f"  [SKIP] Not a file: {filename}")

        # Sort by modified time (newest first)
        files.sort(key=lambda x: x['mtime'], reverse=True)

        print(f"\n[ASSETS] Returning {len(files)} files")
        for f in files:
            print(f"  - {f['name']}")
        print("="*60 + "\n")

        return {'files': files}

    def open_media_folder(self):
        """Open the assets folder in file explorer"""
        try:
            # Open ASSETS_DIR instead of MEDIA_DIR
            assets_dir = ASSETS_DIR
            if not os.path.exists(assets_dir):
                os.makedirs(assets_dir)

            if sys.platform == 'win32':
                os.startfile(assets_dir)
            elif sys.platform == 'darwin':
                subprocess.run(['open', assets_dir])
            else:
                subprocess.run(['xdg-open', assets_dir])

            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def play_media(self, file_path):
        """Play media file with system default player"""
        try:
            if sys.platform == 'win32':
                os.startfile(file_path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', file_path])
            else:
                subprocess.run(['xdg-open', file_path])

            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def execute_command(self, command):
        """Execute a terminal command using persistent cmd.exe session"""
        try:
            print(f"Executing command: {command}")

            # Handle special install-venv command
            if command.strip().lower().startswith('install-venv'):
                parts = command.strip().split()
                if len(parts) >= 2:
                    response = parts[1].lower()
                    if response == 'yes':
                        # User confirmed - install venv
                        return self.install_venv()
                    elif response == 'no':
                        return {
                            'status': 'info',
                            'stdout': 'Installation skipped. You can run "install-venv yes" later to install.',
                            'stderr': '',
                            'returncode': 0
                        }
                    else:
                        return {
                            'status': 'error',
                            'stdout': '',
                            'stderr': 'Invalid response. Please type "install-venv yes" or "install-venv no"',
                            'returncode': 1
                        }
                else:
                    return {
                        'status': 'error',
                        'stdout': '',
                        'stderr': 'Usage: install-venv [yes/no]',
                        'returncode': 1
                    }

            # Handle pip install commands - redirect to venv pip
            if command.strip().lower().startswith('pip '):
                # Get venv pip executable
                if os.name == 'nt':
                    venv_pip = os.path.join(VENV_DIR, 'Scripts', 'pip.exe')
                else:
                    venv_pip = os.path.join(VENV_DIR, 'bin', 'pip')

                # Check if venv pip exists
                if not os.path.exists(venv_pip):
                    return {
                        'status': 'error',
                        'stdout': '',
                        'stderr': 'Virtual environment not found. Please set up the environment first.',
                        'returncode': 1
                    }

                # Replace 'pip' with venv pip path
                command_parts = command.strip().split(maxsplit=1)
                if len(command_parts) > 1:
                    new_command = f'"{venv_pip}" {command_parts[1]}'
                else:
                    new_command = f'"{venv_pip}"'

                print(f"Redirecting to venv pip: {new_command}")
                command = new_command

            # Use persistent cmd.exe session for all commands
            return self.send_terminal_command(command)

        except Exception as e:
            print(f"Error executing command: {e}")
            return {'status': 'error', 'message': str(e), 'stdout': '', 'stderr': '', 'returncode': 1}

    def start_persistent_terminal(self):
        """Start a persistent cmd.exe session using PTY (pywinpty) when available"""
        try:
            if app_state['terminal_process'] is not None:
                return {'status': 'info', 'message': 'Terminal already running'}

            print("[TERMINAL] Starting persistent cmd.exe session...")

            if WINPTY_AVAILABLE:
                print("[TERMINAL] Using pywinpty PTY for real terminal emulation")

                # Spawn cmd.exe with PTY
                # Use wider terminal to properly display progress bars
                terminal_process = winpty.PTY(120, 30)  # 120 columns, 30 rows for better tqdm display
                terminal_process.spawn('cmd.exe')

                app_state['terminal_process'] = terminal_process
                app_state['terminal_output_buffer'] = []
                app_state['terminal_error_buffer'] = []

                # Start background thread to read terminal output
                def read_terminal_output():
                    print("[TERMINAL PTY] Background reader thread started")
                    while True:
                        try:
                            # Read from PTY - this will block until data is available
                            # pywinpty.PTY.read() reads all available data
                            data = terminal_process.read()
                            if data:
                                app_state['terminal_output_buffer'].append(data)
                                app_state['terminal_error_buffer'].append(data)

                                # Keep error buffer to last 1000 items to prevent memory bloat
                                if len(app_state['terminal_error_buffer']) > 1000:
                                    app_state['terminal_error_buffer'] = app_state['terminal_error_buffer'][-1000:]

                                # Debug: Print when we receive progress bar updates (contains \r or ANSI codes)
                                if '\r' in data or '\x1b[' in data:
                                    # This is likely a progress bar update
                                    pass  # Silent - just capturing it
                        except Exception as e:
                            error_msg = str(e).lower()
                            # Ignore common non-error conditions
                            if "closed" not in error_msg and "timeout" not in error_msg and "no data" not in error_msg:
                                print(f"[TERMINAL PTY ERROR] {e}")
                            time.sleep(0.01)
                    print("[TERMINAL PTY] Background reader thread stopped")

                terminal_thread = threading.Thread(target=read_terminal_output, daemon=True)
                terminal_thread.start()
                app_state['terminal_thread'] = terminal_thread

                print("[TERMINAL PTY] Terminal started successfully")
                time.sleep(0.5)

                # Initialize terminal: cd to ASSETS_DIR and activate venv
                print(f"[TERMINAL PTY] Setting up initial environment...")

                # Change to assets directory
                terminal_process.write(f'cd /d "{ASSETS_DIR}"\r\n')
                time.sleep(0.3)

                # Activate virtual environment
                if os.name == 'nt':
                    activate_script = os.path.join(VENV_DIR, 'Scripts', 'activate.bat')
                else:
                    activate_script = os.path.join(VENV_DIR, 'bin', 'activate')

                if os.path.exists(activate_script):
                    terminal_process.write(f'call "{activate_script}"\r\n')
                    time.sleep(0.5)
                    print(f"[TERMINAL PTY] Activated venv at: {VENV_DIR}")
                else:
                    print(f"[TERMINAL PTY WARNING] Venv activate script not found: {activate_script}")

                # Wait for prompt to appear and clear screen
                time.sleep(0.5)

                # Clear the screen to hide initialization commands
                terminal_process.write('cls\r\n')
                time.sleep(0.2)

                # Clear the output buffer so initialization isn't shown to user
                # Keep error buffer for now - it will be cleared when a render/preview starts
                app_state['terminal_output_buffer'] = []

                print("[TERMINAL PTY] Environment setup complete")
                return {'status': 'success', 'message': 'PTY terminal started'}

            else:
                # Fallback to subprocess.Popen
                print("[TERMINAL] Using fallback subprocess mode (no PTY)")

                terminal_process = subprocess.Popen(
                    ['cmd.exe'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=0,
                    env=get_clean_environment(),
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )

                app_state['terminal_process'] = terminal_process
                app_state['terminal_output_buffer'] = []
                app_state['terminal_error_buffer'] = []

                def read_terminal_output():
                    while terminal_process.poll() is None:
                        try:
                            line = terminal_process.stdout.readline()
                            if line:
                                app_state['terminal_output_buffer'].append(line)
                                app_state['terminal_error_buffer'].append(line)

                                # Keep error buffer to last 1000 items to prevent memory bloat
                                if len(app_state['terminal_error_buffer']) > 1000:
                                    app_state['terminal_error_buffer'] = app_state['terminal_error_buffer'][-1000:]

                                print(f"[TERMINAL] {line.rstrip()}")
                        except Exception as e:
                            print(f"[TERMINAL ERROR] {e}")
                            break

                terminal_thread = threading.Thread(target=read_terminal_output, daemon=True)
                terminal_thread.start()
                app_state['terminal_thread'] = terminal_thread

                print("[TERMINAL] Terminal started successfully")
                time.sleep(0.5)

                # Initialize environment
                # Keep error buffer for now - it will be cleared when a render/preview starts
                app_state['terminal_output_buffer'] = []
                terminal_process.stdin.write(f'cd /d "{ASSETS_DIR}"\n')
                terminal_process.stdin.flush()
                time.sleep(0.2)

                if os.name == 'nt':
                    activate_script = os.path.join(VENV_DIR, 'Scripts', 'activate.bat')
                else:
                    activate_script = os.path.join(VENV_DIR, 'bin', 'activate')

                if os.path.exists(activate_script):
                    terminal_process.stdin.write(f'call "{activate_script}"\n')
                    terminal_process.stdin.flush()
                    time.sleep(0.3)

                time.sleep(0.5)
                # Keep error buffer for now - it will be cleared when a render/preview starts
                app_state['terminal_output_buffer'] = []
                return {'status': 'success', 'message': 'Fallback terminal started'}

        except Exception as e:
            print(f"[TERMINAL ERROR] Failed to start terminal: {e}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def send_terminal_command(self, data):
        """Send data (raw input) to persistent terminal PTY"""
        try:
            if app_state['terminal_process'] is None:
                # Auto-start terminal if not running
                result = self.start_persistent_terminal()
                if result['status'] != 'success':
                    return result
                time.sleep(0.5)  # Wait for terminal to initialize

            terminal_process = app_state['terminal_process']

            # Check if using PTY mode or fallback mode
            if WINPTY_AVAILABLE and hasattr(terminal_process, 'write'):
                # PTY mode - send raw data
                terminal_process.write(data)
            else:
                # Fallback mode - use stdin
                terminal_process.stdin.write(data)
                terminal_process.stdin.flush()

            return {'status': 'success'}

        except Exception as e:
            print(f"[TERMINAL ERROR] {e}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def resize_terminal(self, cols, rows):
        """Resize the PTY terminal"""
        try:
            if app_state['terminal_process'] is None:
                return {'status': 'error', 'message': 'Terminal not running'}

            terminal_process = app_state['terminal_process']

            # Check if using PTY mode and has set_size method
            if WINPTY_AVAILABLE and hasattr(terminal_process, 'set_size'):
                print(f"[TERMINAL] Resizing PTY to {cols}x{rows}")
                terminal_process.set_size(cols, rows)
                return {'status': 'success'}
            else:
                # Fallback mode doesn't support resize
                return {'status': 'success', 'message': 'Resize not supported in fallback mode'}

        except Exception as e:
            print(f"[TERMINAL RESIZE ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def get_terminal_output(self):
        """Get all terminal output (for continuous display)"""
        try:
            if app_state['terminal_process'] is None:
                print("[TERMINAL] Process not running, auto-starting...")
                # Auto-start terminal if not running
                self.start_persistent_terminal()
                time.sleep(0.5)  # Wait for initialization

            # Return all buffered output and clear buffer
            output = ''.join(app_state['terminal_output_buffer'])
            app_state['terminal_output_buffer'] = []

            # Only log when there's actual output (reduce spam)
            # if output:
            #     print(f"[TERMINAL] Returning {len(output)} bytes to frontend")

            return {
                'status': 'success',
                'output': output,
                'is_running': app_state['terminal_process'] is not None
            }

        except Exception as e:
            print(f"[TERMINAL ERROR] {e}")
            return {
                'status': 'error',
                'message': str(e),
                'output': '',
                'is_running': False
            }

    def check_claude_code_installed(self):
        """Check if Claude Code CLI is installed"""
        try:
            # Try to run claude --version
            result = subprocess.run(
                ['claude', '--version'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=5,
                env=get_clean_environment()
            )

            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"[CLAUDE CODE] Found: {version}")
                return {
                    'status': 'success',
                    'installed': True,
                    'version': version
                }
            else:
                return {
                    'status': 'success',
                    'installed': False,
                    'message': 'Claude Code not found'
                }

        except FileNotFoundError:
            print("[CLAUDE CODE] Not installed (command not found)")
            return {
                'status': 'success',
                'installed': False,
                'message': 'Claude Code not installed. Install with: npm install -g @anthropic-ai/claude-code'
            }
        except Exception as e:
            print(f"[CLAUDE CODE ERROR] {e}")
            return {
                'status': 'error',
                'message': str(e),
                'installed': False
            }

    # ── Cached model list ──
    _cached_models = None

    @staticmethod
    def _model_id_to_display(model_id):
        """Convert a model ID like 'claude-sonnet-4-6' → 'Sonnet 4.6'."""
        import re
        s = model_id.strip()
        # Remove 'claude-' prefix
        s = re.sub(r'^claude-', '', s)
        # Remove dated suffix like -20250514 or -20251001
        s = re.sub(r'-\d{8}$', '', s)
        # Parse family-major-minor  e.g. 'sonnet-4-6', 'opus-4-6', 'haiku-4-5'
        m = re.match(r'([a-z]+)-(\d+)-(\d+)', s)
        if m:
            family = m.group(1).capitalize()
            return f"{family} {m.group(2)}.{m.group(3)}"
        # Alias like 'sonnet', 'opus', 'haiku'
        m2 = re.match(r'([a-z]+)-(\d+)-(\d+)', s)
        if not m2:
            return s.capitalize()
        return s

    def get_claude_models(self):
        """Return {current_model, models: [{id, display_name}]}.

        Fetches available models from:
          1. Anthropic API  (if ANTHROPIC_API_KEY is set)
          2. ~/.claude.json  usage history (models the user actually used)
          3. Known current model aliases as fallback

        Also returns the currently configured model from settings.
        """
        import json as _json
        import re

        home_dir = os.path.expanduser('~')
        project_dir = os.path.dirname(os.path.abspath(__file__))

        # ── 1. Detect current configured model from settings ──
        current_model = ''
        if os.name == 'nt':
            managed = os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'),
                                   'ClaudeCode', 'managed-settings.json')
        else:
            managed = '/etc/claude-code/managed-settings.json'

        settings_paths = [
            managed,
            os.path.join(project_dir, '.claude', 'settings.local.json'),
            os.path.join(project_dir, '.claude', 'settings.json'),
            os.path.join(home_dir, '.claude', 'settings.json'),
        ]
        for path in settings_paths:
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = _json.load(f)
                    val = data.get('model')
                    if val:
                        current_model = str(val)
                        break
                except Exception:
                    pass
        if not current_model:
            current_model = os.environ.get('ANTHROPIC_MODEL', '')

        # ── 2. Return cache if available ──
        if ManimAPI._cached_models is not None:
            return {'current_model': current_model, 'models': ManimAPI._cached_models}

        fetched_models = []

        # ── 3. Read usage history from ~/.claude.json ──
        usage_model_ids = set()
        claude_json = os.path.join(home_dir, '.claude.json')
        if os.path.isfile(claude_json):
            try:
                with open(claude_json, 'r', encoding='utf-8') as f:
                    cj = _json.load(f)
                projects = cj.get('projects', {})
                for pkey, pval in projects.items():
                    if isinstance(pval, dict):
                        usage = pval.get('lastModelUsage', {})
                        if isinstance(usage, dict):
                            for mid in usage.keys():
                                if mid and 'claude' in mid:
                                    usage_model_ids.add(mid)
            except Exception as e:
                print(f"[AI MODELS] Failed to read .claude.json: {e}")

        # ── 4. Merge: API results + usage history ──
        seen_ids = {m['id'] for m in fetched_models}
        for mid in usage_model_ids:
            if mid not in seen_ids:
                fetched_models.append({
                    'id': mid,
                    'display_name': self._model_id_to_display(mid)
                })
                seen_ids.add(mid)

        # ── 5. Deduplicate: keep only the latest version per family ──
        # Group by family (sonnet, opus, haiku)
        family_map = {}  # family → {version_tuple: model_info}
        other_models = []
        for m in fetched_models:
            mid = m['id']
            match = re.match(r'claude-([a-z]+)-(\d+)-(\d+)', mid)
            if match:
                family = match.group(1)
                ver = (int(match.group(2)), int(match.group(3)))
                if family not in family_map or ver > family_map[family][0]:
                    family_map[family] = (ver, m)
            else:
                other_models.append(m)

        # Build final list: latest per family, sorted by relevance
        final_models = []
        family_order = ['sonnet', 'opus', 'haiku']
        for fam in family_order:
            if fam in family_map:
                final_models.append(family_map[fam][1])
        # Add any families not in the default order
        for fam, (ver, m) in family_map.items():
            if fam not in family_order:
                final_models.append(m)

        # If nothing was found at all, provide known defaults
        if not final_models:
            final_models = [
                {'id': 'sonnet', 'display_name': 'Sonnet (latest)'},
                {'id': 'opus', 'display_name': 'Opus (latest)'},
                {'id': 'haiku', 'display_name': 'Haiku (latest)'},
            ]

        ManimAPI._cached_models = final_models
        return {'current_model': current_model, 'models': final_models}

    # ── Streaming AI edit state ──
    _ai_proc = None           # subprocess.Popen
    _ai_output_buf = ''       # accumulated stdout+stderr (merged)
    _ai_done = False
    _ai_returncode = None
    _ai_workspace = None      # isolated temp workspace directory
    _ai_code_file = None      # path to scene.py inside workspace
    _ai_prompt_file = None    # path to instruction file inside workspace
    _ai_original_code = ''    # original code for comparison

    def ai_edit_code(self, code, prompt, model='', selected_code='',
                     selection_start=0, selection_end=0):
        """Start a real Claude Code agent edit in an isolated workspace.
        Claude Code runs with Read/Write/Edit tools and up to 10 turns,
        working in a temp directory with a copy of the code.
        Use ai_edit_poll() to read live output and the final result.

        Args:
            code:            The full source code.
            prompt:          The instruction for Claude.
            model:           Optional model alias (e.g. 'sonnet', 'opus', 'haiku').
            selected_code:   If non-empty, only this portion should be edited.
            selection_start: 1-based start line of the selection.
            selection_end:   1-based end line of the selection.
        """
        import threading

        # If a previous process is still running, kill it
        self.ai_edit_cancel()

        try:
            check_result = self.check_claude_code_installed()
            if not check_result.get('installed', False):
                return {
                    'status': 'error',
                    'message': 'Claude Code not installed. Install it with: npm install -g @anthropic-ai/claude-code'
                }

            has_selection = bool(selected_code and selected_code.strip())

            print(f"[AI EDIT] Starting Claude Code agent edit...")
            print(f"[AI EDIT] Prompt: {prompt}")
            print(f"[AI EDIT] Selection: {'lines ' + str(selection_start) + '-' + str(selection_end) if has_selection else 'whole file'}")
            if model:
                print(f"[AI EDIT] Model: {model}")

            # ── Create isolated workspace (acts as a lightweight sandbox) ──
            ts = int(time.time())
            workspace = os.path.join(PREVIEW_DIR, f'ai_workspace_{ts}')
            os.makedirs(workspace, exist_ok=True)

            # Copy code into the workspace as scene.py
            code_file = os.path.join(workspace, 'scene.py')
            with open(code_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # ── Create CLAUDE.md — Claude Code auto-reads this on startup ──
            claude_md = os.path.join(workspace, 'CLAUDE.md')
            with open(claude_md, 'w', encoding='utf-8') as f:
                f.write(
                    "# Workspace Rules\n\n"
                    "You are a **code editor**. Your only job is to edit `scene.py`.\n\n"
                    "## Workflow\n"
                    "1. Read `scene.py` with the Read tool\n"
                    "2. Apply the requested changes using the Edit or Write tool\n"
                    "3. Done — do NOT explain, do NOT create new files\n\n"
                    "## Important\n"
                    "- Always modify `scene.py` directly — never just describe changes\n"
                    "- Use the Edit tool for targeted changes or Write tool for full rewrites\n"
                    "- Keep all existing code that wasn't asked to change\n"
                    "- This is a Manim (animation library) Python file\n"
                )

            print(f"[AI EDIT] Workspace: {workspace}")
            print(f"[AI EDIT] Code file: {code_file} ({len(code)} chars)")

            # ── Build the instruction prompt ──
            if has_selection:
                instruction = (
                    f"Edit scene.py — ONLY lines {selection_start}-{selection_end}.\n\n"
                    f"Selected code (lines {selection_start}-{selection_end}):\n"
                    f"```\n{selected_code}\n```\n\n"
                    f"Instruction: {prompt}"
                )
            else:
                instruction = (
                    f"Edit scene.py according to this instruction: {prompt}"
                )

            # Write instruction to a file (avoids Windows cmd.exe quoting issues)
            prompt_file = os.path.join(workspace, 'instruction.txt')
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(instruction)

            # ── Write system prompt file (avoids cmd.exe quoting issues) ──
            sys_prompt_file = os.path.join(workspace, 'system_prompt.txt')
            with open(sys_prompt_file, 'w', encoding='utf-8') as f:
                f.write(
                    "You are a code editor. Your ONLY task is to edit scene.py.\n"
                    "ALWAYS use the Edit or Write tool to modify scene.py directly.\n"
                    "Never just describe changes - apply them to the file.\n"
                    "Do not create new files. Do not run commands.\n"
                    "After editing, you are done."
                )

            # ── Build command — real Claude Code with full tool access ──
            # No --max-turns: lets Claude finish complex edits without hitting limits
            # --dangerously-skip-permissions: needed for non-interactive tool use
            # --no-session-persistence:       don't save sessions to disk
            # --append-system-prompt-file:    reinforces editing behavior
            # stderr=STDOUT merges streams (Claude CLI on Windows writes to stderr)
            model_flag = f' --model "{model}"' if model else ''
            command = (
                f'type "{prompt_file}" | claude -p'
                f' --dangerously-skip-permissions'
                f' --no-session-persistence'
                f'{model_flag}'
                f' --output-format text'
                f' --append-system-prompt-file "{sys_prompt_file}"'
            )

            # Reset state
            ManimAPI._ai_output_buf = ''
            ManimAPI._ai_done = False
            ManimAPI._ai_returncode = None
            ManimAPI._ai_workspace = workspace
            ManimAPI._ai_code_file = code_file
            ManimAPI._ai_prompt_file = prompt_file
            ManimAPI._ai_original_code = code

            # Start the subprocess
            env = get_clean_environment()
            # Remove CLAUDECODE env var so claude CLI doesn't reject nested launch
            env.pop('CLAUDECODE', None)
            env.pop('CLAUDE_CODE_ENTRYPOINT', None)

            print(f"[AI EDIT] Command: {command}")
            ManimAPI._ai_proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr → stdout
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,   # line-buffered for better streaming
                cwd=workspace,  # Run in isolated workspace
                env=env
            )

            # Background thread reads combined stdout+stderr for live streaming display
            def _reader():
                proc = ManimAPI._ai_proc
                try:
                    while True:
                        ch = proc.stdout.read(1)
                        if ch == '':
                            break  # EOF
                        ManimAPI._ai_output_buf += ch
                except Exception as e:
                    print(f"[AI EDIT] Reader error: {e}")

                proc.wait()
                ManimAPI._ai_returncode = proc.returncode
                ManimAPI._ai_done = True
                print(f"[AI EDIT] Process finished, code={proc.returncode}, {len(ManimAPI._ai_output_buf)} chars")

            t = threading.Thread(target=_reader, daemon=True)
            t.start()

            return {'status': 'started', 'message': 'Claude is editing...'}

        except Exception as e:
            print(f"[AI EDIT ERROR] {e}")
            return {'status': 'error', 'message': str(e)}

    def ai_edit_poll(self):
        """Poll the streaming AI edit.  Returns current output and status.
        Call repeatedly from JS (e.g. every 300ms) to update the UI live.

        When done, reads the modified file from the workspace (Claude Code
        edits the file directly using its Write/Edit tools).  Falls back to
        extracting code from text output if the file wasn't modified.
        """
        import shutil

        if ManimAPI._ai_proc is None:
            return {'status': 'idle', 'output': '', 'done': True}

        output = ManimAPI._ai_output_buf

        if ManimAPI._ai_done:
            code_file = ManimAPI._ai_code_file
            workspace = ManimAPI._ai_workspace
            original  = ManimAPI._ai_original_code

            edited_code = None

            # Log workspace contents for debugging
            if workspace and os.path.exists(workspace):
                try:
                    ws_files = os.listdir(workspace)
                    print(f"[AI EDIT] Workspace files after edit: {ws_files}")
                except Exception:
                    pass

            # ── Strategy 1: Read the modified file from workspace ──
            # Claude Code uses Write/Edit tools to modify scene.py directly
            if code_file and os.path.exists(code_file):
                try:
                    with open(code_file, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    # Only use if the file was actually changed
                    if file_content.strip() and file_content != original:
                        edited_code = file_content
                        print(f"[AI EDIT] Strategy 1: Got modified scene.py ({len(edited_code)} chars)")
                    else:
                        print(f"[AI EDIT] Strategy 1: scene.py unchanged ({len(file_content)} chars)")
                except Exception as e:
                    print(f"[AI EDIT] Strategy 1 failed: {e}")

            # ── Strategy 2: Extract code from text output (fallback) ──
            if not edited_code and output.strip():
                extracted = self._extract_code_from_ai_response(output.strip())
                if extracted:
                    edited_code = extracted
                    print(f"[AI EDIT] Strategy 2: Extracted code from text output ({len(edited_code)} chars)")
                else:
                    print(f"[AI EDIT] Strategy 2: Text output is not code ({len(output)} chars): {output[:200]}")

            # ── Clean up workspace ──
            if workspace and os.path.exists(workspace):
                try:
                    shutil.rmtree(workspace, ignore_errors=True)
                    print(f"[AI EDIT] Cleaned up workspace: {workspace}")
                except Exception:
                    pass

            if edited_code:
                return {
                    'status': 'success',
                    'output': output,
                    'edited_code': edited_code,
                    'done': True,
                    'message': 'Done!'
                }
            else:
                err = output or 'Unknown error (no output from Claude)'
                return {
                    'status': 'error',
                    'output': output,
                    'done': True,
                    'message': f'Claude Code error: {err[:500]}'
                }

        # Still running — return partial output
        return {
            'status': 'streaming',
            'output': output,
            'done': False,
            'chars': len(output)
        }

    def ai_edit_cancel(self):
        """Cancel a running AI edit process and clean up workspace."""
        import shutil

        if ManimAPI._ai_proc and not ManimAPI._ai_done:
            try:
                ManimAPI._ai_proc.kill()
                print("[AI EDIT] Process cancelled by user")
            except Exception:
                pass
        ManimAPI._ai_proc = None
        ManimAPI._ai_done = False
        ManimAPI._ai_output_buf = ''
        ManimAPI._ai_returncode = None
        ManimAPI._ai_original_code = ''
        # Clean up workspace directory
        workspace = ManimAPI._ai_workspace
        if workspace and os.path.exists(workspace):
            try:
                shutil.rmtree(workspace, ignore_errors=True)
                print(f"[AI EDIT] Cleaned up workspace: {workspace}")
            except Exception:
                pass
        ManimAPI._ai_workspace = None
        ManimAPI._ai_code_file = None
        ManimAPI._ai_prompt_file = None
        return {'status': 'cancelled'}

    @staticmethod
    def _extract_code_from_ai_response(raw):
        """Strip markdown fences, 'Here is...' preamble, trailing explanations.
        Returns only the Python code, or None if response is not code."""
        import re
        text = raw.strip()

        if not text:
            return None

        # 1) If wrapped in ```python ... ``` or ``` ... ```, extract the content
        fence_match = re.search(r'```(?:python)?\s*\n(.*?)```', text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
            return text if text else None

        # 2) Quick sanity check: does the response look like code at all?
        #    If it has common Python patterns it's likely code
        code_indicators = [
            r'^\s*(from|import)\s+',
            r'^\s*class\s+\w+',
            r'^\s*def\s+\w+',
            r'^\s*self\.',
            r'^\s*#',
        ]
        has_code = any(
            re.search(pat, text, re.MULTILINE)
            for pat in code_indicators
        )
        if not has_code:
            # Response doesn't contain any Python code — likely conversational text
            print(f"[AI EDIT] Response doesn't look like code, raw length={len(text)}")
            return None

        # 3) Strip common preamble lines
        lines = text.split('\n')
        start = 0
        preamble_patterns = [
            r'^here\s+(is|are)',
            r'^sure[,!.]',
            r'^i\'ve\s+(updated|modified|edited|fixed|changed)',
            r'^the\s+(updated|modified|edited|fixed|new)',
            r'^below\s+is',
            r'^this\s+(code|version|script)',
            r'^certainly',
            r'^of\s+course',
            r'^it\s+looks\s+like',
            r'^i\s+need',
            r'^please\s+',
            r'^in\s+the\s+meantime',
            r'^could\s+you',
        ]
        for i, line in enumerate(lines):
            stripped = line.strip().lower()
            if not stripped:
                continue
            if any(re.match(p, stripped) for p in preamble_patterns):
                start = i + 1
                # Skip blank lines after preamble
                while start < len(lines) and not lines[start].strip():
                    start += 1
                continue
            break

        # 4) Strip common postamble from the end
        end = len(lines)
        postamble_patterns = [
            r'^(this|the|i|note|key|these)\s+(code|change|modif|update|add|version|script|fix)',
            r'^let\s+me\s+know',
            r'^i\s+(hope|made|also|added)',
            r'^explanation',
            r'^changes?\s*(made|:)',
            r'^what\s+(i|this)',
            r'^\*\*',
            r'^\d+\.\s+\*\*',
            r'^please\s+approve',
        ]
        for i in range(len(lines) - 1, start - 1, -1):
            stripped = lines[i].strip().lower()
            if not stripped:
                continue
            if any(re.match(p, stripped) for p in postamble_patterns):
                end = i
                # Also skip blank lines before postamble
                while end > start and not lines[end - 1].strip():
                    end -= 1
                continue
            break

        cleaned = '\n'.join(lines[start:end]).strip()
        return cleaned if cleaned else None

    def get_python_path(self):
        """Return the venv Python executable path (used by the LSP client for type resolution)."""
        if os.name == 'nt':
            python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
        else:
            python = os.path.join(VENV_DIR, 'bin', 'python')
        return python if os.path.exists(python) else None

    # ── LSP (basedpyright / pyright) ─────────────────────────────────────────

    def start_lsp(self):
        """
        Start basedpyright-langserver (or pyright-langserver) from the venv as a
        stdio subprocess.  A background thread reads its stdout and pushes each
        JSON-RPC message to the frontend via window.lspReceive(jsonString).
        Returns immediately so the UI is never blocked.
        """
        import json as _json

        if app_state['lsp_running']:
            return {'status': 'already_running'}

        # ── find the language-server executable ──────────────────────────────
        candidates = []
        if os.name == 'nt':
            scripts = os.path.join(VENV_DIR, 'Scripts')
            candidates = [
                os.path.join(scripts, 'basedpyright-langserver.exe'),
                os.path.join(scripts, 'pyright-langserver.exe'),
            ]
        else:
            bin_dir = os.path.join(VENV_DIR, 'bin')
            candidates = [
                os.path.join(bin_dir, 'basedpyright-langserver'),
                os.path.join(bin_dir, 'pyright-langserver'),
            ]

        lsp_exe = next((p for p in candidates if os.path.exists(p)), None)
        if not lsp_exe:
            print('[LSP] Neither basedpyright-langserver nor pyright-langserver found in venv.')
            print('[LSP] Install with: pip install basedpyright')
            return {'status': 'error', 'message': 'basedpyright not installed in venv'}

        print(f'[LSP] Starting language server: {lsp_exe}')

        try:
            env = get_clean_environment()
            proc = subprocess.Popen(
                [lsp_exe, '--stdio'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            app_state['lsp_process'] = proc
            app_state['lsp_running'] = True
            print(f'[LSP] Language server PID: {proc.pid}')
        except Exception as e:
            print(f'[LSP] Failed to start language server: {e}')
            return {'status': 'error', 'message': str(e)}

        # ── background stdout reader ─────────────────────────────────────────
        def _read_lsp():
            buf = b''
            while app_state['lsp_running']:
                try:
                    # Accumulate bytes until we have the full header block
                    while b'\r\n\r\n' not in buf:
                        byte = proc.stdout.read(1)
                        if not byte:            # EOF — server exited
                            app_state['lsp_running'] = False
                            print('[LSP] Server stdout closed (EOF)')
                            return
                        buf += byte

                    header_raw, buf = buf.split(b'\r\n\r\n', 1)
                    content_length = 0
                    for line in header_raw.decode('ascii', errors='replace').split('\r\n'):
                        if line.lower().startswith('content-length:'):
                            content_length = int(line.split(':', 1)[1].strip())

                    # Read exactly content_length bytes (may arrive in chunks)
                    while len(buf) < content_length:
                        chunk = proc.stdout.read(content_length - len(buf))
                        if not chunk:
                            app_state['lsp_running'] = False
                            return
                        buf += chunk

                    message_bytes = buf[:content_length]
                    buf = buf[content_length:]

                    message_str = message_bytes.decode('utf-8', errors='replace')

                    # Push to JS — use json.dumps so the string is a valid JS string literal
                    if app_state.get('window'):
                        js_arg = _json.dumps(message_str)   # e.g. "\"...escaped...\""
                        safe_evaluate_js(
                            app_state['window'],
                            f'window.lspReceive({js_arg})'
                        )

                except Exception as exc:
                    if app_state['lsp_running']:
                        print(f'[LSP] Reader error: {exc}')
                    break

            app_state['lsp_running'] = False
            print('[LSP] Reader thread stopped')

        threading.Thread(target=_read_lsp, daemon=True, name='lsp-reader').start()
        return {'status': 'ok', 'exe': lsp_exe}

    def lsp_send(self, message):
        """
        Write one JSON-RPC message (already serialised to a string) to the
        language server's stdin, prefixed with the required Content-Length header.
        """
        proc = app_state.get('lsp_process')
        if not proc or proc.poll() is not None:
            return {'status': 'error', 'message': 'LSP not running'}
        try:
            encoded = message.encode('utf-8')
            frame = (
                f'Content-Length: {len(encoded)}\r\n\r\n'.encode('ascii')
                + encoded
            )
            proc.stdin.write(frame)
            proc.stdin.flush()
            return {'status': 'ok'}
        except Exception as e:
            print(f'[LSP] lsp_send error: {e}')
            return {'status': 'error', 'message': str(e)}

    def lsp_is_running(self):
        """Return whether the language server process is alive."""
        proc = app_state.get('lsp_process')
        running = bool(proc and proc.poll() is None)
        return {'running': running}

    def setup_lsp_workspace(self):
        """
        Create a real workspace directory for basedpyright and write a
        pyrightconfig.json that points at the Manim venv.
        Returns the workspace URI and scene-file URI so JS can use real paths.
        """
        import json as _json

        workspace_dir = os.path.join(USER_DATA_DIR, 'lsp_workspace')
        os.makedirs(workspace_dir, exist_ok=True)

        # venvPath = parent of VENV_DIR, venv = name of the venv folder
        venv_parent = os.path.dirname(VENV_DIR)
        venv_name   = os.path.basename(VENV_DIR)

        config = {
            'venvPath':              venv_parent,
            'venv':                  venv_name,
            'typeCheckingMode':      'basic',
            'useLibraryCodeForTypes': True,
            # suppress noise for generated/dynamic Manim attributes
            'reportAttributeAccessIssue':  'warning',
            'reportMissingModuleSource':   'none',
        }

        python_path = self.get_python_path()
        if python_path:
            config['pythonPath'] = python_path

        config_path = os.path.join(workspace_dir, 'pyrightconfig.json')
        with open(config_path, 'w', encoding='utf-8') as f:
            _json.dump(config, f, indent=2)

        # Build a proper file:// URI (handles Windows drive letters)
        ws_posix = workspace_dir.replace('\\', '/')
        if not ws_posix.startswith('/'):
            ws_posix = '/' + ws_posix          # e.g.  /C:/Users/...

        workspace_uri = 'file://' + ws_posix
        file_uri      = workspace_uri + '/scene.py'

        print(f'[LSP] Workspace: {workspace_dir}')
        print(f'[LSP] pyrightconfig.json written (venv={venv_name})')

        return {
            'status':        'success',
            'workspace_uri': workspace_uri,
            'file_uri':      file_uri,
            'workspace_dir': workspace_dir,
        }

    def list_assets(self):
        """List all assets in the assets directory"""
        try:
            if not os.path.exists(ASSETS_DIR):
                os.makedirs(ASSETS_DIR, exist_ok=True)
                return {'directory': ASSETS_DIR, 'files': []}

            files = []
            previewable_ext = {'.mp4', '.mov', '.gif', '.png', '.jpg', '.jpeg', '.webp', '.webm'}

            for filename in os.listdir(ASSETS_DIR):
                if filename.startswith('temp_scene_'):
                    continue  # Skip temp files

                full_path = os.path.join(ASSETS_DIR, filename)

                if os.path.isfile(full_path):
                    try:
                        stat = os.stat(full_path)
                        ext = os.path.splitext(filename)[1].lower()
                        files.append({
                            'name': filename,
                            'path': full_path,
                            'size': stat.st_size,
                            'modified': stat.st_mtime,
                            'previewable': ext in previewable_ext
                        })
                    except:
                        continue

            files.sort(key=lambda x: x['modified'], reverse=True)
            return {'directory': ASSETS_DIR, 'files': files}

        except Exception as e:
            return {'directory': ASSETS_DIR, 'files': [], 'error': str(e)}

    def add_assets(self, file_paths):
        """Add assets by copying files to assets directory"""
        try:
            import shutil

            if not file_paths or not isinstance(file_paths, list):
                return {'status': 'error', 'message': 'No file paths provided'}

            os.makedirs(ASSETS_DIR, exist_ok=True)

            added = 0
            errors = []

            for src_path in file_paths:
                try:
                    if not os.path.exists(src_path):
                        errors.append(f'File not found: {src_path}')
                        continue

                    filename = os.path.basename(src_path)
                    dest_path = os.path.join(ASSETS_DIR, filename)

                    shutil.copy2(src_path, dest_path)
                    added += 1
                    print(f'[OK] Copied asset: {filename}')

                except Exception as e:
                    errors.append(f'Failed to copy {os.path.basename(src_path)}: {str(e)}')

            return {
                'status': 'success' if added > 0 else 'error',
                'added': added,
                'total': len(file_paths),
                'errors': errors if errors else None,
                'message': f'Added {added} file(s)' if added > 0 else 'Failed to add files'
            }

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def get_asset_as_bytes(self, file_path):
        """Return file as base64-encoded bytes for frontend to convert to Blob"""
        try:
            import base64
            import mimetypes

            print(f"[ASSET] get_asset_as_bytes called with: {file_path}")

            if not os.path.exists(file_path):
                print(f"[ASSET ERROR] File not found: {file_path}")
                return {'status': 'error', 'message': 'File not found', 'data': None}

            # Read file as binary
            with open(file_path, 'rb') as f:
                file_data = f.read()

            # Encode to base64 for transfer
            base64_data = base64.b64encode(file_data).decode('utf-8')

            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                ext = os.path.splitext(file_path)[1].lower()
                mime_types_map = {
                    '.mp4': 'video/mp4',
                    '.mov': 'video/quicktime',
                    '.webm': 'video/webm',
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif'
                }
                mime_type = mime_types_map.get(ext, 'application/octet-stream')

            print(f"[ASSET] File size: {len(file_data)} bytes")
            print(f"[ASSET] Base64 length: {len(base64_data)} chars")
            print(f"[ASSET] MIME type: {mime_type}")

            return {
                'status': 'success',
                'data': base64_data,  # Base64 encoded binary data
                'mimeType': mime_type,
                'size': len(file_data)
            }

        except Exception as e:
            print(f"[ASSET ERROR] Failed to read file: {e}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': str(e), 'data': None}

    def get_asset_as_data_url(self, file_path):
        """DEPRECATED: Use get_asset_as_bytes instead. Keeping for backwards compatibility."""
        try:
            import shutil
            import mimetypes
            import urllib.parse

            print(f"[ASSET] get_asset_as_data_url called with: {file_path}")

            if not os.path.exists(file_path):
                print(f"[ASSET ERROR] File not found: {file_path}")
                return {'status': 'error', 'message': 'File not found', 'dataUrl': None}

            # Create temp directory in web folder for HTTP serving
            web_temp_dir = os.path.join(BASE_DIR, 'web', 'temp_assets')
            os.makedirs(web_temp_dir, exist_ok=True)

            # Get filename and create temp copy
            filename = os.path.basename(file_path)
            temp_file = os.path.join(web_temp_dir, filename)

            print(f"[ASSET] Copying to: {temp_file}")

            # Copy file to web/temp_assets (fast for local files)
            # Always copy to ensure we have the latest version
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                shutil.copy2(file_path, temp_file)
                print(f"[ASSET] File copied successfully, size: {os.path.getsize(temp_file)} bytes")
            except Exception as copy_err:
                print(f"[ASSET ERROR] Failed to copy file: {copy_err}")
                return {'status': 'error', 'message': f'Failed to copy file: {copy_err}', 'dataUrl': None}

            # Verify the copied file exists and is readable
            if not os.path.exists(temp_file):
                print(f"[ASSET ERROR] Copy verification failed - file doesn't exist: {temp_file}")
                return {'status': 'error', 'message': 'Copy verification failed', 'dataUrl': None}

            # List all files in temp_assets directory for debugging
            try:
                temp_assets_files = os.listdir(web_temp_dir)
                print(f"[ASSET] Files in temp_assets directory: {temp_assets_files}")
            except Exception as list_err:
                print(f"[ASSET] Could not list temp_assets directory: {list_err}")

            # PyWebView can access files in the web directory via relative paths
            # Return the relative path from the HTML file location
            # HTML file is in: BASE_DIR/web/index.html
            # Temp file is in: BASE_DIR/web/temp_assets/filename.mp4
            # So relative path is: temp_assets/filename.mp4

            relative_path = f'temp_assets/{filename}'
            print(f"[ASSET] Returning relative path: {relative_path}")
            print(f"[ASSET] File size: {os.path.getsize(temp_file)} bytes")

            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                ext = os.path.splitext(file_path)[1].lower()
                mime_types_map = {
                    '.mp4': 'video/mp4',
                    '.mov': 'video/quicktime',
                    '.webm': 'video/webm',
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif'
                }
                mime_type = mime_types_map.get(ext, 'application/octet-stream')

            return {
                'status': 'success',
                'dataUrl': relative_path,  # Relative path for PyWebView
                'mimeType': mime_type,
                'size': os.path.getsize(file_path)
            }

        except Exception as e:
            print(f"Error preparing file for display: {e}")
            return {'status': 'error', 'message': str(e), 'dataUrl': None}

    def save_media_file_dialog(self, default_filename='output.mp4'):
        """Show save file dialog for media files (videos, images) and return chosen path"""
        print(f"[SAVE] save_media_file_dialog() called with default_filename={default_filename}")
        try:
            if app_state['window']:
                result = app_state['window'].create_file_dialog(
                    dialog_type=webview.FileDialog.SAVE,
                    save_filename=default_filename,
                    file_types=('Video Files (*.mp4;*.mov;*.gif;*.png)', 'All Files (*.*)')
                )
                print(f"[SAVE] Media dialog result: {result}")

                if result and len(result) > 0:
                    return {'status': 'success', 'path': result[0]}
                else:
                    return {'status': 'cancelled', 'path': None}
            else:
                return {'status': 'error', 'message': 'Window not available'}
        except Exception as e:
            print(f"Error showing save dialog: {e}")
            return {'status': 'error', 'message': str(e)}

    def delete_asset(self, file_path):
        """Delete an asset file"""
        try:
            if not os.path.exists(file_path):
                return {'status': 'error', 'message': 'File not found'}

            os.remove(file_path)
            print(f"[OK] Deleted asset: {file_path}")
            return {'status': 'success', 'message': 'File deleted'}
        except Exception as e:
            print(f"Error deleting asset: {e}")
            return {'status': 'error', 'message': str(e)}

    def read_file_as_base64(self, file_path):
        """Read a file and return as base64 string (for image preview)"""
        try:
            import base64
            if not os.path.exists(file_path):
                raise Exception('File not found')

            with open(file_path, 'rb') as f:
                file_data = f.read()
                base64_data = base64.b64encode(file_data).decode('utf-8')
                return base64_data
        except Exception as e:
            print(f"[ERROR] Failed to read file as base64: {e}")
            raise Exception(f"Failed to read file: {str(e)}")

    def read_file_text(self, file_path):
        """Read text file content (for subtitle/text preview)"""
        try:
            if not os.path.exists(file_path):
                raise Exception('File not found')

            # Check if this is a binary file that shouldn't be read as text
            ext = os.path.splitext(file_path)[1].lower()
            binary_exts = ('.ttf', '.otf', '.woff', '.woff2', '.ttc', '.eot',
                          '.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.wma',
                          '.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv', '.m4v',
                          '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico')
            if ext in binary_exts:
                raise Exception(f'Cannot read binary file as text: {ext}')

            # Try UTF-8 first (most common)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    return content
            except UnicodeDecodeError:
                pass

            # Try UTF-8 with BOM
            try:
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
                    return content
            except UnicodeDecodeError:
                pass

            # Try Windows default encoding (cp1252)
            try:
                with open(file_path, 'r', encoding='cp1252') as f:
                    content = f.read()
                    return content
            except UnicodeDecodeError:
                pass

            # Try latin-1 (accepts all bytes)
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                    return content
            except Exception as e:
                print(f"[ERROR] Failed to read text file with all encodings: {e}")
                raise Exception(f"Failed to read file: Unable to decode with any encoding")

        except Exception as e:
            print(f"[ERROR] Failed to read text file: {e}")
            raise Exception(f"Failed to read file: {str(e)}")

    # Class-level variable for debouncing
    _last_fullscreen_call = 0
    _fullscreen_debounce_delay = 2.0  # 2 seconds

    def open_video_fullscreen(self, video_src):
        """Open video in a new PyWebView window"""
        try:
            import time

            # DEBOUNCE: Check if called too recently
            current_time = time.time()
            time_since_last = current_time - self.__class__._last_fullscreen_call

            if time_since_last < self.__class__._fullscreen_debounce_delay:
                print(f"[INFO] DEBOUNCED: Only {time_since_last:.2f}s since last call, ignoring...")
                return {
                    'status': 'debounced',
                    'message': 'Request debounced - too soon after previous call'
                }

            # Update last call time
            self.__class__._last_fullscreen_call = current_time

            print(f"[INFO] ========== open_video_fullscreen CALLED ==========")
            print(f"[INFO] Video source: {video_src}")

            # Extract the base URL from video source to get the HTTP server address
            # Example: http://127.0.0.1:30614/temp_assets/MyScene.mp4 -> http://127.0.0.1:30614
            if video_src.startswith('http://'):
                from urllib.parse import urlparse, quote
                parsed = urlparse(video_src)
                base_url = f"{parsed.scheme}://{parsed.netloc}"

                print(f"[INFO] Base URL: {base_url}")

                # Encode the video source for URL parameter
                encoded_src = quote(video_src, safe='')

                # Create fullscreen URL using the same HTTP server
                fullscreen_url = f"{base_url}/video_fullscreen.html?src={encoded_src}"

                print(f"[INFO] Fullscreen URL: {fullscreen_url}")
            else:
                raise Exception(f"Video source is not an HTTP URL: {video_src}")

            # Get main window dimensions if available, otherwise use defaults
            main_window = app_state.get('window')
            if main_window and hasattr(main_window, 'width') and hasattr(main_window, 'height'):
                # Use actual main window dimensions
                window_width = main_window.width
                window_height = main_window.height
                print(f"[INFO] Using main window size: {window_width}x{window_height}")
            else:
                # Use default main window size (same as initial create_window)
                window_width = 1600
                window_height = 1000
                print(f"[INFO] Using default window size: {window_width}x{window_height}")

            # Position: Offset slightly from main window so both are visible
            # Offset by 50px right and 50px down from original position
            window_x = 50
            window_y = 50

            print(f"[INFO] Creating new PyWebView window...")
            print(f"[INFO] Window: {window_width}x{window_height} at ({window_x},{window_y})")

            # Create new PyWebView window
            # Since the GUI loop is already running, this window will appear immediately
            import webview
            new_window = webview.create_window(
                'Manim Studio - Video Player',
                fullscreen_url,
                width=window_width,
                height=window_height,
                resizable=True,
                x=window_x,
                y=window_y
            )

            print(f"[INFO] New PyWebView window created")
            print(f"[INFO] Total windows: {len(webview.windows)}")
            print(f"[INFO] ========== COMPLETE ==========")

            return {
                'status': 'success',
                'message': 'Video window opened'
            }

        except Exception as e:
            print(f"[ERROR] Failed to open video window: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'message': str(e)
            }

    def get_setup_info(self):
        """Get setup information for virtual environment"""
        try:
            # Get Python version
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

            return {
                'status': 'success',
                'venv_path': VENV_DIR,
                'python_version': python_version
            }
        except Exception as e:
            print(f"[ERROR] Failed to get setup info: {e}")
            return {'status': 'error', 'message': str(e)}

    def check_manim_installed(self):
        """Check if Manim is installed in the virtual environment"""
        try:
            print("=" * 80)
            print("[INFO] check_manim_installed() CALLED")
            print(f"[INFO] Running as frozen EXE: {getattr(sys, 'frozen', False)}")
            print(f"[INFO] USER_DATA_DIR: {USER_DATA_DIR}")
            print(f"[INFO] VENV_DIR: {VENV_DIR}")

            # Get venv Python path
            if os.name == 'nt':
                venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
            else:
                venv_python = os.path.join(VENV_DIR, 'bin', 'python')

            print(f"[INFO] Expected venv Python path: {venv_python}")
            print(f"[INFO] Venv Python exists: {os.path.exists(venv_python)}")

            # Check if venv Python exists
            if not os.path.exists(venv_python):
                print(f"[WARNING] Virtual environment Python not found at: {venv_python}")
                print(f"[WARNING] Checking if VENV_DIR exists: {os.path.exists(VENV_DIR)}")
                if os.path.exists(VENV_DIR):
                    print(f"[INFO] VENV_DIR exists, listing contents:")
                    try:
                        contents = os.listdir(VENV_DIR)
                        print(f"[INFO] Contents: {contents[:10]}")  # First 10 items
                    except Exception as e:
                        print(f"[ERROR] Cannot list VENV_DIR: {e}")
                print("[INFO] Virtual environment may not be set up yet")
                return {
                    'status': 'success',
                    'installed': False,
                    'version': None,
                    'message': 'Virtual environment not set up'
                }

            print(f"[INFO] Using Python from virtual environment: {venv_python}")

            # Use pip show method directly (more reliable in EXE/MSIX)
            print("[INFO] Checking manim using 'pip show manim'...")
            env = get_clean_environment()
            if os.name == 'nt':
                venv_pip = os.path.join(VENV_DIR, 'Scripts', 'pip.exe')
            else:
                venv_pip = os.path.join(VENV_DIR, 'bin', 'pip')

            if not os.path.exists(venv_pip):
                print(f"[WARNING] Pip not found at: {venv_pip}")
                print("[INFO] Virtual environment may not be properly set up")
                print("=" * 80)
                result = {
                    'status': 'success',
                    'installed': False,
                    'version': None,
                    'message': 'Pip not found in virtual environment'
                }
                print(f"[INFO] check_manim_installed() RESULT: {result}")
                return result

            print(f"[INFO] Using pip from: {venv_pip}")
            result = subprocess.run(
                [venv_pip, 'show', 'manim'],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=5,  # Reduced timeout
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            print(f"[DEBUG] Pip show returncode: {result.returncode}")
            print(f"[DEBUG] Pip show stdout: {result.stdout[:200] if result.stdout else 'None'}")
            print(f"[DEBUG] Pip show stderr: {result.stderr[:200] if result.stderr else 'None'}")

            if result.returncode == 0 and result.stdout:
                version = None
                location = None
                for line in result.stdout.split('\n'):
                    if line.startswith('Version:'):
                        version = line.split(':', 1)[1].strip()
                    elif line.startswith('Location:'):
                        location = line.split(':', 1)[1].strip()

                print(f"[DEBUG] Parsed version from pip: {version}")
                print(f"[DEBUG] Parsed location from pip: {location}")

                if version:
                    print(f"[INFO] [OK] Manim is installed in venv: {version}")
                    if location:
                        print(f"[INFO] Location: {location}")
                    print("=" * 80)
                    pip_result = {
                        'status': 'success',
                        'installed': True,
                        'version': version,
                        'location': location
                    }
                    print(f"[INFO] check_manim_installed() RESULT: {pip_result}")
                    return pip_result

            # Not found
            print("[INFO] Manim is not installed in virtual environment")
            print("=" * 80)
            not_found_result = {
                'status': 'success',
                'installed': False,
                'version': None
            }
            print(f"[INFO] check_manim_installed() RESULT: {not_found_result}")
            return not_found_result

        except Exception as e:
            print(f"[ERROR] Failed to check Manim: {e}")
            import traceback
            traceback.print_exc()
            print("=" * 80)
            result = {
                'status': 'error',
                'installed': False,
                'message': str(e)
            }
            print(f"[ERROR] check_manim_installed() RESULT: {result}")
            return result

    def _perform_prerequisite_check(self):
        """Run dependency checks and return raw results."""
        results = {
            'python': {'installed': False, 'version': None, 'path': None},
            'latex': {'installed': False, 'variant': None, 'path': None}
        }

        # Check Python
        try:
            system_python = find_system_python()
            if system_python:
                results['python']['installed'] = True
                results['python']['path'] = system_python

                env = get_clean_environment()
                version_result = subprocess.run(
                    [system_python, '--version'],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                version_output = (version_result.stdout + version_result.stderr).strip()
                if 'python' in version_output.lower():
                    results['python']['version'] = version_output.replace('Python ', '')
        except Exception as e:
            print(f"[WARNING] Python check failed: {e}")

        # Check LaTeX (try multiple variants)
        latex_commands = [
            ('pdflatex', 'pdfLaTeX (MiKTeX)'),
            ('xelatex', 'XeLaTeX'),
            ('lualatex', 'LuaLaTeX'),
            ('latex', 'LaTeX')
        ]

        for cmd, variant_name in latex_commands:
            try:
                env = get_clean_environment()
                latex_result = subprocess.run(
                    [cmd, '--version'],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                if latex_result.returncode == 0:
                    results['latex']['installed'] = True
                    results['latex']['variant'] = variant_name

                    if os.name == 'nt':
                        where_result = subprocess.run(
                            ['where', cmd],
                            stdin=subprocess.DEVNULL,
                            capture_output=True,
                            text=True,
                            timeout=5,
                            env=env,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        if where_result.returncode == 0:
                            results['latex']['path'] = where_result.stdout.strip().split('\n')[0]
                    break
            except Exception:
                continue

        return results

    def _refresh_dependency_cache(self, reason='manual'):
        """
        Refresh cached dependency status.
        Returns True if this call performed a check, False if another check is already in progress.
        """
        lock = app_state['dependency_check_lock']
        with lock:
            if app_state['dependency_check_in_progress']:
                return False
            app_state['dependency_check_in_progress'] = True

        try:
            print(f"[DEPENDENCY] Running dependency check ({reason})...")
            results = self._perform_prerequisite_check()
            now = time.time()
            with lock:
                app_state['dependency_cache'] = results
                app_state['dependency_last_checked'] = now
                app_state['dependency_check_error'] = None
            print(f"[DEPENDENCY] Dependency check complete ({reason})")
            return True
        except Exception as e:
            print(f"[DEPENDENCY] Dependency check failed ({reason}): {e}")
            with lock:
                app_state['dependency_check_error'] = str(e)
            return False
        finally:
            with lock:
                app_state['dependency_check_in_progress'] = False

    def _start_dependency_refresh_async(self, reason='async'):
        """Start a non-blocking dependency refresh if one isn't already running."""
        lock = app_state['dependency_check_lock']
        with lock:
            if app_state['dependency_check_in_progress']:
                return False

        refresh_thread = threading.Thread(
            target=self._refresh_dependency_cache,
            kwargs={'reason': reason},
            daemon=True
        )
        refresh_thread.start()
        return True

    def start_dependency_checker_background(self):
        """Start periodic dependency checks in the background."""
        lock = app_state['dependency_check_lock']
        with lock:
            existing = app_state.get('dependency_checker_thread')
            if existing and existing.is_alive():
                return {'status': 'already_running'}
            app_state['dependency_stop_event'].clear()

        def run_checker():
            # Initial short delay so startup remains responsive.
            if app_state['dependency_stop_event'].wait(3):
                return

            self._refresh_dependency_cache(reason='startup')

            # Periodic refresh every 5 minutes.
            while not app_state['dependency_stop_event'].wait(300):
                self._refresh_dependency_cache(reason='periodic')

        checker_thread = threading.Thread(target=run_checker, daemon=True)
        checker_thread.start()

        with lock:
            app_state['dependency_checker_thread'] = checker_thread

        return {'status': 'started'}

    def check_prerequisites(self, force_refresh=False):
        """Check prerequisites using cached background results when available."""
        try:
            force_refresh = bool(force_refresh)
            cache_ttl_seconds = 300
            now = time.time()

            lock = app_state['dependency_check_lock']
            with lock:
                cached_results = app_state['dependency_cache']
                last_checked = app_state['dependency_last_checked']
                in_progress = app_state['dependency_check_in_progress']
                last_error = app_state['dependency_check_error']

            cache_age = (now - last_checked) if last_checked else None
            cache_is_fresh = (
                cached_results is not None and
                cache_age is not None and
                cache_age <= cache_ttl_seconds
            )

            # Force refresh or first call without cache performs a synchronous check.
            if force_refresh or cached_results is None:
                self._refresh_dependency_cache(reason='api_forced' if force_refresh else 'api_initial')
                with lock:
                    cached_results = app_state['dependency_cache']
                    last_checked = app_state['dependency_last_checked']
                    in_progress = app_state['dependency_check_in_progress']
                    last_error = app_state['dependency_check_error']
                cache_age = (now - last_checked) if last_checked else None
                cache_is_fresh = (
                    cached_results is not None and
                    cache_age is not None and
                    cache_age <= cache_ttl_seconds
                )

            # If we have cache but it's stale, refresh in background without blocking caller.
            if cached_results is not None and not cache_is_fresh and not in_progress:
                self._start_dependency_refresh_async(reason='api_stale')

            if cached_results is not None:
                return {
                    'status': 'success',
                    'results': cached_results,
                    'cached': True,
                    'stale': not cache_is_fresh,
                    'in_progress': in_progress,
                    'last_checked': last_checked,
                    'last_error': last_error
                }

            return {
                'status': 'error',
                'message': last_error or 'Dependency check did not return results'
            }

        except Exception as e:
            print(f"[ERROR] Failed to check prerequisites: {e}")
            return {'status': 'error', 'message': str(e)}

    def _escape_js_string(self, text):
        """Escape string for safe use in JavaScript evaluate_js calls"""
        if not text:
            return ""
        # Escape backslashes first, then quotes and newlines
        return text.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '')

    def install_environment(self, options):
        """
        Install virtual environment with selected packages.
        This method runs the installation in a background thread to prevent blocking the webview.
        """
        # Start installation in background thread to prevent exe from hanging
        def run_installation():
            self._do_install_environment(options)

        install_thread = threading.Thread(target=run_installation, daemon=True)
        install_thread.start()

        # Return immediately - updates will be sent via evaluate_js
        return {
            'status': 'started',
            'message': 'Installation started in background'
        }

    def _do_install_environment(self, options):
        """Internal method that performs the actual installation work"""
        global PYTHON_EXE

        try:
            optional_packages = options.get('optional_packages', [])
            custom_packages = options.get('custom_packages', [])

            print("[SETUP] Starting virtual environment installation...")

            # Update progress
            if app_state['window']:
                app_state['window'].evaluate_js('window.updateProgress(10, "[INFO] Initializing setup...")')

            # Find system Python
            system_python = find_system_python()
            if not system_python:
                raise Exception("Python not found. Please install Python 3.8+ and add it to PATH.")

            print(f"[SETUP] Using Python: {system_python}")

            # Create .manim_studio directory structure FIRST
            print("[SETUP] Creating .manim_studio directory structure...")
            if app_state['window']:
                app_state['window'].evaluate_js('window.updateProgress(15, "[INFO] Creating directory structure...")')

            # Create main .manim_studio directory
            os.makedirs(USER_DATA_DIR, exist_ok=True)
            print(f"[SETUP] Created: {USER_DATA_DIR}")
            if app_state['window']:
                escaped_path = self._escape_js_string(USER_DATA_DIR)
                app_state['window'].evaluate_js(f'window.updateProgress(16, "[SUCCESS] Created: {escaped_path}")')

            # Create media subdirectory
            os.makedirs(MEDIA_DIR, exist_ok=True)
            print(f"[SETUP] Created: {MEDIA_DIR}")
            if app_state['window']:
                escaped_path = self._escape_js_string(MEDIA_DIR)
                app_state['window'].evaluate_js(f'window.updateProgress(17, "[SUCCESS] Created: {escaped_path}")')

            # Create assets subdirectory
            os.makedirs(ASSETS_DIR, exist_ok=True)
            print(f"[SETUP] Created: {ASSETS_DIR}")
            if app_state['window']:
                escaped_path = self._escape_js_string(ASSETS_DIR)
                app_state['window'].evaluate_js(f'window.updateProgress(18, "[SUCCESS] Created: {escaped_path}")')

            # Create venvs directory
            venvs_dir = os.path.dirname(VENV_DIR)
            os.makedirs(venvs_dir, exist_ok=True)
            print(f"[SETUP] Created: {venvs_dir}")
            if app_state['window']:
                escaped_path = self._escape_js_string(venvs_dir)
                app_state['window'].evaluate_js(f'window.updateProgress(19, "[SUCCESS] Created: {escaped_path}")')

            print("[SETUP] Directory structure created successfully!")

            # Create virtual environment
            if app_state['window']:
                app_state['window'].evaluate_js('window.updateProgress(20, "[INFO] Creating virtual environment...")')

            env = get_clean_environment()
            result = subprocess.run(
                [system_python, '-m', 'venv', VENV_DIR],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode != 0:
                raise Exception(f"Failed to create venv: {result.stderr}")

            print("[SETUP] Virtual environment created successfully")

            # Get venv Python path
            if os.name == 'nt':
                venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
                venv_pip = os.path.join(VENV_DIR, 'Scripts', 'pip.exe')
            else:
                venv_python = os.path.join(VENV_DIR, 'bin', 'python')
                venv_pip = os.path.join(VENV_DIR, 'bin', 'pip')

            PYTHON_EXE = venv_python

            # Upgrade pip
            if app_state['window']:
                app_state['window'].evaluate_js('window.updateProgress(30, "[INFO] Upgrading pip...")')

            subprocess.run(
                [venv_python, '-m', 'pip', 'install', '--upgrade', 'pip'],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            # Helper function to run pip with real-time output
            def run_pip_install(package, progress_value):
                """Run pip install with real-time output streaming"""
                if app_state['window']:
                    app_state['window'].evaluate_js(f'window.updateProgress({progress_value}, "[INFO] Installing {package}...")')

                print(f"[SETUP] Installing {package}...")

                # Use Popen for real-time output
                process = subprocess.Popen(
                    [venv_pip, 'install', package, '--verbose'],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',  # Force UTF-8 encoding
                    errors='replace',  # Replace invalid characters instead of crashing
                    env=env,
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )

                # Stream output line by line
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        # Send each line to UI console
                        escaped_line = self._escape_js_string(line)
                        if app_state['window']:
                            app_state['window'].evaluate_js(f'window.updateProgress({progress_value}, "{escaped_line}")')
                        print(f"  {line}")

                process.wait()

                if process.returncode != 0:
                    print(f"[WARNING] Failed to install {package}")
                    if app_state['window']:
                        app_state['window'].evaluate_js(f'window.updateProgress({progress_value}, "[WARNING] {package} installation had issues")')
                    return False
                else:
                    print(f"[SETUP] {package} installed successfully")
                    if app_state['window']:
                        app_state['window'].evaluate_js(f'window.updateProgress({progress_value}, "[SUCCESS] {package} installed successfully")')
                    return True

            # Install required packages
            required_packages = ['manim', 'manim-fonts', 'pywebview', 'basedpyright']
            progress = 40

            for pkg in required_packages:
                run_pip_install(pkg, progress)
                progress += 10

            # Install optional packages
            if optional_packages:
                for pkg in optional_packages:
                    run_pip_install(pkg, progress)
                    progress = min(progress + 5, 85)

            # Install custom packages
            if custom_packages:
                for pkg in custom_packages:
                    run_pip_install(pkg, progress)
                    progress = min(progress + 5, 90)

            # Final progress
            if app_state['window']:
                app_state['window'].evaluate_js('window.updateProgress(100, "[SUCCESS] Installation complete!")')

            print("[SETUP] Installation complete!")

            # Notify UI that installation is complete
            if app_state['window']:
                app_state['window'].evaluate_js('window.onInstallationComplete(true, "Installation successful")')

        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] Installation failed: {error_msg}")
            if app_state['window']:
                escaped_error = self._escape_js_string(f"[ERROR] Installation failed: {error_msg}")
                app_state['window'].evaluate_js(f'window.updateProgress(0, "{escaped_error}")')
                # Notify UI that installation failed
                app_state['window'].evaluate_js(f'window.onInstallationComplete(false, "{escaped_error}")')

    def open_folder(self, folder_path):
        """Open folder in file explorer"""
        try:
            print(f"[OPEN_FOLDER] Called with path: {folder_path}")

            if not folder_path:
                print("[OPEN_FOLDER] Error: folder_path is empty or None")
                return {'status': 'error', 'message': 'Folder path is empty'}

            if not os.path.exists(folder_path):
                print(f"[OPEN_FOLDER] Error: Path does not exist: {folder_path}")
                return {'status': 'error', 'message': 'Folder does not exist'}

            print(f"[OPEN_FOLDER] Platform: {sys.platform}")

            if sys.platform == 'win32':
                print(f"[OPEN_FOLDER] Opening folder with os.startfile...")
                os.startfile(folder_path)
            elif sys.platform == 'darwin':
                print(f"[OPEN_FOLDER] Opening folder with 'open' command...")
                subprocess.run(['open', folder_path])
            else:
                print(f"[OPEN_FOLDER] Opening folder with 'xdg-open' command...")
                subprocess.run(['xdg-open', folder_path])

            print(f"[OPEN_FOLDER] Successfully opened: {folder_path}")
            return {'status': 'success'}

        except Exception as e:
            print(f"[OPEN_FOLDER] Exception occurred: {e}")
            return {'status': 'error', 'message': str(e)}

    def select_folder(self):
        """Show folder selection dialog"""
        try:
            if app_state['window']:
                result = app_state['window'].create_file_dialog(
                    webview.FOLDER_DIALOG,
                    directory=os.path.expanduser('~')
                )

                if result and len(result) > 0:
                    return {'status': 'success', 'path': result[0]}
                else:
                    return {'status': 'cancelled', 'path': None}
            else:
                return {'status': 'error', 'message': 'Window not available'}

        except Exception as e:
            print(f"Error selecting folder: {e}")
            return {'status': 'error', 'message': str(e)}

    def select_files_to_upload(self):
        """Show file selection dialog for uploading assets"""
        try:
            if app_state['window']:
                result = app_state['window'].create_file_dialog(
                    FileDialog.OPEN,
                    allow_multiple=True,
                    file_types=(
                        'All Assets (*.mp4;*.mov;*.avi;*.webm;*.mkv;*.png;*.jpg;*.jpeg;*.gif;*.svg;*.bmp;*.webp;*.ttf;*.otf;*.woff;*.woff2;*.ttc;*.mp3;*.wav;*.ogg;*.m4a;*.aac;*.flac;*.srt;*.vtt;*.ass;*.txt;*.md;*.json)',
                        'Video Files (*.mp4;*.mov;*.avi;*.webm;*.mkv;*.flv;*.m4v)',
                        'Image Files (*.png;*.jpg;*.jpeg;*.gif;*.svg;*.bmp;*.webp;*.ico)',
                        'Font Files (*.ttf;*.otf;*.woff;*.woff2;*.ttc;*.eot)',
                        'Audio Files (*.mp3;*.wav;*.ogg;*.m4a;*.aac;*.flac;*.wma)',
                        'Subtitle Files (*.srt;*.vtt;*.ass;*.ssa;*.sub)',
                        'Text Files (*.txt;*.md;*.json;*.xml;*.csv)',
                        'All Files (*.*)'
                    )
                )

                if result and len(result) > 0:
                    print(f'[UPLOAD] User selected {len(result)} file(s):')
                    for f in result:
                        print(f'  - {f}')
                    return {'status': 'success', 'file_paths': result}
                else:
                    print('[UPLOAD] User cancelled file selection')
                    return {'status': 'cancelled', 'file_paths': []}
            else:
                return {'status': 'error', 'message': 'Window not available'}

        except Exception as e:
            print(f"[UPLOAD] Error selecting files: {e}")
            return {'status': 'error', 'message': str(e)}

    def upload_assets(self, file_paths):
        """Copy selected files to the assets directory"""
        try:
            import shutil

            if not file_paths:
                return {'status': 'error', 'message': 'No files provided'}

            # Ensure assets directory exists
            os.makedirs(ASSETS_DIR, exist_ok=True)

            uploaded_files = []
            failed_files = []

            for file_path in file_paths:
                try:
                    if not os.path.exists(file_path):
                        failed_files.append({'file': os.path.basename(file_path), 'error': 'File not found'})
                        continue

                    # Get filename and destination
                    filename = os.path.basename(file_path)
                    dest_path = os.path.join(ASSETS_DIR, filename)

                    # Check if file already exists
                    if os.path.exists(dest_path):
                        # Add timestamp to filename to avoid overwrite
                        name, ext = os.path.splitext(filename)
                        filename = f"{name}_{int(time.time())}{ext}"
                        dest_path = os.path.join(ASSETS_DIR, filename)

                    # Copy file to assets
                    shutil.copy2(file_path, dest_path)

                    # Force filesystem sync to ensure file is written
                    try:
                        with open(dest_path, 'rb') as f:
                            os.fsync(f.fileno())
                    except:
                        pass  # If fsync fails, continue anyway

                    uploaded_files.append(filename)
                    print(f'[UPLOAD] Copied {filename} to assets')

                except Exception as e:
                    failed_files.append({'file': os.path.basename(file_path), 'error': str(e)})
                    print(f'[UPLOAD ERROR] Failed to copy {file_path}: {e}')

            # Return result
            if uploaded_files and not failed_files:
                return {
                    'status': 'success',
                    'message': f'Successfully uploaded {len(uploaded_files)} file(s)',
                    'uploaded': uploaded_files
                }
            elif uploaded_files and failed_files:
                return {
                    'status': 'partial',
                    'message': f'Uploaded {len(uploaded_files)} file(s), {len(failed_files)} failed',
                    'uploaded': uploaded_files,
                    'failed': failed_files
                }
            else:
                return {
                    'status': 'error',
                    'message': 'All uploads failed',
                    'failed': failed_files
                }

        except Exception as e:
            print(f"[UPLOAD ERROR] {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def upload_file_content(self, filename, base64_content):
        """Upload a file from base64 content (for drag and drop)"""
        try:
            import base64

            if not filename or not base64_content:
                return {'status': 'error', 'message': 'Missing filename or content'}

            # Ensure assets directory exists
            os.makedirs(ASSETS_DIR, exist_ok=True)

            # Decode base64 content
            try:
                file_data = base64.b64decode(base64_content)
            except Exception as e:
                return {'status': 'error', 'message': f'Failed to decode file: {e}'}

            # Generate destination path
            dest_path = os.path.join(ASSETS_DIR, filename)

            # Check if file already exists
            if os.path.exists(dest_path):
                # Add timestamp to filename to avoid overwrite
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{int(time.time())}{ext}"
                dest_path = os.path.join(ASSETS_DIR, filename)

            # Write file
            with open(dest_path, 'wb') as f:
                f.write(file_data)
                # Force filesystem sync to ensure file is written
                try:
                    os.fsync(f.fileno())
                except:
                    pass

            print(f'[UPLOAD] Saved {filename} to assets ({len(file_data)} bytes)')

            return {
                'status': 'success',
                'message': f'Uploaded {filename}',
                'filename': filename
            }

        except Exception as e:
            print(f"[UPLOAD ERROR] {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def save_app_settings(self, settings):
        """Save app settings to .manim_studio/settings.json"""
        try:
            import json
            settings_file = os.path.join(USER_DATA_DIR, 'settings.json')

            # Ensure user data directory exists
            os.makedirs(USER_DATA_DIR, exist_ok=True)

            # Save settings to file
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)

            print(f"[SETTINGS] Saved settings to {settings_file}")
            return {'status': 'success', 'message': 'Settings saved successfully'}

        except Exception as e:
            print(f"Error saving settings: {e}")
            return {'status': 'error', 'message': str(e)}

    def load_app_settings(self):
        """Load app settings from .manim_studio/settings.json"""
        try:
            import json
            settings_file = os.path.join(USER_DATA_DIR, 'settings.json')

            # Check if settings file exists
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                print(f"[SETTINGS] Loaded settings from {settings_file}")
                return {'status': 'success', 'settings': settings}
            else:
                # Return default settings
                default_settings = {
                    'defaultSaveLocation': '',
                    'renderQuality': '1080p',
                    'fps': 60,
                    'autoSave': True,
                    'autoOpenOutput': False,
                    'theme': 'dark',
                    'disableCache': False  # Cache enabled by default
                }
                print("[SETTINGS] No settings file found, using defaults")
                return {'status': 'success', 'settings': default_settings}

        except Exception as e:
            print(f"Error loading settings: {e}")
            return {'status': 'error', 'message': str(e), 'settings': {}}

    def get_system_info(self):
        """Get system information and Python environment details"""
        import platform

        print("=" * 80)
        print("[SYSTEM INFO] get_system_info() CALLED")
        print(f"[SYSTEM INFO] Running as frozen EXE: {getattr(sys, 'frozen', False)}")
        print(f"[SYSTEM INFO] USER_DATA_DIR: {USER_DATA_DIR}")
        print(f"[SYSTEM INFO] VENV_DIR: {VENV_DIR}")

        # Get actual Python executable being used for manim operations
        # IMPORTANT: This should show the Python used for MANIM, not the Python running this app
        global PYTHON_EXE

        print("[SYSTEM INFO] Determining Python executable for manim operations...")

        # Determine venv Python path
        if os.name == 'nt':
            venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
        else:
            venv_python = os.path.join(VENV_DIR, 'bin', 'python')

        print(f"[SYSTEM INFO] Expected venv Python: {venv_python}")
        print(f"[SYSTEM INFO] Venv Python exists: {os.path.exists(venv_python)}")

        # Check what Python will be used for manim operations
        if os.path.exists(venv_python):
            # Venv exists - this is what will be used for manim
            actual_python = venv_python
            python_source = f".manim_studio venv (used for manim)"
            print(f"[SYSTEM INFO] Found .manim_studio venv: {actual_python}")
        elif PYTHON_EXE:
            # PYTHON_EXE is cached - this is what will be used
            actual_python = PYTHON_EXE
            python_source = "System Python (used for manim)"
            print(f"[SYSTEM INFO] Using cached system Python: {actual_python}")
        else:
            # Need to find system Python
            actual_python = find_system_python()
            if actual_python:
                python_source = "System Python (used for manim)"
                print(f"[SYSTEM INFO] Found system Python: {actual_python}")
            else:
                actual_python = "ERROR: No Python found! Install Python to use this app."
                python_source = "not found"
                print(f"[SYSTEM INFO] ERROR: No Python found!")

        # Get Python version from the actual Python that will be used
        try:
            if actual_python and os.path.exists(actual_python):
                result = subprocess.run(
                    [actual_python, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=get_clean_environment()
                )
                python_version = (result.stdout + result.stderr).strip()
            else:
                python_version = "Unknown - Python not found"
        except Exception:
            python_version = sys.version if not getattr(sys, 'frozen', False) else "Unable to determine"

        info = {
            'python_version': python_version,
            'python_exe': actual_python,
            'python_source': python_source,
            'platform': platform.platform(),
            'processor': platform.processor(),
            'base_dir': BASE_DIR,
            'media_dir': app_state['output_dir'],
            'assets_dir': ASSETS_DIR,
            'venv_path': VENV_DIR,
            'venv_exists': os.path.exists(venv_python)
        }

        # Check Manim using the working check_manim_installed() method
        # This uses 'pip show manim' which is reliable in EXE/MSIX
        print("[SYSTEM INFO] Checking manim using check_manim_installed()...")
        try:
            manim_check = self.check_manim_installed()
            if manim_check.get('installed'):
                version = manim_check.get('version', 'Unknown')
                info['manim_version'] = f'Manim Community v{version}'
                info['manim_installed'] = True
                print(f"[SYSTEM INFO] [OK] Manim detected: v{version}")
            else:
                info['manim_version'] = 'Not installed'
                info['manim_installed'] = False
                message = manim_check.get('message', 'Unknown reason')
                print(f"[SYSTEM INFO] Manim not installed: {message}")
        except Exception as e:
            print(f"[SYSTEM INFO] Error checking manim: {e}")
            import traceback
            traceback.print_exc()
            info['manim_version'] = 'Not installed'
            info['manim_installed'] = False
            print(f"[SYSTEM INFO] Setting manim_installed=False due to exception")

        # Check for essential Python libraries using the actual Python
        try:
            if actual_python and os.path.exists(actual_python):
                result = subprocess.run(
                    [actual_python, '-m', 'pip', 'list', '--format=json'],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=get_clean_environment()
                )
                if result.returncode == 0:
                    packages = json.loads(result.stdout)
                    info['installed_packages'] = packages
                    info['packages_count'] = len(packages)

                    # Check for essential packages
                    package_names = [pkg['name'].lower() for pkg in packages]
                    essential_packages = ['manim', 'numpy', 'pillow', 'opencv-python']
                    missing_packages = [pkg for pkg in essential_packages if pkg not in package_names]

                    info['missing_packages'] = missing_packages
                    info['essential_packages_installed'] = len(missing_packages) == 0
                else:
                    info['packages_count'] = 0
                    info['installed_packages'] = []
                    info['packages_error'] = 'Failed to list packages'
            else:
                info['packages_count'] = 0
                info['installed_packages'] = []
                info['packages_error'] = 'Python not available'

        except Exception as e:
            print(f'Error checking Python packages: {e}')
            info['packages_count'] = 0
            info['installed_packages'] = []

        print("=" * 80)
        print(f"[SYSTEM INFO] get_system_info() RETURNING:")
        print(f"[SYSTEM INFO]   manim_installed: {info.get('manim_installed', 'NOT SET')}")
        print(f"[SYSTEM INFO]   manim_version: {info.get('manim_version', 'NOT SET')}")
        print("=" * 80)
        return info

    def get_app_version(self):
        """Return the application version string"""
        return {'version': APP_VERSION}

    def get_scene_names(self, code):
        """Extract all scene class names from the provided code"""
        import inspect
        import importlib.util

        temp_module_name = None
        try:
            temp_module_name = f"_temp_manim_scenes_{int(time.time() * 1000000)}"
            spec = importlib.util.spec_from_loader(temp_module_name, loader=None)
            if spec is None:
                matches = re.findall(r'class\s+(\w+)\s*\([^)]*\):', code)
                return matches

            temp_module = importlib.util.module_from_spec(spec)
            import sys as _sys
            _sys.modules[temp_module_name] = temp_module
            exec(code, temp_module.__dict__)

            try:
                from manim import Scene
                scene_classes = []
                for name, obj in inspect.getmembers(temp_module, inspect.isclass):
                    try:
                        if obj != Scene and issubclass(obj, Scene) and obj.__module__ == temp_module_name:
                            scene_classes.append(name)
                    except TypeError:
                        continue
                return scene_classes
            except ImportError:
                matches = re.findall(r'class\s+(\w+)\s*\([^)]*\):', code)
                return matches

        except Exception:
            matches = re.findall(r'class\s+(\w+)\s*\([^)]*\):', code)
            return matches
        finally:
            if temp_module_name:
                import sys as _sys
                _sys.modules.pop(temp_module_name, None)

    def get_gpu_info(self):
        """Get GPU information and availability for OpenGL rendering"""
        print("[GPU INFO] get_gpu_info() called")

        # Check if GPU detection packages are installed
        packages_ok, missing = check_gpu_detection_packages()

        if not packages_ok:
            # Notify user that GPU detection packages are missing
            warning_msg = f"GPU detection unavailable. Missing packages: {', '.join(missing)}. These should have been installed during venv setup."
            print(f"[GPU INFO] {warning_msg}")

            # Return limited info
            return {
                'available': False,
                'gpu_present': False,
                'info': f'GPU detection unavailable (missing: {", ".join(missing)})',
                'vendor': 'Unknown',
                'renderer': 'Unknown',
                'version': 'Unknown'
            }

        gpu_info = detect_gpu()
        print(f"[GPU INFO] GPU Available: {gpu_info['available']}")
        print(f"[GPU INFO] GPU Info: {gpu_info['info']}")
        return gpu_info

    def get_performance_data(self):
        """Get current performance metrics for CPU, GPU, RAM, VRAM"""
        return get_performance_metrics()

    def install_venv(self):
        """Install virtual environment - called by user confirmation"""
        result = setup_venv(window=app_state['window'])
        if result:
            return {'status': 'success', 'message': 'Virtual environment installed successfully', 'returncode': 0, 'stdout': 'Installation complete', 'stderr': ''}
        else:
            return {'status': 'error', 'message': 'Failed to install virtual environment', 'returncode': 1, 'stdout': '', 'stderr': 'Installation failed'}

    # AI/LLM code completion removed

    def get_video_files(self):
        """Get list of all video files from media directory"""
        try:
            video_files = []
            media_path = MEDIA_DIR

            if not os.path.exists(media_path):
                return {'status': 'success', 'videos': []}

            # Supported video extensions
            video_extensions = ('.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv', '.m4v')

            for root, dirs, files in os.walk(media_path):
                for file in files:
                    if file.lower().endswith(video_extensions):
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, media_path)

                        # Get video duration using ffprobe if available
                        try:
                            duration = self._get_video_duration(full_path)
                        except:
                            duration = 0

                        video_files.append({
                            'name': file,
                            'path': full_path,
                            'relative_path': rel_path,
                            'duration': duration
                        })

            # Sort by modification time (newest first)
            video_files.sort(key=lambda x: os.path.getmtime(x['path']), reverse=True)

            return {'status': 'success', 'videos': video_files}

        except Exception as e:
            print(f"[VIDEO LIST ERROR] {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def _get_video_duration(self, video_path):
        """Get video duration in seconds using ffprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
            return 0
        except Exception:
            return 0

    def trim_video(self, video_path, start_time, end_time, output_name):
        """Trim video using FFmpeg"""
        try:
            # Validate inputs
            if not os.path.exists(video_path):
                return {'status': 'error', 'message': 'Video file not found'}

            if not output_name:
                output_name = f"trimmed_{os.path.basename(video_path)}"

            # Ensure output has .mp4 extension
            if not output_name.lower().endswith('.mp4'):
                output_name += '.mp4'

            output_path = os.path.join(MEDIA_DIR, output_name)

            # Build FFmpeg command
            cmd = ['ffmpeg', '-i', video_path, '-y']  # -y to overwrite

            # Add start time if specified
            if start_time > 0:
                cmd.extend(['-ss', str(start_time)])

            # Add duration/end time if specified
            if end_time > 0:
                if start_time > 0:
                    duration = end_time - start_time
                    cmd.extend(['-t', str(duration)])
                else:
                    cmd.extend(['-to', str(end_time)])

            # Copy codec for fast processing (no re-encoding)
            cmd.extend(['-c', 'copy', output_path])

            print(f"[TRIM VIDEO] Running command: {' '.join(cmd)}")

            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                return {
                    'status': 'success',
                    'message': f'Video trimmed successfully: {output_name}',
                    'output_path': output_path
                }
            else:
                return {
                    'status': 'error',
                    'message': f'FFmpeg error: {result.stderr}'
                }

        except subprocess.TimeoutExpired:
            return {'status': 'error', 'message': 'Video trimming timed out'}
        except FileNotFoundError:
            return {'status': 'error', 'message': 'FFmpeg not found. Please install FFmpeg.'}
        except Exception as e:
            print(f"[TRIM VIDEO ERROR] {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def combine_videos(self, video_paths, output_name):
        """Combine multiple videos using FFmpeg"""
        try:
            # Validate inputs
            if not video_paths or len(video_paths) < 2:
                return {'status': 'error', 'message': 'Please select at least 2 videos to combine'}

            # Validate all paths exist
            for path in video_paths:
                if not os.path.exists(path):
                    return {'status': 'error', 'message': f'Video file not found: {os.path.basename(path)}'}

            if not output_name:
                output_name = f"combined_{int(time.time())}.mp4"

            # Ensure output has .mp4 extension
            if not output_name.lower().endswith('.mp4'):
                output_name += '.mp4'

            output_path = os.path.join(MEDIA_DIR, output_name)

            # Create concat file list
            concat_file = os.path.join(MEDIA_DIR, f'concat_list_{int(time.time())}.txt')

            with open(concat_file, 'w', encoding='utf-8') as f:
                for video_path in video_paths:
                    # FFmpeg concat requires absolute paths with forward slashes
                    abs_path = os.path.abspath(video_path).replace('\\', '/')
                    f.write(f"file '{abs_path}'\n")

            # Build FFmpeg command for concatenation
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',  # Copy codec for fast processing
                '-y',  # Overwrite output file
                output_path
            ]

            print(f"[COMBINE VIDEOS] Running command: {' '.join(cmd)}")

            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            # Clean up concat file
            try:
                os.remove(concat_file)
            except:
                pass

            if result.returncode == 0:
                return {
                    'status': 'success',
                    'message': f'Videos combined successfully: {output_name}',
                    'output_path': output_path
                }
            else:
                return {
                    'status': 'error',
                    'message': f'FFmpeg error: {result.stderr}'
                }

        except subprocess.TimeoutExpired:
            return {'status': 'error', 'message': 'Video combining timed out'}
        except FileNotFoundError:
            return {'status': 'error', 'message': 'FFmpeg not found. Please install FFmpeg.'}
        except Exception as e:
            print(f"[COMBINE VIDEOS ERROR] {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_installed_packages(self):
        """Get list of installed packages in the virtual environment"""
        try:
            print("[VENV] Getting installed packages...")

            # Get venv Python executable
            if os.name == 'nt':
                venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
            else:
                venv_python = os.path.join(VENV_DIR, 'bin', 'python')

            if not os.path.exists(venv_python):
                return {
                    'status': 'error',
                    'message': 'Virtual environment not found. Please install it first.',
                    'packages': []
                }

            # Run pip list --format=json
            cmd = [venv_python, '-m', 'pip', 'list', '--format=json']
            env = get_clean_environment()

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=30
            )

            if result.returncode == 0:
                import json
                packages = json.loads(result.stdout)
                print(f"[VENV] Found {len(packages)} installed packages")
                return {
                    'status': 'success',
                    'packages': packages
                }
            else:
                return {
                    'status': 'error',
                    'message': f'Failed to get package list: {result.stderr}',
                    'packages': []
                }

        except Exception as e:
            print(f"[VENV ERROR] {e}")
            traceback.print_exc()
            return {
                'status': 'error',
                'message': str(e),
                'packages': []
            }

    def check_missing_required_packages(self):
        """Check which required packages are missing from the venv."""
        required = ['basedpyright']
        try:
            if os.name == 'nt':
                venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
            else:
                venv_python = os.path.join(VENV_DIR, 'bin', 'python')

            if not os.path.exists(venv_python):
                return {'status': 'no_venv', 'missing': []}

            result = subprocess.run(
                [venv_python, '-m', 'pip', 'list', '--format=json'],
                capture_output=True, text=True, timeout=30,
                env=get_clean_environment()
            )
            if result.returncode != 0:
                return {'status': 'error', 'missing': []}

            import json as _json
            installed = {p['name'].lower() for p in _json.loads(result.stdout)}
            missing = [p for p in required if p.lower() not in installed]
            return {'status': 'success', 'missing': missing}
        except Exception as e:
            print(f'[VENV] check_missing_required_packages error: {e}')
            return {'status': 'error', 'missing': []}

    def install_missing_required_packages(self, packages):
        """Install missing required packages, streaming pip output to JS."""
        import json as _json

        def _run():
            try:
                if os.name == 'nt':
                    venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
                    flags = subprocess.CREATE_NO_WINDOW
                else:
                    venv_python = os.path.join(VENV_DIR, 'bin', 'python')
                    flags = 0

                env = get_clean_environment()
                win = app_state.get('window')

                for pkg in packages:
                    safe_evaluate_js(win, f'window.onMissingPkgLog({_json.dumps(f">>> pip install {pkg}")})')
                    proc = subprocess.Popen(
                        [venv_python, '-m', 'pip', 'install', pkg],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding='utf-8', errors='replace',
                        env=env, creationflags=flags
                    )
                    for line in iter(proc.stdout.readline, ''):
                        line = line.rstrip()
                        if line:
                            safe_evaluate_js(win, f'window.onMissingPkgLog({_json.dumps(line)})')
                    proc.wait()
                    if proc.returncode != 0:
                        safe_evaluate_js(win, f'window.onMissingPkgLog({_json.dumps(f"[ERROR] Failed to install {pkg}")})')
                        safe_evaluate_js(win, 'window.onMissingPkgDone(false)')
                        return

                safe_evaluate_js(win, 'window.onMissingPkgDone(true)')
            except Exception as exc:
                import json as _j
                safe_evaluate_js(app_state.get('window'),
                    f'window.onMissingPkgLog({_j.dumps(f"[ERROR] {exc}")})')
                safe_evaluate_js(app_state.get('window'), 'window.onMissingPkgDone(false)')

        threading.Thread(target=_run, daemon=True, name='install-missing-req').start()
        return {'status': 'started'}

    def check_package_dependencies(self, package_name):
        """Check package dependencies and potential conflicts before installation"""
        try:
            print(f"[VENV] Checking dependencies for: {package_name}")

            if not package_name or not package_name.strip():
                return {'status': 'error', 'message': 'Package name cannot be empty'}

            # Get venv Python executable
            if os.name == 'nt':
                venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
            else:
                venv_python = os.path.join(VENV_DIR, 'bin', 'python')

            if not os.path.exists(venv_python):
                return {'status': 'error', 'message': 'Virtual environment not found'}

            # Use pip to do a dry-run installation to check dependencies
            cmd = [venv_python, '-m', 'pip', 'install', '--dry-run', '--report', '-', package_name]
            env = get_clean_environment()

            print(f"[VENV] Running dependency check: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60
            )

            # Critical packages that should not be changed (to protect Manim)
            critical_packages = ['manim', 'manim-fonts', 'manimce', 'cairo', 'pycairo',
                               'manimpango', 'pango', 'numpy', 'pillow', 'scipy',
                               'moderngl', 'pygments']

            warnings = []
            conflicts = []
            dependencies = []

            # Parse the output to find what will be installed/upgraded
            if result.returncode == 0 or 'install' in result.stdout.lower():
                import json
                try:
                    # Try to parse JSON report
                    report = json.loads(result.stdout)
                    if 'install' in report:
                        for pkg in report['install']:
                            pkg_name = pkg.get('metadata', {}).get('name', '').lower()
                            if pkg_name:
                                dependencies.append({
                                    'name': pkg_name,
                                    'version': pkg.get('metadata', {}).get('version', 'unknown')
                                })
                                # Check if it's a critical package
                                if pkg_name in critical_packages:
                                    conflicts.append({
                                        'name': pkg_name,
                                        'type': 'critical',
                                        'message': f'Will modify {pkg_name} which is critical for Manim'
                                    })
                except:
                    # Fallback: parse text output
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if 'Would install' in line or 'would install' in line:
                            # Extract package names
                            parts = line.split('Would install')[-1].strip()
                            for pkg in parts.split():
                                pkg_name = pkg.split('-')[0].lower()
                                if pkg_name in critical_packages:
                                    warnings.append(f'May affect critical package: {pkg_name}')

            # Also check with pip check for conflicts
            check_cmd = [venv_python, '-m', 'pip', 'check']
            check_result = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=30
            )

            # Return comprehensive information
            return {
                'status': 'success',
                'package': package_name,
                'dependencies': dependencies,
                'conflicts': conflicts,
                'warnings': warnings,
                'has_conflicts': len(conflicts) > 0,
                'safe_to_install': len(conflicts) == 0,
                'output': result.stdout
            }

        except subprocess.TimeoutExpired:
            return {'status': 'error', 'message': 'Dependency check timed out'}
        except Exception as e:
            print(f"[VENV ERROR] {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def install_package(self, package_name):
        """Install a package in the virtual environment"""
        try:
            print(f"[VENV] Installing package: {package_name}")

            if not package_name or not package_name.strip():
                return {'status': 'error', 'message': 'Package name cannot be empty'}

            # Get venv Python executable
            if os.name == 'nt':
                venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
            else:
                venv_python = os.path.join(VENV_DIR, 'bin', 'python')

            if not os.path.exists(venv_python):
                return {'status': 'error', 'message': 'Virtual environment not found'}

            # Run pip install
            cmd = [venv_python, '-m', 'pip', 'install', package_name]
            env = get_clean_environment()

            print(f"[VENV] Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                print(f"[VENV] Successfully installed: {package_name}")
                return {
                    'status': 'success',
                    'message': f'Successfully installed {package_name}',
                    'output': result.stdout
                }
            else:
                print(f"[VENV] Installation failed: {result.stderr}")
                return {
                    'status': 'error',
                    'message': f'Installation failed: {result.stderr}',
                    'output': result.stderr
                }

        except subprocess.TimeoutExpired:
            return {'status': 'error', 'message': 'Installation timed out'}
        except Exception as e:
            print(f"[VENV ERROR] {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def uninstall_package(self, package_name):
        """Uninstall a package from the virtual environment"""
        try:
            print(f"[VENV] Uninstalling package: {package_name}")

            if not package_name or not package_name.strip():
                return {'status': 'error', 'message': 'Package name cannot be empty'}

            # Prevent uninstalling critical packages
            critical_packages = ['pip', 'setuptools', 'wheel', 'manim', 'manim-fonts']
            if package_name.lower() in critical_packages:
                return {
                    'status': 'error',
                    'message': f'Cannot uninstall critical package: {package_name}'
                }

            # Get venv Python executable
            if os.name == 'nt':
                venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
            else:
                venv_python = os.path.join(VENV_DIR, 'bin', 'python')

            if not os.path.exists(venv_python):
                return {'status': 'error', 'message': 'Virtual environment not found'}

            # Run pip uninstall -y
            cmd = [venv_python, '-m', 'pip', 'uninstall', '-y', package_name]
            env = get_clean_environment()

            print(f"[VENV] Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60
            )

            if result.returncode == 0:
                print(f"[VENV] Successfully uninstalled: {package_name}")
                return {
                    'status': 'success',
                    'message': f'Successfully uninstalled {package_name}',
                    'output': result.stdout
                }
            else:
                print(f"[VENV] Uninstallation failed: {result.stderr}")
                return {
                    'status': 'error',
                    'message': f'Uninstallation failed: {result.stderr}',
                    'output': result.stderr
                }

        except subprocess.TimeoutExpired:
            return {'status': 'error', 'message': 'Uninstallation timed out'}
        except Exception as e:
            print(f"[VENV ERROR] {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def check_package_updates(self):
        """Check for available package updates and check for Manim conflicts"""
        try:
            print("[VENV] Checking for package updates...")

            # Get venv Python executable
            if os.name == 'nt':
                venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
            else:
                venv_python = os.path.join(VENV_DIR, 'bin', 'python')

            if not os.path.exists(venv_python):
                return {
                    'status': 'error',
                    'message': 'Virtual environment not found',
                    'updates': []
                }

            # Run pip list --outdated --format=json
            cmd = [venv_python, '-m', 'pip', 'list', '--outdated', '--format=json']
            env = get_clean_environment()

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60
            )

            if result.returncode == 0:
                import json
                updates = json.loads(result.stdout) if result.stdout.strip() else []
                print(f"[VENV] Found {len(updates)} packages with updates available")

                # Critical packages that Manim depends on
                critical_packages = ['manim', 'manim-fonts', 'manimce', 'cairo', 'pycairo',
                                   'manimpango', 'pango', 'numpy', 'pillow', 'scipy',
                                   'moderngl', 'pygments']

                # Check each update for Manim compatibility
                for update in updates:
                    package_name = update.get('name', '').lower()
                    current_version = update.get('version', '')
                    latest_version = update.get('latest_version', '')

                    # Default values
                    update['safe_to_update'] = True
                    update['warning'] = None
                    update['is_critical'] = False

                    # Check if it's a critical package
                    if package_name in critical_packages:
                        update['is_critical'] = True
                        update['safe_to_update'] = False
                        update['warning'] = f'⚠️ Critical for Manim - updating may cause compatibility issues'
                        print(f"[VENV] WARNING: {package_name} is critical for Manim")

                    # For non-critical packages, do a dry-run to check dependencies
                    elif package_name not in critical_packages:
                        try:
                            # Quick check using pip install --dry-run
                            check_cmd = [venv_python, '-m', 'pip', 'install', '--dry-run', '--upgrade', package_name]
                            check_result = subprocess.run(
                                check_cmd,
                                capture_output=True,
                                text=True,
                                env=env,
                                timeout=30
                            )

                            # Check if output mentions critical packages
                            output_lower = (check_result.stdout + check_result.stderr).lower()
                            affected_critical = [pkg for pkg in critical_packages if pkg in output_lower]

                            if affected_critical:
                                update['safe_to_update'] = False
                                update['warning'] = f'⚠️ May affect: {", ".join(affected_critical)}'
                                print(f"[VENV] WARNING: Updating {package_name} may affect: {affected_critical}")
                        except Exception as check_error:
                            print(f"[VENV] Could not check {package_name}: {check_error}")
                            # If we can't check, mark as potentially unsafe
                            update['safe_to_update'] = True
                            update['warning'] = None

                return {
                    'status': 'success',
                    'updates': updates
                }
            else:
                return {
                    'status': 'error',
                    'message': f'Failed to check updates: {result.stderr}',
                    'updates': []
                }

        except Exception as e:
            print(f"[VENV ERROR] {e}")
            traceback.print_exc()
            return {
                'status': 'error',
                'message': str(e),
                'updates': []
            }

    def update_package(self, package_name):
        """Update a package to the latest version"""
        try:
            print(f"[VENV] Updating package: {package_name}")

            if not package_name or not package_name.strip():
                return {'status': 'error', 'message': 'Package name cannot be empty'}

            # Get venv Python executable
            if os.name == 'nt':
                venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
            else:
                venv_python = os.path.join(VENV_DIR, 'bin', 'python')

            if not os.path.exists(venv_python):
                return {'status': 'error', 'message': 'Virtual environment not found'}

            # Run pip install --upgrade
            cmd = [venv_python, '-m', 'pip', 'install', '--upgrade', package_name]
            env = get_clean_environment()

            print(f"[VENV] Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                print(f"[VENV] Successfully updated: {package_name}")
                return {
                    'status': 'success',
                    'message': f'Successfully updated {package_name}',
                    'output': result.stdout
                }
            else:
                print(f"[VENV] Update failed: {result.stderr}")
                return {
                    'status': 'error',
                    'message': f'Update failed: {result.stderr}',
                    'output': result.stderr
                }

        except subprocess.TimeoutExpired:
            return {'status': 'error', 'message': 'Update timed out'}
        except Exception as e:
            print(f"[VENV ERROR] {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}


def find_free_port():
    """Find a free port on localhost"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def check_venv_exists():
    """Check if virtual environment exists"""
    if os.name == 'nt':
        venv_python = os.path.join(VENV_DIR, 'Scripts', 'python.exe')
    else:
        venv_python = os.path.join(VENV_DIR, 'bin', 'python')

    return os.path.exists(venv_python)


def start_app():
    """Start the desktop application"""
    # Load settings
    load_settings()

    # Create required directories
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(PREVIEW_DIR, exist_ok=True)

    # Check if virtual environment exists
    venv_exists = check_venv_exists()

    print("=" * 60)
    if venv_exists:
        print("[OK] Virtual environment found")
        print(f"[OK] Location: {VENV_DIR}")
    else:
        print("[INFO] Virtual environment not found")
        print("[INFO] Will launch setup wizard")
    print("=" * 60)

    # Start Pyright LSP bridge for VSCode-quality IntelliSense
    def start_lsp_bridge():
        """Start the LSP bridge in background"""
        import threading
        import time

        def run_lsp():
            try:
                # Check if lsp_venv exists
                lsp_venv_path = os.path.join(BASE_DIR, 'lsp_venv')
                if os.name == 'nt':
                    python_path = os.path.join(lsp_venv_path, 'Scripts', 'python.exe')
                else:
                    python_path = os.path.join(lsp_venv_path, 'bin', 'python')

                lsp_bridge_path = os.path.join(BASE_DIR, 'lsp_bridge.py')

                if not os.path.exists(python_path) or not os.path.exists(lsp_bridge_path):
                    print('[LSP] LSP environment or bridge not found, skipping IntelliSense startup')
                    return

                print('[LSP] Starting Pyright Language Server on port 8765...')

                # Start LSP bridge process
                env = get_clean_environment()
                process = subprocess.Popen(
                    [python_path, lsp_bridge_path, '8765', lsp_venv_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding='utf-8',  # Force UTF-8 encoding
                    errors='replace',  # Replace invalid characters instead of crashing
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )

                # Store process for cleanup
                app_state['lsp_process'] = process

                print('[LSP] [OK] Pyright Language Server started')

            except Exception as e:
                print(f'[LSP] Failed to start LSP bridge: {e}')

        # Start in background thread
        threading.Thread(target=run_lsp, daemon=True).start()

    # LSP bridge disabled - using basic Monaco editor without LSP
    # start_lsp_bridge()

    # Create API instance
    api = ManimAPI()

    # Choose HTML file based on venv existence
    if venv_exists:
        html_path = os.path.join(BASE_DIR, 'web', 'index.html')
        window_title = 'Manim Studio - Professional Edition'
    else:
        html_path = os.path.join(BASE_DIR, 'web', 'setup.html')
        window_title = 'Manim Studio - Virtual Environment Setup'

    # DEBUG: Verify HTML file exists
    print(f"[DEBUG] HTML Path: {html_path}")
    print(f"[DEBUG] HTML exists: {os.path.exists(html_path)}")
    print(f"[DEBUG] BASE_DIR: {BASE_DIR}")
    print(f"[DEBUG] web folder exists: {os.path.exists(os.path.join(BASE_DIR, 'web'))}")
    if os.path.exists(os.path.join(BASE_DIR, 'web')):
        web_contents = os.listdir(os.path.join(BASE_DIR, 'web'))
        print(f"[DEBUG] web folder contents: {web_contents}")

    if not os.path.exists(html_path):
        print(f"[ERROR] HTML file not found at: {html_path}")
        print("[ERROR] Cannot create window without HTML file!")
        print("[ERROR] Application will exit")
        return

    # Create native desktop window with DPI awareness
    print(f"[DEBUG] Creating webview window...")
    print(f"[DEBUG] Title: {window_title}")
    try:
        window = webview.create_window(
            title=window_title,
            url=html_path,
            js_api=api,
            width=1600,
            height=1000,
            resizable=True,
            frameless=False,
            easy_drag=False,
            min_size=(1200, 800),
            # Enable DPI awareness for proper scaling on high-DPI displays
            text_select=True
        )
        print(f"[DEBUG] Window created successfully")

        # Store window reference
        app_state['window'] = window

        # Add window closing event handler for autosave
        def on_window_closing():
            """Handle window closing event - autosave if needed"""
            print("[WINDOW] Closing event triggered")
            try:
                # Check if there's code in the current state that needs autosaving
                current_code = app_state.get('current_code')
                if current_code:
                    print("[WINDOW] Autosaving code before closing...")
                    api.autosave_code(current_code)
                    print("[WINDOW] Autosave completed")
            except Exception as e:
                print(f"[WINDOW] Error during autosave on close: {e}")

            # Call cleanup
            cleanup_on_exit()
            return True

        # Register the closing event
        window.events.closing += on_window_closing

        # Start the application
        print(f"[DEBUG] Starting webview...")
        webview.start(debug=False)  # Debug mode disabled
        print(f"[DEBUG] Webview started and returned")
    except Exception as e:
        print(f"[ERROR] Failed to create or start window: {e}")
        import traceback
        traceback.print_exc()
        return



def cleanup_on_exit():
    """Clean up unsaved temp folders and preview files"""
    print("\n[CLEANUP] App is closing, cleaning up...")

    import shutil

    # Stop LSP language server process
    try:
        lsp_proc = app_state.get('lsp_process')
        if lsp_proc and lsp_proc.poll() is None:
            app_state['lsp_running'] = False
            lsp_proc.terminate()
            lsp_proc.wait(timeout=2)
            print("[CLEANUP] LSP language server stopped")
    except Exception as e:
        print(f"[CLEANUP] Failed to stop LSP cleanly: {e}")

    # Stop background dependency checker thread.
    try:
        app_state['dependency_stop_event'].set()
        checker_thread = app_state.get('dependency_checker_thread')
        if checker_thread and checker_thread.is_alive():
            checker_thread.join(timeout=1.0)
            print("[CLEANUP] Dependency checker stopped")
    except Exception as e:
        print(f"[CLEANUP] Failed to stop dependency checker cleanly: {e}")

    # Keep preview files in assets folder (don't delete them)
    # Preview files stay in ASSETS_DIR for user access even after app closes
    print("[CLEANUP] Preview files kept in assets folder:")
    if app_state['preview_files_to_cleanup']:
        print(f"  {len(app_state['preview_files_to_cleanup'])} preview file(s) saved in {ASSETS_DIR}")
        for preview_file in app_state['preview_files_to_cleanup']:
            if os.path.exists(preview_file):
                print(f"    - {os.path.basename(preview_file)}")
        print("[INFO] Preview files will persist - manually delete from assets folder if needed")
    else:
        print("[OK] No preview files were created")

    # Clean up temp folders in MEDIA_DIR (only if user didn't save)
    print("[CLEANUP] Cleaning up unsaved temp folders...")
    cleanup_count = 0

    # Check videos folder for temp_ folders
    videos_base = os.path.join(MEDIA_DIR, 'videos')
    if os.path.exists(videos_base):
        try:
            for folder_name in os.listdir(videos_base):
                folder_path = os.path.join(videos_base, folder_name)
                if os.path.isdir(folder_path) and folder_name.startswith('temp_'):
                    shutil.rmtree(folder_path)
                    cleanup_count += 1
                    print(f"  Removed temp folder: {folder_name}")
        except Exception as e:
            print(f"  Error cleaning videos temp folders: {e}")

    # Check images folder for temp_ folders
    images_base = os.path.join(MEDIA_DIR, 'images')
    if os.path.exists(images_base):
        try:
            for folder_name in os.listdir(images_base):
                folder_path = os.path.join(images_base, folder_name)
                if os.path.isdir(folder_path) and folder_name.startswith('temp_'):
                    shutil.rmtree(folder_path)
                    cleanup_count += 1
                    print(f"  Removed temp folder: {folder_name}")
        except Exception as e:
            print(f"  Error cleaning images temp folders: {e}")

    if cleanup_count > 0:
        print(f"[OK] Cleaned up {cleanup_count} temp folder(s)")
    else:
        print("[OK] No temp folders to clean")
    print("[OK] Cleanup complete")

if __name__ == '__main__':
    # CRITICAL: Must be first for frozen exe with pywebview (uses multiprocessing)
    # Without this, exe will freeze/not open when console is disabled
    import multiprocessing
    multiprocessing.freeze_support()

    # Enable DPI awareness on Windows for proper high-DPI display support
    if sys.platform == 'win32':
        try:
            import ctypes
            # Try to set DPI awareness (Windows 8.1+)
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
                print("[DPI] Per-monitor DPI awareness enabled (Windows 8.1+)")
            except Exception:
                # Fallback for older Windows versions
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                    print("[DPI] System DPI awareness enabled (Windows Vista+)")
                except Exception:
                    print("[DPI] Could not set DPI awareness (running on older Windows)")
        except Exception as e:
            print(f"[DPI] Warning: Failed to set DPI awareness: {e}")

    import atexit
    atexit.register(cleanup_on_exit)

    # When running as frozen exe, also log to file for debugging double-click issues
    if getattr(sys, 'frozen', False):
        log_file = os.path.join(USER_DATA_DIR, 'manim_studio_debug.log')
        try:
            os.makedirs(USER_DATA_DIR, exist_ok=True)
            log_handle = open(log_file, 'w', encoding='utf-8')

            # Create a custom print that writes to both console and file
            original_print = print
            def print_dual(*args, **kwargs):
                original_print(*args, **kwargs)
                try:
                    original_print(*args, **kwargs, file=log_handle, flush=True)
                except:
                    pass

            # Replace built-in print
            import builtins
            builtins.print = print_dual

            print(f"[LOGGING] Debug log file created: {log_file}")
        except Exception as e:
            print(f"[WARNING] Could not create debug log: {e}")

    print("=" * 60)
    print("Starting Manim Studio Desktop App...")
    print("=" * 60)
    print(f"Base Directory: {BASE_DIR}")
    print(f"User Data: {USER_DATA_DIR}")
    print(f"Media Directory: {MEDIA_DIR}")
    print(f"Assets Directory: {ASSETS_DIR}")
    print(f"Preview Directory: {PREVIEW_DIR}")
    print("=" * 60)

    try:
        start_app()
    except Exception as e:
        print(f"[FATAL ERROR] Application crashed: {e}")
        import traceback
        traceback.print_exc()
        # Keep window open if there's an error
        if getattr(sys, 'frozen', False):
            input("Press Enter to exit...")
