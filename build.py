"""Build script for creating Windows executable with Nuitka."""
import subprocess
import sys
import os

# Ensure we're in the project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

# Nuitka build command
NUITKA_CMD = [
    sys.executable, "-m", "nuitka",
    
    # Basic options
    "--standalone",
    "--onefile",
    "--windows-console-mode=disable",  # No console window
    
    # Output
    "--output-dir=dist",
    "--output-filename=XenRay.exe",
    
    # Include data files
    "--include-data-dir=assets=assets",
    "--include-data-dir=bin=bin",
    
    # Python optimization
    "--python-flag=no_site",
    "--python-flag=no_warnings",
    
    # Windows specific
    "--windows-icon-from-ico=assets/icon.ico",
    "--windows-company-name=Xenups",
    "--windows-product-name=XenRay",
    "--windows-file-version=1.0.0.0",
    "--windows-product-version=1.0.0.0",
    "--windows-file-description=XenRay VPN Client",
    
    # Include packages
    "--include-package=flet",
    "--include-package=flet_core",
    "--include-package=flet_runtime",
    "--include-package=loguru",
    "--include-package=requests",
    
    # Entry point
    "src/main.py",
]

def main():
    print("=" * 60)
    print("Building XenRay with Nuitka...")
    print("=" * 60)
    
    # Check if Nuitka is installed
    try:
        subprocess.run([sys.executable, "-m", "nuitka", "--version"], 
                      check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("ERROR: Nuitka not installed!")
        print("Install with: pip install nuitka")
        sys.exit(1)
    
    # Create dist directory
    os.makedirs("dist", exist_ok=True)
    
    # Run Nuitka
    print("\nRunning Nuitka (this may take several minutes)...\n")
    result = subprocess.run(NUITKA_CMD, cwd=PROJECT_ROOT)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("BUILD SUCCESSFUL!")
        print("Executable: dist/XenRay.exe")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("BUILD FAILED!")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
