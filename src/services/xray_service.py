"""Xray service for managing Xray process."""

import os
import subprocess
import time
from typing import Optional

from src.core.constants import (
    DNS_IP_CLOUDFLARE,
    DNS_IP_GOOGLE,
    XRAY_EXECUTABLE,
    XRAY_LOCATION_ASSET,
    XRAY_LOG_FILE,
    XRAY_PID_FILE,
)
from src.core.logger import logger
from src.utils.process_utils import ProcessUtils

# Constants
PROCESS_START_DELAY = 0.2  # seconds - delay to ensure previous instance is terminated
STOP_CHECK_RETRIES = 3
STOP_CHECK_DELAY = 0.1  # seconds


class XrayService:
    """Service for managing Xray process."""

    def __init__(self):
        """Initialize Xray service."""
        self._process = None
        self._pid: Optional[int] = None
        self._check_and_restore_pid()

    def _check_and_restore_pid(self):
        """Restore PID from file if it's still running (CLI state adoption)."""
        if os.path.exists(XRAY_PID_FILE):
            try:
                with open(XRAY_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    logger.debug(f"[XrayService] Restored PID {self._pid} from file")
            except Exception:
                pass

    def _remove_nrpt_rules(self):
        """Remove any XenRay NRPT DNS rules to restore system DNS."""
        from src.utils.platform_utils import PlatformUtils

        if PlatformUtils.get_platform() == "windows":
            logger.info("[XrayService] Removing XenRay NRPT DNS rules...")
            creation_flags = PlatformUtils.get_subprocess_flags()
            cmd_remove = [
                "powershell",
                "-Command",
                "Get-DnsClientNrptRule | "
                "Where-Object { $_.Namespace -eq '.' -and $_.Comment -like '*XenRay*' } | "
                "Remove-DnsClientNrptRule -Force",
            ]
            subprocess.run(cmd_remove, check=False, creationflags=creation_flags)

    def _cleanup_previous_instance(self):
        """Check for and kill any previous instance using PID file."""
        if os.path.exists(XRAY_PID_FILE):
            try:
                with open(XRAY_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())

                if ProcessUtils.is_running(old_pid):
                    logger.info(f"[XrayService] Found orphan process {old_pid}, killing...")
                    ProcessUtils.kill_process(old_pid, force=True)

                os.remove(XRAY_PID_FILE)
            except Exception as e:
                logger.warning(f"[XrayService] Failed to cleanup old PID file: {e}")

        # Always remove NRPT rules to clean up system state
        self._remove_nrpt_rules()

    def _configure_windows_tun_dns(self, config_file_path: str):
        """Configure DNS and NRPT settings for the virtual TUN adapter on Windows."""
        from src.utils.platform_utils import PlatformUtils

        if PlatformUtils.get_platform() != "windows":
            return

        is_tun = False
        tun_dns = []
        try:
            import json

            with open(config_file_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            inbounds = cfg.get("inbounds", [])
            for ib in inbounds:
                if ib.get("protocol") == "tun":
                    is_tun = True
                    tun_dns = ib.get("settings", {}).get("dns", [])
                    break
        except Exception as e:
            logger.warning(f"[XrayService] Failed to parse config to check for TUN mode: {e}")
            return

        if not is_tun:
            return

        # Wait for xenray-tun adapter to be created
        logger.info("[XrayService] TUN mode detected. Waiting for 'xenray-tun' interface...")
        tun_created = False
        creation_flags = PlatformUtils.get_subprocess_flags()
        for _ in range(10):  # Wait up to 5 seconds
            time.sleep(0.5)
            check_res = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Get-NetAdapter -Name 'xenray-tun'",
                ],
                capture_output=True,
                text=True,
                check=False,
                creationflags=creation_flags,
            )
            if check_res.returncode == 0:
                tun_created = True
                break

        if not tun_created:
            logger.error("[XrayService] 'xenray-tun' interface was not created in time. DNS override skipped.")
            return

        # Force a static DNS override on the TUN adapter.
        tun_dns_servers = list(tun_dns) if tun_dns else []
        if not tun_dns_servers:
            tun_dns_servers = [
                DNS_IP_CLOUDFLARE,
                DNS_IP_GOOGLE,
            ]
        primary_dns = tun_dns_servers[0]

        logger.info(f"[XrayService] 'xenray-tun' interface detected. Setting DNS to {primary_dns}...")

        # Primary DNS:
        #   netsh interface ip set dns name="xenray-tun" static <dns>
        cmd_dns = [
            "netsh",
            "interface",
            "ip",
            "set",
            "dns",
            "name=xenray-tun",
            "static",
            primary_dns,
        ]
        subprocess.run(cmd_dns, check=False, creationflags=creation_flags)
        logger.info(f"[XrayService] Successfully set 'xenray-tun' DNS to {primary_dns}")

        # Secondary DNS servers (index 2+):
        #   netsh interface ip add dns name="xenray-tun" <dns> index=N
        secondary_dns = [s for s in tun_dns_servers[1:] if s != primary_dns]
        if not secondary_dns:
            secondary_dns = [DNS_IP_GOOGLE]
        for index, server in enumerate(secondary_dns, start=2):
            cmd_add_dns = [
                "netsh",
                "interface",
                "ip",
                "add",
                "dns",
                "name=xenray-tun",
                server,
                f"index={index}",
            ]
            subprocess.run(
                cmd_add_dns,
                check=False,
                creationflags=creation_flags,
            )
        logger.info(f"[XrayService] Added secondary DNS on 'xenray-tun': {secondary_dns}")

        # Add NRPT rule to prevent DNS leaks by forcing all name resolution to the TUN DNS
        logger.info(f"[XrayService] Adding NRPT rule for namespace '.' pointing to {primary_dns}...")
        cmd_nrpt = [
            "powershell",
            "-Command",
            f"Add-DnsClientNrptRule -Namespace '.' -NameServers '{primary_dns}' " "-Comment 'XenRay TUN DNS'",
        ]
        subprocess.run(cmd_nrpt, check=False, creationflags=creation_flags)

        # Flush the system DNS cache
        subprocess.run(
            ["ipconfig", "/flushdns"],
            check=False,
            creationflags=creation_flags,
            capture_output=True,
        )
        logger.info("[XrayService] Flushed system DNS cache")

    def start(self, config_file_path: str) -> Optional[int]:
        """
        Start Xray with the given configuration.
        """
        # Ensure cleanup again just in case
        self._cleanup_previous_instance()

        logger.debug(f"[XrayService] Starting Xray with config: {config_file_path}")

        if not os.path.isfile(config_file_path):
            logger.error(f"[XrayService] Config not found: {config_file_path}")
            return None

        # Ensure XRAY_LOCATION_ASSET environment variable is set
        os.environ["XRAY_LOCATION_ASSET"] = XRAY_LOCATION_ASSET
        logger.debug(f"[XrayService] XRAY_LOCATION_ASSET set to: {XRAY_LOCATION_ASSET}")

        # Small delay to ensure previous instance is fully terminated
        time.sleep(PROCESS_START_DELAY)

        cmd = [XRAY_EXECUTABLE, "run", "-c", config_file_path]

        logger.debug(f"[XrayService] Executing command: {' '.join(cmd)}")
        logger.debug(f"[XrayService] Log file: {XRAY_LOG_FILE}")

        try:
            self._process = ProcessUtils.run_command(cmd, stdout_file=XRAY_LOG_FILE, stderr_file=XRAY_LOG_FILE)

            if self._process:
                self._pid = self._process.pid
                logger.info(f"[XrayService] Started with PID {self._pid}")

                # Write PID file
                try:
                    with open(XRAY_PID_FILE, "w") as f:
                        f.write(str(self._pid))
                except Exception as e:
                    logger.error(f"[XrayService] Failed to write PID file: {e}")

                # Windows virtual adapter DNS override (Wintun)
                self._configure_windows_tun_dns(config_file_path)

                return self._pid
            else:
                logger.error("[XrayService] Failed to start process")
                return None
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[XrayService] Failed to start Xray: {e}")
            return None

    def stop(self) -> bool:
        """
        Stop Xray process.
        """
        # Always remove NRPT rules to clean up system state on stop
        self._remove_nrpt_rules()

        # Checks memory PID first
        pid_to_kill = self._pid

        # If no memory PID, check file
        if not pid_to_kill and os.path.exists(XRAY_PID_FILE):
            try:
                with open(XRAY_PID_FILE, "r") as f:
                    pid_to_kill = int(f.read().strip())
            except Exception:
                pass

        if not pid_to_kill:
            logger.debug("[XrayService] No process to stop")
            return True

        try:
            logger.info(f"[XrayService] Stopping process {pid_to_kill}")
            ProcessUtils.kill_process(pid_to_kill)
            self._pid = None
            self._process = None

            # Remove PID file
            if os.path.exists(XRAY_PID_FILE):
                try:
                    os.remove(XRAY_PID_FILE)
                except Exception as e:
                    logger.warning(f"[XrayService] Failed to remove PID file: {e}")

            return True
        except Exception as e:
            logger.error(f"[XrayService] Failed to stop Xray: {e}")
            return False

    @property
    def pid(self) -> Optional[int]:
        """Get process PID if running."""
        if self._pid and ProcessUtils.is_running(self._pid):
            return self._pid
        return None

    @property
    def is_running(self) -> bool:
        """Check if Xray is currently running."""
        return self.pid is not None
