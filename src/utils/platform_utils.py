"""Platform detection and abstraction utilities."""

import os
import platform
import sys
from typing import Literal, Optional, Tuple

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
    def get_system_dns_servers() -> list:
        """Return the system's DNS servers (IPv4) — used for DIRECT-routed domains.

        On Windows, reads the active adapter's DNS via ``Get-DnsClientServerAddress``
        (or ``ipconfig`` fallback). These are LOCAL resolvers (router/gateway) —
        the right choice for direct domains on networks where foreign DNS
        (8.8.8.8 / 1.1.1.1) is blocked or tampered with (e.g. Iran).
        """
        import subprocess

        plat = PlatformUtils.get_platform()
        servers: list = []
        try:
            if plat == "windows":
                try:
                    out = subprocess.run(
                        [
                            "powershell",
                            "-NoProfile",
                            "-Command",
                            "Get-DnsClientServerAddress -AddressFamily IPv4 | "
                            "Where-Object {$_.ServerAddresses.Count -gt 0} | "
                            "ForEach-Object {$_.ServerAddresses} | Select-Object -Unique",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    for line in (out.stdout or "").splitlines():
                        line = line.strip()
                        # Skip the TUN adapter's own DNS (10.0.0.x) if present —
                        # that loops back into sing-box.
                        if line and not line.startswith("10.0.0."):
                            servers.append(line)
                except Exception:
                    pass
                # Fallback: ipconfig
                if not servers:
                    out = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, timeout=5)
                    lines = (out.stdout or "").splitlines()
                    for i, line in enumerate(lines):
                        if "DNS Servers" in line and i + 1 < len(lines):
                            nxt = lines[i + 1].strip()
                            if nxt and nxt[0].isdigit():
                                servers.append(nxt.split()[0])
            elif plat == "linux":
                with open("/etc/resolv.conf") as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2 and parts[0] == "nameserver":
                            servers.append(parts[1])
            elif plat == "macos":
                out = subprocess.run(["scutil", "--dns"], capture_output=True, text=True, timeout=5)
                for line in (out.stdout or "").splitlines():
                    line = line.strip()
                    if "nameserver" in line and "[" not in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            servers.append(parts[-1])
        except Exception:
            pass
        return servers

    @staticmethod
    def supports_privileged_helper() -> bool:
        """
        Check if the platform supports privileged helper tools.

        Returns:
            True for macOS (SMJobBless), False otherwise
        """
        return PlatformUtils.get_platform() == "macos"

    # ------------------------------------------------------------------
    # Windows SMHR (Smart Multi-Homed Name Resolution) helpers
    #
    # SMHR causes Windows to send DNS queries to ALL adapters in parallel
    # and use the first reply — bypassing the TUN adapter's DNS servers
    # and leaking queries to the physical interface while a VPN is active.
    # Disabling it for the duration of a TUN session prevents DNS leaks.
    #
    # Consolidated here from the duplicate implementations that previously
    # existed in both XrayService and SingboxService.
    # ------------------------------------------------------------------

    @staticmethod
    def read_smhr_state() -> "Optional[bool]":
        """Read the current SMHR enabled state from the Windows registry.

        Returns:
            True  — SMHR is enabled (OS default)
            False — SMHR is disabled
            None  — state could not be read (non-Windows or registry error)
        """
        try:
            import winreg  # Windows-only

            key_path = r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, "DisableSmartNameResolution")
                    return value == 0  # 0 = SMHR on, 1 = SMHR off
                except FileNotFoundError:
                    return True  # Key absent → SMHR is enabled (OS default)
        except Exception:
            return None

    @staticmethod
    def set_smhr_state(enabled: bool) -> None:
        """Enable or disable SMHR via the Windows registry.

        Args:
            enabled: True to enable SMHR (OS default), False to disable.
        """
        try:
            import winreg  # Windows-only

            key_path = r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, access=winreg.KEY_SET_VALUE) as key:
                # DisableSmartNameResolution: 0 = on, 1 = off
                winreg.SetValueEx(
                    key,
                    "DisableSmartNameResolution",
                    0,
                    winreg.REG_DWORD,
                    0 if enabled else 1,
                )
                # Also toggle the parallel A+AAAA sub-feature
                winreg.SetValueEx(
                    key,
                    "DisableParallelAandAAAA",
                    0,
                    winreg.REG_DWORD,
                    0 if enabled else 1,
                )
        except Exception as exc:
            from src.core.logger import logger  # lazy to avoid circular import at module level

            logger.warning(f"[PlatformUtils] Could not set SMHR registry value: {exc}")

    @staticmethod
    def suppress_smhr() -> "Optional[bool]":
        """Disable SMHR for a TUN session and return the previous state.

        Only takes effect on Windows; returns None immediately on other platforms.

        Returns:
            The SMHR state *before* suppression (True = was enabled, False = was
            already disabled, None = not Windows / registry error).  Pass this
            value to :meth:`restore_smhr` on teardown.
        """
        if PlatformUtils.get_platform() != "windows":
            return None

        from src.core.logger import logger  # lazy to avoid circular import

        previous = PlatformUtils.read_smhr_state()
        if previous is True:
            logger.info("[PlatformUtils] Disabling SMHR to prevent DNS leaks during TUN session")
            PlatformUtils.set_smhr_state(enabled=False)
        return previous

    @staticmethod
    def restore_smhr(previous_state: "Optional[bool]") -> None:
        """Restore SMHR to its pre-TUN state.

        Args:
            previous_state: The value returned by :meth:`suppress_smhr`.
                If True, SMHR is re-enabled.  Any other value is a no-op.
        """
        if PlatformUtils.get_platform() != "windows":
            return
        if previous_state is True:
            from src.core.logger import logger  # lazy to avoid circular import

            logger.info("[PlatformUtils] Restoring SMHR to enabled state")
            PlatformUtils.set_smhr_state(enabled=True)
