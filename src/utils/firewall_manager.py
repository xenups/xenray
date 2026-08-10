"""Windows Firewall automation for LAN proxy sharing.

Binding proxy inbounds to ``0.0.0.0`` is blocked by Windows Defender Firewall
for incoming traffic. This manager creates / checks / removes the dedicated
inbound allow rule (``XenRay Inbound LAN Proxy``) so LAN devices can reach the
SOCKS and HTTP proxy ports. Non-Windows platforms skip all automation.
"""

import subprocess
from typing import List

from loguru import logger

from src.core.constants import LAN_FIREWALL_RULE_NAME
from src.utils.platform_utils import PlatformUtils

FIREWALL_COMMAND_TIMEOUT = 10  # seconds


class FirewallManager:
    """Manage the Windows Defender Firewall inbound rule for LAN sharing."""

    RULE_NAME = LAN_FIREWALL_RULE_NAME

    @staticmethod
    def _run(cmd: List[str]) -> bool:
        """Run a firewall command and report success."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=FIREWALL_COMMAND_TIMEOUT,
                check=False,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[FirewallManager] Command failed: {e}")
            return False

    @staticmethod
    def check_lan_firewall_rule() -> bool:
        """Return True if the inbound rule already exists (Windows only)."""
        if PlatformUtils.get_platform() != "windows":
            return False
        try:
            result = subprocess.run(
                [
                    "netsh",
                    "advfirewall",
                    "firewall",
                    "show",
                    "rule",
                    f"name={FirewallManager.RULE_NAME}",
                ],
                capture_output=True,
                text=True,
                timeout=FIREWALL_COMMAND_TIMEOUT,
                check=False,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            if result.returncode != 0:
                return False
            return "No rules match the specified criteria" not in result.stdout
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[FirewallManager] Rule check failed: {e}")
            return False

    @staticmethod
    def add_lan_firewall_rule(ports: List[int]) -> bool:
        """Create the inbound allow rule for the given ports (elevated).

        Returns:
            True on success (or if the rule already exists), False on failure.
        """
        if PlatformUtils.get_platform() != "windows":
            logger.info("[FirewallManager] LAN firewall rule skipped (non-Windows)")
            return False

        if FirewallManager.check_lan_firewall_rule():
            logger.info("[FirewallManager] LAN firewall rule already exists, skipping creation")
            return True

        if not ports:
            logger.warning("[FirewallManager] No ports provided for LAN firewall rule")
            return False

        port_list = ",".join(str(p) for p in sorted(set(ports)))
        cmd = [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={FirewallManager.RULE_NAME}",
            "dir=in",
            "action=allow",
            "protocol=TCP",
            f"localport={port_list}",
        ]
        ok = FirewallManager._run(cmd)
        if ok:
            logger.info(f"[FirewallManager] LAN firewall rule created for ports {port_list}")
        else:
            logger.error("[FirewallManager] Failed to create LAN firewall rule (may require elevation)")
        return ok

    @staticmethod
    def remove_lan_firewall_rule() -> None:
        """Remove the inbound allow rule created by XenRay."""
        if PlatformUtils.get_platform() != "windows":
            return
        if not FirewallManager.check_lan_firewall_rule():
            return
        cmd = [
            "netsh",
            "advfirewall",
            "firewall",
            "delete",
            "rule",
            f"name={FirewallManager.RULE_NAME}",
        ]
        if FirewallManager._run(cmd):
            logger.info("[FirewallManager] LAN firewall rule removed")
        else:
            logger.warning("[FirewallManager] Failed to remove LAN firewall rule")
