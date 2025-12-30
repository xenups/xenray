"""Platform detection and abstraction utilities."""
import os
import platform
import sys
from enum import Enum
from typing import Tuple


class Platform(Enum):
    """Operating system platforms."""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class Architecture(Enum):
    """CPU architectures."""
    X86_64 = "x86_64"
    ARM64 = "arm64"
    X86 = "x86"
    UNKNOWN = "unknown"


class PlatformUtils:
    """Utility class for platform detection and abstraction."""

    @staticmethod
    def get_platform() -> Platform:
        """
        Detect the current operating system.

        Returns:
            Platform enum value: Platform.WINDOWS, Platform.MACOS, or Platform.LINUX
        """
        system = platform.system()
        if system == "Windows" or os.name == "nt":
            return Platform.WINDOWS
        elif system == "Darwin":
            return Platform.MACOS
        else:
            return Platform.LINUX

    @staticmethod
    def get_architecture() -> Architecture:
        """
        Detect the CPU architecture.

        Returns:
            Architecture enum value
        """
        machine = platform.machine().lower()

        # Normalize common architecture names
        if machine in ("amd64", "x86_64", "x64"):
            return Architecture.X86_64
        elif machine in ("arm64", "aarch64", "arm64-v8a"):
            return Architecture.ARM64
        elif machine in ("i386", "i686", "x86"):
            return Architecture.X86
        else:
            return Architecture.UNKNOWN

    @staticmethod
    def get_platform_arch() -> Tuple[Platform, Architecture]:
        """
        Get both platform and architecture.

        Returns:
            Tuple of (Platform, Architecture) enums
        """
        return PlatformUtils.get_platform(), PlatformUtils.get_architecture()

    @staticmethod
    def get_binary_suffix() -> str:
        """
        Get the executable file suffix for current platform.

        Returns:
            '.exe' for Windows, empty string for Unix-like systems
        """
        return ".exe" if PlatformUtils.get_platform() == Platform.WINDOWS else ""

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

        # Map platform enum values to directory conventions
        platform_map = {
            Platform.WINDOWS: "windows",
            Platform.MACOS: "darwin",
            Platform.LINUX: "linux"
        }

        platform_dir = platform_map.get(plat, plat.value)
        return os.path.join(base_dir, f"{platform_dir}-{arch.value}")

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

        if PlatformUtils.get_platform() == Platform.WINDOWS:
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

        if PlatformUtils.get_platform() == Platform.WINDOWS:
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
        if plat == Platform.WINDOWS:
            return "SINGTUN"
        elif plat == Platform.MACOS:
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
        return PlatformUtils.get_platform() == Platform.MACOS
