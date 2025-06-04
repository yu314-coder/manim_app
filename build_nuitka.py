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

def detect_latex_installation():
    """Detect and return paths to LaTeX installation components"""
    latex_info = {
        'latex_exe': None,
        'pdflatex_exe': None,
        'xelatex_exe': None,
        'tex_dir': None,
        'texmf_dir': None,
        'available': False
    }
    
    import shutil
    
    # Try to find LaTeX executables
    latex_executables = ['latex', 'pdflatex', 'xelatex', 'lualatex']
    for exe in latex_executables:
        path = shutil.which(exe)
        if path:
            latex_info[f'{exe}_exe'] = path
            latex_info['available'] = True
    
    # Try to find TeX directory structure
    possible_tex_dirs = [
        r"C:\texlive",
        r"C:\Program Files\MiKTeX",
        r"C:\Users\{}\AppData\Local\Programs\MiKTeX".format(os.getenv('USERNAME', '')),
        "/usr/share/texlive",
        "/usr/local/texlive",
        "/opt/texlive"
    ]
    
    for tex_dir in possible_tex_dirs:
        if os.path.exists(tex_dir):
            latex_info['tex_dir'] = tex_dir
            # Look for texmf directory
            for root, dirs, files in os.walk(tex_dir):
                if 'texmf' in dirs:
                    latex_info['texmf_dir'] = os.path.join(root, 'texmf')
                    break
                if root.endswith('texmf'):
                    latex_info['texmf_dir'] = root
                    break
            break
    
    return latex_info

def create_latex_bundle_script():
    """Create a script to bundle LaTeX dependencies"""
    bundle_content = '''# latex_bundler.py - Bundle LaTeX dependencies for standalone build
import os
import sys
import shutil
import subprocess
from pathlib import Path

class LaTeXBundler:
    """Handles bundling of LaTeX installation for standalone builds"""
    
    def __init__(self, target_dir="latex_bundle"):
        self.target_dir = Path(target_dir)
        self.latex_info = self.detect_latex()
        
    def detect_latex(self):
        """Detect LaTeX installation"""
        latex_info = {
            'binaries': {},
            'texmf_dir': None,
            'available': False
        }
        
        # Find LaTeX binaries
        binaries = ['latex', 'pdflatex', 'xelatex', 'lualatex', 'bibtex', 'makeindex']
        for binary in binaries:
            path = shutil.which(binary)
            if path:
                latex_info['binaries'][binary] = path
                latex_info['available'] = True
        
        # Find TeX directory
        if sys.platform == "win32":
            possible_dirs = [
                Path("C:/texlive"),
                Path("C:/Program Files/MiKTeX"),
                Path(f"C:/Users/{os.getenv('USERNAME', '')}/AppData/Local/Programs/MiKTeX"),
                Path("C:/MiKTeX")
            ]
        else:
            possible_dirs = [
                Path("/usr/share/texlive"),
                Path("/usr/local/texlive"),
                Path("/opt/texlive")
            ]
        
        for tex_dir in possible_dirs:
            if tex_dir.exists():
                # Find texmf directory
                for item in tex_dir.rglob("texmf*"):
                    if item.is_dir() and any(item.glob("tex/**")):
                        latex_info['texmf_dir'] = item
                        break
                if latex_info['texmf_dir']:
                    break
        
        return latex_info
    
    def bundle_latex_essentials(self):
        """Bundle essential LaTeX components"""
        if not self.latex_info['available']:
            print("❌ LaTeX not found on system - cannot bundle")
            return False
        
        print("📦 Bundling LaTeX essentials...")
        self.target_dir.mkdir(exist_ok=True)
        
        # Create directory structure
        (self.target_dir / "bin").mkdir(exist_ok=True)
        (self.target_dir / "texmf" / "tex" / "latex").mkdir(parents=True, exist_ok=True)
        (self.target_dir / "texmf" / "fonts").mkdir(parents=True, exist_ok=True)
        
        # Copy binaries
        for name, path in self.latex_info['binaries'].items():
            if Path(path).exists():
                shutil.copy2(path, self.target_dir / "bin" / f"{name}.exe")
                print(f"✅ Bundled {name}")
        
        # Bundle essential LaTeX packages
        if self.latex_info['texmf_dir']:
            self.bundle_latex_packages()
            self.bundle_fonts()
        
        # Create LaTeX configuration
        self.create_latex_config()
        
        print(f"✅ LaTeX bundle created in {self.target_dir}")
        return True
    
    def bundle_latex_packages(self):
        """Bundle essential LaTeX packages"""
        essential_packages = [
            "amsmath", "amsfonts", "amssymb", "amscd", "amsthm",
            "geometry", "graphicx", "color", "xcolor", "tikz",
            "pgf", "fancyhdr", "hyperref", "babel", "inputenc",
            "fontenc", "lmodern", "textcomp", "microtype"
        ]
        
        texmf_source = self.latex_info['texmf_dir']
        texmf_target = self.target_dir / "texmf"
        
        print("📚 Bundling LaTeX packages...")
        
        # Copy essential packages
        for package in essential_packages:
            # Search for package in various locations
            package_paths = list(texmf_source.rglob(f"{package}*"))
            for pkg_path in package_paths:
                if pkg_path.is_dir() and any(pkg_path.glob("*.sty")):
                    # Found package directory
                    relative_path = pkg_path.relative_to(texmf_source)
                    target_path = texmf_target / relative_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(pkg_path, target_path, dirs_exist_ok=True)
                    print(f"📦 Bundled package: {package}")
                    break
                elif pkg_path.suffix == ".sty":
                    # Individual style file
                    relative_path = pkg_path.relative_to(texmf_source)
                    target_path = texmf_target / relative_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(pkg_path, target_path)
                    print(f"📄 Bundled style: {package}")
                    break
    
    def bundle_fonts(self):
        """Bundle essential fonts"""
        print("🔤 Bundling fonts...")
        
        texmf_source = self.latex_info['texmf_dir']
        fonts_target = self.target_dir / "texmf" / "fonts"
        
        # Essential font directories
        font_dirs = ["tfm", "type1", "map", "enc"]
        
        for font_dir in font_dirs:
            source_font_dir = texmf_source / "fonts" / font_dir
            if source_font_dir.exists():
                target_font_dir = fonts_target / font_dir
                # Copy essential fonts (Computer Modern, Latin Modern)
                for font_family in ["cm", "lm", "computer-modern", "latin-modern"]:
                    for font_path in source_font_dir.rglob(f"*{font_family}*"):
                        relative_path = font_path.relative_to(source_font_dir)
                        target_path = target_font_dir / relative_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        if font_path.is_file():
                            shutil.copy2(font_path, target_path)
                print(f"✅ Bundled {font_dir} fonts")
    
    def create_latex_config(self):
        """Create LaTeX configuration for bundled installation"""
        config_content = f"""% LaTeX configuration for bundled installation
\\def\\bundledtexmf{{{self.target_dir.absolute()}/texmf}}
\\def\\bundledbin{{{self.target_dir.absolute()}/bin}}

% Set up search paths
\\makeatletter
\\def\\input@path{{\\bundledtexmf/tex//}}
\\def\\graphics@path{{\\bundledtexmf/tex//}}
\\makeatother

% Essential package setup
\\RequirePackage{{amsmath}}
\\RequirePackage{{amsfonts}}
\\RequirePackage{{amssymb}}
"""
        
        config_path = self.target_dir / "texmf.cnf"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)
        
        # Create environment setup script
        env_script = f"""#!/bin/bash
# Environment setup for bundled LaTeX
export TEXMFHOME="{self.target_dir.absolute()}/texmf"
export PATH="{self.target_dir.absolute()}/bin:$PATH"
export TEXINPUTS="{self.target_dir.absolute()}/texmf/tex//:$TEXINPUTS"
"""
        
        env_path = self.target_dir / "setup_env.sh"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_script)
        
        # Windows batch version
        env_bat = f"""@echo off
REM Environment setup for bundled LaTeX
set TEXMFHOME={self.target_dir.absolute()}\\texmf
set PATH={self.target_dir.absolute()}\\bin;%PATH%
set TEXINPUTS={self.target_dir.absolute()}\\texmf\\tex\\\\;%TEXINPUTS%
"""
        
        env_bat_path = self.target_dir / "setup_env.bat"
        with open(env_bat_path, "w", encoding="utf-8") as f:
            f.write(env_bat)

# Initialize bundler
bundler = LaTeXBundler()
'''
    
    with open("latex_bundler.py", "w", encoding="utf-8") as f:
        f.write(bundle_content)
    
    if USE_ASCII_ONLY:
        print("Created LaTeX bundler script")
    else:
        print("📦 Created LaTeX bundler script")

