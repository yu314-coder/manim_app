#!/usr/bin/env python3
import subprocess
import sys
import os
from pathlib import Path
import shutil

def build_production_version():
    """Build production version without console, optimized for speed"""
    
    print("🚀 Building PRODUCTION version (no console, standalone)...")
    
    # Clean previous builds
    if Path("build").exists():
        print("🧹 Cleaning build directory...")
        shutil.rmtree("build")
    if Path("dist").exists():
        print("🧹 Cleaning dist directory...")
        shutil.rmtree("dist")
    
    # Build command optimized for production
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--mingw64",
        
        # CRITICAL: Hide console window
        "--windows-disable-console",
        
        # CRITICAL: Enable tkinter plugin
        "--enable-plugin=tk-inter",
        
        # Minimize output for faster build
        "--show-progress",
        
        # Output options
        "--output-dir=dist",
        "--output-filename=ManimStudio.exe",
        
        # Icon (if available)
        "--windows-icon-from-ico=assets/icon.ico",
        
        # Version info
        "--product-name=Manim Animation Studio",
        "--file-version=3.5.0.0",
        "--product-version=3.5.0",
        "--file-description=Professional Manim Animation Studio",
        "--company-name=Manim Studio Team",
        
        # Essential packages with explicit inclusion
        "--include-package=customtkinter",
        "--include-package=tkinter",
        "--include-package=PIL",
        "--include-package=numpy",
        "--include-package=cv2",
        
        # Include data directories if they exist
        "--include-data-dir=assets=assets",
        
        # Optimize for speed - use all CPU cores
        "--jobs=0",  # 0 means use all available cores
        
        # Performance optimizations
        "--assume-yes-for-downloads",
        
        # Final target
        "app.py"
    ]
    
    print("🔨 Building production version...")
    print("Key features:")
    print("  ✅ No console window")
    print("  ✅ Standalone directory (not onefile)")
    print("  ✅ Tkinter plugin enabled")
    print("  ✅ Optimized for speed")
    print()
    print("Command:", " ".join(cmd))
    print("=" * 60)
    
    # Run build with real-time output
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Print output in real-time
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())
    
    return_code = process.poll()
    
    if return_code == 0:
        print("=" * 60)
        print("✅ Production build successful!")
        
        # Find executable
        exe_path = find_executable()
        
        if exe_path:
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"📁 Executable: {exe_path} ({size_mb:.1f} MB)")
            
            # Show dist directory contents
            list_dist_contents()
            
            print(f"\n🎉 Build completed successfully!")
            print(f"📁 Output directory: dist/")
            print(f"🚀 Main executable: {exe_path}")
            print(f"\n⚡ Next step: Run create_installer_fast.py to package everything!")
            
            return exe_path
        else:
            print("❌ Executable not found")
            list_dist_contents()
            return None
    else:
        print("=" * 60)
        print("❌ Build failed!")
        print(f"Return code: {return_code}")
        return None

def find_executable():
    """Find the executable in various locations"""
    possible_paths = [
        Path("dist/ManimStudio.exe"),
        Path("dist/app.dist/ManimStudio.exe"),
    ]
    
    # Search for executable
    for path in possible_paths:
        if path.exists():
            return path
    
    # Also search in subdirectories
    dist_dir = Path("dist")
    if dist_dir.exists():
        for item in dist_dir.rglob("*.exe"):
            if "ManimStudio" in item.name:
                return item
    
    return None

def list_dist_contents():
    """List contents of dist directory"""
    dist_dir = Path("dist")
    if dist_dir.exists():
        print("\n📂 Contents of dist/:")
        total_size = 0
        for item in dist_dir.iterdir():
            if item.is_file():
                size = item.stat().st_size / (1024 * 1024)
                total_size += size
                print(f"  📄 {item.name} ({size:.1f} MB)")
            elif item.is_dir():
                dir_size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file()) / (1024 * 1024)
                total_size += dir_size
                print(f"  📁 {item.name}/ ({dir_size:.1f} MB)")
                # Show key files in subdirectories
                for subitem in item.iterdir():
                    if subitem.name.endswith('.exe'):
                        size = subitem.stat().st_size / (1024 * 1024)
                        print(f"    📄 {subitem.name} ({size:.1f} MB)")
        
        print(f"\n📦 Total dist size: {total_size:.1f} MB")

