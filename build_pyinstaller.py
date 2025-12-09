"""Build script for creating Windows executable with PyInstaller."""
import subprocess
import sys
import os
import shutil

# Ensure we're in the project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

def main():
    print("=" * 60)
    print("Building XenRay with PyInstaller...")
    print("=" * 60)
    
    # Check if icon exists and use absolute path
    icon_option = []
    icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.ico")
    if os.path.exists(icon_path):
        print(f"Using icon: {icon_path}")
        # Copy to root to be safe and avoid relative path issues
        shutil.copy(icon_path, "icon.ico")
        icon_option = ["--icon=icon.ico"]
    else:
        print(f"WARNING: Icon not found at {icon_path}")
    
    # Clean previous builds
    shutil.rmtree("build", ignore_errors=True)
    shutil.rmtree("dist", ignore_errors=True)
    
    # Build command - use python -m PyInstaller for cross-environment compatibility  
    cmd = [
        sys.executable,  # Use current Python interpreter
        "-m", "PyInstaller",  # Run PyInstaller as a module
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name=XenRay",
        
        # Flet imports
        "--hidden-import=flet",
        "--hidden-import=flet.flet",
        
        # Other necessary imports
        "--hidden-import=requests",
        "--hidden-import=loguru",
        "--hidden-import=pystray",
        "--hidden-import=PIL",
        "--hidden-import=pycountry",
        "--hidden-import=msgpack",
        "--hidden-import=zstandard",
        "--hidden-import=dotenv",
        
        # Main script
        "src/main.py",
        
        # Custom hooks
        f"--additional-hooks-dir={os.path.join(PROJECT_ROOT, 'hooks')}"
    ] + icon_option
    
    print("\nRunning PyInstaller...")
    print(f"Command: {' '.join(cmd[:5])}...") 
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("BUILD SUCCESSFUL!")
        print(f"Executable: dist/XenRay.exe")
        
        # Copy external resources
        print("Copying external resources...")
        
        # Copy assets folder
        assets_src = os.path.join(PROJECT_ROOT, "assets")
        assets_dst = os.path.join(PROJECT_ROOT, "dist", "assets")
        if os.path.exists(assets_src):
            shutil.copytree(assets_src, assets_dst, dirs_exist_ok=True)
            print("Copied assets to dist/")
        
        # Copy bin folder
        bin_src = os.path.join(PROJECT_ROOT, "bin")
        bin_dst = os.path.join(PROJECT_ROOT, "dist", "bin")
        if os.path.exists(bin_src):
            shutil.copytree(bin_src, bin_dst, dirs_exist_ok=True)
            print("Copied bin to dist/")
        
        print("=" * 60)
    else:
        print("\nBUILD FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    main()