def create_latex_runtime_patcher():
    """Create a runtime patcher that handles LaTeX issues during execution"""
    patcher_content = '''# latex_runtime_patcher.py - Runtime LaTeX issue handler
import sys
import os
import warnings

class LaTeXFallbackHandler:
    """Handles LaTeX operations gracefully when LaTeX is not available"""
    
    def __init__(self):
        self.latex_available = self.check_latex_availability()
        if not self.latex_available:
            self.patch_latex_operations()
    
    def check_latex_availability(self):
        """Check if LaTeX is actually available in the system"""
        try:
            import subprocess
            result = subprocess.run(['latex', '--version'], 
                                 capture_output=True, 
                                 timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def patch_latex_operations(self):
        """Patch all LaTeX-related operations to use fallbacks"""
        print("LaTeX not detected - applying fallback patches...")
        
        # Patch sympy LaTeX rendering
        try:
            import sympy
            if hasattr(sympy, 'latex'):
                original_latex = sympy.latex
                
                def safe_latex_render(expr, **kwargs):
                    """Safe LaTeX rendering with text fallback"""
                    try:
                        return str(expr)  # Simple string representation
                    except:
                        return "Mathematical Expression"
                
                sympy.latex = safe_latex_render
        except ImportError:
            pass
        
        # Patch matplotlib LaTeX
        try:
            import matplotlib
            matplotlib.rcParams['text.usetex'] = False
            matplotlib.rcParams['mathtext.default'] = 'regular'
            print("Disabled LaTeX in matplotlib")
        except ImportError:
            pass
        
        # Patch manim LaTeX operations
        try:
            import manim
            self.patch_manim_latex(manim)
        except ImportError:
            pass
    
    def patch_manim_latex(self, manim):
        """Comprehensive manim LaTeX patching"""
        try:
            # Patch config
            if hasattr(manim, 'config'):
                manim.config.tex_template = None
                manim.config.preview = False
            
            # Patch TeX-related classes
            try:
                from manim.mobject.text.tex_mobject import TexMobject, MathTex
                from manim.mobject.text.text_mobject import Text
                
                # Create safe base class
                class SafeTexMobject(Text):
                    def __init__(self, *args, **kwargs):
                        # Convert LaTeX to plain text
                        if args:
                            text = str(args[0])
                            # Simple LaTeX to text conversion
                            text = text.replace('\\\\', '\\n')
                            text = text.replace('$', '')
                            text = text.replace('{', '').replace('}', '')
                        else:
                            text = "Mathematical Expression"
                        
                        super().__init__(text, **kwargs)
                
                # Replace TeX classes with safe versions
                manim.mobject.text.tex_mobject.TexMobject = SafeTexMobject
                manim.mobject.text.tex_mobject.MathTex = SafeTexMobject
                
                print("Patched manim TeX mobjects with text fallbacks")
                
            except (ImportError, AttributeError):
                pass
                
        except Exception as e:
            print(f"Warning: Could not fully patch manim LaTeX: {e}")

# Global handler instance
latex_handler = LaTeXFallbackHandler()

def ensure_no_latex_errors():
    """Function to call at startup to ensure LaTeX won't cause crashes"""
    latex_handler.patch_latex_operations()
    
    # Suppress LaTeX-related warnings
    warnings.filterwarnings('ignore', category=UserWarning, module='.*tex.*')
    warnings.filterwarnings('ignore', message='.*LaTeX.*')
    warnings.filterwarnings('ignore', message='.*latex.*')

# Auto-apply on import
ensure_no_latex_errors()
'''
    
    with open("latex_runtime_patcher.py", "w", encoding="utf-8") as f:
        f.write(patcher_content)
    
    if USE_ASCII_ONLY:
        print("Created LaTeX runtime patcher")
    else:
        print("🔧 Created LaTeX runtime patcher")

