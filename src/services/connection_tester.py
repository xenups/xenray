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
TEST_TIMEOUT = 5  # seconds for the whole test
CONNECT_TIMEOUT = 3  # seconds for HTTP request


class ConnectionTester:
    """Tests real connection latency via Xray Core."""

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
        """Create a temporary Xray config for testing."""
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
                    "streamSettings": {"sockopt": {"mark": 255}},
                },
            ],
        }

        # Inject Mark 255 into the User's Outbound Config as well
        # This ensures the connection to the proxy server itself bypasses the Tun
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
        profile_config: dict, fetch_country: bool = False
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Test connection for a profile synchronously.
        Returns (success, latency_ms_str, country_data).
        country_data is {'code': 'XX', 'name': 'Country'} or None.
        This must be run in a thread.
        """
        # Find the first valid outbound (vmess/vless/etc)
        target_outbound = None
        if "outbounds" in profile_config:
            # Try to find the proxy outbound
            for out in profile_config["outbounds"]:
                if out.get("protocol") not in ["freedom", "blackhole", "dns"]:
                    target_outbound = out
                    break

        # If no specific outbound found (e.g. raw vless config object), assume it is the outbound
        if not target_outbound:
            # Check if the profile_config itself looks like an outbound
            if "protocol" in profile_config:
                target_outbound = profile_config
            else:
                return False, t("connection.invalid_config"), None

        # 1. Prepare environment
        port = ConnectionTester._find_free_port()
        config_path = ConnectionTester._create_temp_config(port, target_outbound)

        if not config_path:
            return False, t("connection.error"), None

        process = None
        try:
            # 2. Start partial Xray
            # Run without log output for speed
            cmd = [XRAY_EXECUTABLE, "run", "-c", config_path]

            # Using startupinfo to hide window on Windows
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # Give it a moment to bind port
            time.sleep(0.5)

            if process.poll() is not None:
                return False, t("connection.core_failed"), None

            # 3. Test Connection
            proxies = {
                "http": f"http://127.0.0.1:{port}",
                "https": f"http://127.0.0.1:{port}",
            }

            # Target URL: Use something reliable and fast
            target_url = "http://cp.cloudflare.com/"

            start_time = time.time()
            response = requests.get(
                target_url, proxies=proxies, timeout=CONNECT_TIMEOUT
            )

            latency = int((time.time() - start_time) * 1000)

            country_data = None
            # ANY response means connection works! Even 5xx errors mean proxy is functional.
            # The key is that we got a response through the proxy tunnel.
            if response.status_code:  # Any response code = success
                if fetch_country:
                    try:
                        # Use ip-api via the same proxy
                        geo_resp = requests.get(
                            "http://ip-api.com/json", proxies=proxies, timeout=3
                        )
                        if geo_resp.status_code == 200:
                            gdata = geo_resp.json()
                            if gdata.get("status") == "success":
                                country_data = {
                                    "country_code": gdata.get("countryCode"),
                                    "country_name": gdata.get("country"),
                                    "city": gdata.get("city"),
                                }
                    except:
                        pass  # Fail silently for geoip

                return True, t("connection.latency_ms", value=latency), country_data

        except requests.exceptions.Timeout:
            return False, t("connection.timeout"), None
        except requests.exceptions.RequestException:
            return False, t("connection.conn_error"), None
        except Exception as e:
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
                except:
                    pass

    @staticmethod
    def test_connection(profile_config: dict, callback, fetch_country: bool = False):
        """Run test in a dedicated thread and invoke callback(success, result_str, country_data)."""

        def _wrapper():
            success, result, country_data = ConnectionTester.test_connection_sync(
                profile_config, fetch_country
            )
            if callback:
                callback(success, result, country_data)

        threading.Thread(target=_wrapper, daemon=True).start()
