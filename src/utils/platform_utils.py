"""Platform detection and abstraction utilities.

Pure system-metadata container: only ``os``/``platform``/``sys`` introspection
and enum classification.  All OS side-effect methods (subprocess flags,
DNS/network discovery, registry/SMHR, TUN naming, privileged-helper checks)
live in the platform adapters under ``src/platform/`` — use the factory:
``get_process_adapter()``, ``get_network_adapter()``,
``get_system_settings_adapter()``.
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Tuple

# Type-safe platform enums (formerly plain Literals). str-based, so legacy
# string comparisons remain valid while new code can use enum members.
from src.platform.enums import ArchType, PlatformType  # noqa: E402

__all__ = ["PlatformUtils", "PlatformType", "ArchType"]


class PlatformUtils:
    """Pure OS-metadata utilities: platform/arch/sys introspection only."""

    @staticmethod
    def get_platform() -> PlatformType:
        """
        Detect the current operating system.

        Returns:
            A ``PlatformType`` enum member ('windows', 'macos', or 'linux').
        """
        system = platform.system()
        if system == "Windows" or os.name == "nt":
            return PlatformType.WINDOWS
        elif system == "Darwin":
            return PlatformType.MACOS
        else:
            return PlatformType.LINUX

    @staticmethod
    def is_windows() -> bool:
        """True if running on Windows."""
        return PlatformUtils.get_platform() == PlatformType.WINDOWS

    @staticmethod
    def is_macos() -> bool:
        """True if running on macOS."""
        return PlatformUtils.get_platform() == PlatformType.MACOS

    @staticmethod
    def is_linux() -> bool:
        """True if running on Linux."""
        return PlatformUtils.get_platform() == PlatformType.LINUX

    @staticmethod
    def get_architecture() -> ArchType:
        """
        Detect the CPU architecture.

        Returns:
            An ``ArchType`` enum member.
        """
        machine = platform.machine().lower()

        # Normalize common architecture names
        if machine in ("amd64", "x86_64", "x64"):
            return ArchType.X86_64
        elif machine in ("arm64", "aarch64", "arm64-v8a"):
            return ArchType.ARM64
        elif machine in ("i386", "i686", "x86"):
            return ArchType.X86
        return ArchType.UNKNOWN

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
    def get_tun_interface_name() -> str:
        """
        Get the default TUN interface name for the platform.

        Pure platform metadata (no OS side effect).

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
    def get_temp_dir() -> str:
        """Get platform-appropriate temporary cache directory for XenRay."""
        import tempfile

        if PlatformUtils.is_windows():
            return os.path.join(tempfile.gettempdir(), "xenray")
        elif PlatformUtils.is_macos():
            return os.path.join(os.path.expanduser("~/Library/Caches"), "xenray")
        else:
            return os.environ.get("TMPDIR", "/tmp/xenray")

    @staticmethod
    def supports_privileged_helper() -> bool:
        """
        Check if the platform supports privileged helper tools.

        Pure platform metadata (no OS side effect).

        Returns:
            True for macOS (SMJobBless), False otherwise
        """
        return PlatformUtils.get_platform() == "macos"