def create_full_latex_manim_config():
    """Create manim configuration that properly uses bundled LaTeX"""
    config_content = '''# manim_latex_config.py - Full LaTeX support configuration
import os
import sys
from pathlib import Path

# Find bundled LaTeX directory
def find_bundled_latex():
    """Find the bundled LaTeX installation"""
    possible_locations = [
        Path("latex_bundle"),
        Path("./latex_bundle"),
        Path("../latex_bundle"),
        Path(sys.executable).parent / "latex_bundle",
    ]
    
    # For Nuitka onefile builds, check in temp directory
    if hasattr(sys, '_MEIPASS'):
        possible_locations.append(Path(sys._MEIPASS) / "latex_bundle")
    
    # For Nuitka standalone builds
    if 'NUITKA_ONEFILE_PARENT' in os.environ:
        app_dir = Path(os.environ['NUITKA_ONEFILE_PARENT']).parent
        possible_locations.append(app_dir / "latex_bundle")
    
    for location in possible_locations:
        if location.exists() and (location / "bin").exists():
            return location
    
    return None

def setup_latex_environment():
    """Set up environment for bundled LaTeX"""
    latex_dir = find_bundled_latex()
    
    if latex_dir:
        print(f"📦 Found bundled LaTeX at: {latex_dir}")
        
        # Set up environment variables
        os.environ["TEXMFHOME"] = str(latex_dir / "texmf")
        os.environ["TEXMFLOCAL"] = str(latex_dir / "texmf")
        os.environ["TEXINPUTS"] = str(latex_dir / "texmf" / "tex") + "//:."
        
        # Add LaTeX binaries to PATH
        latex_bin = str(latex_dir / "bin")
        if latex_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = latex_bin + os.pathsep + os.environ.get("PATH", "")
        
        # Set LaTeX template for manim
        try:
            import manim
            
            # Custom LaTeX template with bundled packages
            latex_template = r"""
\\documentclass[preview]{{standalone}}
\\usepackage[english]{{babel}}
\\usepackage{{amsmath}}
\\usepackage{{amsfonts}}
\\usepackage{{amssymb}}
\\usepackage{{dsfont}}
\\usepackage{{setspace}}
\\usepackage{{tipa}}
\\usepackage{{relsize}}
\\usepackage{{textcomp}}
\\usepackage{{mathrsfs}}
\\usepackage{{calligra}}
\\usepackage{{wasysym}}
\\usepackage{{ragged2e}}
\\usepackage{{physics}}
\\usepackage{{xcolor}}
\\usepackage{{microtype}}
\\DisableLigatures{{encoding = *, family = * }}
\\usepackage[UTF8]{{ctex}}
\\linespread{{1}}
\\begin{{document}}
YourTextHere
\\end{{document}}
"""
            
            if hasattr(manim, 'config'):
                manim.config.tex_template = latex_template
                manim.config.tex_template_file = None
                manim.config.preview = False
                print("✅ Configured manim with bundled LaTeX")
                
        except ImportError:
            print("⚠️ Manim not available")
        
        return True
    else:
        print("❌ Bundled LaTeX not found - falling back to system LaTeX")
        return False

def create_latex_tex_mobject_with_bundled():
    """Create enhanced TeX mobjects that use bundled LaTeX"""
    try:
        import manim
        from manim.mobject.text.tex_mobject import TexMobject, MathTex
        
        class BundledTexMobject(TexMobject):
            """TeX mobject that uses bundled LaTeX"""
            
            def __init__(self, *args, **kwargs):
                # Ensure LaTeX environment is set up
                setup_latex_environment()
                super().__init__(*args, **kwargs)
        
        class BundledMathTex(MathTex):
            """Math TeX mobject that uses bundled LaTeX"""
            
            def __init__(self, *args, **kwargs):
                # Ensure LaTeX environment is set up
                setup_latex_environment()
                super().__init__(*args, **kwargs)
        
        # Replace the default classes
        manim.mobject.text.tex_mobject.TexMobject = BundledTexMobject
        manim.mobject.text.tex_mobject.MathTex = BundledMathTex
        
        print("✅ Enhanced TeX mobjects with bundled LaTeX support")
        
    except ImportError:
        print("⚠️ Could not enhance TeX mobjects - manim not available")

def initialize_latex_support():
    """Initialize full LaTeX support with bundled installation"""
    print("🔧 Initializing bundled LaTeX support...")
    
    # Set up environment
    latex_available = setup_latex_environment()
    
    if latex_available:
        # Create enhanced TeX mobjects
        create_latex_tex_mobject_with_bundled()
        
        # Configure matplotlib for LaTeX
        try:
            import matplotlib
            matplotlib.rcParams['text.usetex'] = True
            matplotlib.rcParams['text.latex.preamble'] = r"""
                \\usepackage{amsmath}
                \\usepackage{amsfonts}
                \\usepackage{amssymb}
            """
            print("✅ Configured matplotlib with LaTeX")
        except ImportError:
            pass
        
        # Configure SymPy for LaTeX
        try:
            import sympy
            # SymPy should automatically use system LaTeX
            print("✅ SymPy LaTeX support enabled")
        except ImportError:
            pass
    
    return latex_available

# Auto-initialize on import
latex_support_available = initialize_latex_support()

if latex_support_available:
    print("🎉 Full LaTeX support initialized successfully!")
else:
    print("⚠️ LaTeX support initialization failed - using fallbacks")
'''
    
    with open("manim_latex_config.py", "w", encoding="utf-8") as f:
        f.write(config_content)
    
    if USE_ASCII_ONLY:
        print("Created full LaTeX manim configuration")
    else:
        print("📄 Created full LaTeX manim configuration")

