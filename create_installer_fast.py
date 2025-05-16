#!/usr/bin/env python3
import os
import shutil
import subprocess
from pathlib import Path
from build_config import APP_NAME, APP_VERSION, APP_AUTHOR

def find_inno_setup():
    """Find Inno Setup installation"""
    common_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\iscc.exe",
        r"C:\Program Files\Inno Setup 6\iscc.exe",
        r"C:\Program Files (x86)\Inno Setup 5\iscc.exe",
        r"C:\Program Files\Inno Setup 5\iscc.exe",
    ]
    
    for path in common_paths:
        if Path(path).exists():
            return path
    return None

def find_nuitka_executable():
    """Find the Nuitka executable in various possible locations"""
    possible_paths = [
        Path("dist/ManimStudio.exe"),
        Path("dist/app.dist/ManimStudio.exe"),
        Path("dist/app/ManimStudio.exe"),
    ]
    
    for path in possible_paths:
        if path.exists():
            print(f"✅ Found executable at: {path}")
            return path
    
    print("❌ Could not find ManimStudio.exe")
    return None

def copy_nuitka_files_to_dist():
    """Copy all Nuitka files from subdirectory to main dist folder"""
    source_dir = Path("dist/app.dist")
    dest_dir = Path("dist")
    
    if not source_dir.exists():
        print("❌ Source directory not found:", source_dir)
        return False
    
    print(f"📦 Copying files from {source_dir} to {dest_dir}")
    
    # Copy all files from app.dist to the main dist folder
    for item in source_dir.iterdir():
        dest_path = dest_dir / item.name
        
        if item.is_file():
            if dest_path.exists():
                dest_path.unlink()  # Remove existing file
            shutil.copy2(item, dest_path)
            print(f"  📄 Copied {item.name}")
        elif item.is_dir():
            if dest_path.exists():
                shutil.rmtree(dest_path)
            shutil.copytree(item, dest_path)
            print(f"  📁 Copied {item.name}/")
    
    return True

