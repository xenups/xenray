"""Platform detection and abstraction utilities."""
import os
import platform
import sys
from typing import Literal, Tuple

PlatformType = Literal["windows", "macos", "linux"]
ArchType = Literal["x86_64", "arm64", "x86", "unknown"]


class PlatformUtils:
    """Utility class for platform detection and abstraction."""

    @staticmethod
    def get_platform() -> PlatformType:
        """
        Detect the current operating system.

        Returns:
            Platform identifier: 'windows', 'macos', or 'linux'
        """
        system = platform.system()
        if system == "Windows" or os.name == "nt":
            return "windows"
        elif system == "Darwin":
            return "macos"
        else:
            return "linux"

    @staticmethod
    def get_architecture() -> ArchType:
        """
        Detect the CPU architecture.

        Returns:
            Architecture identifier: 'x86_64', 'arm64', 'x86', or 'unknown'
        """
        machine = platform.machine().lower()

        # Normalize common architecture names
        if machine in ("amd64", "x86_64", "x64"):
            return "x86_64"
        elif machine in ("arm64", "aarch64", "arm64-v8a"):
            return "arm64"
        elif machine in ("i386", "i686", "x86"):
            return "x86"
        else:
            return "unknown"

    @staticmethod
    def get_platform_arch() -> Tuple[PlatformType, ArchType]:
        """
        Get both platform and architecture.

        Returns:
            Tuple of (platform, architecture)
        """
        return PlatformUtils.get_platform(), PlatformUtils.get_architecture()

    @staticmethod
    def get_binary_suffix() -> str:
        """
        Get the executable file suffix for current platform.

        Returns:
            '.exe' for Windows, empty string for Unix-like systems
        """
        return ".exe" if PlatformUtils.get_platform() == "windows" else ""

    @staticmethod
    def get_platform_bin_dir(base_dir: str) -> str:
        """
        Get platform-specific binary directory.

        Args:
            base_dir: Base directory containing platform subdirectories

        Returns:
            Path to platform-specific binary directory
            (e.g., 'bin/darwin-arm64', 'bin/windows-x86_64')
        """
        plat, arch = PlatformUtils.get_platform_arch()

        # Map platform names to directory conventions
        platform_map = {"windows": "windows", "macos": "darwin", "linux": "linux"}

        platform_dir = platform_map.get(plat, plat)
        return os.path.join(base_dir, f"{platform_dir}-{arch}")

    @staticmethod
    def is_frozen() -> bool:
        """
        Check if running as a compiled executable (PyInstaller, etc.).

        Returns:
            True if frozen, False if running as script
        """
        return getattr(sys, "frozen", False)

    @staticmethod
    def get_app_dir() -> str:
        """
        Get the application directory for BUNDLED resources (like assets).

        Returns:
            - When frozen (PyInstaller): _MEIPASS (temporary extraction directory for bundled files)
            - When running as script: Project root directory
        """
        if PlatformUtils.is_frozen():
            # Return _MEIPASS for bundled assets (from --add-data)
            if hasattr(sys, "_MEIPASS"):
                return sys._MEIPASS
            # Fallback to the directory of the executable
            return os.path.dirname(sys.executable)
        else:
            # If running as script, go up from src/utils to project root
            current_file = os.path.abspath(__file__)
            return os.path.dirname(os.path.dirname(os.path.dirname(current_file)))

    @staticmethod
    def get_executable_dir() -> str:
        """
        Get the directory containing the executable for EXTERNAL resources (like bin/, scripts/).

        Returns:
            - When frozen (PyInstaller): Directory containing the .exe file
            - When running as script: Same as get_app_dir()
        """
        if PlatformUtils.is_frozen():
            # Return the directory containing the executable (for external resources)
            return os.path.dirname(sys.executable)
        else:
            # If running as script, same as app dir
            return PlatformUtils.get_app_dir()

    @staticmethod
    def get_subprocess_flags() -> int:
        """
        Get platform-specific subprocess creation flags.

        Returns:
            CREATE_NO_WINDOW flag on Windows, 0 on other platforms
        """
        import subprocess

        if PlatformUtils.get_platform() == "windows":
            # CREATE_NO_WINDOW only exists on Windows
            return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        return 0

    @staticmethod
    def get_startupinfo():
        """
        Get STARTUPINFO object for hiding subprocess windows on Windows.

        Returns:
            STARTUPINFO object with STARTF_USESHOWWINDOW on Windows, None otherwise
        """
        import subprocess

        if PlatformUtils.get_platform() == "windows":
            # STARTUPINFO and related constants only exist on Windows
            STARTUPINFO = getattr(subprocess, "STARTUPINFO", None)
            if STARTUPINFO:
                startupinfo = STARTUPINFO()
                startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
                startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
                return startupinfo
        return None

    @staticmethod
    def get_tun_interface_name() -> str:
        """
        Get the default TUN interface name for the platform.

        Returns:
            'SINGTUN' for Windows, 'utun9' for macOS, 'tun0' for Linux
        """
        plat = PlatformUtils.get_platform()
        if plat == "windows":
            return "SINGTUN"
        elif plat == "macos":
            return "utun9"
        else:
            return "tun0"

    @staticmethod
    def supports_privileged_helper() -> bool:
        """
        Check if the platform supports privileged helper tools.

        Returns:
            True for macOS (SMJobBless), False otherwise
        """
        return PlatformUtils.get_platform() == "macos"