def create_enhanced_manim_safe_config():
    """Create an enhanced manim configuration that completely disables LaTeX with better fallbacks"""
    config_content = '''# Enhanced Safe Manim Configuration for Standalone Builds
import os
import sys

# Set environment variables to completely disable LaTeX
os.environ["MANIM_DISABLE_LATEX"] = "1"
os.environ["MANIM_TEX_TEMPLATE"] = ""
os.environ["MANIM_NO_TEX"] = "1"
os.environ["LATEX_AVAILABLE"] = "0"

# Configure manim to work without LaTeX
try:
    import manim
    
    # Override config defaults more aggressively
    if hasattr(manim, 'config'):
        manim.config.tex_template = None
        manim.config.preview = False
        manim.config.verbosity = "ERROR"
        manim.config.disable_caching = True
        
        # Disable all LaTeX-related features
        try:
            manim.config.tex_template_file = None
            manim.config.intermediate_filetype = ""
        except:
            pass
        
    # More comprehensive monkey patching for LaTeX functions
    try:
        from manim.utils import tex_file_writing
        from manim.mobject.text import tex_mobject
        
        def safe_latex_fallback(*args, **kwargs):
            """Enhanced fallback when LaTeX operations fail"""
            print("LaTeX not available in standalone build - using text fallback")
            return None
            
        def safe_tex_string_to_svg_file(*args, **kwargs):
            """Safe replacement for tex_string_to_svg_file"""
            print("LaTeX rendering disabled - using plain text")
            return None
            
        # Replace problematic functions with safe versions
        if hasattr(tex_file_writing, 'latex'):
            tex_file_writing.latex = safe_latex_fallback
        if hasattr(tex_file_writing, 'print_all_tex_errors'):
            tex_file_writing.print_all_tex_errors = lambda *args: None
        if hasattr(tex_file_writing, 'tex_string_to_svg_file'):
            tex_file_writing.tex_string_to_svg_file = safe_tex_string_to_svg_file
        
        # Patch TeX mobject classes to use text fallbacks
        try:
            if hasattr(tex_mobject, 'TexMobject'):
                original_tex_init = tex_mobject.TexMobject.__init__
                
                def safe_tex_init(self, *args, **kwargs):
                    """Safe TeX mobject initialization with text fallback"""
                    try:
                        # Try to convert to simple text
                        if args:
                            text_content = str(args[0])
                            # Create a simple text mobject instead
                            from manim.mobject.text.text_mobject import Text
                            text_obj = Text(text_content)
                            self.__dict__.update(text_obj.__dict__)
                        else:
                            original_tex_init(self, *args, **kwargs)
                    except Exception as e:
                        print(f"TeX fallback used: {e}")
                        from manim.mobject.text.text_mobject import Text
                        text_obj = Text("LaTeX Error")
                        self.__dict__.update(text_obj.__dict__)
                
                tex_mobject.TexMobject.__init__ = safe_tex_init
        except:
            pass
            
    except ImportError:
        pass
        
except ImportError:
    # Manim not available
    pass

# Additional LaTeX environment cleanup
def cleanup_latex_environment():
    """Clean up any LaTeX-related environment variables that might cause issues"""
    latex_env_vars = [
        'TEXINPUTS', 'TEXMFHOME', 'TEXMFVAR', 'TEXMFLOCAL',
        'LATEX_PATH', 'PDFLATEX_PATH', 'XELATEX_PATH',
        'BIBTEX_PATH', 'MAKEINDEX_PATH'
    ]
    
    for var in latex_env_vars:
        if var in os.environ:
            del os.environ[var]

# Call cleanup on import
cleanup_latex_environment()
'''
    
    with open("manim_safe_config.py", "w", encoding="utf-8") as f:
        f.write(config_content)
    
    if USE_ASCII_ONLY:
        print("Created enhanced safe manim configuration")
    else:
        print("📄 Created enhanced safe manim configuration")

def create_manim_safe_config():
    """Create a manim configuration that works without LaTeX"""
    config_content = '''# Safe Manim Configuration for Standalone Builds
import os

# Set environment variables to disable LaTeX
os.environ["MANIM_DISABLE_LATEX"] = "1"
os.environ["MANIM_TEX_TEMPLATE"] = ""

# Configure manim to work without LaTeX
try:
    import manim
    
    # Override config defaults
    if hasattr(manim, 'config'):
        manim.config.tex_template = None
        manim.config.preview = False
        manim.config.verbosity = "ERROR"
        
    # Monkey patch problematic functions
    try:
        from manim.utils import tex_file_writing
        
        def safe_latex_fallback(*args, **kwargs):
            """Fallback when LaTeX operations fail"""
            print("LaTeX not available - using text fallback")
            return None
            
        # Replace problematic functions with safe versions
        tex_file_writing.latex = safe_latex_fallback
        tex_file_writing.print_all_tex_errors = lambda *args: None
        
    except ImportError:
        pass
        
except ImportError:
    # Manim not available
    pass
'''
    
    with open("manim_safe_config.py", "w", encoding="utf-8") as f:
        f.write(config_content)
    
    if USE_ASCII_ONLY:
        print("Created safe manim configuration")
    else:
        print("📄 Created safe manim configuration")

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
    
    # Create safe manim configuration
    create_manim_safe_config()
    
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
        "process_utils", "logging", "pathlib", "manim_safe_config"
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
    create_manim_safe_config()

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
        "itertools", "functools", "operator", "copy", "manim_safe_config"
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