def create_valid_ico_file():
    """Create a properly formatted ICO file using a simpler method"""
    print("🎨 Creating a new, valid icon file...")
    
    # Create assets directory
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)
    
    # Remove any existing corrupted icon
    icon_path = assets_dir / "icon.ico"
    if icon_path.exists():
        icon_path.unlink()
        print("🗑️ Removed old icon file")
    
    try:
        from PIL import Image, ImageDraw
        
        # Create multiple sizes for a proper ICO file
        sizes = [16, 32, 48, 64, 128, 256]
        images = []
        
        for size in sizes:
            # Create a simple, solid icon
            img = Image.new('RGBA', (size, size), (70, 130, 180, 255))  # Steel blue
            draw = ImageDraw.Draw(img)
            
            # Draw a simple white square in the center
            margin = size // 4
            draw.rectangle([margin, margin, size-margin, size-margin], 
                          fill=(255, 255, 255, 255))
            
            # Add a simple "M" or dot in the center for larger sizes
            if size >= 32:
                center = size // 2
                dot_size = max(2, size // 16)
                draw.rectangle([center-dot_size, center-dot_size, 
                               center+dot_size, center+dot_size], 
                              fill=(70, 130, 180, 255))
            
            images.append(img)
        
        # Save as ICO with all sizes
        images[0].save(
            icon_path, 
            format='ICO',
            sizes=[(img.width, img.height) for img in images],
            append_images=images[1:]
        )
        
        print(f"✅ Created new icon: {icon_path}")
        print(f"📐 Icon file size: {icon_path.stat().st_size} bytes")
        
        # Verify the ICO file
        test_img = Image.open(icon_path)
        test_img.close()
        print("✅ Icon file verified as valid")
        
        return True
        
    except ImportError:
        print("⚠️ PIL not available, trying alternative method...")
        return create_simple_ico_without_pil()
    except Exception as e:
        print(f"❌ Error creating icon with PIL: {e}")
        return create_simple_ico_without_pil()

def create_simple_ico_without_pil():
    """Create a minimal but valid ICO file without PIL"""
    print("🔧 Creating minimal ICO file...")
    
    # This creates a properly formatted 16x16 ICO file
    # ICO format is complex, so we'll use a known-good minimal template
    ico_header = bytearray([
        # ICO Header (6 bytes)
        0x00, 0x00,              # Reserved
        0x01, 0x00,              # Image type (1 = ICO)
        0x01, 0x00,              # Number of images
        
        # Image Directory Entry (16 bytes)
        0x10,                    # Width (16)
        0x10,                    # Height (16)
        0x00,                    # Colors (0 = 256+)
        0x00,                    # Reserved
        0x01, 0x00,              # Color planes
        0x20, 0x00,              # Bits per pixel (32-bit)
        0x68, 0x04, 0x00, 0x00,  # Size of image data
        0x16, 0x00, 0x00, 0x00,  # Offset to image data
    ])
    
    # BMP Header for 16x16 32-bit image
    bmp_header = bytearray([
        0x28, 0x00, 0x00, 0x00,  # Header size (40)
        0x10, 0x00, 0x00, 0x00,  # Width (16)
        0x20, 0x00, 0x00, 0x00,  # Height (32, double for ICO)
        0x01, 0x00,              # Color planes
        0x20, 0x00,              # Bits per pixel (32)
        0x00, 0x00, 0x00, 0x00,  # Compression (none)
        0x00, 0x04, 0x00, 0x00,  # Image size
        0x00, 0x00, 0x00, 0x00,  # X pixels per meter
        0x00, 0x00, 0x00, 0x00,  # Y pixels per meter
        0x00, 0x00, 0x00, 0x00,  # Colors used
        0x00, 0x00, 0x00, 0x00,  # Important colors
    ])
    
    # Create 16x16 pixel data (BGRA format)
    # Blue background with white center square
    pixel_data = bytearray()
    for y in range(32):  # ICO uses double height
        for x in range(16):
            if y < 16:  # Only first 16 rows contain actual image
                # Create a simple blue square with white center
                if 4 <= x <= 11 and 4 <= y <= 11:
                    # White center
                    pixel_data.extend([0xFF, 0xFF, 0xFF, 0xFF])  # BGRA
                else:
                    # Blue border
                    pixel_data.extend([0xB4, 0x82, 0x46, 0xFF])  # BGRA
            else:
                # AND mask (transparency) - all opaque
                pass  # AND mask comes after pixel data
    
    # AND mask (1 bit per pixel, all pixels opaque)
    and_mask = bytearray([0x00] * 32)  # 16x16 = 256 bits = 32 bytes
    
    # Combine all parts
    ico_data = ico_header + bmp_header + pixel_data + and_mask
    
    # Write to file
    icon_path = Path("assets/icon.ico")
    with open(icon_path, 'wb') as f:
        f.write(ico_data)
    
    print(f"✅ Created minimal icon: {icon_path}")
    print(f"📐 Icon file size: {icon_path.stat().st_size} bytes")
    return True

def create_fast_installer():
    """Create installer quickly using the Nuitka output"""
    
    print("📦 Creating fast installer...")
    
    # First, try to find and organize the executable
    exe_path = find_nuitka_executable()
    
    if not exe_path:
        print("❌ No executable found! Make sure build completed successfully.")
        return False
    
    # If executable is in a subdirectory, copy everything to main dist
    if exe_path.parent != Path("dist"):
        print("📁 Reorganizing files...")
        copy_nuitka_files_to_dist()
        # Update path to new location
        exe_path = Path("dist/ManimStudio.exe")
    
    # Verify the executable exists in the expected location
    if not exe_path.exists():
        print(f"❌ Executable not found at: {exe_path}")
        return False
    
    # Create installer directory
    installer_dir = Path("installer")
    installer_dir.mkdir(exist_ok=True)
    
    # Always create a fresh, valid icon
    icon_created = create_valid_ico_file()
    
    # Get absolute paths
    current_dir = Path.cwd()
    icon_path = current_dir / "assets" / "icon.ico"
    
    # Decide whether to include icon
    use_icon = icon_created and icon_path.exists()
    
    # Create Inno Setup script
    if use_icon:
        icon_line = f'SetupIconFile={icon_path}'
        print(f"📁 Using icon: {icon_path}")
    else:
        icon_line = '; No icon file'
        print("⚠️ Building without icon")
    
    # Create the installer script
    inno_script = f'''[Setup]
AppId={{{{F9A1B2C3-D4E5-6F7A-8B9C-0D1E2F3A4B5C}}}}
AppName={APP_NAME}
AppVersion={APP_VERSION}
AppPublisher={APP_AUTHOR}
DefaultDirName={{{{autopf}}}}\\{APP_NAME}
DefaultGroupName={APP_NAME}
OutputDir={current_dir}\\installer
OutputBaseFilename=ManimStudio-{APP_VERSION}-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
{icon_line}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Main executable and all Nuitka output
Source: "{current_dir}\\dist\\*"; DestDir: "{{{{app}}}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{{{autoprograms}}}}\\{APP_NAME}"; Filename: "{{{{app}}}}\\ManimStudio.exe"
Name: "{{{{autodesktop}}}}\\{APP_NAME}"; Filename: "{{{{app}}}}\\ManimStudio.exe"; Tasks: desktopicon

[Registry]
; File association for .py files (optional)
Root: HKCR; Subkey: ".py\\OpenWithProgids"; ValueType: string; ValueName: "ManimStudio.py"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCR; Subkey: "ManimStudio.py"; ValueType: string; ValueName: ""; ValueData: "Manim Scene File"; Flags: uninsdeletekey
Root: HKCR; Subkey: "ManimStudio.py\\shell\\open\\command"; ValueType: string; ValueName: ""; ValueData: """{{{{app}}}}\\ManimStudio.exe"" ""%1"""

[Run]
Filename: "{{{{app}}}}\\ManimStudio.exe"; Description: "Launch {APP_NAME}"; Flags: nowait postinstall skipifsilent
'''
    
    # Write the script
    script_path = installer_dir / "setup.iss"
    with open(script_path, "w") as f:
        f.write(inno_script)
    
    # Find Inno Setup
    iscc_path = find_inno_setup()
    
    if not iscc_path:
        print("⚠️ Inno Setup not found in common locations!")
        print("Download from: https://jrsoftware.org/isdl.php")
        print("Script created at:", script_path)
        return False
    
    print(f"✅ Found Inno Setup at: {iscc_path}")
    print(f"📝 Inno Setup script: {script_path}")
    
    # Run Inno Setup with full path
    print("🔨 Building installer...")
    result = subprocess.run([iscc_path, str(script_path)], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Installer created successfully!")
        installer_file = installer_dir / f"ManimStudio-{APP_VERSION}-Setup.exe"
        print(f"📁 Location: {installer_file}")
        
        # Show installer size
        if installer_file.exists():
            size_mb = installer_file.stat().st_size / (1024 * 1024)
            print(f"📦 Installer size: {size_mb:.1f} MB")
        
        print(f"\n🎉 SUCCESS! Your professional installer is ready!")
        print(f"✨ Installer: {installer_file}")
        print(f"🚀 Users can now install Manim Studio by running this .exe")
        print(f"\n💡 Next steps for Microsoft Store:")
        print(f"   - Run: python create_msix_fast.py")
        print(f"   - Sign the MSIX package")
        print(f"   - Upload to Microsoft Partner Center")
        
        return True
    else:
        print("❌ Installer creation failed!")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        
        # If it still fails, try without icon
        if use_icon:
            print("\n🔄 Retrying without icon...")
            return create_installer_without_icon(current_dir, installer_dir, script_path, iscc_path)
        return False

def create_installer_without_icon(current_dir, installer_dir, script_path, iscc_path):
    """Create installer without icon as fallback"""
    
    # Create script without icon
    inno_script_no_icon = f'''[Setup]
AppId={{{{F9A1B2C3-D4E5-6F7A-8B9C-0D1E2F3A4B5C}}}}
AppName={APP_NAME}
AppVersion={APP_VERSION}
AppPublisher={APP_AUTHOR}
DefaultDirName={{{{autopf}}}}\\{APP_NAME}
DefaultGroupName={APP_NAME}
OutputDir={current_dir}\\installer
OutputBaseFilename=ManimStudio-{APP_VERSION}-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Main executable and all Nuitka output
Source: "{current_dir}\\dist\\*"; DestDir: "{{{{app}}}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{{{autoprograms}}}}\\{APP_NAME}"; Filename: "{{{{app}}}}\\ManimStudio.exe"
Name: "{{{{autodesktop}}}}\\{APP_NAME}"; Filename: "{{{{app}}}}\\ManimStudio.exe"; Tasks: desktopicon

[Registry]
; File association for .py files (optional)
Root: HKCR; Subkey: ".py\\OpenWithProgids"; ValueType: string; ValueName: "ManimStudio.py"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCR; Subkey: "ManimStudio.py"; ValueType: string; ValueName: ""; ValueData: "Manim Scene File"; Flags: uninsdeletekey
Root: HKCR; Subkey: "ManimStudio.py\\shell\\open\\command"; ValueType: string; ValueName: ""; ValueData: """{{{{app}}}}\\ManimStudio.exe"" ""%1"""

[Run]
Filename: "{{{{app}}}}\\ManimStudio.exe"; Description: "Launch {APP_NAME}"; Flags: nowait postinstall skipifsilent
'''
    
    # Write script without icon
    with open(script_path, "w") as f:
        f.write(inno_script_no_icon)
    
    print("🔨 Building installer without icon...")
    result = subprocess.run([iscc_path, str(script_path)], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Installer created successfully (without icon)!")
        installer_file = installer_dir / f"ManimStudio-{APP_VERSION}-Setup.exe"
        
        if installer_file.exists():
            size_mb = installer_file.stat().st_size / (1024 * 1024)
            print(f"📦 Installer size: {size_mb:.1f} MB")
            print(f"📁 Location: {installer_file}")
            
        print(f"\n🎉 SUCCESS! Your installer is ready!")
        print(f"⚠️ Note: Installer created without icon due to icon file issues")
        return True
    else:
        print("❌ Installer creation failed even without icon!")
        print("STDERR:", result.stderr)
        return False

if __name__ == "__main__":
    create_fast_installer()