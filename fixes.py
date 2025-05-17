# fixes.py - Applied patches for the build process
import os
import sys
from pathlib import Path
import subprocess
import shutil
import site

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

# Fix the subprocess conflict in our patch
def fix_subprocess_conflict():
    """Fix the subprocess capture_output and stdout/stderr conflict"""
    original_run = subprocess.run
    
    def fixed_run(*args, **kwargs):
        """Fixed run that properly handles stdout/stderr with capture_output"""
        if 'capture_output' in kwargs and kwargs['capture_output']:
            # Remove stdout/stderr if capture_output is True
            kwargs.pop('stdout', None)
            kwargs.pop('stderr', None)
        return original_run(*args, **kwargs)
    
    subprocess.run = fixed_run