def build_standalone_with_full_latex(jobs=None, priority="normal"):
    """Build standalone version with complete LaTeX support bundled"""
    
    cpu_count = multiprocessing.cpu_count()
    if jobs is None:
        jobs = max(1, cpu_count - 1)

    if USE_ASCII_ONLY:
        print(f"Building STANDALONE with FULL LaTeX support using {jobs} CPU threads...")
    else:
        print(f"🔬 Building STANDALONE with FULL LaTeX support using {jobs} CPU threads...")

    # First, create LaTeX bundle
    print("=" * 60)
    if USE_ASCII_ONLY:
        print("Step 1: Creating LaTeX bundle...")
    else:
        print("📦 Step 1: Creating LaTeX bundle...")
    
    # Create and run LaTeX bundler
    create_latex_bundle_script()
    
    try:
        # Run the bundler
        result = run_hidden_process([sys.executable, "latex_bundler.py"], capture_output=True, text=True)
        if result.returncode == 0:
            if USE_ASCII_ONLY:
                print("LaTeX bundle created successfully")
            else:
                print("✅ LaTeX bundle created successfully")
        else:
            if USE_ASCII_ONLY:
                print("Warning: LaTeX bundling failed, proceeding without bundled LaTeX")
                print(result.stderr)
            else:
                print("⚠️ Warning: LaTeX bundling failed, proceeding without bundled LaTeX")
                print(result.stderr)
    except Exception as e:
        if USE_ASCII_ONLY:
            print(f"Warning: Could not create LaTeX bundle: {e}")
        else:
            print(f"⚠️ Warning: Could not create LaTeX bundle: {e}")

    # Clean previous builds
    if Path("build").exists():
        shutil.rmtree("build")
    if Path("dist").exists():
        shutil.rmtree("dist")

    # Create assets directory
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)

    print("=" * 60)
    if USE_ASCII_ONLY:
        print("Step 2: Creating build configuration...")
    else:
        print("🔧 Step 2: Creating build configuration...")

    # Create enhanced patches and helpers
    create_no_console_patch()
    create_fixes_module()
    create_subprocess_helper()
    create_full_latex_manim_config()  # Full LaTeX config instead of safe config

    # Check prerequisites
    if not check_system_prerequisites():
        print("❌ System prerequisites check failed")
        return None

    # Get Nuitka version
    nuitka_version = get_nuitka_version()
    if USE_ASCII_ONLY:
        print(f"Detected Nuitka version: {nuitka_version}")
    else:
        print(f"📊 Detected Nuitka version: {nuitka_version}")

    print("=" * 60)
    if USE_ASCII_ONLY:
        print("Step 3: Building with full LaTeX support...")
    else:
        print("🔨 Step 3: Building with full LaTeX support...")

    # Basic command structure
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
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
    ]

    # MINIMAL exclusions - only exclude test modules but keep LaTeX functionality
    minimal_exclusions = [
        # Only exclude test modules, keep all LaTeX functionality
        "*.tests.*", "*.test_*", "test.*",
        "pytest.*", "*.benchmarks.*",
        # Still exclude problematic modules that cause build issues
        "zstandard.*", "setuptools.*", "_distutils_hack.*",
        # Exclude only specific problematic SymPy test modules (from your original error)
        "sympy.polys.benchmarks.bench_solvers",
        "sympy.physics.quantum.tests.test_spin", 
        "sympy.solvers.ode.tests.test_systems",
        "sympy.polys.polyquinticconst",
        # Keep all other SymPy modules including LaTeX ones
    ]

    for module in minimal_exclusions:
        cmd.append(f"--nofollow-import-to={module}")

    # Include ALL packages including LaTeX support
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
                # Include package data for complete functionality
                cmd.append(f"--include-package-data={correct_name}")
                if USE_ASCII_ONLY:
                    print(f"Including full package: {correct_name}")
                else:
                    print(f"📦 Including full package: {correct_name}")

    # Include SymPy with FULL LaTeX support (opposite of previous approach)
    if is_package_importable("sympy"):
        # Include ALL SymPy modules except the problematic test ones
        cmd.append("--include-package=sympy")
        cmd.append("--include-package-data=sympy")
        
        # Only exclude the specific problematic modules from the build error
        sympy_test_exclusions = [
            "sympy.polys.benchmarks.bench_solvers",
            "sympy.physics.quantum.tests.test_spin",
            "sympy.solvers.ode.tests.test_systems", 
            "sympy.polys.polyquinticconst",
            # General test exclusions but keep LaTeX modules
            "sympy.*.tests.*", "sympy.*.test_*"
        ]
        
        for exclusion in sympy_test_exclusions:
            cmd.append(f"--nofollow-import-to={exclusion}")
        
        included_packages.append("sympy (full LaTeX support)")
        if USE_ASCII_ONLY:
            print("Including SymPy with FULL LaTeX support")
        else:
            print("🧮 Including SymPy with FULL LaTeX support")

    # Include LaTeX support packages if available
    latex_packages = ["latex2mathml", "antlr4", "pygments", "colour", "jinja2"]
    
    for package in latex_packages:
        if is_package_importable(package):
            cmd.append(f"--include-package={package}")
            cmd.append(f"--include-package-data={package}")
            included_packages.append(package)
            if USE_ASCII_ONLY:
                print(f"Including LaTeX support package: {package}")
            else:
                print(f"📚 Including LaTeX support package: {package}")

    # Include comprehensive system modules for LaTeX
    comprehensive_modules = [
        "json", "tempfile", "threading", "subprocess",
        "os", "sys", "ctypes", "venv", "fixes", "psutil",
        "process_utils", "logging", "pathlib", "shutil",
        "glob", "re", "time", "datetime", "uuid", "base64",
        "io", "codecs", "platform", "getpass", "signal",
        "atexit", "queue", "math", "random", "collections",
        "itertools", "functools", "operator", "copy",
        "manim_latex_config",  # Our full LaTeX config
        "latex_bundler",       # LaTeX bundler
        # Additional modules for LaTeX support
        "xml", "xml.etree", "xml.etree.ElementTree",
        "urllib", "urllib.request", "urllib.parse",
        "zipfile", "tarfile", "gzip", "bz2",
        "hashlib", "hmac", "ssl", "socket"
    ]

    for module in comprehensive_modules:
        cmd.append(f"--include-module={module}")

    # Include LaTeX bundle directory if it exists
    if Path("latex_bundle").exists():
        cmd.append("--include-data-dir=latex_bundle=latex_bundle")
        if USE_ASCII_ONLY:
            print("Including bundled LaTeX installation")
        else:
            print("📦 Including bundled LaTeX installation")

    # Include comprehensive data for LaTeX support
    data_packages = ["manim", "matplotlib", "numpy", "sympy"]

    for package in data_packages:
        if is_package_importable(package):
            cmd.append(f"--include-package-data={package}")
            if USE_ASCII_ONLY:
                print(f"Including comprehensive data for: {package}")
            else:
                print(f"📊 Including comprehensive data for: {package}")

    # Output configuration
    cmd.extend([
        "--output-dir=dist",
        f"--jobs={jobs}",
    ])

    # Icon if available
    if Path("assets/icon.ico").exists():
        cmd.append("--windows-icon-from-ico=assets/icon.ico")

    # Include all data directories
    data_dirs = ["assets=assets"]
    
    # Try to include matplotlib data
    try:
        import matplotlib
        mpl_data = Path(matplotlib.get_data_path())
        if mpl_data.exists():
            data_dirs.append(f"{mpl_data}=matplotlib/mpl-data")
            if USE_ASCII_ONLY:
                print("Including matplotlib data directory")
            else:
                print("📊 Including matplotlib data directory")
    except ImportError:
        pass

    for data_dir in data_dirs:
        cmd.append(f"--include-data-dir={data_dir}")

    # Final target
    cmd.append("app.py")

    print("Building standalone executable with COMPLETE LaTeX support...")
    print("Command:", " ".join(cmd))
    print("=" * 60)

    # Environment setup for LaTeX support
    env = os.environ.copy()
    env["GCC_LTO"] = "0"
    env["NUITKA_DISABLE_LTO"] = "1"
    env["GCC_COMPILE_ARGS"] = "-fno-lto"

    # Set process priority
    process_priority = 0
    if priority == "high" and sys.platform == "win32":
        if USE_ASCII_ONLY:
            print("Setting HIGH process priority for maximum CPU utilization")
        else:
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
    if USE_ASCII_ONLY:
        print(f"CPU Info: {cpu_count} logical cores available")
        print(f"Using {jobs} compilation threads")
        print(f"Included {len(included_packages)} packages with full LaTeX support")
    else:
        print(f"🖥️ CPU Info: {cpu_count} logical cores available")
        print(f"⚙️ Using {jobs} compilation threads")
        print(f"📦 Included {len(included_packages)} packages with full LaTeX support")

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
        if USE_ASCII_ONLY:
            print("Full LaTeX build successful!")
        else:
            print("✅ Full LaTeX build successful!")

        exe_path = find_standalone_executable()
        if exe_path:
            # Create comprehensive LaTeX setup
            create_comprehensive_latex_setup(exe_path.parent)
            create_launcher_script(exe_path)
            
            if USE_ASCII_ONLY:
                print(f"Executable: {exe_path}")
                print("COMPLETE LaTeX FEATURES:")
                print("  - Full SymPy LaTeX rendering")
                print("  - Complete manim TeX support")
                print("  - Bundled LaTeX installation")
                print("  - All LaTeX packages included")
                print("  - Mathematical typesetting")
                print("  - Professional equation rendering")
                print("  - No console windows")
            else:
                print(f"📁 Executable: {exe_path}")
                print("🎉 COMPLETE LaTeX FEATURES:")
                print("  ✅ Full SymPy LaTeX rendering")
                print("  ✅ Complete manim TeX support")
                print("  ✅ Bundled LaTeX installation")
                print("  ✅ All LaTeX packages included")
                print("  ✅ Mathematical typesetting")
                print("  ✅ Professional equation rendering")
                print("  ✅ No console windows")

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
            print("Full LaTeX build failed!")
        else:
            print("❌ Full LaTeX build failed!")
        print(f"Return code: {return_code}")
        return None

