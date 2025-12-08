"""Connection Tester Service."""
import json
import os
import socket
import subprocess
import threading
import time
import requests
import uuid
from typing import Optional, Tuple

from src.core.constants import XRAY_EXECUTABLE, TMPDIR
from src.core.logger import logger
from src.utils.process_utils import ProcessUtils

# Timeout configuration
TEST_TIMEOUT = 5  # seconds for the whole test
CONNECT_TIMEOUT = 3 # seconds for HTTP request

class ConnectionTester:
    """Tests real connection latency via Xray Core."""

    @staticmethod
    def _find_free_port() -> int:
        """Find a free local port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    @staticmethod
    def _create_temp_config(listen_port: int, outbound_config: dict) -> str:
        """Create a temporary Xray config for testing."""
        config = {
            "log": {
                "loglevel": "none"
            },
            "inbounds": [
                {
                    "port": listen_port,
                    "protocol": "http",
                    "settings": {
                        "allowTransparent": False
                    },
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls"]
                    }
                }
            ],
            "outbounds": [
                outbound_config,
                {
                    "protocol": "freedom",
                    "tag": "direct"
                }
            ]
        }
        
        filename = f"test_{uuid.uuid4()}.json"
        path = os.path.join(TMPDIR, filename)
        
        try:
            with open(path, 'w') as f:
                json.dump(config, f)
            return path
        except Exception as e:
            logger.error(f"[ConnectionTester] Failed to write temp config: {e}")
            return ""

    @staticmethod
    def test_connection_sync(profile_config: dict) -> Tuple[bool, str]:
        """
        Test connection for a profile synchronously.
        Returns (success, latency_ms_str).
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
                return False, "Invalid Config"

        # 1. Prepare environment
        port = ConnectionTester._find_free_port()
        config_path = ConnectionTester._create_temp_config(port, target_outbound)
        
        if not config_path:
            return False, "Config Error"

        process = None
        try:
            # 2. Start partial Xray
            # Run without log output for speed
            cmd = [XRAY_EXECUTABLE, "run", "-c", config_path]
            
            # Using startupinfo to hide window on Windows
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo
            )
            
            # Give it a moment to bind port
            time.sleep(0.5)
            
            if process.poll() is not None:
                return False, "Core Failed"

            # 3. Test Connection
            proxies = {
                "http": f"http://127.0.0.1:{port}",
                "https": f"http://127.0.0.1:{port}",
            }
            
            # Target URL: Use something reliable and fast (Cloudflare trace or Google 204)
            target_url = "http://cp.cloudflare.com/"
            
            start_time = time.time()
            response = requests.get(
                target_url, 
                proxies=proxies, 
                timeout=CONNECT_TIMEOUT
            )
            
            latency = int((time.time() - start_time) * 1000)
            
            if response.status_code == 204 or (200 <= response.status_code < 300):
                 # "Real Delay" often adds ~100ms overhead for process startup/proxying
                 # but it's accurate for "is it working".
                return True, f"{latency}ms"
            else:
                return False, f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            return False, "Timeout"
        except requests.exceptions.RequestException:
            return False, "Conn Error"
        except Exception as e:
            return False, "Error"
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
    def test_connection(profile_config: dict, callback):
        """Run test in a dedicated thread and invoke callback(success, result_str)."""
        def _wrapper():
            success, result = ConnectionTester.test_connection_sync(profile_config)
            if callback:
                callback(success, result)
        
        threading.Thread(target=_wrapper, daemon=True).start()
