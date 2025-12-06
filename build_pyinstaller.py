"""Build script for creating Windows executable with PyInstaller."""
import subprocess
import sys
import os
import shutil

# Ensure we're in the project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

# Path to PyInstaller in the poetry venv
# Using absolute path from previous step output: 
# C:\Users\Xenups\AppData\Local\pypoetry\Cache\virtualenvs\xenray-7N7VD6iT-py3.13\Scripts\pyinstaller.exe
PYINSTALLER_PATH = r"C:\Users\Xenups\AppData\Local\pypoetry\Cache\virtualenvs\xenray-7N7VD6iT-py3.13\Scripts\pyinstaller.exe"

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
    
    # Build command
    cmd = [
        PYINSTALLER_PATH,
        "--noconfirm",
        "--onefile",
        "--windowed",  # No console window
        "--name=XenRay",
        "--clean",
        
        # Hidden imports (حذف flet_desktop/flet_runtime و واگذاری به Hook)
        # فقط flet را نگه می‌داریم و بقیه را به Hook می‌سپاریم
        "--hidden-import=flet",
        # خطوط زیر حذف شدند چون در Hook مدیریت می‌شوند:
        # "--hidden-import=flet_desktop",
        # "--hidden-import=flet.desktop",
        # "--hidden-import=flet_runtime",
        
        # Other necessary imports
        "--hidden-import=requests",
        "--hidden-import=loguru",
        "--hidden-import=pystray",
        "--hidden-import=PIL",
        
        # Main script
        "src/main.py",
        
        # Custom hooks: مسیر مطلق
        f"--additional-hooks-dir={os.path.join(PROJECT_ROOT, 'hooks')}"
    ] + icon_option
    
    print("\nRunning PyInstaller...")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("BUILD SUCCESSFUL!")
        print("Executable: dist/XenRay.exe")
        
        # Post-build: Copy bin and assets folders to dist
        print("Copying external resources...")
        dist_dir = os.path.join(PROJECT_ROOT, "dist")
        
        for folder in ["assets", "bin"]:
            src = os.path.join(PROJECT_ROOT, folder)
            dst = os.path.join(dist_dir, folder)
            if os.path.exists(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                print(f"Copied {folder} to dist/")
            else:
                print(f"Warning: {folder} not found in source!")

        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("BUILD FAILED! Check PyInstaller output for details.")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()