"""Connection Tester Service."""

import json
import os
import socket
import subprocess
import threading
import time
import uuid
from typing import Optional, Tuple

import requests

from src.core.constants import TMPDIR, XRAY_EXECUTABLE
from src.core.i18n import t
from src.core.logger import logger

# Timeout configuration
TEST_TIMEOUT = 10  # seconds for the whole test
CONNECT_TIMEOUT = 3  # hard per-node timeout for the HTTP latency probe

# v2rayNG-style latency probing: dedicated HTTP 204 No-Content endpoints with a
# zero-byte body. Primary endpoint first, then a fallback. The probe measures the
# handshake + first-byte (status header) RTT and never downloads a body.
GENERATE_204_URLS = [
    "http://www.gstatic.com/generate_204",
    "http://cp.cloudflare.com/generate_204",
]

# SO_MARK is Linux-only; omitted on Windows where sing-box TUN
# provides bypass via ip_cidr / process_name route rules instead.
_IS_WINDOWS = os.name == "nt"


class ConnectionTester:
    """Tests real connection latency via Xray Core."""

    @staticmethod
    def _probe_204(proxies: dict, timeout: float = CONNECT_TIMEOUT) -> Tuple[bool, int]:
        """Measure handshake + first-byte RTT to a 204 No-Content endpoint.

        Uses ``stream=True`` and never reads the response body, so the latency
        reflects how long the proxy takes to reach the endpoint's status header —
        matching v2rayNG-style delay numbers instead of full-body downloads.
        Each endpoint gets one attempt, then we fail over to the next URL.

        Returns (ok, latency_ms).
        """
        for url in GENERATE_204_URLS:
            start_time = time.time()
            try:
                with requests.get(url, proxies=proxies, timeout=timeout, stream=True) as resp:
                    latency = int((time.time() - start_time) * 1000)
                    if resp.status_code < 400:
                        return True, latency
            except (
                requests.exceptions.Timeout,
                requests.exceptions.RequestException,
                OSError,
            ):
                continue
        return False, 0

    @staticmethod
    def _find_free_port() -> int:
        """Find a free local port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    @staticmethod
    def _create_temp_config(listen_port: int, outbound_config: dict) -> str:
        """Create a temporary Xray config for testing.

        On Windows the SO_MARK socket option is silently ignored by the
        kernel, so we skip it entirely.
        """
        config = {
            "log": {"loglevel": "none"},
            "inbounds": [
                {
                    "port": listen_port,
                    "protocol": "http",
                    "settings": {"allowTransparent": False},
                    "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
                }
            ],
            "outbounds": [
                outbound_config,
                {
                    "protocol": "freedom",
                    "tag": "direct",
                },
            ],
        }

        # On Linux, mark=255 helps bypass VPN routing for the test Xray.
        # Omitted on Windows (no-op / may cause warnings).
        if not _IS_WINDOWS:
            if "streamSettings" not in config["outbounds"][0]:
                config["outbounds"][0]["streamSettings"] = {}
            if "sockopt" not in config["outbounds"][0]["streamSettings"]:
                config["outbounds"][0]["streamSettings"]["sockopt"] = {}
            config["outbounds"][0]["streamSettings"]["sockopt"]["mark"] = 255

        filename = f"test_{uuid.uuid4()}.json"
        path = os.path.join(TMPDIR, filename)

        try:
            with open(path, "w") as f:
                json.dump(config, f)
            return path
        except Exception as e:
            logger.error(f"[ConnectionTester] Failed to write temp config: {e}")
            return ""

    @staticmethod
    def test_connection_sync(
        profile_config: dict,
        fetch_country: bool = False,
        socks_port: int = 0,
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Test connection for a profile synchronously.

        When *socks_port* is > 0 the test is performed through an existing Xray
        SOCKS proxy directly (avoids spawning a second Xray that would be
        disrupted by the sing-box TUN on Windows).

        Returns (success, latency_ms_str, country_data).
        country_data is {'code': 'XX', 'name': 'Country'} or None.
        This must be run in a thread.
        """
        # ── SOCKS proxy mode (bypass TUN interference on Windows) ──
        # For the real end-to-end check we route an HTTP/generate_204 probe
        # through the existing SOCKS proxy. A bare TCP connect to the proxy port
        # does NOT prove the tunnel routes data, so no TCP-only fallback is used:
        # if the HTTP probe cannot reach a remote endpoint, the check fails.
        if socks_port:
            from src.utils.network_utils import NetworkUtils

            start_time = time.time()
            if NetworkUtils.check_proxy_connectivity(socks_port):
                latency = int((time.time() - start_time) * 1000)
                logger.info(f"[ConnectionTester] SOCKS proxy verified at 127.0.0.1:{socks_port} ({latency}ms)")
                return (True, t("connection.latency_ms", value=latency), None)

            logger.warning(f"[ConnectionTester] HTTP health check failed through SOCKS proxy {socks_port}")
            return False, t("connection.conn_error"), None

        # ── Direct Xray instance mode (proxy mode / Linux) ──
        # Find the first valid outbound (vmess/vless/etc)
        target_outbound = None
        if "outbounds" in profile_config:
            for out in profile_config["outbounds"]:
                if out.get("protocol") not in ["freedom", "blackhole", "dns"]:
                    target_outbound = out
                    break

        if not target_outbound:
            if "protocol" in profile_config:
                target_outbound = profile_config
            else:
                return False, t("connection.invalid_config"), None

        port = ConnectionTester._find_free_port()
        config_path = ConnectionTester._create_temp_config(port, target_outbound)

        if not config_path:
            return False, t("connection.error"), None

        process = None
        try:
            cmd = [XRAY_EXECUTABLE, "run", "-c", config_path]

            from src.utils.platform_utils import PlatformUtils

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=PlatformUtils.get_startupinfo(),
                creationflags=PlatformUtils.get_subprocess_flags(),
            )

            time.sleep(2.5)

            if process.poll() is not None:
                return False, t("connection.core_failed"), None

            proxies = {
                "http": f"http://127.0.0.1:{port}",
                "https": f"http://127.0.0.1:{port}",
            }

            # v2rayNG-style probe: 204 No-Content endpoint, headers only. A single
            # retry rides out transient stalls; each request is bounded by the 3s
            # CONNECT_TIMEOUT and the probe never downloads a response body.
            for attempt in range(2):
                ok, latency = ConnectionTester._probe_204(proxies, timeout=CONNECT_TIMEOUT)
                if ok:
                    country_data = None
                    if fetch_country:
                        try:
                            geo_resp = requests.get("http://ip-api.com/json", proxies=proxies, timeout=3)
                            if geo_resp.status_code == 200:
                                gdata = geo_resp.json()
                                if gdata.get("status") == "success":
                                    country_data = {
                                        "country_code": gdata.get("countryCode"),
                                        "country_name": gdata.get("country"),
                                        "city": gdata.get("city"),
                                    }
                        except Exception:
                            pass  # country fetch is best-effort

                    return (
                        True,
                        t("connection.latency_ms", value=latency),
                        country_data,
                    )
                if attempt == 0:
                    time.sleep(0.3)

            return False, t("connection.conn_error"), None

        except Exception:
            return False, t("connection.error"), None
        finally:
            # 4. Cleanup
            if process:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()

            if os.path.exists(config_path):
                try:
                    os.remove(config_path)
                except Exception:
                    pass

    @staticmethod
    def test_connection(profile_config: dict, callback, fetch_country: bool = False):
        """Run test in a dedicated thread and invoke callback(success, result_str, country_data)."""

        def _wrapper():
            success, result, country_data = ConnectionTester.test_connection_sync(profile_config, fetch_country)
            if callback:
                callback(success, result, country_data)

        threading.Thread(target=_wrapper, daemon=True).start()
