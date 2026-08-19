"""Windows IFirewallAdapter — netsh advfirewall rule management.

All ``netsh advfirewall`` commands live here, behind the interface. Non-Windows
return False / no-op.
"""

from __future__ import annotations

import subprocess
from typing import List, Optional

from loguru import logger

from src.platform.constants import CMD_NETSH
from src.platform.factory import _is_windows, get_process_adapter
from src.platform.interfaces import IFirewallAdapter

FIREWALL_COMMAND_TIMEOUT = 10  # seconds

# Windows Defender Firewall command literals.
_FW_SHOW_RULE = "show"
_FW_ADD_RULE = "add"
_FW_DELETE_RULE = "delete"
_FW_NO_MATCH = "No rules match the specified criteria"
_NETSH_FIREWALL_SECTION = ["advfirewall", "firewall"]


class WindowsFirewallAdapter(IFirewallAdapter):
    """Inbound allow rule management for LAN proxy sharing (Windows)."""

    def __init__(self, rule_name: str = "XenRay Inbound LAN Proxy") -> None:
        self._rule_name = rule_name

    def add_rule(self, name: str, port: int, interface: Optional[str] = None) -> bool:
        return self.add_lan_firewall_rule([port])

    def remove_rule(self, name: str) -> bool:
        self.remove_lan_firewall_rule()
        return True

    # -- FirewallManager-compatible surface ----------------------------
    def check_lan_firewall_rule(self) -> bool:
        if not _is_windows():
            return False
        r = self._run([CMD_NETSH, *_NETSH_FIREWALL_SECTION, _FW_SHOW_RULE, "rule", f"name={self._rule_name}"])
        if not r:
            return False
        return _FW_NO_MATCH not in r

    def add_lan_firewall_rule(self, ports: List[int]) -> bool:
        if not _is_windows():
            logger.info("[WindowsFirewallAdapter] LAN firewall rule skipped (non-Windows)")
            return False
        if self.check_lan_firewall_rule():
            logger.info("[WindowsFirewallAdapter] LAN firewall rule already exists, skipping creation")
            return True
        if not ports:
            logger.warning("[WindowsFirewallAdapter] No ports provided for LAN firewall rule")
            return False
        port_list = ",".join(str(p) for p in sorted(set(ports)))
        outcome = self._run(
            [
                CMD_NETSH,
                *_NETSH_FIREWALL_SECTION,
                _FW_ADD_RULE,
                "rule",
                f"name={self._rule_name}",
                "dir=in",
                "action=allow",
                "protocol=TCP",
                f"localport={port_list}",
            ]
        )
        ok = outcome is not None
        if ok:
            logger.info(f"[WindowsFirewallAdapter] LAN firewall rule created for ports {port_list}")
        else:
            logger.error("[WindowsFirewallAdapter] Failed to create LAN firewall rule (may require elevation)")
        return ok

    def remove_lan_firewall_rule(self) -> None:
        if not _is_windows():
            return
        if not self.check_lan_firewall_rule():
            return
        ok = self._run(
            [
                CMD_NETSH,
                *_NETSH_FIREWALL_SECTION,
                _FW_DELETE_RULE,
                "rule",
                f"name={self._rule_name}",
            ]
        )
        if ok:
            logger.info("[WindowsFirewallAdapter] LAN firewall rule removed")
        else:
            logger.warning("[WindowsFirewallAdapter] Failed to remove LAN firewall rule")

    # -- internals -----------------------------------------------------
    def _run(self, cmd: List[str]) -> Optional[str]:
        """Run a netsh command; return stdout on success, None on failure."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=FIREWALL_COMMAND_TIMEOUT,
                check=False,
                creationflags=get_process_adapter().get_subprocess_flags(),
                startupinfo=get_process_adapter().get_startupinfo(),
            )
            if result.returncode == 0:
                return result.stdout or ""
            return None
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[WindowsFirewallAdapter] Command failed: {e}")
            return None


__all__ = ["WindowsFirewallAdapter"]
