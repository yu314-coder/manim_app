# fixes.py - Applied patches for the build process
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

# Legacy apply_fixes kept for backward compatibility; real logic is in
# ``apply_all_fixes`` defined later.
def apply_fixes():
    return apply_all_fixes()

def fix_manim_config():
    """Fix the manim configuration issue by creating a default.cfg file
    and a minimal TeX template that does not rely on the ``standalone``
    LaTeX class.  The template is written to ``tex_template.tex`` in the
    same directory as ``default.cfg`` and the path is exposed via the
    ``MANIM_TEX_TEMPLATE_PATH`` environment variable so that Manim can
    pick it up at runtime.
    """
    try:
        # Determine a persistent base directory. When running from a
        # packaged executable we want this to live alongside the exe
        # rather than inside the temporary ``onefile`` extraction
        # directory.  Falling back to the directory of this file when
        # running from source.
        if hasattr(sys, 'frozen') and hasattr(sys, '_MEIPASS'):
            # We're running as a packaged executable
            if 'onefile' in str(sys.executable).lower() or 'temp' in str(sys.executable).lower():
                # Onefile build - use a persistent directory
                base_dir = os.path.dirname(os.path.realpath(sys.executable))
            else:
                # Directory build - use the directory containing the executable
                base_dir = os.path.dirname(sys.executable)
        else:
            # Running from source
            base_dir = os.path.dirname(os.path.abspath(__file__))

        manim_config_dir = os.path.join(base_dir, 'manim_config')
        os.makedirs(manim_config_dir, exist_ok=True)

        # Create default manim configuration
        default_cfg_path = os.path.join(manim_config_dir, 'default.cfg')
        with open(default_cfg_path, 'w', encoding='utf-8') as f:
            f.write(DEFAULT_MANIM_CONFIG)

        if not os.path.exists(default_cfg_path) or os.path.getsize(default_cfg_path) == 0:
            print(f"Warning: failed to write {default_cfg_path}")
            return False

        # Set environment variable for manim to find the config
        os.environ['MANIM_CONFIG_FILE'] = default_cfg_path

        # Create a basic TeX template that does not rely on ``standalone``.
        # This prevents the common
        # "standalone not found" error when LaTeX is incomplete.
        template_path = os.path.join(manim_config_dir, 'tex_template.tex')
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(BASIC_TEX_TEMPLATE)

        if not os.path.exists(template_path) or os.path.getsize(template_path) == 0:
            print(f"Warning: failed to write {template_path}")
            return False

        # Expose the template path so other modules can use it
        os.environ['MANIM_TEX_TEMPLATE'] = template_path

        print(f"Created manim config at: {default_cfg_path}")
        return True
    except Exception as e:
        print(f"Error fixing manim config: {e}")
    return False

def patch_manim_latex():
    """Patch Manim LaTeX handling for better compatibility"""
    try:
        # Set environment variables for better LaTeX compatibility
        os.environ['MANIM_LATEX_PREAMBLE'] = r'\usepackage{amsmath,amssymb}'
        
        # Try to set a basic LaTeX template path
        if 'MANIM_TEX_TEMPLATE' not in os.environ:
            # Use a basic template path
            template_dir = os.path.join(os.path.expanduser("~"), ".manim")
            os.makedirs(template_dir, exist_ok=True)
            template_path = os.path.join(template_dir, "tex_template.tex")
            
            # Create basic template if it doesn't exist
            if not os.path.exists(template_path):
                with open(template_path, 'w', encoding='utf-8') as f:
                    f.write(BASIC_TEX_TEMPLATE)
            
            os.environ['MANIM_TEX_TEMPLATE'] = template_path
            
        return True
    except Exception as e:
        print(f"Warning: LaTeX patch failed: {e}")
        return False

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
                startupinfo = kwargs.get('startupinfo', None)
                if startupinfo is None:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    kwargs['startupinfo'] = startupinfo
                
                # Add creation flags
                creationflags = kwargs.get('creationflags', 0)
                kwargs['creationflags'] = creationflags | subprocess.CREATE_NO_WINDOW
            
            return original_run(*args, **kwargs)
        
        def safe_popen_wrapper(*args, **kwargs):
            # Add window hiding for Windows
            if sys.platform == "win32":
                startupinfo = kwargs.get('startupinfo', None)
                if startupinfo is None:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    kwargs['startupinfo'] = startupinfo
                
                # Add creation flags
                creationflags = kwargs.get('creationflags', 0)
                kwargs['creationflags'] = creationflags | subprocess.CREATE_NO_WINDOW
            
            return original_popen(*args, **kwargs)
        
        # Apply patches
        subprocess.run = safe_run_wrapper
        subprocess.Popen = safe_popen_wrapper
        
        # Mark as patched
        subprocess._manimstudio_patched = True
        
        print("Subprocess patched successfully")
        return True
        
    except Exception as e:
        print(f"Warning: Subprocess patching failed: {e}")
        return False

