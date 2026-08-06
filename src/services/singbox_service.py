"""Sing-box Service Manager.

Port of the working Sing-box TUN service from XenRay v0.1.17-beta, adapted to
the current branch:

- Non-blocking process management via ``asyncio.subprocess`` (dedicated daemon
  event-loop thread; the caller-facing API stays synchronous).
- Pre-flight configuration validation (``sing-box check -c <config>``) before
  the process is launched.
- Graceful stop: ``terminate()`` with a fallback to ``kill()``.
- Same atexit / SIGTERM / SIGBREAK cleanup contract as ``XrayService``.
- IPv4-only TUN setup: single IPv4 subnet and IPv4-only DNS resolution. IPv6 is
  disabled to avoid system-stack prefix binding errors ("need one more IPv6
  address...") and IPv6-related latency spikes.

In the dual-engine mode the flow is: Xray runs as the proxy (SOCKS inbound) and
sing-box runs as the TUN engine, routing all captured traffic into Xray's SOCKS
port. This mirrors the 0.1.17-beta architecture.
"""

import asyncio
import atexit
import ipaddress
import json
import os
import signal
import socket
import subprocess
import threading
import time
from typing import List, Optional, Union

from src.core.constants import (
    SINGBOX_CONFIG_PATH,
    SINGBOX_EXECUTABLE,
    SINGBOX_LOG_FILE,
    SINGBOX_PID_FILE,
    SINGBOX_RULE_SETS,
    TUN_GATEWAY_IPV4,
    XRAY_EXECUTABLE,
)
from src.core.logger import logger
from src.utils.network_interface import NetworkInterfaceDetector
from src.utils.platform_utils import PlatformUtils
from src.utils.process_utils import ProcessUtils

# Constants
XRAY_READY_RETRY_COUNT = 20
XRAY_READY_RETRY_DELAY = 0.5  # seconds
XRAY_READY_TIMEOUT = XRAY_READY_RETRY_COUNT * XRAY_READY_RETRY_DELAY  # 10 seconds
PROCESS_TERMINATE_TIMEOUT = 8.0  # seconds
DNS_RESOLUTION_TIMEOUT = 5.0  # seconds
SINGBOX_CHECK_TIMEOUT = 15.0  # seconds - pre-flight `sing-box check` timeout
LOOP_START_TIMEOUT = 2.0  # seconds - max wait for the asyncio loop thread


