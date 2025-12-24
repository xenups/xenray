"""Cross-platform build script for creating executables with PyInstaller."""
import subprocess
import sys
import os
import shutil
import platform

# Ensure we're in the project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)


def get_platform():
    """Detect the current platform."""
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system == "Darwin":
        return "macos"
    else:
        return "linux"


def get_icon_path():
    """Get platform-specific icon path."""
    current_platform = get_platform()

    if current_platform == "windows":
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.ico")
        if os.path.exists(icon_path):
            # Copy to root for PyInstaller
            shutil.copy(icon_path, "icon.ico")
            return ["--icon=icon.ico"]
        else:
            print(f"WARNING: Windows icon not found at {icon_path}")
            return []

    elif current_platform == "macos":
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.icns")
        if os.path.exists(icon_path):
            return [f"--icon={icon_path}"]
        else:
            print(f"WARNING: macOS icon not found at {icon_path}")
            print("You can create icon.icns from icon.ico using online converter or iconutil")
            return []

    return []


def get_executable_name():
    """Get platform-specific executable name."""
    current_platform = get_platform()

    if current_platform == "windows":
        return "XenRay.exe"
    else:
        return "XenRay"


def get_platform_specific_args():
    """Get platform-specific PyInstaller arguments."""
    current_platform = get_platform()
    args = []

    if current_platform == "macos":
        # macOS-specific options
        args.extend(
            [
                "--osx-bundle-identifier=com.xenray.vpn",
                # Uncomment below for code signing (requires Developer ID)
                # "--codesign-identity=Developer ID Application: Your Name (TEAM_ID)",
            ]
        )

    return args


def copy_resources_selective(src, dst, patterns_to_include=None):
    """Copy resources selectively to reduce memory usage during copy."""
    if not os.path.exists(src):
        return False

    if patterns_to_include is None:
        # Copy everything
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        # Selective copy
        os.makedirs(dst, exist_ok=True)
        for root, dirs, files in os.walk(src):
            # Calculate relative path
            rel_path = os.path.relpath(root, src)
            target_dir = os.path.join(dst, rel_path) if rel_path != "." else dst

            # Create target directory
            os.makedirs(target_dir, exist_ok=True)

            # Copy files matching patterns
            for file in files:
                if any(file.endswith(pattern) or pattern == "*" for pattern in patterns_to_include):
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    shutil.copy2(src_file, dst_file)

    return True


def main():
    current_platform = get_platform()

    print("=" * 60)
    print(f"Building XenRay for {current_platform.upper()} with PyInstaller...")
    print("=" * 60)

    # Get icon
    icon_option = get_icon_path()

    # Clean previous builds (reduces RAM by clearing old caches)
    print("\nCleaning previous builds...")
    shutil.rmtree("build", ignore_errors=True)
    shutil.rmtree("dist", ignore_errors=True)

    # Base command with optimizations
    cmd = [
        sys.executable,  # Use current Python interpreter
        "-m",
        "PyInstaller",  # Run PyInstaller as a module
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--clean",  # Clean PyInstaller cache before build (reduces RAM)
        "--name=XenRay",
        # Exclude large unused modules (reduces memory footprint)
        "--exclude-module=tkinter",
        "--exclude-module=_tkinter",
        "--exclude-module=tcl",
        "--exclude-module=tk",
        "--exclude-module=matplotlib",
        "--exclude-module=numpy",
        "--exclude-module=scipy",
        "--exclude-module=pandas",
        "--exclude-module=IPython",
        "--exclude-module=jupyter",
        "--exclude-module=notebook",
        "--exclude-module=pytest",
        "--exclude-module=unittest",
        "--exclude-module=test",
        # Core dependencies only (minimal set to reduce RAM)
        "--hidden-import=requests",
        "--hidden-import=loguru",
        "--hidden-import=pystray",
        "--hidden-import=PIL",
        "--hidden-import=psutil",
        # Dependency Injector essentials
        "--hidden-import=dependency_injector",
        "--hidden-import=dependency_injector.errors",
        "--hidden-import=dependency_injector.containers",
        "--hidden-import=dependency_injector.providers",
        "--hidden-import=dependency_injector.wiring",
        # Other core deps
        "--hidden-import=msgpack",
        "--hidden-import=zstandard",
        "--hidden-import=dotenv",
        "--hidden-import=cryptography",
        "--hidden-import=pycountry",
        # Main script
        "src/main.py",
        # Custom hooks (handles flet, DI string imports, etc.)
        # This hook will handle dynamic imports from DI container
        f"--additional-hooks-dir={os.path.join(PROJECT_ROOT, 'hooks')}",
        # Use --add-data for assets (more efficient than post-build copy)
        f"--add-data={'assets;assets' if current_platform == 'windows' else 'assets:assets'}",
    ]

    # Add icon
    cmd.extend(icon_option)

    # Add platform-specific args
    cmd.extend(get_platform_specific_args())

    print("\nRunning PyInstaller with optimized settings...")
    print(f"Command: {' '.join(cmd[:5])}...")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("BUILD SUCCESSFUL!")

        executable_name = get_executable_name()

        if current_platform == "macos":
            print(f"Application Bundle: dist/XenRay.app")  # noqa: F541
            print(f"Executable: dist/XenRay.app/Contents/MacOS/{executable_name}")

            # Copy external resources to macOS app bundle
            print("\nCopying external resources to app bundle...")

            bundle_resources = os.path.join(PROJECT_ROOT, "dist", "XenRay.app", "Contents", "MacOS")

            # Copy bin folder only (binaries)
            bin_src = os.path.join(PROJECT_ROOT, "bin")
            bin_dst = os.path.join(bundle_resources, "bin")
            if os.path.exists(bin_src):
                shutil.copytree(bin_src, bin_dst, dirs_exist_ok=True)
                print("Copied bin to app bundle")

                # Make binaries executable
                for root, dirs, files in os.walk(bin_dst):
                    for file in files:
                        file_path = os.path.join(root, file)
                        os.chmod(file_path, 0o755)
                print("Set executable permissions on binaries")

        else:
            print(f"Executable: dist/{executable_name}")

            # Copy external resources with selective patterns
            print("\nCopying external resources...")

            # Copy bin folder (Xray, Singbox binaries)
            bin_src = os.path.join(PROJECT_ROOT, "bin")
            bin_dst = os.path.join(PROJECT_ROOT, "dist", "bin")
            if os.path.exists(bin_src):
                # Copy only executable files to reduce memory
                copy_resources_selective(bin_src, bin_dst, ["*"])
                print("Copied bin to dist/")

            # Copy scripts folder (for updater) - selective copy
            scripts_src = os.path.join(PROJECT_ROOT, "scripts")
            scripts_dst = os.path.join(PROJECT_ROOT, "dist", "scripts")
            if os.path.exists(scripts_src):
                # Only copy .ps1 and .sh files
                copy_resources_selective(scripts_src, scripts_dst, [".ps1", ".sh", ".bat"])
                print("Copied scripts to dist/")

        print("=" * 60)

        if current_platform == "macos":
            print("\nmacOS Next Steps:")
            print("1. Test the app: open dist/XenRay.app")
            print("2. For distribution, sign the app:")
            print("   codesign --deep --force --sign 'Developer ID Application' dist/XenRay.app")
            print("3. Create DMG: run scripts/create_dmg.sh")

    else:
        print("\nBUILD FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    main()