def build_debug_version():
    """Build debug version with console for testing"""
    
    print("🐛 Building DEBUG version with console...")
    
    # Clean previous builds
    if Path("build").exists():
        print("🧹 Cleaning build directory...")
        shutil.rmtree("build")
    if Path("dist_debug").exists():
        print("🧹 Cleaning dist_debug directory...")
        shutil.rmtree("dist_debug")
    
    # Build command with console for debugging
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--mingw64",
        
        # CRITICAL: Enable tkinter plugin
        "--enable-plugin=tk-inter",
        
        # Keep console for debugging
        # "--windows-disable-console",  # Commented out for debug version
        
        # Progress options
        "--show-progress",
        "--show-memory",
        
        # Output options
        "--output-dir=dist_debug",
        "--output-filename=ManimStudio_DEBUG.exe",
        
        # Icon (if available)
        "--windows-icon-from-ico=assets/icon.ico",
        
        # Version info
        "--product-name=Manim Animation Studio Debug",
        "--file-version=3.5.0.0",
        "--product-version=3.5.0",
        "--file-description=Manim Studio Debug Build with Console",
        
        # Essential packages
        "--include-package=customtkinter",
        "--include-package=tkinter",
        "--include-package=PIL",
        "--include-package=numpy",
        "--include-package=cv2",
        
        # Include data directories
        "--include-data-dir=assets=assets",
        
        # Jobs for faster compilation
        "--jobs=0",
        
        # Final target
        "app.py"
    ]
    
    print("🔨 Building debug version with console...")
    print("Command:", " ".join(cmd))
    print("=" * 60)
    
    # Run build
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Print output in real-time
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())
    
    return_code = process.poll()
    
    if return_code == 0:
        print("=" * 60)
        print("✅ Debug build successful!")
        
        # Find executable
        exe_path = find_debug_executable()
        
        if exe_path:
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"📁 Debug executable: {exe_path} ({size_mb:.1f} MB)")
            
            # Copy to main directory for easier access
            debug_exe_main = Path("ManimStudio_DEBUG.exe")
            if debug_exe_main.exists():
                debug_exe_main.unlink()
            shutil.copy2(exe_path, debug_exe_main)
            print(f"📁 Copied to: {debug_exe_main}")
            print(f"\n🧪 Test the debug version: ManimStudio_DEBUG.exe")
            
            return exe_path
        else:
            print("❌ Debug executable not found")
            return None
    else:
        print("=" * 60)
        print("❌ Debug build failed!")
        print(f"Return code: {return_code}")
        return None

def find_debug_executable():
    """Find the debug executable"""
    possible_paths = [
        Path("dist_debug/ManimStudio_DEBUG.exe"),
        Path("dist_debug/app.dist/ManimStudio_DEBUG.exe"),
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    # Search in subdirectories
    dist_debug = Path("dist_debug")
    if dist_debug.exists():
        for item in dist_debug.rglob("*.exe"):
            if "ManimStudio_DEBUG" in item.name:
                return item
    
    return None

if __name__ == "__main__":
    print("🚀 Manim Studio Builder")
    print("=" * 40)
    
    # Ask user which version to build
    print("Choose build type:")
    print("1. Production (no console, optimized)")
    print("2. Debug (with console, for testing)")
    
    choice = input("\nEnter choice (1 or 2) [default: 1]: ").strip() or "1"
    
    if choice == "2":
        debug_exe = build_debug_version()
        if debug_exe:
            print("\n🎉 Debug build completed!")
            print("🧪 Test by running: ManimStudio_DEBUG.exe")
    else:
        prod_exe = build_production_version()
        if prod_exe:
            print("\n🎉 Production build completed!")
            print("⚡ Next: python create_installer_fast.py")