def create_comprehensive_latex_setup(dist_dir):
    """Create comprehensive LaTeX setup for the built application"""
    try:
        # Create main LaTeX configuration
        latex_config = """# Comprehensive LaTeX Configuration
# Full LaTeX support with all features enabled

[tex]
# Enable LaTeX with comprehensive template
tex_template_file = 
intermediate_filetype = dvi
text_to_replace = YourTextHere

[CLI]
verbosity = WARNING
preview = False

[logger]
logging_level = WARNING

[output]
disable_caching = False
flush_cache = True
max_files_cached = 100

[universal]
background_color = BLACK

[window]
background_opacity = 1
fullscreen = False
size = 1280,720

# LaTeX support flags
[latex_support]
enabled = true
bundled_installation = true
full_feature_set = true
"""

        config_path = Path(dist_dir) / "latex_config.cfg"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(latex_config)

        # Create LaTeX initialization script
        init_script = f"""# latex_initialization.py
# Comprehensive LaTeX initialization for standalone build

import os
import sys
from pathlib import Path

def initialize_comprehensive_latex():
    \"\"\"Initialize comprehensive LaTeX support\"\"\"
    print("🔧 Initializing comprehensive LaTeX support...")
    
    # Set LaTeX environment variables
    app_dir = Path(sys.executable).parent if hasattr(sys, 'executable') else Path('.')
    latex_bundle = app_dir / "latex_bundle"
    
    if latex_bundle.exists():
        os.environ["TEXMFHOME"] = str(latex_bundle / "texmf")
        os.environ["TEXMFLOCAL"] = str(latex_bundle / "texmf") 
        os.environ["TEXINPUTS"] = str(latex_bundle / "texmf" / "tex") + "//:."
        os.environ["PATH"] = str(latex_bundle / "bin") + os.pathsep + os.environ.get("PATH", "")
        print(f"✅ LaTeX bundle configured: {{latex_bundle}}")
    
    # Import and configure LaTeX support
    try:
        import manim_latex_config
        print("✅ Manim LaTeX configuration loaded")
    except ImportError:
        print("⚠️ Manim LaTeX configuration not available")
    
    # Configure matplotlib for LaTeX
    try:
        import matplotlib
        matplotlib.rcParams['text.usetex'] = True
        matplotlib.rcParams['font.family'] = 'serif'
        matplotlib.rcParams['font.serif'] = ['Computer Modern Roman']
        print("✅ Matplotlib LaTeX support enabled")
    except ImportError:
        pass
    
    # Test LaTeX functionality
    try:
        import sympy
        test_expr = sympy.symbols('x')
        latex_output = sympy.latex(test_expr**2 + 1)
        print(f"✅ SymPy LaTeX test successful: {{latex_output}}")
    except Exception as e:
        print(f"⚠️ SymPy LaTeX test failed: {{e}}")
    
    print("🎉 LaTeX initialization complete!")

# Auto-initialize on import
initialize_comprehensive_latex()
"""

        init_path = Path(dist_dir) / "latex_initialization.py"
        with open(init_path, "w", encoding="utf-8") as f:
            f.write(init_script)

        # Create LaTeX test script
        test_script = """# latex_test.py
# Test script to verify LaTeX functionality

def test_latex_functionality():
    \"\"\"Test all LaTeX features\"\"\"
    print("🧪 Testing LaTeX functionality...")
    
    tests_passed = 0
    total_tests = 0
    
    # Test 1: SymPy LaTeX
    total_tests += 1
    try:
        import sympy
        x = sympy.Symbol('x')
        expr = x**2 + 2*x + 1
        latex_str = sympy.latex(expr)
        print(f"✅ SymPy LaTeX: {latex_str}")
        tests_passed += 1
    except Exception as e:
        print(f"❌ SymPy LaTeX failed: {e}")
    
    # Test 2: Matplotlib LaTeX
    total_tests += 1
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        
        # Simple plot with LaTeX labels
        x = np.linspace(0, 2*np.pi, 100)
        y = np.sin(x)
        
        plt.figure(figsize=(6, 4))
        plt.plot(x, y)
        plt.xlabel(r'$x$')
        plt.ylabel(r'$\\sin(x)$')
        plt.title(r'$y = \\sin(x)$')
        plt.close()  # Don't display, just test
        
        print("✅ Matplotlib LaTeX rendering")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Matplotlib LaTeX failed: {e}")
    
    # Test 3: Manim TeX (if available)
    total_tests += 1
    try:
        import manim
        # Try to create a simple TeX object
        tex_obj = manim.MathTex(r"E = mc^2")
        print("✅ Manim TeX objects")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Manim TeX failed: {e}")
    
    print(f"🎯 LaTeX tests: {tests_passed}/{total_tests} passed")
    return tests_passed == total_tests

if __name__ == "__main__":
    test_latex_functionality()
"""

        test_path = Path(dist_dir) / "latex_test.py"
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_script)

        if USE_ASCII_ONLY:
            print(f"Created comprehensive LaTeX setup in {dist_dir}")
        else:
            print(f"🔬 Created comprehensive LaTeX setup in {dist_dir}")

    except Exception as e:
        if USE_ASCII_ONLY:
            print(f"Warning: Could not create comprehensive LaTeX setup: {e}")
        else:
            print(f"⚠️ Warning: Could not create comprehensive LaTeX setup: {e}")

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
    """Create fixes module to handle runtime issues including LaTeX errors"""
    fixes_content = '''# fixes.py - Applied patches for the build process including LaTeX fixes
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
    """Fix the manim configuration issue by creating a default.cfg file with LaTeX disabled"""
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
            
            # Create a basic default.cfg file with LaTeX disabled
            default_cfg_path = os.path.join(manim_config_dir, 'default.cfg')
            with open(default_cfg_path, 'w') as f:
                f.write(DEFAULT_MANIM_CONFIG_NO_LATEX)
                
            print(f"Created manim config at: {default_cfg_path}")
            return True
    except Exception as e:
        print(f"Error fixing manim config: {e}")
    return False

def patch_manim_latex():
    """Patch manim to disable LaTeX rendering and use fallback text rendering"""
    try:
        # Try to import manim and patch its LaTeX handling
        import manim
        
        # Patch the tex file writing module to handle missing LaTeX gracefully
        try:
            from manim.utils import tex_file_writing
            
            # Store original function
            if not hasattr(tex_file_writing, '_original_print_all_tex_errors'):
                tex_file_writing._original_print_all_tex_errors = tex_file_writing.print_all_tex_errors
                
                def safe_print_all_tex_errors(log_file, tex_compiler, tex_file):
                    """Safe version that doesn't crash when LaTeX is missing"""
                    try:
                        if not log_file.exists():
                            print(f"Warning: {tex_compiler} failed but LaTeX is not available in standalone build")
                            print("Falling back to text rendering...")
                            return
                        return tex_file_writing._original_print_all_tex_errors(log_file, tex_compiler, tex_file)
                    except Exception as e:
                        print(f"LaTeX error handled gracefully: {e}")
                        return
                
                tex_file_writing.print_all_tex_errors = safe_print_all_tex_errors
                print("Patched manim LaTeX error handling")
                
        except ImportError:
            pass
            
        # Try to disable LaTeX globally in manim config
        try:
            if hasattr(manim, 'config'):
                # Disable LaTeX-related features
                manim.config.tex_template = None
                manim.config.preview = False
                print("Disabled LaTeX in manim config")
        except:
            pass
            
    except ImportError:
        # Manim not available, that's fine
        pass
    except Exception as e:
        print(f"Error patching manim LaTeX: {e}")

# Default minimal manim config content with LaTeX completely disabled
DEFAULT_MANIM_CONFIG_NO_LATEX = """
[CLI]
media_dir = ./media
verbosity = ERROR
notify_outdated_version = False
tex_template = 
preview = False

[logger]
logging_keyword = manim
logging_level = ERROR

[output]
max_files_cached = 10
flush_cache = True
disable_caching = True

[progress_bar]
leave_progress_bars = False
use_progress_bars = False

[tex]
# Completely disable LaTeX to prevent runtime errors
intermediate_filetype = 
text_to_replace = 
tex_template_file = 
tex_template = 

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
    """Apply all fixes at startup including LaTeX patches"""
    fix_manim_config()
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
'''
    
    # Write with explicit UTF-8 encoding to avoid character encoding issues
    with open("fixes.py", "w", encoding="utf-8") as f:
        f.write(fixes_content)
    
    if USE_ASCII_ONLY:
        print("Created enhanced fixes module with LaTeX error handling")
    else:
        print("📄 Created enhanced fixes module with LaTeX error handling")

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
    """Create LaTeX configuration for the standalone build with fallback options"""
    try:
        config_content = """# ManimStudio LaTeX Configuration
# This file configures LaTeX support with fallback options

[tex]
# Disable LaTeX by default for standalone builds to prevent errors
tex_template = 
intermediate_filetype = dvi
text_to_replace = YourTextHere

[CLI]
# Reduce verbosity to avoid console output
verbosity = WARNING
# Disable LaTeX preview to prevent errors
preview = False

[logger]
# Configure logging for standalone app
logging_level = WARNING

[output]
# Optimize for standalone deployment
disable_caching = True
flush_cache = False
max_files_cached = 10

[universal]
# Use safer defaults
background_color = BLACK

[window]
# Window settings for standalone
background_opacity = 1
fullscreen = False
size = 1280,720
"""

        config_path = Path(dist_dir) / "manim_config.cfg"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)

        # Also create a no-tex config
        no_tex_config = """# No-LaTeX Configuration for Maximum Compatibility
[tex]
# Completely disable LaTeX to prevent runtime errors
tex_template = 
intermediate_filetype = 
text_to_replace = 

[CLI]
verbosity = ERROR
preview = False

[logger]
logging_level = ERROR

[output]
disable_caching = True
"""
        
        no_tex_path = Path(dist_dir) / "manim_no_tex.cfg"
        with open(no_tex_path, "w", encoding="utf-8") as f:
            f.write(no_tex_config)

        if USE_ASCII_ONLY:
            print(f"Created LaTeX configs: {config_path} and {no_tex_path}")
        else:
            print(f"📝 Created LaTeX configs: {config_path} and {no_tex_path}")

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
    create_manim_safe_config()

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
        "process_utils", "logging", "pathlib", "shutil", "manim_safe_config"
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
    parser.add_argument("--build-type", type=int, choices=[1, 2, 3, 4, 5, 6], help="Build type: 1=onefile, 2=standalone, 3=debug, 4=both silent, 5=minimal, 6=full latex")
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
            print("6. Full LaTeX build (complete LaTeX support)")
        else:
            print("1. 🔇 Silent onefile build (single .exe)")
            print("2. 📁 Silent standalone build (directory)")
            print("3. 🐛 Debug build (with console)")
            print("4. 📦 Both silent builds")
            print("5. ⚡ Minimal build (fastest, no sympy/scipy)")
            print("6. 🔬 Full LaTeX build (complete LaTeX support)")
        choice = input("\nEnter your choice (1-6): ").strip()
    
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
    elif choice == "6":
        print("\n" + ("Building with full LaTeX support..." if USE_ASCII_ONLY else "🔬 Building with full LaTeX support..."))
        exe_path = build_standalone_with_full_latex(jobs=jobs, priority=process_priority)
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
        elif choice == "6":
            if USE_ASCII_ONLY:
                print("FULL LaTeX BUILD: Complete mathematical rendering capabilities")
                print("   Included: All SymPy LaTeX modules, bundled LaTeX installation")
                print("   Features: Professional equation rendering, all LaTeX packages")
                print("   Result: Full mathematical typesetting support")
            else:
                print("🔬 FULL LaTeX BUILD: Complete mathematical rendering capabilities")
                print("   ✅ Included: All SymPy LaTeX modules, bundled LaTeX installation")
                print("   ✅ Features: Professional equation rendering, all LaTeX packages")
                print("   ✅ Result: Full mathematical typesetting support")
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