def patch_site_packages():
    """Patch site-packages loading for frozen executables"""
    try:
        if hasattr(sys, 'frozen'):
            # We're in a frozen executable, ensure site-packages are in path
            import site
            
            # Add potential site-packages directories
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller-style frozen app
                site_packages = os.path.join(sys._MEIPASS, 'site-packages')
                if os.path.exists(site_packages) and site_packages not in sys.path:
                    sys.path.insert(0, site_packages)
            
            # Try to find and add any site-packages directories
            for path in sys.path[:]:
                site_pkg_path = os.path.join(path, 'site-packages')
                if os.path.exists(site_pkg_path) and site_pkg_path not in sys.path:
                    sys.path.insert(0, site_pkg_path)
                    
        return True
    except Exception as e:
        print(f"Warning: Site packages patching failed: {e}")
        return False

def patch_imports():
    """Patch problematic imports for frozen executables"""
    try:
        # Disable problematic modules that can cause issues in frozen builds
        problematic_modules = [
            'zstandard',  # Can cause linking issues
            'lzma',       # Sometimes causes issues in frozen builds
        ]
        
        for module_name in problematic_modules:
            if module_name not in sys.modules:
                try:
                    # Try to import normally first
                    __import__(module_name)
                except (ImportError, OSError):
                    # If import fails, set to None to prevent further attempts
                    sys.modules[module_name] = None
                    
        return True
    except Exception as e:
        print(f"Warning: Import patching failed: {e}")
        return False

def fix_path_encoding():
    """Fix path encoding issues on Windows"""
    try:
        if sys.platform == "win32":
            # Ensure proper encoding for paths
            import locale
            
            # Set locale to handle Unicode properly
            try:
                locale.setlocale(locale.LC_ALL, '')
            except locale.Error:
                pass
                
            # Ensure sys.stdout and sys.stderr can handle Unicode
            if hasattr(sys.stdout, 'reconfigure'):
                try:
                    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
                except:
                    pass
                    
        return True
    except Exception as e:
        print(f"Warning: Path encoding fix failed: {e}")
        return False

def fix_encoding_issues():
    """Fix encoding issues that cause crashes"""
    try:
        # Force UTF-8 encoding for std streams
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
                sys.stderr.reconfigure(encoding='utf-8', errors='ignore')
            except Exception:
                pass

        os.environ['PYTHONIOENCODING'] = 'utf-8'
        os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = '0'

        return True
    except Exception as e:
        print(f"Warning: Encoding fix failed: {e}")
        return False

def ensure_ascii_path(path: str) -> str:
    """Ensure the returned path only contains ASCII characters."""
    if os.name == "nt" and any(ord(c) > 127 for c in path):
        # Fallback to a simple ASCII location if needed
        fallback = os.path.join("C:\\", "manim_temp")
        os.makedirs(fallback, exist_ok=True)
        return fallback
    return path


def setup_temp_directories():
    """Setup temporary directories for the application"""
    try:
        import tempfile

        base_temp = ensure_ascii_path(tempfile.gettempdir())

        # Create application-specific temp directory
        app_temp_dir = os.path.join(base_temp, "manim_studio_temp")
        os.makedirs(app_temp_dir, exist_ok=True)

        # Set environment variable for other parts of the app to use
        os.environ['MANIM_STUDIO_TEMP'] = app_temp_dir

        # Create media temp directory
        media_temp_dir = os.path.join(app_temp_dir, "media")
        os.makedirs(media_temp_dir, exist_ok=True)
        os.environ['MANIM_MEDIA_TEMP'] = media_temp_dir

        return True
    except Exception as e:
        print(f"Warning: Temp directory setup failed: {e}")
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

# Minimal LaTeX template that does not require the ``standalone``
# document class.  Used when generating the temporary Manim
# configuration for the packaged application.
BASIC_TEX_TEMPLATE = r"""
\documentclass[preview]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath, amssymb}
\usepackage[english]{babel}
\begin{document}
YourTextHere
\end{document}
"""

def apply_all_fixes():
    """Apply all available fixes - comprehensive fix application"""
    fixes_applied = []
    
    print("Applying startup fixes...")
    
    # 1. Fix imports first
    if patch_imports():
        fixes_applied.append("imports")

    # 2. Fix encoding issues
    if fix_encoding_issues():
        fixes_applied.append("encoding")

    # 3. Fix path encoding
    if fix_path_encoding():
        fixes_applied.append("path_encoding")

    # 4. Setup temp directories
    if setup_temp_directories():
        fixes_applied.append("temp_directories")

    # 5. Fix site packages
    if patch_site_packages():
        fixes_applied.append("site_packages")

    # 6. Fix subprocess
    if patch_subprocess():
        fixes_applied.append("subprocess")

    # 7. Fix Manim config
    if fix_manim_config():
        fixes_applied.append("manim_config")

    # 8. Fix LaTeX
    if patch_manim_latex():
        fixes_applied.append("manim_latex")
    
    if fixes_applied:
        print(f"Applied fixes: {', '.join(fixes_applied)}")
    else:
        print("Warning: No fixes were successfully applied")
    
    return len(fixes_applied) > 0

# Module-level initialization
if __name__ == "__main__":
    # If run directly, apply all fixes
    apply_all_fixes()
