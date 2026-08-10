"""Xray service for managing Xray process."""

import atexit
import os
import signal
import subprocess
import threading
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

# Maximum time to wait for xenray-tun adapter to appear (seconds x 0.5 s interval)
TUN_ADAPTER_WAIT_ITERATIONS = 60  # 30 seconds total
TUN_ADAPTER_POLL_INTERVAL = 0.5


class XrayService:
    """Service for managing Xray process."""

    def __init__(self):
        """Initialize Xray service."""
        self._process = None
        self._pid: Optional[int] = None
        self._is_tun_mode: bool = False
        self._smhr_was_enabled: Optional[bool] = None  # tracks SMHR state before VPN
        self._cleanup_lock = threading.Lock()
        self._check_and_restore_pid()

        # Guarantee teardown even on unclean exit (SIGKILL bypasses this, but
        # SIGTERM, interpreter shutdown, and atexit are all covered).
        atexit.register(self._guaranteed_cleanup)
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
        except (OSError, ValueError):
            pass

        if hasattr(signal, "SIGBREAK"):
            try:
                signal.signal(signal.SIGBREAK, self._signal_handler)  # type: ignore[attr-defined]
            except (OSError, ValueError, AttributeError):
                pass

    # ------------------------------------------------------------------
    # Signal / atexit handlers
    # ------------------------------------------------------------------

    def _signal_handler(self, signum, frame):
        """Handle OS termination signals by performing a clean stop."""
        logger.info(f"[XrayService] Received signal {signum}, performing cleanup...")
        self._guaranteed_cleanup()

    def _guaranteed_cleanup(self):
        """Idempotent teardown — safe to call multiple times (guarded by lock)."""
        with self._cleanup_lock:
            self._remove_nrpt_rules()
            self._restore_smhr()
            if self._is_tun_mode:
                self._cleanup_tun_dns()
                self._is_tun_mode = False

    # ------------------------------------------------------------------
    # NRPT helpers
    # ------------------------------------------------------------------

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
            subprocess.run(
                cmd_remove,
                check=False,
                creationflags=creation_flags,
                capture_output=True,
                timeout=10,
            )

    # ------------------------------------------------------------------
    # TUN adapter DNS cleanup helpers
    # ------------------------------------------------------------------

    def _cleanup_tun_dns(self):
        """Remove static DNS entries from the xenray-tun adapter (if it still exists).

        Must be called at teardown so no stale DNS entries survive if Wintun's
        kernel driver is slow to destroy the adapter.
        """
        from src.utils.platform_utils import PlatformUtils

        if PlatformUtils.get_platform() != "windows":
            return

        creation_flags = PlatformUtils.get_subprocess_flags()

        # Verify the adapter is still present before issuing netsh commands.
        check_res = subprocess.run(
            ["powershell", "-Command", "Get-NetAdapter -Name 'xenray-tun'"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=creation_flags,
            timeout=10,
        )
        if check_res.returncode != 0:
            logger.debug("[XrayService] xenray-tun adapter already gone — skipping DNS cleanup")
            return

        logger.info("[XrayService] Clearing static DNS from xenray-tun adapter...")
        for proto in ("ip", "ipv6"):
            res = subprocess.run(
                [
                    "netsh",
                    "interface",
                    proto,
                    "delete",
                    "dnsserver",
                    "xenray-tun",
                    "all",
                ],
                capture_output=True,
                text=True,
                check=False,
                creationflags=creation_flags,
                timeout=10,
            )
            if res.returncode != 0:
                logger.debug(
                    f"[XrayService] netsh interface {proto} delete dnsserver: "
                    f"rc={res.returncode} {res.stdout.strip() or res.stderr.strip()}"
                )

    # ------------------------------------------------------------------
    # Smart Multi-Homed Name Resolution (SMHR) management
    # ------------------------------------------------------------------

    @staticmethod
    def _read_smhr_state() -> Optional[bool]:
        from src.utils.platform_utils import PlatformUtils
        return PlatformUtils.read_smhr_state()

    @staticmethod
    def _set_smhr_state(enabled: bool):
        from src.utils.platform_utils import PlatformUtils
        PlatformUtils.set_smhr_state(enabled)

    def _suppress_smhr(self):
        from src.utils.platform_utils import PlatformUtils
        self._smhr_was_enabled = PlatformUtils.suppress_smhr()

    def _restore_smhr(self):
        from src.utils.platform_utils import PlatformUtils
        PlatformUtils.restore_smhr(self._smhr_was_enabled)
        self._smhr_was_enabled = None

    # ------------------------------------------------------------------
    # Instance management
    # ------------------------------------------------------------------

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

        # Always remove NRPT rules, clear TUN DNS, and restore SMHR from any
        # previous crashed session before starting a new one.
        self._remove_nrpt_rules()
        self._cleanup_tun_dns()
        self._restore_smhr()

    def _configure_windows_tun_dns(self, config_file_path: str):
        """Configure DNS and NRPT settings for the virtual TUN adapter on Windows.

        This method is called from a daemon thread so it never blocks the UI.
        """
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

        self._is_tun_mode = True

        # Suppress SMHR before touching DNS so Windows does not immediately
        # leak queries to physical adapters in parallel.
        self._suppress_smhr()

        # Wait for xenray-tun adapter to be created (up to 30 s)
        logger.info("[XrayService] TUN mode detected. Waiting for 'xenray-tun' interface...")
        tun_created = False
        creation_flags = PlatformUtils.get_subprocess_flags()
        for _ in range(TUN_ADAPTER_WAIT_ITERATIONS):
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
            logger.error(
                "[XrayService] 'xenray-tun' interface was not created within 30 s. "
                "DNS override skipped — VPN may leak DNS."
            )
            return

        # Build DNS server lists
        tun_dns_servers = list(tun_dns) if tun_dns else []
        if not tun_dns_servers:
            tun_dns_servers = [
                DNS_IP_CLOUDFLARE,
                DNS_IP_GOOGLE,
            ]

        ipv4_servers = [s for s in tun_dns_servers if ":" not in s]
        ipv6_servers = [s for s in tun_dns_servers if ":" in s]

        # --- IPv4 DNS ---
        primary_v4 = ipv4_servers[0] if ipv4_servers else DNS_IP_CLOUDFLARE
        logger.info(f"[XrayService] Setting 'xenray-tun' IPv4 DNS to {primary_v4}...")

        res = subprocess.run(
            [
                "netsh",
                "interface",
                "ip",
                "set",
                "dns",
                "name=xenray-tun",
                "static",
                primary_v4,
            ],
            capture_output=True,
            text=True,
            check=False,
            creationflags=creation_flags,
        )
        if res.returncode != 0:
            logger.warning(
                f"[XrayService] netsh set IPv4 DNS failed (rc={res.returncode}): "
                f"{res.stdout.strip() or res.stderr.strip()}"
            )
        else:
            logger.info(f"[XrayService] Set 'xenray-tun' IPv4 DNS to {primary_v4}")

        # Secondary IPv4 DNS servers (index 2+)
        # Fallback: prefer Cloudflare if Google is primary, or Google otherwise —
        # never duplicate the primary server (MIN-02 fix).
        secondary_v4 = [s for s in ipv4_servers[1:] if s != primary_v4]
        if not secondary_v4:
            secondary_v4 = [DNS_IP_GOOGLE if primary_v4 != DNS_IP_GOOGLE else DNS_IP_CLOUDFLARE]

        for index, server in enumerate(secondary_v4, start=2):
            res = subprocess.run(
                [
                    "netsh",
                    "interface",
                    "ip",
                    "add",
                    "dns",
                    "name=xenray-tun",
                    server,
                    f"index={index}",
                ],
                capture_output=True,
                text=True,
                check=False,
                creationflags=creation_flags,
            )
            if res.returncode != 0:
                logger.warning(
                    f"[XrayService] netsh add IPv4 DNS[{index}] failed (rc={res.returncode}): "
                    f"{res.stdout.strip() or res.stderr.strip()}"
                )
        logger.info(f"[XrayService] Added secondary IPv4 DNS on 'xenray-tun': {secondary_v4}")

        # --- IPv6 DNS (dual-stack) ---
        # Pre-flight check: verify IPv6 is enabled before issuing ipv6 netsh commands.
        ipv6_enabled = self._check_ipv6_interface_available(creation_flags)
        if ipv6_servers and ipv6_enabled:
            primary_v6 = ipv6_servers[0]
            res = subprocess.run(
                [
                    "netsh",
                    "interface",
                    "ipv6",
                    "set",
                    "dns",
                    "name=xenray-tun",
                    "static",
                    primary_v6,
                ],
                capture_output=True,
                text=True,
                check=False,
                creationflags=creation_flags,
            )
            if res.returncode != 0:
                logger.warning(
                    f"[XrayService] netsh set IPv6 DNS failed (rc={res.returncode}): "
                    f"{res.stdout.strip() or res.stderr.strip()} — "
                    f"IPv6 DNS will not be configured on xenray-tun"
                )
            else:
                logger.info(f"[XrayService] Set 'xenray-tun' IPv6 DNS to {primary_v6}")

                secondary_v6 = [s for s in ipv6_servers[1:] if s != primary_v6]
                for index, server in enumerate(secondary_v6, start=2):
                    res = subprocess.run(
                        [
                            "netsh",
                            "interface",
                            "ipv6",
                            "add",
                            "dns",
                            "name=xenray-tun",
                            server,
                            f"index={index}",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                        creationflags=creation_flags,
                    )
                    if res.returncode != 0:
                        logger.warning(
                            f"[XrayService] netsh add IPv6 DNS[{index}] failed "
                            f"(rc={res.returncode}): "
                            f"{res.stdout.strip() or res.stderr.strip()}"
                        )
                if secondary_v6:
                    logger.info(f"[XrayService] Added secondary IPv6 DNS on 'xenray-tun': {secondary_v6}")
        elif ipv6_servers and not ipv6_enabled:
            logger.info("[XrayService] IPv6 is disabled on this system — skipping IPv6 DNS configuration")

        # Add NRPT rule to prevent DNS leaks (all namespaces → TUN DNS)
        logger.info(f"[XrayService] Adding NRPT rule for namespace '.' pointing to {primary_v4}...")
        cmd_nrpt = [
            "powershell",
            "-Command",
            f"Add-DnsClientNrptRule -Namespace '.' -NameServers '{primary_v4}' " "-Comment 'XenRay TUN DNS'",
        ]
        res = subprocess.run(
            cmd_nrpt,
            capture_output=True,
            text=True,
            check=False,
            creationflags=creation_flags,
        )
        if res.returncode != 0:
            logger.warning(
                f"[XrayService] NRPT rule creation failed (rc={res.returncode}): "
                f"{res.stdout.strip() or res.stderr.strip()}"
            )
        else:
            logger.info("[XrayService] NRPT rule added successfully")

        # Flush the system DNS cache
        subprocess.run(
            ["ipconfig", "/flushdns"],
            check=False,
            creationflags=creation_flags,
            capture_output=True,
        )
        logger.info("[XrayService] Flushed system DNS cache")

    @staticmethod
    def _check_ipv6_interface_available(creation_flags: int) -> bool:
        """Return True if the Windows IPv6 stack is enabled and operational.

        Uses `netsh interface ipv6 show interfaces` as the lightest probe —
        if IPv6 is fully disabled (registry DisabledComponents=0xFF) this
        command returns a non-zero exit code.
        """
        try:
            res = subprocess.run(
                ["netsh", "interface", "ipv6", "show", "interfaces"],
                capture_output=True,
                text=True,
                check=False,
                creationflags=creation_flags,
                timeout=5,
            )
            return res.returncode == 0
        except Exception:
            return False

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

                # Windows virtual adapter DNS override — run in a daemon thread so
                # we never block the UI thread (CRIT-04 / MAJ-05 fix).
                dns_thread = threading.Thread(
                    target=self._configure_windows_tun_dns,
                    args=(config_file_path,),
                    daemon=True,
                    name="xenray-tun-dns",
                )
                dns_thread.start()

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
        # Perform guaranteed teardown (NRPT, SMHR, TUN DNS cleanup)
        self._guaranteed_cleanup()

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
