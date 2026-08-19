"""Windows ITunDnsConfigurator — NRPT + netsh DNS on the TUN adapter.

All PowerShell / netsh commands for TUN DNS live here, behind the interface.
"""

from __future__ import annotations

import json
import subprocess
import time

from loguru import logger

from src.platform.constants import CMD_IPCONFIG, CMD_NETSH, CMD_POWERSHELL, DNS_FALLBACK_V4, TUN_ADAPTER_NAME
from src.platform.factory import get_process_adapter
from src.platform.interfaces import ITunDnsConfigurator

# TUN adapter appear wait (30 s total).
TUN_ADAPTER_WAIT_ITERATIONS = 60
TUN_ADAPTER_POLL_INTERVAL = 0.5


class WindowsTunDnsConfigurator(ITunDnsConfigurator):
    """NRPT + netsh DNS management on the TUN adapter (Windows)."""

    def configure_tun_dns(self, config_file_path: str, adapter_name: str = TUN_ADAPTER_NAME) -> bool:
        is_tun = False
        tun_dns = []
        try:
            with open(config_file_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for ib in cfg.get("inbounds", []):
                if ib.get("protocol") == "tun":
                    is_tun = True
                    tun_dns = ib.get("settings", {}).get("dns", [])
                    break
        except Exception as e:
            logger.warning(f"[WindowsTunDnsConfigurator] Failed to parse config: {e}")
            return False
        if not is_tun:
            return False

        if not self._wait_for_adapter(adapter_name):
            logger.error(f"[WindowsTunDnsConfigurator] '{adapter_name}' not created within 30 s")
            return False

        flags = self._flags()
        servers = list(tun_dns) if tun_dns else list(DNS_FALLBACK_V4)
        v4 = [s for s in servers if ":" not in s]
        v6 = [s for s in servers if ":" in s]

        primary_v4 = v4[0] if v4 else DNS_FALLBACK_V4[0]
        self._set_v4(adapter_name, primary_v4, v4, flags)
        self._set_v6(adapter_name, v6, flags)
        self._add_nrpt(primary_v4, flags)
        self._flush_dns(flags)
        return True

    def cleanup_tun_dns(self, adapter_name: str = TUN_ADAPTER_NAME) -> None:
        self._remove_nrpt()
        if not self._adapter_exists(adapter_name):
            return
        flags = self._flags()
        for proto in ("ip", "ipv6"):
            subprocess.run(
                [CMD_NETSH, "interface", proto, "delete", "dnsserver", adapter_name, "all"],
                capture_output=True,
                text=True,
                check=False,
                creationflags=flags,
                timeout=10,
            )

    # -- internals -----------------------------------------------------
    def _flags(self) -> int:
        return get_process_adapter().get_subprocess_flags()

    def _wait_for_adapter(self, name: str) -> bool:
        for _ in range(TUN_ADAPTER_WAIT_ITERATIONS):
            time.sleep(TUN_ADAPTER_POLL_INTERVAL)
            if self._adapter_exists(name):
                return True
        return False

    def _adapter_exists(self, name: str) -> bool:
        r = subprocess.run(
            [CMD_POWERSHELL, "-Command", f"Get-NetAdapter -Name '{name}'"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=self._flags(),
            timeout=10,
        )
        return r.returncode == 0

    def _set_v4(self, name, primary, v4, flags) -> None:
        r = subprocess.run(
            [CMD_NETSH, "interface", "ip", "set", "dns", f"name={name}", "static", primary],
            capture_output=True,
            text=True,
            check=False,
            creationflags=flags,
        )
        if r.returncode != 0:
            logger.warning(
                f"[WindowsTunDnsConfigurator] netsh set IPv4 DNS failed: {r.stdout.strip() or r.stderr.strip()}"
            )
            return
        secondary = [s for s in v4[1:] if s != primary]
        if not secondary:
            secondary = [DNS_FALLBACK_V4[1]]
        for idx, server in enumerate(secondary, start=2):
            subprocess.run(
                [CMD_NETSH, "interface", "ip", "add", "dns", f"name={name}", server, f"index={idx}"],
                capture_output=True,
                text=True,
                check=False,
                creationflags=flags,
            )

    def _set_v6(self, name, v6, flags) -> None:
        if not v6:
            return
        if not self._ipv6_enabled(flags):
            logger.info("[WindowsTunDnsConfigurator] IPv6 disabled — skipping v6 DNS")
            return
        primary = v6[0]
        r = subprocess.run(
            [CMD_NETSH, "interface", "ipv6", "set", "dns", f"name={name}", "static", primary],
            capture_output=True,
            text=True,
            check=False,
            creationflags=flags,
        )
        if r.returncode != 0:
            logger.warning(
                f"[WindowsTunDnsConfigurator] netsh set IPv6 DNS failed: {r.stdout.strip() or r.stderr.strip()}"
            )
            return
        for idx, server in enumerate(v6[1:], start=2):
            subprocess.run(
                [CMD_NETSH, "interface", "ipv6", "add", "dns", f"name={name}", server, f"index={idx}"],
                capture_output=True,
                text=True,
                check=False,
                creationflags=flags,
            )

    def _ipv6_enabled(self, flags) -> bool:
        try:
            r = subprocess.run(
                [CMD_NETSH, "interface", "ipv6", "show", "interfaces"],
                capture_output=True,
                text=True,
                check=False,
                creationflags=flags,
                timeout=5,
            )
            return r.returncode == 0
        except Exception:
            return False

    def _add_nrpt(self, primary_v4, flags) -> None:
        subprocess.run(
            [
                CMD_POWERSHELL,
                "-Command",
                f"Add-DnsClientNrptRule -Namespace '.' -NameServers '{primary_v4}' -Comment 'XenRay TUN DNS'",
            ],
            capture_output=True,
            text=True,
            check=False,
            creationflags=flags,
        )

    def _remove_nrpt(self) -> None:
        subprocess.run(
            [
                CMD_POWERSHELL,
                "-Command",
                "Get-DnsClientNrptRule | "
                "Where-Object { $_.Namespace -eq '.' -and $_.Comment -like '*XenRay*' } | "
                "Remove-DnsClientNrptRule -Force",
            ],
            check=False,
            creationflags=self._flags(),
            capture_output=True,
            timeout=10,
        )

    def _flush_dns(self, flags) -> None:
        subprocess.run([CMD_IPCONFIG, "/flushdns"], check=False, creationflags=flags, capture_output=True)


__all__ = ["WindowsTunDnsConfigurator"]
