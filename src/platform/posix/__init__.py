"""No-op / minimal implementations for non-Windows platforms (Linux, macOS).

Kept as explicit, honest stubs so a dev on Linux/macOS can import and run the
abstraction without Windows-only ctypes/iphlpapi code, and nothing crashes when
a service reaches for a platform adapter. All return empty/None (deterministic
unavailable) — never fabricated values.
"""

from __future__ import annotations

from typing import Any, Optional

from src.platform.interfaces import (
    IFirewallAdapter,
    INetworkAdapter,
    IProcessAdapter,
    ISystemSettingsAdapter,
    ITunDnsConfigurator,
)


class NoopFirewallAdapter(IFirewallAdapter):
    """Non-Windows: no netsh firewall — unsupported, returns False / None."""

    def add_rule(self, name: str, port: int, interface=None) -> bool:
        return False

    def remove_rule(self, name: str) -> bool:
        return False

    def check_lan_firewall_rule(self) -> bool:
        return False

    def add_lan_firewall_rule(self, ports: list[int]) -> bool:
        return False

    def remove_lan_firewall_rule(self) -> None:
        return None


NoOpFirewallAdapter = NoopFirewallAdapter


class NoopTunDnsConfigurator(ITunDnsConfigurator):
    """Non-Windows: no NRPT/netsh — unsupported, no-op."""

    def configure_tun_dns(self, config_file_path: str, adapter_name: str) -> bool:
        return False

    def cleanup_tun_dns(self, adapter_name: str) -> None:
        return None


class NoopSystemSettingsAdapter(ISystemSettingsAdapter):
    """Non-Windows: SMHR and Registry autostart not applicable."""

    def read_smhr_state(self) -> Optional[bool]:
        return None

    def set_smhr_state(self, enabled: bool) -> None:
        return None

    def suppress_smhr(self) -> Optional[bool]:
        return None

    def restore_smhr(self, previous: Optional[bool]) -> None:
        return None

    def is_autostart_enabled(self, app_name: str = "XenRay") -> bool:
        return False

    def enable_autostart(self, app_name: str, launch_command: str) -> tuple[bool, str]:
        return False, "Unsupported on non-Windows"

    def disable_autostart(self, app_name: str = "XenRay") -> tuple[bool, str]:
        return False, "Unsupported on non-Windows"


class PosixProcessAdapter(IProcessAdapter):
    """POSIX: process flags and elevation."""

    def get_subprocess_flags(self) -> int:
        return 0

    def get_startupinfo(self) -> Optional[Any]:
        return None

    def is_elevated(self) -> bool:
        import os

        return os.geteuid() == 0 if hasattr(os, "geteuid") else False

    def request_elevation(self, executable: Optional[str] = None, params: Optional[str] = None) -> bool:
        return False

    def supports_interactive_elevation(self) -> bool:
        return False

    def get_elevation_hint(self) -> str:
        import sys

        return f"💡 Please run with sudo:\n   sudo {' '.join(sys.argv)}"

    def initialize_environment(self) -> None:
        pass

    def restart_as_admin(self) -> None:
        """Restart with admin privileges on POSIX (macOS via osascript, Linux noop)."""
        import subprocess
        import sys

        from loguru import logger

        if sys.platform == "darwin":
            try:
                if getattr(sys, "frozen", False):
                    executable = sys.executable
                    if ".app/Contents/MacOS" in executable:
                        app_path = executable.split(".app/Contents/MacOS")[0] + ".app"
                        script = f'do shell script "open -a \\"{app_path}\\"" with administrator privileges'
                    else:
                        script = f'do shell script "\\"{executable}\\"" with administrator privileges'
                else:
                    executable = sys.executable
                    script_path = sys.argv[0]
                    script = f'do shell script "\\"{executable}\\" \\"{script_path}\\"" with administrator privileges'

                logger.info("[PosixProcessAdapter] Requesting admin privileges via osascript...")
                result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info("Successfully launched new instance with admin privileges")
                    sys.exit(0)
                else:
                    logger.error(f"osascript failed: {result.stderr}")
            except Exception as e:
                logger.error(f"Failed to restart as admin on macOS: {e}")
        else:
            logger.warning("[PosixProcessAdapter] restart_as_admin is not supported on Linux")

    def acquire_singleton_mutex(self, name: str = "XenRay_Singleton_Mutex_v1") -> bool:
        """POSIX single-instance lock via pidfile."""
        import errno
        import os

        try:
            import fcntl

            pid_file = os.path.expanduser("~/.xenray.pid")
            self._pid_file_handle = open(pid_file, "w")
            fcntl.flock(self._pid_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._pid_file_handle.write(str(os.getpid()))
            return True
        except (IOError, OSError) as e:
            if hasattr(e, "errno") and e.errno in (errno.EAGAIN, errno.EACCES):
                return False
            return True
        except Exception:
            return True


class PosixNetworkAdapter(INetworkAdapter):
    """POSIX: psutil-based discovery (no IP Helper on Linux/macOS)."""

    def get_physical_nic_candidates(self) -> list[dict]:
        return []

    def get_physical_lan_ip(self) -> Optional[str]:
        return None

    def get_system_dns_servers(self) -> list[str]:
        return []

    def get_primary_interface(self) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        return (None, None, None, None)

    def ping_mtu(self, host: str, payload_size: int, timeout: int) -> bool:
        """Ping host with Don't Fragment (DF) flag on POSIX (macOS/Linux)."""
        import subprocess
        import sys

        try:
            if sys.platform == "darwin":
                # macOS: -D is Don't Fragment, -W timeout in ms
                cmd = [
                    "ping",
                    "-c",
                    "1",
                    "-W",
                    str(timeout * 1000),
                    "-D",
                    "-s",
                    str(payload_size),
                    host,
                ]
            else:
                # Linux: -M do is Don't Fragment, -W timeout in s
                cmd = [
                    "ping",
                    "-c",
                    "1",
                    "-W",
                    str(timeout),
                    "-M",
                    "do",
                    "-s",
                    str(payload_size),
                    host,
                ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 1,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False
