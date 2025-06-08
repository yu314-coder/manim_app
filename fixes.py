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

def fix_manim_config():
    """Fix the manim configuration issue by creating a default.cfg file
    and a minimal TeX template that does not rely on the ``standalone``
    LaTeX class.  The template is written to ``tex_template.tex`` in the
    same directory as ``default.cfg`` and the path is exposed via the
    ``MANIM_TEX_TEMPLATE_PATH`` environment variable so that Manim can
    pick it up at runtime.
    """
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
            with open(default_cfg_path, 'w', encoding='utf-8') as f:
                f.write(DEFAULT_MANIM_CONFIG)

            if not os.path.exists(default_cfg_path) or os.path.getsize(default_cfg_path) == 0:
                print(f"Warning: failed to write {default_cfg_path}")
                return False

            # Write minimal LaTeX template that works without the
            # ``standalone`` package.  This prevents the common
            # "standalone not found" error when LaTeX is incomplete.
            template_path = os.path.join(manim_config_dir, 'tex_template.tex')
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(BASIC_TEX_TEMPLATE)

            if not os.path.exists(template_path) or os.path.getsize(template_path) == 0:
                print(f"Warning: failed to write {template_path}")
                return False

            # Expose the template path so other modules can use it
            os.environ['MANIM_TEX_TEMPLATE_PATH'] = template_path

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

# Add this to app.py's main() at the start
def apply_fixes():
    """Apply all fixes at startup"""
    if not fix_manim_config():
        print("Warning: Manim config setup failed")
    patch_subprocess()
    patch_manim_latex()

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


def patch_manim_latex():
    """Apply custom LaTeX template if available."""
    try:
        template_path = os.environ.get('MANIM_TEX_TEMPLATE_PATH')
        if not template_path or not os.path.exists(template_path):
            return False

        import manim
        from manim.utils.tex_templates import TexTemplate

        with open(template_path, 'r', encoding='utf-8') as f:
            template_text = f.read()

        manim.config.tex_template = TexTemplate(template_text)
        return True
    except Exception as e:
        print(f"Error applying LaTeX template: {e}")
        return False