class SingboxService:
    """Manages the sing-box TUN process with safe loop prevention."""

    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._pid: Optional[int] = None
        self._log_handle = None
        self._added_routes: List[str] = []
        self._added_lan_routes: List[str] = []
        # RLock (reentrant) so that atexit/_guaranteed_cleanup can safely call
        # stop() even when a concurrent stop() is already in progress on the same
        # thread (e.g. interpreter shutdown while teardown is running).
        self._cleanup_lock = threading.RLock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        # Tracks SMHR state before TUN session (BUG-08 fix)
        self._smhr_was_enabled: Optional[bool] = None

        # Support PID adoption for CLI state restoration
        self._check_and_restore_pid()

        # Guarantee teardown even on unclean exit (SIGKILL bypasses this, but
        # SIGTERM, interpreter shutdown, and atexit are all covered).
        # NOTE: atexit.register is ADDITIVE — each service adds its own entry.
        atexit.register(self._guaranteed_cleanup)

        # BUG-02 FIX: Do NOT unconditionally overwrite the SIGTERM/SIGBREAK
        # signal handler.  XrayService registers its own handler first; a blind
        # signal.signal() call here would silently discard it, orphaning the Xray
        # process on SIGTERM.  Instead, chain: store the previous handler and
        # invoke it after our own cleanup so both services are torn down.
        for sig in (signal.SIGTERM,):
            try:
                prev = signal.getsignal(sig)
                if callable(prev) and prev not in (signal.SIG_DFL, signal.SIG_IGN):

                    def _chained(signum, frame, _prev=prev):
                        self._signal_handler(signum, frame)
                        _prev(signum, frame)

                    signal.signal(sig, _chained)
                else:
                    signal.signal(sig, self._signal_handler)
            except (OSError, ValueError):
                pass
        # SIGBREAK is Windows-only and typically not registered by XrayService
        try:
            signal.signal(signal.SIGBREAK, self._signal_handler)  # type: ignore[attr-defined]
        except (OSError, ValueError, AttributeError):
            pass

    # ------------------------------------------------------------------
    # Signal / atexit handlers
    # ------------------------------------------------------------------

    def _signal_handler(self, signum, frame):
        """Handle OS termination signals by performing a clean stop."""
        logger.info(f"[SingboxService] Received signal {signum}, performing cleanup...")
        self._guaranteed_cleanup()

    def _guaranteed_cleanup(self):
        """Idempotent teardown — safe to call multiple times (guarded by lock)."""
        self.stop()

    # ------------------------------------------------------------------
    # Asyncio event-loop plumbing (non-blocking process management)
    # ------------------------------------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Lazily start a dedicated daemon thread running an asyncio loop.

        The loop lives for the lifetime of the service so the spawned
        ``asyncio.subprocess`` object stays bound to a live loop and can be
        stopped later (a fresh ``asyncio.run`` per call would close the loop
        under the process).
        """
        if self._loop is not None:
            return self._loop

        def _run_loop():
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self._loop_thread = threading.Thread(
            target=_run_loop,
            daemon=True,
            name="singbox-asyncio",
        )
        self._loop_thread.start()

        deadline = time.monotonic() + LOOP_START_TIMEOUT
        while self._loop is None:
            if time.monotonic() > deadline:
                raise RuntimeError("[SingboxService] asyncio loop failed to start")
            time.sleep(0.01)
        return self._loop

    def _run_async(self, coro, timeout: float = 60.0):
        """Schedule ``coro`` on the background loop and block for its result."""
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    async def _run_check(self):
        """Run ``sing-box check -c <config>`` and return (rc, stdout, stderr)."""
        proc = await asyncio.subprocess.create_subprocess_exec(
            SINGBOX_EXECUTABLE,
            "check",
            "-c",
            SINGBOX_CONFIG_PATH,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=PlatformUtils.get_subprocess_flags(),
            startupinfo=PlatformUtils.get_startupinfo(),
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout, stderr

    async def _spawn_process(self) -> Optional[asyncio.subprocess.Process]:
        """Spawn the sing-box run process on the background event loop."""
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        startupinfo = PlatformUtils.get_startupinfo()
        return await asyncio.subprocess.create_subprocess_exec(
            SINGBOX_EXECUTABLE,
            "run",
            "-c",
            SINGBOX_CONFIG_PATH,
            stdout=self._log_handle,
            stderr=self._log_handle,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )

    async def _terminate_process(self):
        """Gracefully stop the spawned asyncio process: terminate → kill."""
        process = self._process
        if process is None or process.returncode is not None:
            return
        try:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=PROCESS_TERMINATE_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning("[SingboxService] Graceful terminate timed out, forcing kill")
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
        except Exception as e:
            logger.error(f"[SingboxService] Error terminating process: {e}")
            # Last-resort fallback: force kill via psutil
            try:
                ProcessUtils.kill_process(process.pid, force=True)
            except Exception:
                pass

    @staticmethod
    def _terminate_pid(pid: int):
        """Gracefully stop an adopted PID: terminate → wait → kill fallback."""
        if not pid or not ProcessUtils.is_running(pid):
            return
        try:
            ProcessUtils.kill_process(pid, force=False)  # graceful terminate
            deadline = time.monotonic() + PROCESS_TERMINATE_TIMEOUT
            while ProcessUtils.is_running(pid) and time.monotonic() < deadline:
                time.sleep(0.1)
            if ProcessUtils.is_running(pid):
                logger.warning("[SingboxService] Graceful stop timed out, forcing kill")
                ProcessUtils.kill_process(pid, force=True)
        except Exception as e:
            logger.error(f"[SingboxService] Error stopping PID {pid}: {e}")

    # ------------------------------------------------------------------
    # PID state management
    # ------------------------------------------------------------------

    def _check_and_restore_pid(self):
        """Restore PID from file if it's still running (CLI state adoption)."""
        if os.path.exists(SINGBOX_PID_FILE):
            try:
                with open(SINGBOX_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    logger.debug(f"[SingboxService] Restored PID {self._pid} from file")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Smart Multi-Homed Name Resolution (SMHR) management
    # Ported from XrayService — same pattern, same registry keys.
    # ------------------------------------------------------------------

    @staticmethod
    def _read_smhr_state() -> Optional[bool]:
        """Read current SMHR enabled state from the Windows registry.

        Returns True if SMHR is enabled (OS default), False if disabled, None on error.
        """
        try:
            import winreg  # Windows-only

            key_path = r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, "DisableSmartNameResolution")
                    return value == 0  # 0 = SMHR enabled, 1 = SMHR disabled
                except FileNotFoundError:
                    return True  # Key absent → SMHR is enabled (OS default)
        except Exception:
            return None

    @staticmethod
    def _set_smhr_state(enabled: bool):
        """Enable or disable SMHR via the Windows registry."""
        try:
            import winreg  # Windows-only

            key_path = r"SYSTEM\CurrentControlSet\Services\Dnscache\Parameters"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, access=winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(
                    key,
                    "DisableSmartNameResolution",
                    0,
                    winreg.REG_DWORD,
                    0 if enabled else 1,
                )
                winreg.SetValueEx(
                    key,
                    "DisableParallelAandAAAA",
                    0,
                    winreg.REG_DWORD,
                    0 if enabled else 1,
                )
        except Exception as e:
            logger.warning(f"[SingboxService] Could not set SMHR registry value: {e}")

    def _suppress_smhr(self):
        """Disable SMHR for the TUN session, saving previous state for restore."""
        if PlatformUtils.get_platform() != "windows":
            return
        self._smhr_was_enabled = self._read_smhr_state()
        if self._smhr_was_enabled is True:
            logger.info("[SingboxService] Disabling SMHR to prevent DNS leaks during TUN session")
            self._set_smhr_state(enabled=False)

    def _restore_smhr(self):
        """Restore SMHR to its pre-TUN state."""
        if PlatformUtils.get_platform() != "windows":
            return
        if self._smhr_was_enabled is True:
            logger.info("[SingboxService] Restoring SMHR to enabled state")
            self._set_smhr_state(enabled=True)
            self._smhr_was_enabled = None

    # ------------------------------------------------------------------
    # Route / IP helpers (ported from 0.1.17-beta)
    # ------------------------------------------------------------------

    def _normalize_list(self, value: Union[str, List[str], None]) -> List[str]:
        """Normalize input to list of strings."""
        if not value:
            return []
        if isinstance(value, str):
            value = [value]
        return [
            item.strip().lower().replace("'", "").replace('"', "").replace("[", "").replace("]", "")
            for item in value
            if isinstance(item, str)
        ]

    def _filter_real_ips(self, lst: List[str]) -> List[str]:
        """Filter list to only include valid IP addresses."""
        result = []
        for item in lst:
            try:
                ipaddress.ip_address(item)
                result.append(item)
            except (ValueError, ipaddress.AddressValueError):
                continue
        return result

    @staticmethod
    def _is_private_or_reserved(ip: str) -> bool:
        """True if the address is in private/reserved IPv4 space (never route).

        Covers RFC1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback
        (127.0.0.0/8), link-local (169.254.0.0/16), CGNAT (100.64.0.0/10) and
        other IANA-reserved blocks.
        """
        try:
            return bool(ipaddress.ip_address(ip).is_private)
        except ValueError:
            return True

    def _filter_domains(self, lst: List[str]) -> List[str]:
        """Filter list to only include domain names (not IPs)."""
        # An entry is a domain if and only if it is NOT a valid IP address.
        # The original implementation was incorrect: it tested
        # ``item.endswith('.8.8.8.8')`` which is never True for any domain.
        valid_ips: set = set(self._filter_real_ips(lst))
        return [item for item in lst if item not in valid_ips]

    def _resolve_ips(self, endpoints: List[str]) -> List[str]:
        """Resolve domain names to IP addresses with timeout."""
        resolved_ips = []
        for ep in endpoints:
            # Check if already an IP
            try:
                ipaddress.ip_address(ep)
                resolved_ips.append(ep)
                continue
            except (ValueError, ipaddress.AddressValueError):
                pass  # It's a domain, need to resolve

            try:
                logger.info(f"[SingboxService] Resolving {ep} for route bypass...")
                # Set timeout for DNS resolution
                socket.setdefaulttimeout(DNS_RESOLUTION_TIMEOUT)
                addrs = socket.getaddrinfo(ep, None, socket.AF_INET)
                ips = list({info[4][0] for info in addrs})
                logger.info(f"[SingboxService] Resolved {ep} → {ips}")
                resolved_ips.extend(ips)
            except (socket.gaierror, socket.timeout, OSError) as e:
                logger.warning(f"[SingboxService] Failed to resolve {ep}: {e}")
            finally:
                socket.setdefaulttimeout(None)  # Reset timeout
        return list(set(resolved_ips))

    def _add_static_route(self, ip: str, gateway: str) -> None:
        """Add static route for IP via gateway."""
        if ip in self._added_routes:
            return
        # Ignore private/reserved IP space (10.0.0.0/8, 172.16.0.0/12,
        # 192.168.0.0/16, loopback, link-local, CGNAT, ...) when adding bypass
        # routes. Routing a private IP via the physical gateway produces an
        # invalid binding — and for an ISP-hijacked DNS IP it would leak DNS off
        # the encrypted tunnel.
        if self._is_private_or_reserved(ip):
            logger.debug(f"[SingboxService] Skipping static route for private/reserved IP: {ip}")
            return
        try:
            logger.info(f"[SingboxService] Adding static route: {ip} → {gateway}")

            # Platform-specific route commands
            platform = PlatformUtils.get_platform()

            if platform == "windows":
                cmd = [
                    "route",
                    "add",
                    ip,
                    "mask",
                    "255.255.255.255",
                    gateway,
                    "metric",
                    "1",
                ]
            elif platform == "macos":
                cmd = [
                    "route",
                    "-n",
                    "add",
                    "-host",
                    ip,
                    gateway,
                ]
            else:  # Linux
                cmd = [
                    "ip",
                    "route",
                    "add",
                    ip,
                    "via",
                    gateway,
                ]

            subprocess.run(
                cmd,
                check=False,
                capture_output=True,  # suppress console window flash on Windows (BUG-03)
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            self._added_routes.append(ip)
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[SingboxService] Failed to add route for {ip}: {e}")

    def _cleanup_routes(self) -> None:
        """Remove all added static routes."""
        platform = PlatformUtils.get_platform()

        for ip in self._added_routes[:]:
            try:
                logger.debug(f"[SingboxService] Removing static route: {ip}")

                # Platform-specific route delete commands
                if platform == "windows":
                    cmd = ["route", "delete", ip]
                elif platform == "macos":
                    cmd = ["route", "-n", "delete", "-host", ip]
                else:  # Linux
                    cmd = ["ip", "route", "del", ip]

                subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,  # suppress console window flash on Windows (BUG-03)
                    creationflags=PlatformUtils.get_subprocess_flags(),
                    startupinfo=PlatformUtils.get_startupinfo(),
                )
            except (OSError, subprocess.SubprocessError) as e:
                logger.warning(f"[SingboxService] Failed to remove route for {ip}: {e}")
            finally:
                if ip in self._added_routes:
                    self._added_routes.remove(ip)

        self._cleanup_lan_routes()

    def _add_lan_routes(self, gateway: str) -> None:
        """Add static routes for private LAN ranges via the physical gateway.

        Required for LAN proxy sharing: without these, packets from LAN devices
        would be captured by the TUN adapter and looped back through the tunnel
        instead of reaching the physical LAN interface.
        """
        from src.core.constants import LAN_PRIVATE_RANGES

        for cidr in LAN_PRIVATE_RANGES:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                logger.warning(f"[SingboxService] Skipping invalid LAN range: {cidr}")
                continue
            self._add_cidr_route(network, gateway)

    def _add_cidr_route(self, network, gateway: str) -> None:
        """Add a network (CIDR) static route via the physical gateway."""
        key = str(network)
        if key in self._added_lan_routes:
            return
        platform = PlatformUtils.get_platform()

        if platform == "windows":
            cmd = [
                "route",
                "add",
                str(network.network_address),
                "mask",
                str(network.netmask),
                gateway,
                "metric",
                "1",
            ]
        elif platform == "macos":
            cmd = ["route", "-n", "add", "-net", str(network), gateway]
        else:  # Linux
            cmd = ["ip", "route", "add", str(network), "via", gateway]

        try:
            logger.info(f"[SingboxService] Adding LAN route: {network} → {gateway}")
            subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            self._added_lan_routes.append(key)
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[SingboxService] Failed to add LAN route {network}: {e}")

    def _cleanup_lan_routes(self) -> None:
        """Remove all LAN range static routes added for LAN sharing."""
        platform = PlatformUtils.get_platform()

        for key in self._added_lan_routes[:]:
            try:
                network = ipaddress.ip_network(key, strict=False)
                if platform == "windows":
                    cmd = ["route", "delete", str(network.network_address)]
                elif platform == "macos":
                    cmd = ["route", "-n", "delete", "-net", str(network)]
                else:  # Linux
                    cmd = ["ip", "route", "del", str(network)]

                logger.debug(f"[SingboxService] Removing LAN route: {key}")
                subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    creationflags=PlatformUtils.get_subprocess_flags(),
                    startupinfo=PlatformUtils.get_startupinfo(),
                )
            except (OSError, subprocess.SubprocessError) as e:
                logger.warning(f"[SingboxService] Failed to remove LAN route {key}: {e}")
            finally:
                if key in self._added_lan_routes:
                    self._added_lan_routes.remove(key)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        xray_socks_port: int,
        proxy_server_ip: Union[str, List[str]] = "",
        routing_country: str = "",
        routing_rules: dict = None,
        mtu: int = 1420,
        allow_lan: bool = False,
    ) -> Optional[int]:
        """Start the sing-box TUN service.

        Args:
            xray_socks_port: Xray SOCKS port that sing-box routes traffic into.
            proxy_server_ip: Proxy server IP(s)/domain(s) to bypass via static routes.
            routing_country: Country routing code ("" or "none" to disable).
            routing_rules: User routing rules {direct/proxy/block: [targets]}.
            mtu: TUN MTU.
            allow_lan: When True, private LAN ranges get static routes via the
                physical gateway so LAN-device traffic bypasses the TUN (LAN
                proxy sharing).

        Returns:
            sing-box PID on success, ``None`` on failure.
        """
        try:
            # 1. Detect interface & gateway
            (
                iface_name,
                iface_ip,
                _,
                gateway,
            ) = NetworkInterfaceDetector.get_primary_interface()
            if not gateway:
                logger.warning("[SingboxService] No gateway detected! Route bypass may be incomplete.")

            # 2. Bypass list: ONLY the proxy server node endpoint(s). These static
            #    routes break the Wintun routing loop so the sing-box → Xray →
            #    proxy-server connection stays outside the TUN.
            #
            #    DoH / remote DNS hostnames (dns.google, cloudflare-dns.com,
            #    1.1.1.1, 8.8.8.8) are INTENTIONALLY excluded: resolving them on
            #    the host can return ISP-hijacked private IPs (e.g. 10.10.34.35),
            #    and static-routing those leaks DNS over the plaintext local
            #    interface. DNS must flow through sing-box's hijack-dns / SOCKS
            #    proxy outbound instead. User "direct" rules are also handled by
            #    the sing-box route config, not OS static routes.
            bypass_list = self._normalize_list(proxy_server_ip)

            resolved_ips = self._resolve_ips(bypass_list)

            # 3. Add static routes for the proxy server endpoints only
            if gateway:
                for ip in resolved_ips:
                    self._add_static_route(ip, gateway)

            # When LAN sharing is enabled, pin private LAN ranges to the physical
            # gateway so LAN-device packets bypass the TUN (no loopbacks).
            if allow_lan and gateway:
                self._add_lan_routes(gateway)

            # BUG-08 FIX: Suppress Windows SMHR so DNS queries are not leaked to
            # physical adapters in parallel while the TUN interface is active.
            # This mirrors the XrayService._suppress_smhr() pattern.
            self._suppress_smhr()

            # 4. Generate config - pass interface name for default_interface and MTU
            config = self._generate_config(
                xray_socks_port,
                proxy_server_ip,
                routing_country,
                iface_name,
                routing_rules,
                mtu,
            )

            # 5. Wait for Xray to be ready (with retry)
            if not self._wait_for_xray_ready(xray_socks_port):
                self._cleanup_routes()
                return None

            # 6. Write config & start sing-box (with pre-flight validation)
            if not self._write_config_and_start(config):
                self._cleanup_routes()
                return None

            self._pid = self._process.pid

            # Write PID file
            try:
                with open(SINGBOX_PID_FILE, "w") as f:
                    f.write(str(self._pid))
            except Exception as e:
                logger.error(f"[SingboxService] Failed to write PID file: {e}")

            logger.info(f"[SingboxService] sing-box started successfully | PID: {self._pid}")
            return self._pid

        except Exception as e:
            logger.exception(f"[SingboxService] Failed to start: {e}")
            self._close_log()
            self._cleanup_routes()
            return None

    def _wait_for_xray_ready(self, port: int) -> bool:
        """Wait for Xray SOCKS port to be ready."""
        logger.info(f"[SingboxService] Waiting for Xray on port {port}...")
        for _ in range(XRAY_READY_RETRY_COUNT):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    logger.info("[SingboxService] Xray is ready.")
                    return True
            except (socket.timeout, ConnectionRefusedError, OSError):
                time.sleep(XRAY_READY_RETRY_DELAY)

        logger.error("[SingboxService] Timed out waiting for Xray.")
        return False

    def _write_config_and_start(self, config: dict) -> bool:
        """Write config to file, validate it, and start the process."""
        try:
            # Write config
            with open(SINGBOX_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            # Open log file — rotate an oversized leftover first so the active
            # log never exceeds the 5 MB ceiling.
            from src.utils.process_utils import rotate_oversized_log_file

            rotate_oversized_log_file(SINGBOX_LOG_FILE)
            self._log_handle = open(SINGBOX_LOG_FILE, "w", encoding="utf-8")

            # Pre-flight validation: sing-box check -c <config_path>
            if not self._validate_config():
                logger.error("[SingboxService] sing-box config validation failed, aborting start")
                self._close_log()
                return False

            # Start process on the background asyncio loop (non-blocking)
            self._process = self._run_async(self._spawn_process(), timeout=30)

            if self._process is None:
                logger.error("[SingboxService] Failed to spawn sing-box process")
                self._close_log()
                return False

            return True
        except Exception as e:
            logger.error(f"[SingboxService] Failed to start process: {e}")
            self._close_log()
            return False

    def _validate_config(self) -> bool:
        """Pre-flight config validation using ``sing-box check -c <config>``."""
        try:
            rc, stdout, stderr = self._run_async(self._run_check(), timeout=SINGBOX_CHECK_TIMEOUT)
            if rc != 0:
                err = (stdout or stderr).decode(errors="replace").strip()
                logger.error(f"[SingboxService] Config validation failed (rc={rc}): {err}")
                return False
            logger.info("[SingboxService] Config validation passed (sing-box check)")
            return True
        except Exception as e:
            logger.error(f"[SingboxService] Config validation error: {e}")
            return False

    def _close_log(self):
        """Close log file handle."""
        if self._log_handle:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    def stop(self):
        """Stop the sing-box service (graceful terminate with kill fallback)."""
        with self._cleanup_lock:
            pid_to_kill = self._pid or (self._process.pid if self._process else None)

            try:
                if self._process is not None:
                    self._run_async(self._terminate_process(), timeout=PROCESS_TERMINATE_TIMEOUT + 5)
                elif pid_to_kill:
                    self._terminate_pid(pid_to_kill)
            except Exception as e:
                logger.warning(f"[SingboxService] Async termination failed, falling back to psutil: {e}")
                if pid_to_kill:
                    self._terminate_pid(pid_to_kill)

            self._process = None
            self._pid = None

            # Remove PID file
            if os.path.exists(SINGBOX_PID_FILE):
                try:
                    os.remove(SINGBOX_PID_FILE)
                except Exception:
                    pass

            self._cleanup_routes()
            self._close_log()
            self._restore_smhr()  # BUG-08 FIX: restore SMHR to pre-TUN state
            logger.info("[SingboxService] Stopped.")

    def is_running(self) -> bool:
        """Check if sing-box is running."""
        if self._pid and ProcessUtils.is_running(self._pid):
            return True

        # Fallback to PID file
        if os.path.exists(SINGBOX_PID_FILE):
            try:
                with open(SINGBOX_PID_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if ProcessUtils.is_running(old_pid):
                    self._pid = old_pid
                    return True
            except Exception:
                pass

        # Clear stale state
        self._pid = None
        self._process = None
        return False

    @property
    def pid(self) -> Optional[int]:
        """Get sing-box process ID."""
        return self._pid

    def get_version(self) -> Optional[str]:
        """Get installed sing-box version."""
        if not os.path.exists(SINGBOX_EXECUTABLE):
            return None
        try:
            # Output: "sing-box version 1.13.14 ..."
            result = subprocess.run(
                [SINGBOX_EXECUTABLE, "version"],
                capture_output=True,
                text=True,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )
            if result.returncode == 0:
                first_line = result.stdout.split("\n")[0]
                parts = first_line.split()
                if len(parts) >= 3:
                    return parts[2]  # "1.13.14"
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # CONFIG GENERATOR — ported from 0.1.17-beta (dual-stack TUN)
    # ------------------------------------------------------------------

    def _generate_config(
        self,
        socks_port: int,
        proxy_server_ip: Union[str, List[str]],
        routing_country: str = "",
        interface_name: Optional[str] = None,
        routing_rules: dict = None,
        mtu: int = 1420,
    ) -> dict:
        """Generate a dual-stack sing-box configuration."""
        proxy_list = self._normalize_list(proxy_server_ip)
        proxy_ips = self._filter_real_ips(proxy_list)
        proxy_domains = self._filter_domains(proxy_list)

        # Build process bypass list dynamically to include frozen binary name
        import sys

        current_exe = os.path.basename(sys.executable).lower()
        process_names = [
            "xray.exe",
            "v2ray.exe",
            "sing-box.exe",
            "python.exe",
            "pythonw.exe",
            "curl.exe",
            "curl",
        ]
        if current_exe not in process_names:
            process_names.append(current_exe)

        cfg = {
            "log": {"level": "warn", "timestamp": True},
            "dns": {
                "servers": [
                    {
                        "tag": "bootstrap",
                        "type": "udp",
                        "server": "8.8.8.8",
                        "detour": "direct",
                    },
                    {
                        "tag": "remote_proxy",
                        # DoH (DNS-over-HTTPS) through the SOCKS proxy.
                        # Port-53 TCP/UDP is unreliable through proxy chains;
                        # many proxy servers block port 53, and Xray's SOCKS
                        # inbound doesn't support UDP ASSOCIATE.
                        # DoH on port 443 avoids both issues.
                        # NOTE: sing-box appends /dns-query automatically for
                        # type="https", so server is just the hostname.
                        "type": "https",
                        "server": "1.1.1.1",
                        "domain_resolver": "bootstrap",
                        "detour": "proxy",
                    },
                ],
                "rules": [
                    {
                        "inbound": ["tun-in"],
                        "server": "remote_proxy",
                    },
                ],
                "final": "remote_proxy",
                # IPv4-only resolution: never query AAAA, avoiding IPv6 DNS
                # latency and stack errors while IPv6 is disabled on the TUN.
                "strategy": "ipv4_only",
                "disable_cache": False,
                "disable_expire": False,
                "independent_cache": True,
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "interface_name": PlatformUtils.get_tun_interface_name(),
                    # IPv4-only subnet — IPv6 is disabled to avoid system-stack
                    # prefix binding errors ("need one more IPv6 address...")
                    # and IPv6-related latency spikes. auto_route captures the
                    # 0.0.0.0/0 default route only.
                    "address": [TUN_GATEWAY_IPV4],
                    "mtu": mtu,
                    "auto_route": True,
                    "strict_route": True,
                    "stack": "mixed",
                    # sniff/sniff_override_destination migrated to route.rules
                    # (sing-box 1.11.0+: inbound sniff fields removed)
                    "endpoint_independent_nat": True,
                }
            ],
            "outbounds": [
                {
                    "type": "socks",
                    "tag": "proxy",
                    "server": "127.0.0.1",
                    "server_port": socks_port,
                    "domain_resolver": "remote_proxy",
                },
                {
                    "type": "direct",
                    "tag": "direct",
                    "domain_resolver": "bootstrap",
                    **({"bind_interface": interface_name} if interface_name else {}),
                },
                {"type": "block", "tag": "block"},
            ],
            "route": {
                "rules": [
                    # Process bypass rules FIRST — ensures Python/curl/xray subprocess
                    # traffic bypasses TUN on Windows (process_name matching is unreliable
                    # for TUN-captured packets, so ip_cidr/process rules must come early)
                    {
                        "process_name": process_names,
                        "outbound": "direct",
                    },
                    {"process_path": [XRAY_EXECUTABLE], "outbound": "direct"},
                    # Protocol sniffing — required for hijack-dns to function.
                    # Without it the DNS protocol can't be detected, queries
                    # bypass the hijack-dns rule and go DIRECT (filtered by ISP).
                    # Scoped to port 53 (DNS) only to minimise overhead.
                    # See: https://sing-box.sagernet.org/migration/#migrate-legacy-inbound-fields-to-rule-actions
                    {
                        "inbound": ["tun-in"],
                        "port": [53],
                        "action": "sniff",
                    },
                    {
                        "protocol": "dns",
                        "action": "hijack-dns",
                    },
                    {"network": "udp", "port": 443, "outbound": "proxy"},
                    {"ip_cidr": ["224.0.0.0/3", "ff00::/8"], "outbound": "block"},
                    {
                        "ip_cidr": [
                            "10.0.0.0/8",
                            "172.16.0.0/12",
                            "192.168.0.0/16",
                            "127.0.0.0/8",
                            "169.254.0.0/16",
                            "fc00::/7",  # IPv6 Unique Local Addresses
                            "fe80::/10",  # IPv6 Link-Local
                            "::1/128",  # IPv6 localhost
                        ],
                        "outbound": "direct",
                    },
                ],
                "final": "proxy",
                "auto_detect_interface": True,
                **({"default_interface": interface_name} if interface_name else {}),
            },
        }

        rules = cfg["route"]["rules"]
        dns_rules = cfg["dns"]["rules"]

        # 2. Add Proxy Server IP/Domain Bypass Rules
        #
        # NOTE: Public DNS resolvers (1.1.1.1, 8.8.8.8) are deliberately NOT
        # routed 'direct'. All port 53 / DNS-bound traffic must be intercepted
        # by the sniff (Rule: port 53 -> action sniff) + hijack-dns rules below
        # so every DNS query is answered inside the tunnel — a 'direct' rule for
        # a public DNS IP would bypass the hijack, re-enabling ISP-level DNS
        # tampering on raw socket queries.
        insert_index = len([r for r in rules if "process" in r])

        for ip in proxy_ips:
            rules.insert(insert_index, {"ip_cidr": f"{ip}/32", "outbound": "direct"})
            insert_index += 1

        for domain in proxy_domains:
            rules.insert(insert_index, {"domain_suffix": domain, "outbound": "direct"})
            insert_index += 1
            dns_rules.append({"domain_suffix": domain, "server": "bootstrap"})

        # --- USER ROUTING RULES (Direct / Proxy / Block) ---
        if routing_rules:
            # Helper: Validate IP/CIDR
            def is_valid_ip_cidr(val):
                try:
                    ipaddress.ip_network(val, strict=False)
                    return True
                except ValueError:
                    return False

            for action in ["direct", "proxy", "block"]:
                if action not in routing_rules:
                    continue

                targets = routing_rules[action]
                outbound_tag = action

                s_ips = []
                s_domains = []
                s_domain_suffixes = []

                for t in targets:
                    t = t.strip()
                    if not t:
                        continue

                    # 1. Handle IP/CIDR
                    if is_valid_ip_cidr(t):
                        s_ips.append(t)
                        continue

                    # 2. Handle Tags
                    lower_t = t.lower()
                    if lower_t.startswith("geosite:") or lower_t.startswith("geoip:"):
                        # Incompatible with Singbox loose config (needs .db or rule_set)
                        # We skip to prevent crash, but maybe log it?
                        # logger.debug(f"Skipping Xray tag for Singbox: {t}")
                        continue

                    if lower_t.startswith("domain:"):
                        s_domain_suffixes.append(
                            t[7:]
                        )  # treat 'domain:' as suffix in xray usually means substring/suffix
                    elif lower_t.startswith("full:"):
                        s_domains.append(t[5:])  # exact match
                    else:
                        # Default assumption: It's a domain suffix (e.g. "google.com")
                        s_domain_suffixes.append(t)

                # Add Rules
                if s_ips:
                    rules.append({"ip_cidr": s_ips, "outbound": outbound_tag})

                if s_domains:
                    rules.append({"domain": s_domains, "outbound": outbound_tag})
                    if outbound_tag == "direct":
                        dns_rules.append({"domain": s_domains, "server": "bootstrap"})

                if s_domain_suffixes:
                    rules.append({"domain_suffix": s_domain_suffixes, "outbound": outbound_tag})
                    if outbound_tag == "direct":
                        dns_rules.append({"domain_suffix": s_domain_suffixes, "server": "bootstrap"})

        # 3. Country routing
        if routing_country and routing_country.lower() != "none":
            rule_sets_mapping = SINGBOX_RULE_SETS
            country = routing_country.lower()
            logger.info(f"[SingboxService] Applying country-based routing for: {country}")

            if country in rule_sets_mapping:
                if "rule_set" not in cfg["route"]:
                    cfg["route"]["rule_set"] = []

                for idx, url in enumerate(rule_sets_mapping[country]):
                    tag_name = f"{country}-rules-{idx}"
                    logger.debug(f"[SingboxService] Adding rule set: {tag_name} from {url}")

                    cfg["route"]["rule_set"].append(
                        {
                            "tag": tag_name,
                            "type": "remote",
                            "format": "binary",
                            "url": url,
                            "download_detour": "direct",
                            "update_interval": "24h",
                        }
                    )
                    # Insert country rules BEFORE final proxy rule
                    rules.append({"rule_set": tag_name, "outbound": "direct"})
                    dns_rules.append({"rule_set": tag_name, "server": "bootstrap"})
                    logger.info(f"[SingboxService] Country rule added: {tag_name} -> direct")
            else:
                logger.warning(f"[SingboxService] Unknown country code '{country}'")

        # Log final routing configuration for debugging
        logger.debug(f"[SingboxService] Total routing rules: {len(rules)}")
        logger.debug(f"[SingboxService] Total DNS rules: {len(dns_rules)}")
        for idx, rule in enumerate(rules[:10]):  # Log first 10 rules
            logger.debug(f"[SingboxService] Route rule {idx}: {rule}")

        return cfg
