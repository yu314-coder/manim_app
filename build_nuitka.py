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
def detect_and_use_existing_miktex(latex_bundle_dir):
    """Detect existing MiKTeX installations specifically"""
    import subprocess
    import os
    
    print("🔍 Scanning specifically for MiKTeX installations...")
    
    # MiKTeX-specific paths
    miktex_paths = [
        # Standard MiKTeX installation paths
        r"C:\Program Files\MiKTeX",
        r"C:\Program Files (x86)\MiKTeX",
        r"C:\Users\Public\MiKTeX",
        r"C:\MiKTeX",
        os.path.expanduser(r"~\AppData\Local\Programs\MiKTeX"),
        os.path.expanduser(r"~\AppData\Roaming\MiKTeX"),
        # Custom MiKTeX paths - ADD YOUR CUSTOM MIKTEX PATH HERE
        r"D:\LaTeX\MiKTeX",
        r"C:\Tools\MiKTeX",
        r"E:\MiKTeX",
        # Portable MiKTeX installations
        "./miktex_portable",
        "./MiKTeX",
        "../MiKTeX",
    ]
    
    # Try to find miktex.exe or latex.exe specifically in MiKTeX structure
    try:
        result = subprocess.run(["where", "miktex"], capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            miktex_exe_path = result.stdout.strip().split('\n')[0]
            miktex_root = Path(miktex_exe_path).parent.parent
            print(f"✅ Found MiKTeX in PATH: {miktex_exe_path}")
            return create_symlink_installation(miktex_root, latex_bundle_dir)
    except:
        pass
    
    # Check MiKTeX-specific paths
    for path_str in miktex_paths:
        path = Path(path_str)
        if path.exists():
            # Look for MiKTeX-specific structure
            miktex_indicators = [
                "miktex/bin/latex.exe",
                "texmfs/install/miktex/bin/latex.exe",
                "texmfs/install/miktex/bin/x64/latex.exe",
                "bin/latex.exe",
                "bin/x64/latex.exe"
            ]
            
            for indicator in miktex_indicators:
                miktex_exe = path / indicator
                if miktex_exe.exists():
                    print(f"✅ Found MiKTeX installation: {path}")
                    return create_symlink_installation(path, latex_bundle_dir)
            
            # Also check for miktex.exe specifically
            miktex_dirs = list(path.rglob("miktex.exe"))
            if miktex_dirs:
                miktex_root = miktex_dirs[0].parent.parent
                print(f"✅ Found MiKTeX installation via miktex.exe: {miktex_root}")
                return create_symlink_installation(miktex_root, latex_bundle_dir)
    
    print("❌ No existing MiKTeX installation found")
    return False
def show_manual_miktex_installation_instructions():
    """Show detailed manual MiKTeX installation instructions"""
    print("\n" + "="*80)
    print("🔧 MANUAL MIKTEX INSTALLATION INSTRUCTIONS")
    print("="*80)
    print("\n📋 RECOMMENDED: MiKTeX (Best LaTeX distribution)")
    print("   1. Go to: https://miktex.org/download")
    print("   2. Download: 'MiKTeX Installer' for Windows")
    print("   3. Run the installer with these EXACT settings:")
    print("      ✅ Install for: 'Anyone who uses this computer'")
    print("      ✅ Preferred paper: A4 or Letter")
    print("      ✅ Install missing packages: 'Yes' (IMPORTANT!)")
    print("      ✅ Check 'Always install missing packages on-the-fly'")
    print("   4. Wait for installation to complete (~10-15 minutes)")
    print("   5. After installation, verify by opening Command Prompt:")
    print("      > latex --version")
    print("      > miktex --version")
    print("   6. Re-run this build script - it will auto-detect MiKTeX!")
    
    print("\n📋 ALTERNATIVE: MiKTeX Portable (Manual)")
    print("   1. Download MiKTeX Portable from:")
    print("      https://miktex.org/portable")
    print("   2. Extract to: 'miktex_portable' folder next to this script")
    print("   3. Re-run this build script")
    
    print("\n🔧 CUSTOM MIKTEX PATH:")
    print("   If you have MiKTeX installed in a custom location:")
    print("   1. Edit this script (build_nuitka.py)")
    print("   2. Find the 'miktex_paths' list in detect_and_use_existing_miktex()")
    print("   3. Add your custom path to the list")
    print("   4. Example: r'D:\\MyPrograms\\MiKTeX'")
    
    print("\n⚡ VERIFICATION:")
    print("   After installation, run these commands:")
    print("   > miktex --version")
    print("   > latex --version")
    print("   > pdflatex --version")
    print("   All should work without errors.")
    
    print("\n🎯 GUARANTEE:")
    print("   This script is optimized for MiKTeX and will work best with it!")
    print("="*80)
def download_advanced_latex_distribution():
    """Download MiKTeX first, with fallbacks only if MiKTeX fails"""
    import urllib.request
    import zipfile
    import tempfile
    import tarfile
    
    print("🚀 Prioritizing MiKTeX LaTeX Distribution...")
    
    # Create latex_bundle directory
    latex_bundle_dir = Path("latex_bundle")
    if latex_bundle_dir.exists():
        shutil.rmtree(latex_bundle_dir)
    latex_bundle_dir.mkdir(exist_ok=True)
    
    # FIRST: Try to detect existing MiKTeX installations specifically
    print("🔍 Checking for existing MiKTeX installations...")
    if detect_and_use_existing_miktex(latex_bundle_dir):
        print("✅ Found and configured existing MiKTeX installation!")
        return True
    
    # SECOND: Download MiKTeX Portable (Primary choice)
    print("📦 Primary Option: Downloading MiKTeX Portable...")
    if download_miktex_portable(latex_bundle_dir):
        print("✅ MiKTeX Portable downloaded successfully!")
        return True
    
    # If MiKTeX fails, ask user if they want to try alternatives
    print("❌ MiKTeX download failed!")
    print("🤔 MiKTeX is the preferred LaTeX distribution but failed to download.")
    
    try_alternatives = input("Would you like to try alternative LaTeX distributions? (y/N): ").strip().lower()
    if try_alternatives not in ['y', 'yes']:
        print("❌ Build cancelled - MiKTeX required but not available")
        print("💡 You can manually install MiKTeX and re-run this script")
        show_manual_miktex_installation_instructions()
        sys.exit(1)
    
    # Fallback options (only if user agrees)
    print("📦 Fallback Option 1: Attempting TeX Live Basic...")
    if download_texlive_basic(latex_bundle_dir):
        print("✅ TeX Live Basic downloaded successfully!")
        return True
    
    print("📦 Fallback Option 2: Attempting W32TeX...")
    if download_w32tex(latex_bundle_dir):
        print("✅ W32TeX downloaded successfully!")
        return True
    
    print("📦 Fallback Option 3: Attempting ProTeXt Basic...")
    if download_protext_basic(latex_bundle_dir):
        print("✅ ProTeXt Basic downloaded successfully!")
        return True
    
    # All options failed
    print("❌ CRITICAL ERROR: All LaTeX distribution downloads failed")
    print("🚫 BUILD CANNOT CONTINUE WITHOUT LATEX")
    show_manual_miktex_installation_instructions()
    sys.exit(1)
def detect_and_use_existing_latex(latex_bundle_dir):
    """Detect existing LaTeX installations on the system"""
    import subprocess
    import os
    
    print("🔍 Scanning for existing LaTeX installations...")
    
    # Common LaTeX installation paths
    common_paths = [
        # MiKTeX paths
        r"C:\Program Files\MiKTeX",
        r"C:\Users\Public\MiKTeX",
        r"C:\MiKTeX",
        os.path.expanduser(r"~\AppData\Local\Programs\MiKTeX"),
        # TeX Live paths
        r"C:\texlive",
        r"C:\Program Files\texlive",
        # Custom paths - ADD YOUR LATEX PATH HERE IF NEEDED
        r"D:\LaTeX\MiKTeX",  # Example custom path
        r"C:\Tools\MiKTeX",  # Example custom path
        # ADD MORE PATHS HERE AS NEEDED
        # Portable installations
        "./miktex_portable",
        "./texlive_portable",
        "./latex_portable"
    ]
    
    # Try to find latex.exe in PATH
    try:
        result = subprocess.run(["where", "latex"], capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            latex_exe_path = result.stdout.strip().split('\n')[0]
            latex_root = Path(latex_exe_path).parent.parent
            print(f"✅ Found LaTeX in PATH: {latex_exe_path}")
            return create_symlink_installation(latex_root, latex_bundle_dir)
    except:
        pass
    
    # Check common installation paths
    for path_str in common_paths:
        path = Path(path_str)
        if path.exists():
            # Look for bin directory with latex.exe
            bin_dirs = list(path.rglob("bin"))
            for bin_dir in bin_dirs:
                latex_exe = bin_dir / "latex.exe"
                if latex_exe.exists():
                    print(f"✅ Found LaTeX installation: {path}")
                    return create_symlink_installation(path, latex_bundle_dir)
    
    print("❌ No existing LaTeX installation found")
    return False

def create_symlink_installation(source_path, target_dir):
    """Create a symlink-based installation for existing LaTeX"""
    try:
        # Create a symbolic link to the existing installation
        target_path = target_dir / "existing_latex"
        
        # On Windows, try to create a junction/symlink
        if sys.platform == "win32":
            try:
                # Try creating a junction first (doesn't require admin rights)
                subprocess.run(["mklink", "/J", str(target_path), str(source_path)],
                             shell=True, check=True, capture_output=True)
                print(f"✅ Created junction link: {target_path} -> {source_path}")
            except Exception:
                # If junction fails, fall back to copying the entire tree
                print("⚠️  Junction creation failed, copying LaTeX installation. This may take some time...")
                shutil.copytree(source_path, target_path, dirs_exist_ok=True)
                print(f"✅ Copied LaTeX installation to: {target_path}")
        else:
            # On Unix systems, create a symbolic link
            os.symlink(source_path, target_path)
            print(f"✅ Created symbolic link: {target_path} -> {source_path}")

        # Create environment setup for existing installation
        create_existing_latex_environment_setup(target_path)
        
        return verify_latex_installation(target_dir)
        
    except Exception as e:
        print(f"❌ Failed to create symlink installation: {e}")
        return False

def show_manual_installation_instructions():
    """Show detailed manual installation instructions"""
    print("\n" + "="*80)
    print("🔧 MANUAL LATEX INSTALLATION INSTRUCTIONS")
    print("="*80)
    print("\n📋 OPTION 1: MiKTeX (Recommended - Easiest)")
    print("   1. Go to: https://miktex.org/download")
    print("   2. Download: 'MiKTeX Installer' for Windows")
    print("   3. Run the installer with these settings:")
    print("      ✅ Install for: 'Anyone who uses this computer'")
    print("      ✅ Preferred paper: A4 or Letter")
    print("      ✅ Install missing packages: 'Yes'")
    print("   4. Wait for installation to complete (~10-15 minutes)")
    print("   5. Re-run this build script - it will auto-detect MiKTeX!")
    
    print("\n📋 OPTION 2: TeX Live (More comprehensive)")
    print("   1. Go to: https://www.tug.org/texlive/windows.html")
    print("   2. Download: 'install-tl-windows.exe'")
    print("   3. Run installer and select 'Basic' scheme")
    print("   4. Wait for installation (~45-60 minutes)")
    print("   5. Re-run this build script - it will auto-detect TeX Live!")
    
    print("\n📋 OPTION 3: Portable MiKTeX (Manual)")
    print("   1. Download MiKTeX Portable from:")
    print("      https://miktex.org/portable")
    print("   2. Extract to: 'miktex_portable' folder next to this script")
    print("   3. Re-run this build script")
    
    print("\n🔧 VERIFICATION:")
    print("   After installation, open Command Prompt and run:")
    print("   > latex --version")
    print("   You should see LaTeX version information.")
    
    print("\n⚡ QUICK TEST:")
    print("   Run this build script again after installing LaTeX")
    print("   It will automatically detect and use your installation!")
    print("="*80)

def download_miktex_portable(latex_bundle_dir):
    """Download MiKTeX Portable (~800MB) - Most reliable option"""
    import urllib.request
    import tempfile
    import os
    try:
        print("📥 Downloading MiKTeX Portable (Advanced LaTeX, ~800MB)...")
        
        # MiKTeX Portable download URLs (updated for latest versions)
        miktex_urls = [
            "https://miktex.org/download/ctan/systems/win32/miktex/setup/windows-x64/miktexsetup-5.5.0+1763023f-x64.exe",
            "https://mirrors.ctan.org/systems/win32/miktex/setup/windows-x64/miktexsetup-5.5.0+1763023f-x64.exe",
            "https://mirror.ctan.org/systems/win32/miktex/setup/windows-x64/miktexsetup-5.5.0+1763023f-x64.exe"
        ]
        
        for url in miktex_urls:
            try:
                print(f"📥 Trying: {url}")
                
                with tempfile.NamedTemporaryFile(suffix='.exe', delete=False) as temp_file:
                    # Download with progress
                    urllib.request.urlretrieve(url, temp_file.name, reporthook=download_progress)
                    setup_exe = temp_file.name
                
                print("✅ MiKTeX setup downloaded")
                
                # Create a portable installation
                portable_dir = latex_bundle_dir / "miktex_portable"
                portable_dir.mkdir(exist_ok=True)
                
                print("🔧 Creating MiKTeX portable installation...")
                
                # Run MiKTeX setup in portable mode
                setup_cmd = [
                    setup_exe,
                    "--portable", str(portable_dir),
                    "--package-set=basic",
                    "--auto-install=yes",
                    "--quiet"
                ]
                
                result = run_hidden_process(setup_cmd, timeout=1800)  # 30 minutes timeout
                
                # Clean up setup file
                os.unlink(setup_exe)
                
                if result.returncode == 0 and verify_latex_installation(portable_dir):
                    print("✅ MiKTeX Portable installation successful")
                    create_miktex_environment_setup(portable_dir)
                    return True
                else:
                    print(f"❌ MiKTeX setup failed with return code: {result.returncode}")
                    
            except Exception as e:
                print(f"⚠️ Failed to download from {url}: {e}")
                continue
        
        return False
        
    except Exception as e:
        print(f"❌ MiKTeX Portable download failed: {e}")
        return False

def download_texlive_basic(latex_bundle_dir):
    """Download TeX Live Basic (~1.5GB) - Comprehensive option"""
    import urllib.request
    import zipfile
    import tempfile
    import os
    try:
        print("📥 Downloading TeX Live Basic (Comprehensive LaTeX, ~1.5GB)...")
        
        # TeX Live Basic URLs
        texlive_urls = [
            "https://mirror.ctan.org/systems/texlive/tlnet/install-tl.zip",
            "https://mirrors.ctan.org/systems/texlive/tlnet/install-tl.zip",
            "https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2024/install-tl.zip"
        ]
        
        for url in texlive_urls:
            try:
                print(f"📥 Trying: {url}")
                
                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                    urllib.request.urlretrieve(url, temp_file.name, reporthook=download_progress)
                    install_zip = temp_file.name
                
                print("✅ TeX Live installer downloaded")
                
                # Extract installer
                install_dir = latex_bundle_dir / "texlive_installer"
                install_dir.mkdir(exist_ok=True)
                
                with zipfile.ZipFile(install_zip, 'r') as zip_ref:
                    zip_ref.extractall(install_dir)
                
                # Clean up zip file
                os.unlink(install_zip)
                
                # Find install-tl script
                install_script = None
                for item in install_dir.rglob("install-tl*"):
                    if item.is_file() and (item.suffix == '.bat' or item.suffix == ''):
                        install_script = item
                        break
                
                if not install_script:
                    print("❌ Could not find TeX Live install script")
                    continue
                
                # Create portable installation
                portable_dir = latex_bundle_dir / "texlive_basic"
                portable_dir.mkdir(exist_ok=True)
                
                print("🔧 Creating TeX Live Basic installation...")
                
                # Create install profile for basic installation
                profile_content = f"""
selected_scheme scheme-basic
TEXDIR {portable_dir}
TEXMFCONFIG {portable_dir}/texmf-config
TEXMFVAR {portable_dir}/texmf-var
TEXMFHOME {portable_dir}/texmf-home
TEXMFLOCAL {portable_dir}/texmf-local
TEXMFSYSCONFIG {portable_dir}/texmf-config
TEXMFSYSVAR {portable_dir}/texmf-var
option_adjustrepo 1
option_autobackup 0
option_backupdir tlpkg/backups
option_desktop_integration 0
option_doc 0
option_file_assocs 0
option_fmt 1
option_letter 0
option_menu_integration 0
option_path 0
option_post_code 1
option_src 0
option_sys_bin /usr/local/bin
option_sys_info /usr/local/share/info
option_sys_man /usr/local/share/man
option_w32_multi_user 0
option_write18_restricted 1
portable 1
"""
                
                profile_path = install_dir / "basic.profile"
                with open(profile_path, 'w') as f:
                    f.write(profile_content)
                
                # Run installation
                install_cmd = [str(install_script), "-profile", str(profile_path), "-no-gui"]
                
                result = run_hidden_process(install_cmd, timeout=3600)  # 60 minutes timeout
                
                if result.returncode == 0 and verify_latex_installation(portable_dir):
                    print("✅ TeX Live Basic installation successful")
                    create_texlive_environment_setup(portable_dir)
                    return True
                else:
                    print(f"❌ TeX Live installation failed with return code: {result.returncode}")
                    
            except Exception as e:
                print(f"⚠️ Failed to download from {url}: {e}")
                continue
        
        return False
        
    except Exception as e:
        print(f"❌ TeX Live Basic download failed: {e}")
        return False

def download_w32tex(latex_bundle_dir):
    """Download W32TeX (~600MB) - Lightweight but comprehensive"""
    import urllib.request
    import tempfile
    import tarfile
    import lzma
    import os
    try:
        print("📥 Downloading W32TeX (Lightweight LaTeX, ~600MB)...")
        
        # W32TeX download URLs
        w32tex_packages = [
            "https://www.ring.gr.jp/pub/text/TeX/ptex-win32/current/w32tex.tar.xz",
            "https://mirrors.ctan.org/systems/win32/w32tex/current/w32tex.tar.xz",
            "http://w32tex.org/current/w32tex.tar.xz"
        ]
        
        for url in w32tex_packages:
            try:
                print(f"📥 Trying: {url}")
                
                with tempfile.NamedTemporaryFile(suffix='.tar.xz', delete=False) as temp_file:
                    urllib.request.urlretrieve(url, temp_file.name, reporthook=download_progress)
                    package_file = temp_file.name
                
                print("✅ W32TeX package downloaded")
                
                # Extract W32TeX
                w32tex_dir = latex_bundle_dir / "w32tex"
                w32tex_dir.mkdir(exist_ok=True)
                
                # Extract tar.xz file
                with lzma.open(package_file, 'rb') as xz_file:
                    with tarfile.open(fileobj=xz_file, mode='r|') as tar:
                        tar.extractall(w32tex_dir)
                
                # Clean up package file
                os.unlink(package_file)
                
                if verify_latex_installation(w32tex_dir):
                    print("✅ W32TeX installation successful")
                    create_w32tex_environment_setup(w32tex_dir)
                    return True
                else:
                    print("❌ W32TeX verification failed")
                    
            except Exception as e:
                print(f"⚠️ Failed to download from {url}: {e}")
                continue
        
        return False
        
    except Exception as e:
        print(f"❌ W32TeX download failed: {e}")
        return False

def download_protext_basic(latex_bundle_dir):
    """Download ProTeXt Basic (~900MB) - Alternative comprehensive option"""
    import urllib.request
    import tempfile
    import os
    try:
        print("📥 Downloading ProTeXt Basic (Alternative LaTeX, ~900MB)...")
        
        # ProTeXt download URLs
        protext_urls = [
            "https://mirror.ctan.org/systems/windows/protext/protext.exe",
            "https://mirrors.ctan.org/systems/windows/protext/protext.exe"
        ]
        
        for url in protext_urls:
            try:
                print(f"📥 Trying: {url}")
                
                with tempfile.NamedTemporaryFile(suffix='.exe', delete=False) as temp_file:
                    urllib.request.urlretrieve(url, temp_file.name, reporthook=download_progress)
                    installer_exe = temp_file.name
                
                print("✅ ProTeXt installer downloaded")
                
                # Create portable installation directory
                protext_dir = latex_bundle_dir / "protext_basic"
                protext_dir.mkdir(exist_ok=True)
                
                print("🔧 Creating ProTeXt Basic installation...")
                
                # Extract ProTeXt (it's usually a self-extracting archive)
                extract_cmd = [installer_exe, "/S", f"/D={protext_dir}"]
                
                result = run_hidden_process(extract_cmd, timeout=1800)  # 30 minutes timeout
                
                # Clean up installer
                os.unlink(installer_exe)
                
                if result.returncode == 0 and verify_latex_installation(protext_dir):
                    print("✅ ProTeXt Basic installation successful")
                    create_protext_environment_setup(protext_dir)
                    return True
                else:
                    print(f"❌ ProTeXt installation failed with return code: {result.returncode}")
                    
            except Exception as e:
                print(f"⚠️ Failed to download from {url}: {e}")
                continue
        
        return False
        
    except Exception as e:
        print(f"❌ ProTeXt Basic download failed: {e}")
        return False

def download_progress(block_num, block_size, total_size):
    """Show download progress"""
    if total_size > 0:
        percent = min(100, (block_num * block_size * 100) // total_size)
        mb_downloaded = (block_num * block_size) // (1024 * 1024)
        mb_total = total_size // (1024 * 1024)
        print(f"\r📥 Progress: {percent}% ({mb_downloaded}/{mb_total} MB)", end='', flush=True)
        if percent >= 100:
            print()  # New line when complete

def create_miktex_environment_setup(miktex_dir):
    """Create environment setup for MiKTeX"""
    setup_script = f'''# MiKTeX Environment Setup
import os
import sys
from pathlib import Path

def setup_miktex_environment():
    """Set up MiKTeX environment"""
    miktex_dir = Path("{miktex_dir}")
    
    if miktex_dir.exists():
        # Add MiKTeX bin to PATH
        bin_dir = miktex_dir / "texmfs" / "install" / "miktex" / "bin" / "x64"
        if not bin_dir.exists():
            bin_dir = miktex_dir / "bin"
        
        if bin_dir.exists():
            current_path = os.environ.get("PATH", "")
            if str(bin_dir) not in current_path:
                os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
        
        # Set MIKTEX environment variables
        os.environ["MIKTEX_ROOT"] = str(miktex_dir)
        os.environ["TEXMFHOME"] = str(miktex_dir / "texmf")
        
        print("✅ MiKTeX environment configured")
        return True
    
    return False

# Auto-setup on import
setup_miktex_environment()
'''
    
    with open("miktex_env_setup.py", "w", encoding="utf-8") as f:
        f.write(setup_script)

def create_texlive_environment_setup(texlive_dir):
    """Create environment setup for TeX Live"""
    setup_script = f'''# TeX Live Environment Setup
import os
import sys
from pathlib import Path

def setup_texlive_environment():
    """Set up TeX Live environment"""
    texlive_dir = Path("{texlive_dir}")
    
    if texlive_dir.exists():
        # Add TeX Live bin to PATH
        bin_dir = texlive_dir / "bin" / "win32"
        if not bin_dir.exists():
            bin_dir = texlive_dir / "bin" / "windows"
        if not bin_dir.exists():
            bin_dir = texlive_dir / "bin"
        
        if bin_dir.exists():
            current_path = os.environ.get("PATH", "")
            if str(bin_dir) not in current_path:
                os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
        
        # Set TeX Live environment variables
        os.environ["TEXLIVE_ROOT"] = str(texlive_dir)
        os.environ["TEXMFHOME"] = str(texlive_dir / "texmf-home")
        os.environ["TEXMFLOCAL"] = str(texlive_dir / "texmf-local")
        
        print("✅ TeX Live environment configured")
        return True
    
    return False

# Auto-setup on import
setup_texlive_environment()
'''
    
    with open("texlive_env_setup.py", "w", encoding="utf-8") as f:
        f.write(setup_script)

def create_w32tex_environment_setup(w32tex_dir):
    """Create environment setup for W32TeX"""
    setup_script = f'''# W32TeX Environment Setup
import os
import sys
from pathlib import Path

def setup_w32tex_environment():
    """Set up W32TeX environment"""
    w32tex_dir = Path("{w32tex_dir}")
    
    if w32tex_dir.exists():
        # Add W32TeX bin to PATH
        bin_dir = w32tex_dir / "bin"
        
        if bin_dir.exists():
            current_path = os.environ.get("PATH", "")
            if str(bin_dir) not in current_path:
                os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
        
        # Set W32TeX environment variables
        os.environ["W32TEX_ROOT"] = str(w32tex_dir)
        os.environ["TEXMFHOME"] = str(w32tex_dir / "share" / "texmf")
        
        print("✅ W32TeX environment configured")
        return True
    
    return False

# Auto-setup on import
setup_w32tex_environment()
'''
    
    with open("w32tex_env_setup.py", "w", encoding="utf-8") as f:
        f.write(setup_script)

def create_existing_latex_environment_setup(latex_path):
    """Create environment setup for existing LaTeX installation"""
    setup_script = f'''# Existing LaTeX Environment Setup
import os
import sys
from pathlib import Path

def setup_existing_latex_environment():
    """Set up existing LaTeX environment"""
    latex_path = Path("{latex_path}")
    
    if latex_path.exists():
        # Find bin directories
        bin_dirs = list(latex_path.rglob("bin"))
        
        for bin_dir in bin_dirs:
            if (bin_dir / "latex.exe").exists() or (bin_dir / "latex").exists():
                current_path = os.environ.get("PATH", "")
                if str(bin_dir) not in current_path:
                    os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
                
                # Set common LaTeX environment variables
                os.environ["LATEX_ROOT"] = str(latex_path)
                
                # Try to find TEXMF directories
                texmf_dirs = list(latex_path.rglob("*texmf*"))
                if texmf_dirs:
                    os.environ["TEXMFHOME"] = str(texmf_dirs[0])
                
                print(f"✅ Existing LaTeX environment configured: {{bin_dir}}")
                return True
    
    return False

# Auto-setup on import
setup_existing_latex_environment()
'''
    
    with open("existing_latex_env_setup.py", "w", encoding="utf-8") as f:
        f.write(setup_script)
    
    print(f"📄 Created environment setup for existing LaTeX: {latex_path}")

def create_protext_environment_setup(protext_dir):
    """Create environment setup for ProTeXt"""
    setup_script = f'''# ProTeXt Environment Setup
import os
import sys
from pathlib import Path

def setup_protext_environment():
    """Set up ProTeXt environment"""
    protext_dir = Path("{protext_dir}")
    
    if protext_dir.exists():
        # Add ProTeXt bin to PATH
        bin_dir = protext_dir / "MiKTeX" / "miktex" / "bin" / "x64"
        if not bin_dir.exists():
            bin_dir = protext_dir / "bin"
        
        if bin_dir.exists():
            current_path = os.environ.get("PATH", "")
            if str(bin_dir) not in current_path:
                os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
        
        # Set ProTeXt environment variables
        os.environ["PROTEXT_ROOT"] = str(protext_dir)
        os.environ["TEXMFHOME"] = str(protext_dir / "texmf")
        
        print("✅ ProTeXt environment configured")
        return True
    
    return False

# Auto-setup on import
setup_protext_environment()
'''
    
    with open("protext_env_setup.py", "w", encoding="utf-8") as f:
        f.write(setup_script)

def create_advanced_latex_config():
    """Create advanced LaTeX configuration that works with multiple distributions"""
    config_content = r'''# advanced_latex_config.py - Advanced Multi-Distribution LaTeX Support
import os
import sys
from pathlib import Path

def find_latex_distribution():
    """Find any available LaTeX distribution"""
    possible_locations = [
        Path("latex_bundle"),
        Path("./latex_bundle"),
        Path("../latex_bundle"),
        Path(sys.executable).parent / "latex_bundle" if hasattr(sys, 'executable') else None,
    ]
    
    # For Nuitka builds
    if hasattr(sys, '_MEIPASS'):
        possible_locations.append(Path(sys._MEIPASS) / "latex_bundle")
    
    if 'NUITKA_ONEFILE_PARENT' in os.environ:
        app_dir = Path(os.environ['NUITKA_ONEFILE_PARENT']).parent
        possible_locations.append(app_dir / "latex_bundle")
    
    for location in possible_locations:
        if location and location.exists():
            return detect_latex_distribution_type(location)
    
    return None, None

def detect_latex_distribution_type(latex_dir):
    """Detect the type of LaTeX distribution"""
    # Check for existing LaTeX installation
    if (latex_dir / "existing_latex").exists():
        return "existing", latex_dir / "existing_latex"
    
    # Check for MiKTeX
    if (latex_dir / "miktex_portable").exists():
        return "miktex", latex_dir / "miktex_portable"
    
    # Check for TeX Live
    if (latex_dir / "texlive_basic").exists():
        return "texlive", latex_dir / "texlive_basic"
    
    # Check for W32TeX
    if (latex_dir / "w32tex").exists():
        return "w32tex", latex_dir / "w32tex"
    
    # Check for ProTeXt
    if (latex_dir / "protext_basic").exists():
        return "protext", latex_dir / "protext_basic"
    
    # Generic detection
    return "generic", latex_dir

def setup_latex_environment():
    """Set up environment for any LaTeX distribution"""
    dist_type, latex_dir = find_latex_distribution()
    
    if not latex_dir:
        print("❌ No LaTeX distribution found")
        return False
    
    print(f"📦 Found LaTeX distribution: {dist_type} at {latex_dir}")
    
    if dist_type == "existing":
        return setup_existing_latex_environment_from_bundle(latex_dir)
    elif dist_type == "miktex":
        return setup_miktex_environment(latex_dir)
    elif dist_type == "texlive":
        return setup_texlive_environment(latex_dir)
    elif dist_type == "w32tex":
        return setup_w32tex_environment(latex_dir)
    elif dist_type == "protext":
        return setup_protext_environment(latex_dir)
    else:
        return setup_generic_environment(latex_dir)

def setup_existing_latex_environment_from_bundle(latex_dir):
    """Set up existing LaTeX environment from bundle"""
    # The actual LaTeX installation is linked/copied to existing_latex
    existing_dir = latex_dir / "existing_latex"
    if existing_dir.exists():
        # Find bin directories in the existing installation
        bin_dirs = list(existing_dir.rglob("bin"))
        
        for bin_dir in bin_dirs:
            if (bin_dir / "latex.exe").exists() or (bin_dir / "latex").exists():
                current_path = os.environ.get("PATH", "")
                if str(bin_dir) not in current_path:
                    os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
                
                os.environ["LATEX_ROOT"] = str(existing_dir)
                
                # Set TEXMF variables if found
                texmf_dirs = list(existing_dir.rglob("*texmf*"))
                if texmf_dirs:
                    os.environ["TEXMFHOME"] = str(texmf_dirs[0])
                
                print(f"✅ Existing LaTeX environment configured from bundle")
                return True
    
    return False

def setup_miktex_environment(miktex_dir):
    """Set up MiKTeX environment"""
    bin_dirs = [
        miktex_dir / "texmfs" / "install" / "miktex" / "bin" / "x64",
        miktex_dir / "texmfs" / "install" / "miktex" / "bin",
        miktex_dir / "bin" / "x64",
        miktex_dir / "bin"
    ]
    
    for bin_dir in bin_dirs:
        if bin_dir.exists():
            current_path = os.environ.get("PATH", "")
            if str(bin_dir) not in current_path:
                os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
            
            os.environ["MIKTEX_ROOT"] = str(miktex_dir)
            os.environ["TEXMFHOME"] = str(miktex_dir / "texmf")
            print("✅ MiKTeX environment configured")
            return True
    
    return False

def setup_texlive_environment(texlive_dir):
    """Set up TeX Live environment"""
    bin_dirs = [
        texlive_dir / "bin" / "win32",
        texlive_dir / "bin" / "windows",
        texlive_dir / "bin" / "x86_64-win32",
        texlive_dir / "bin"
    ]
    
    for bin_dir in bin_dirs:
        if bin_dir.exists():
            current_path = os.environ.get("PATH", "")
            if str(bin_dir) not in current_path:
                os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
            
            os.environ["TEXLIVE_ROOT"] = str(texlive_dir)
            os.environ["TEXMFHOME"] = str(texlive_dir / "texmf-home")
            os.environ["TEXMFLOCAL"] = str(texlive_dir / "texmf-local")
            print("✅ TeX Live environment configured")
            return True
    
    return False

def setup_w32tex_environment(w32tex_dir):
    """Set up W32TeX environment"""
    bin_dir = w32tex_dir / "bin"
    
    if bin_dir.exists():
        current_path = os.environ.get("PATH", "")
        if str(bin_dir) not in current_path:
            os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
        
        os.environ["W32TEX_ROOT"] = str(w32tex_dir)
        os.environ["TEXMFHOME"] = str(w32tex_dir / "share" / "texmf")
        print("✅ W32TeX environment configured")
        return True
    
    return False

def setup_protext_environment(protext_dir):
    """Set up ProTeXt environment"""
    bin_dirs = [
        protext_dir / "MiKTeX" / "miktex" / "bin" / "x64",
        protext_dir / "MiKTeX" / "miktex" / "bin",
        protext_dir / "bin"
    ]
    
    for bin_dir in bin_dirs:
        if bin_dir.exists():
            current_path = os.environ.get("PATH", "")
            if str(bin_dir) not in current_path:
                os.environ["PATH"] = str(bin_dir) + os.pathsep + current_path
            
            os.environ["PROTEXT_ROOT"] = str(protext_dir)
            os.environ["TEXMFHOME"] = str(protext_dir / "texmf")
            print("✅ ProTeXt environment configured")
            return True
    
    return False

def setup_generic_environment(latex_dir):
    """Set up generic LaTeX environment"""
    # Search for executables
    latex_executables = []
    for pattern in ['*latex*', '*tex*']:
        latex_executables.extend(latex_dir.rglob(pattern))
    
    paths_to_add = set()
    for exe in latex_executables:
        if exe.is_file() and (exe.suffix.lower() in ['.exe', ''] or exe.name.lower() in ['latex', 'pdflatex', 'xelatex']):
            paths_to_add.add(str(exe.parent))
    
    if paths_to_add:
        current_path = os.environ.get("PATH", "")
        for path in paths_to_add:
            if path not in current_path:
                os.environ["PATH"] = path + os.pathsep + current_path
                current_path = os.environ["PATH"]
        
        # Set generic environment variables
        os.environ["LATEX_ROOT"] = str(latex_dir)
        texmf_dirs = list(latex_dir.rglob("*texmf*"))
        if texmf_dirs:
            os.environ["TEXMFHOME"] = str(texmf_dirs[0])
        
        print("✅ Generic LaTeX environment configured")
        return True
    
    return False

def configure_manim_for_advanced_latex():
    """Configure manim to use the advanced LaTeX distribution"""
    try:
        import manim
        
        if hasattr(manim, 'config'):
            try:
                from manim.utils.tex_templates import TexTemplate
                
                advanced_latex_template = TexTemplate(
                    documentclass="standalone",
                    geometry_options={"margin": "0mm"},
                    fontsize="12pt",
                    tex_compiler="latex",
                    output_format=".dvi",
                    preamble=r"""
                    \usepackage[english]{babel}
                    \usepackage{amsmath}
                    \usepackage{amsfonts}
                    \usepackage{amssymb}
                    \usepackage{dsfont}
                    \usepackage{setspace}
                    \usepackage{tipa}
                    \usepackage{relsize}
                    \usepackage{textcomp}
                    \usepackage{mathrsfs}
                    \usepackage{calligra}
                    \usepackage{wasysym}
                    \usepackage{ragged2e}
                    \usepackage{physics}
                    \usepackage{xcolor}
                    \usepackage{microtype}
                    \usepackage{graphicx}
                    \usepackage{tikz}
                    \usepackage{pgfplots}
                    \pgfplotsset{compat=1.18}
                    \DisableLigatures{encoding = *, family = * }
                    \linespread{1}
                    """
                )
                
                manim.config.tex_template = advanced_latex_template
                manim.config.preview = False
                print("✅ Manim configured with advanced LaTeX template")
                
            except Exception as e:
                print(f"❌ CRITICAL: Could not set LaTeX template: {e}")
                raise Exception(f"Manim LaTeX configuration failed: {e}")
            
    except ImportError:
        print("⚠️ Manim not available for configuration")
    except Exception as e:
        print(f"❌ CRITICAL: Error configuring manim: {e}")
        raise

def initialize_advanced_latex_support():
    """Initialize advanced LaTeX support"""
    print("🚀 Initializing Advanced LaTeX Distribution Support...")
    
    if setup_latex_environment():
        configure_manim_for_advanced_latex()
        print("🎉 Advanced LaTeX initialization complete!")
        return True
    else:
        print("❌ CRITICAL: Advanced LaTeX initialization failed")
        raise Exception("Advanced LaTeX initialization failed")

# Auto-initialize on import
if __name__ != "__main__":
    try:
        initialize_advanced_latex_support()
    except Exception as e:
        print(f"❌ FATAL: Advanced LaTeX initialization error: {e}")
        sys.exit(1)
'''
    
    with open("advanced_latex_config.py", "w", encoding="utf-8") as f:
        f.write(config_content)
    
    print("📄 Created Advanced LaTeX configuration")

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

# Default manim config content
DEFAULT_MANIM_CONFIG = """
[CLI]
media_dir = ./media
verbosity = WARNING
notify_outdated_version = False
preview = False

[logger]
logging_keyword = manim
logging_level = WARNING

[output]
max_files_cached = 10
flush_cache = True
disable_caching = False

[tex]
intermediate_filetype = dvi
text_to_replace = YourTextHere

[universal]
background_color = BLACK
assets_dir = ./

[window]
background_opacity = 1
fullscreen = False
size = 1280,720
"""

def apply_fixes():
    """Apply all fixes at startup"""
    fix_manim_config()
    patch_subprocess()

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
    
    print("📄 Created fixes module")

def create_no_console_patch():
    """Create a more aggressive patch file to ensure NO subprocess calls show console windows"""
    patch_content = '''# ENHANCED_NO_CONSOLE_PATCH.py
# This ensures all subprocess calls hide console windows

import subprocess
import sys
import os
import ctypes

# Check if already patched to prevent recursion
if hasattr(subprocess, '_manimstudio_patched'):
    print("Subprocess already patched, skipping additional patching")
else:
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

    # Store original functions BEFORE defining any wrappers
    _original_run = subprocess.run
    _original_popen = subprocess.Popen
    _original_call = subprocess.call
    _original_check_output = subprocess.check_output
    _original_check_call = subprocess.check_call

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
        
        # Run the process using original run
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
        return run_hidden_process(*args, **kwargs).returncode

    def _no_console_check_output(*args, **kwargs):
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.DEVNULL
        result = run_hidden_process(*args, **kwargs)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, args[0], result.stdout, result.stderr)
        return result.stdout

    def _no_console_check_call(*args, **kwargs):
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

    # Mark as patched to prevent recursive patching
    subprocess._manimstudio_patched = True
    subprocess._original_run = _original_run
    subprocess._original_popen = _original_popen

    print("Subprocess patching complete - all console windows will be hidden")

# Export the utility functions so they can be imported
__all__ = ['run_hidden_process', 'popen_hidden_process']
'''
    
    # Write with explicit UTF-8 encoding
    with open("ENHANCED_NO_CONSOLE_PATCH.py", "w", encoding="utf-8") as f:
        f.write(patch_content)
    
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

def verify_latex_installation(latex_dir):
    """Verify that we have a working LaTeX installation"""
    try:
        print("🔍 Verifying LaTeX installation...")
        
        # Look for LaTeX executables
        latex_executables = []
        for pattern in ['*latex*', '*tex*', '*pdftex*']:
            latex_executables.extend(latex_dir.rglob(pattern))
        
        # Filter to actual executables
        actual_executables = []
        for exe in latex_executables:
            if exe.is_file() and (exe.suffix.lower() in ['.exe', ''] or 
                                exe.name.lower() in ['latex', 'pdflatex', 'xelatex', 'lualatex', 'tex', 'pdftex']):
                actual_executables.append(exe)
        
        if actual_executables:
            print(f"✅ Found {len(actual_executables)} LaTeX executables:")
            for exe in actual_executables[:5]:  # Show first 5
                print(f"  📄 {exe.relative_to(latex_dir)}")
            return True
        
        # Look for TeX distribution structure
        texmf_dirs = list(latex_dir.rglob("*texmf*"))
        if texmf_dirs:
            print(f"✅ Found {len(texmf_dirs)} TEXMF directories")
            return True
        
        # Look for any substantial LaTeX content
        latex_files = list(latex_dir.rglob("*.sty")) + list(latex_dir.rglob("*.cls"))
        if len(latex_files) > 10:  # Substantial number of LaTeX files
            print(f"✅ Found {len(latex_files)} LaTeX style/class files")
            return True
        
        print("❌ No substantial LaTeX installation found")
        return False
        
    except Exception as e:
        print(f"⚠️ Verification error: {e}")
        return False

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

def build_standalone_with_advanced_latex(jobs=None, priority="normal"):
    """Build standalone version with advanced LaTeX distribution (<2GB)"""
    
    cpu_count = multiprocessing.cpu_count()
    if jobs is None:
        jobs = max(1, cpu_count - 1)

    print(f"🚀 Building STANDALONE with Advanced LaTeX (<2GB) using {jobs} CPU threads...")

    # STEP 1: CRITICAL - Download and setup Advanced LaTeX Distribution
    print("=" * 60)
    print("📦 Step 1: Downloading Advanced LaTeX Distribution (<2GB)...")
    
    # Download the advanced LaTeX distribution - THIS MUST SUCCEED
    latex_success = download_advanced_latex_distribution()
    
    if not latex_success:
        print("❌ CRITICAL FAILURE: Could not download Advanced LaTeX Distribution")
        print("🚫 Build cannot continue without LaTeX support")
        sys.exit(1)

    # Clean previous builds
    if Path("build").exists():
        shutil.rmtree("build")
    if Path("dist").exists():
        shutil.rmtree("dist")

    # Create assets directory
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("🔧 Step 2: Creating enhanced build configuration...")

    # Create enhanced patches and helpers
    create_no_console_patch()
    create_fixes_module()
    create_subprocess_helper()
    create_advanced_latex_config()  # Use the new advanced LaTeX config

    # Check prerequisites
    if not check_system_prerequisites():
        print("❌ System prerequisites check failed")
        sys.exit(1)

    # Get Nuitka version
    nuitka_version = get_nuitka_version()
    print(f"📊 Detected Nuitka version: {nuitka_version}")

    print("=" * 60)
    print("🔨 Step 3: Building with Advanced LaTeX support...")

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
        # Exclude only specific problematic SymPy test modules
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
                print(f"📦 Including full package: {correct_name}")

    # Include SymPy with FULL LaTeX support
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
        print("🧮 Including SymPy with FULL LaTeX support")

    # Include LaTeX support packages if available
    latex_packages = ["latex2mathml", "antlr4", "pygments", "colour", "jinja2"]
    
    for package in latex_packages:
        if is_package_importable(package):
            cmd.append(f"--include-package={package}")
            cmd.append(f"--include-package-data={package}")
            included_packages.append(package)
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
        "advanced_latex_config",  # Our Advanced LaTeX config
        # Additional modules for LaTeX support
        "xml", "xml.etree", "xml.etree.ElementTree",
        "urllib", "urllib.request", "urllib.parse",
        "zipfile", "tarfile", "gzip", "bz2", "lzma",
        "hashlib", "hmac", "ssl", "socket"
    ]

    for module in comprehensive_modules:
        cmd.append(f"--include-module={module}")

    # Include Advanced LaTeX bundle directory if it exists
    if Path("latex_bundle").exists():
        cmd.append("--include-data-dir=latex_bundle=latex_bundle")
        print("📦 Including Advanced LaTeX bundle")

    # Include comprehensive data for LaTeX support
    data_packages = ["manim", "matplotlib", "numpy", "sympy"]

    for package in data_packages:
        if is_package_importable(package):
            cmd.append(f"--include-package-data={package}")
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
            print("📊 Including matplotlib data directory")
    except ImportError:
        pass

    for data_dir in data_dirs:
        cmd.append(f"--include-data-dir={data_dir}")

    # Final target
    cmd.append("app.py")

    print("Building standalone executable with Advanced LaTeX support...")
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
    print(f"📦 Included {len(included_packages)} packages with Advanced LaTeX")

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
        print("✅ Advanced LaTeX build successful!")

        exe_path = find_standalone_executable()
        if exe_path:
            # Create launcher scripts
            create_launcher_script(exe_path)
            
            print(f"📁 Executable: {exe_path}")
            print("🎉 ADVANCED LATEX FEATURES:")
            print("  ✅ Multi-distribution LaTeX support (<2GB)")
            print("  ✅ MiKTeX Portable / TeX Live Basic / W32TeX / ProTeXt")
            print("  ✅ Automatic fallback between distributions")
            print("  ✅ Complete LaTeX rendering support")
            print("  ✅ Professional mathematical typesetting")
            print("  ✅ Advanced LaTeX packages included")
            print("  ✅ Portable LaTeX installation")
            print("  ✅ No console windows")

            return exe_path
        else:
            print("❌ Executable not found")
            list_contents()
            return None
    else:
        print("=" * 60)
        print("❌ Advanced LaTeX build failed!")
        print(f"Return code: {return_code}")
        sys.exit(1)

def main():
    """Main function - MiKTeX-prioritized LaTeX build option"""
    import sys  # Explicitly import here to fix scope issue
    
    print("🚀 Manim Studio - MiKTeX-Prioritized LaTeX Builder (<2GB)")
    print("=" * 50)
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Build Manim Studio with MiKTeX-Prioritized LaTeX (<2GB)")
    parser.add_argument("--jobs", type=int, help="Number of CPU threads to use (default: CPU count - 1)")
    parser.add_argument("--max-cpu", action="store_true", help="Use all available CPU cores with oversubscription")
    parser.add_argument("--turbo", action="store_true", help="Use turbo mode - maximum CPU with high priority")
    parser.add_argument("--ascii", action="store_true", help="Use ASCII output instead of Unicode symbols")
    parser.add_argument("--miktex-only", action="store_true", help="Force MiKTeX-only mode (no fallbacks)")
    parser.add_argument("--check-miktex", action="store_true", help="Only check for existing MiKTeX installation and exit")
    
    # Parse args but keep default behavior if not specified
    args, remaining_args = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + remaining_args
    
    global USE_ASCII_ONLY
    if args.ascii:
        USE_ASCII_ONLY = True
    
    # Handle MiKTeX check mode
    if args.check_miktex:
        print("🔍 Checking for existing MiKTeX installations...")
        latex_bundle_dir = Path("temp_check")
        latex_bundle_dir.mkdir(exist_ok=True)
        
        if detect_and_use_existing_miktex(latex_bundle_dir):
            print("✅ MiKTeX found and ready!")
        else:
            print("❌ No MiKTeX installation detected")
            show_manual_miktex_installation_instructions()
        
        # Clean up temp directory
        if latex_bundle_dir.exists():
            shutil.rmtree(latex_bundle_dir)
        sys.exit(0)
    
    # Store MiKTeX-only preference globally or pass it down
    global FORCE_MIKTEX_ONLY
    FORCE_MIKTEX_ONLY = args.miktex_only
    
    # Determine job count
    cpu_count = multiprocessing.cpu_count()
    process_priority = "normal"
    
    if args.turbo:
        # Turbo mode: maximum cores + oversubscription + high priority
        jobs = int(cpu_count * 2)  # Double the cores for extreme oversubscription
        process_priority = "high"
        print(f"🚀 TURBO MODE: Maximum CPU power with {jobs} threads and HIGH priority!")
    elif args.max_cpu:
        # Maximum cores with oversubscription
        jobs = int(cpu_count * 1.5)  # Oversubscription by 50%
        print(f"🔥 Maximum CPU mode: {jobs} threads (oversubscribed from {cpu_count} cores)")
    elif args.jobs:
        jobs = args.jobs
        print(f"⚙️ Using specified CPU threads: {jobs} of {cpu_count} available")
    else:
        jobs = max(1, cpu_count - 1)
        print(f"⚙️ Using optimal CPU threads: {jobs} of {cpu_count} available")
    
    # Check requirements first
    if not check_requirements():
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
    
    logging.info("Building with MiKTeX-prioritized LaTeX distribution support")
    
    # Display build information based on mode
    if args.miktex_only:
        print("\n🎯 Building with MiKTeX-ONLY Mode...")
        print("📋 This build includes:")
        print("  🎯 MiKTeX detection and installation ONLY")
        print("  ✅ MiKTeX Portable (~800MB) if not found")
        print("  🚫 NO fallback distributions")
        print("  ✅ Complete LaTeX rendering support")
        print("  ✅ Professional mathematical typesetting")
        print("  ✅ Portable MiKTeX installation")
        print("  ✅ No console windows")
        print("  ⚠️  Build will FAIL if MiKTeX cannot be obtained")
    else:
        print("\n🎯 Building with MiKTeX-Prioritized LaTeX Distribution...")
        print("📋 This build includes:")
        print("  🥇 PRIMARY: MiKTeX detection and Portable (~800MB)")
        print("  🥈 FALLBACK OPTIONS (if MiKTeX fails):")
        print("      🔸 TeX Live Basic (~1.5GB)")
        print("      🔸 W32TeX (~600MB)")
        print("      🔸 ProTeXt Basic (~900MB)")
        print("  ✅ Automatic fallback between distributions")
        print("  ✅ Complete LaTeX rendering support")
        print("  ✅ Professional mathematical typesetting")
        print("  ✅ Portable LaTeX installation")
        print("  ✅ No console windows")
    
    # Show what we'll check for first
    print(f"\n🔍 Pre-build MiKTeX detection:")
    print("  📂 Checking standard MiKTeX installation paths...")
    print("  📂 Checking PATH for MiKTeX executables...")
    print("  📂 Checking portable MiKTeX locations...")
    
    # Perform a quick pre-check to inform the user
    print("\n🔍 Performing quick MiKTeX detection...")
    temp_check_dir = Path("temp_miktex_check")
    temp_check_dir.mkdir(exist_ok=True)
    
    try:
        if detect_and_use_existing_miktex(temp_check_dir):
            print("✅ Existing MiKTeX installation detected!")
            print("   📁 Your existing MiKTeX will be used for the build")
        else:
            print("❌ No existing MiKTeX found")
            if args.miktex_only:
                print("   📥 MiKTeX Portable will be downloaded during build")
            else:
                print("   📥 MiKTeX Portable will be tried first, with fallbacks available")
    except Exception as e:
        print(f"⚠️ Detection check failed: {e}")
        print("   🔄 Full detection will be performed during build")
    finally:
        # Clean up temp directory
        if temp_check_dir.exists():
            shutil.rmtree(temp_check_dir)
    
    # Confirmation
    mode_text = "MiKTeX-ONLY" if args.miktex_only else "MiKTeX-Prioritized"
    confirm = input(f"\n🚀 Proceed with {mode_text} LaTeX build? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("❌ Build cancelled by user")
        sys.exit(0)
    
    # Show additional information for MiKTeX-only mode
    if args.miktex_only:
        print("\n⚠️  MiKTeX-ONLY Mode Active:")
        print("   🎯 Only MiKTeX will be considered")
        print("   📥 If no existing MiKTeX found, MiKTeX Portable will be downloaded")
        print("   🚫 Build will FAIL if MiKTeX cannot be obtained")
        print("   💡 If build fails, you can:")
        print("      1. Install MiKTeX manually from https://miktex.org/download")
        print("      2. Re-run without --miktex-only for fallback options")
        
        final_confirm = input("Continue with MiKTeX-ONLY mode? (y/N): ").strip().lower()
        if final_confirm not in ['y', 'yes']:
            print("❌ Build cancelled by user")
            print("💡 Tip: Run without --miktex-only for fallback options")
            sys.exit(0)
    
    # Execute the build
    print(f"\n🚀 Starting {mode_text} build process...")
    exe_path = build_standalone_with_advanced_latex(jobs=jobs, priority=process_priority)
    success = exe_path is not None
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Build completed successfully!")
        if args.miktex_only:
            print("🚀 MIKTEX-ONLY BUILD: Optimized for MiKTeX!")
            print("   🆕 FEATURES:")
            print("   ✅ MiKTeX-exclusive LaTeX support")
            print("   ✅ Optimized for MiKTeX performance")
            print("   ✅ Guaranteed MiKTeX compatibility")
            print("   ✅ Smaller build size (MiKTeX optimized)")
            print("   🎯 Pure MiKTeX distribution used")
        else:
            print("🚀 MIKTEX-PRIORITIZED BUILD: Best of both worlds!")
            print("   🆕 FEATURES:")
            print("   🥇 MiKTeX-first with smart fallbacks")
            print("   ✅ MiKTeX Portable / TeX Live Basic / W32TeX / ProTeXt support")
            print("   ✅ Intelligent distribution selection")
            print("   ✅ Enhanced error handling with fallbacks")
        
        print("   ✅ Complete LaTeX rendering support")
        print("   ✅ Professional mathematical typesetting")
        print("   ✅ Advanced LaTeX packages included")
        print("   ✅ Portable LaTeX installation")
        print("   ✅ No console windows")
        print("   🎯 OPTIMIZED: Best MiKTeX integration!")
        print("🚀 Professional desktop application ready!")
        
        # Show usage instructions
        print("\n📋 USAGE INSTRUCTIONS:")
        print(f"   📁 Executable location: {exe_path}")
        print("   🚀 Run the .exe file to start Manim Studio")
        print("   🎯 LaTeX rendering is fully configured and ready")
        if args.miktex_only:
            print("   ✅ MiKTeX-optimized build for best performance")
        else:
            print("   ✅ Multi-distribution LaTeX support included")
        
    else:
        print("❌ Build failed!")
        if args.miktex_only:
            print("💡 MiKTeX-ONLY mode failed. You can:")
            print("   1. Install MiKTeX manually: https://miktex.org/download")
            print("   2. Try again without --miktex-only for fallback options")
            print("   3. Use --check-miktex to verify MiKTeX installation")
        else:
            print("💡 Build failed even with fallback options. Check the logs above.")
            print("   📄 Check build.log for detailed error information")
        sys.exit(1)
if __name__ == "__main__":
    main()
