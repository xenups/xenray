"""Network utilities."""
import socket
import subprocess
import shutil
from src.core.logger import logger

class NetworkUtils:
    """Utilities for network operations."""

    @staticmethod
    def check_internet_connection(host="8.8.8.8", port=53, timeout=3):
        """
        Check if there is an active internet connection by connecting to a reliable host.
        Default is Google DNS (8.8.8.8) on port 53 (DNS).
        """
        try:
            socket.setdefaulttimeout(timeout)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((host, port))
            return True
        except Exception as e:
            logger.warning(f"Internet connection check failed: {e}")
            return False

    @staticmethod
    def check_proxy_connectivity(port: int, target_url="http://www.gstatic.com/generate_204", timeout=5) -> bool:
        """
        Check connectivity through a local SOCKS5 proxy using curl.
        Returns True if successful (HTTP 204/200), False otherwise.
        """
        curl_path = shutil.which("curl")
        if not curl_path:
            logger.warning("curl not found, skipping proxy connectivity check")
            # If curl is missing, we assume success to avoid blocking users on constrained systems
            return True

        # Command: curl -x socks5h://127.0.0.1:PORT URL --connect-timeout N
        # -I might hang if HEAD not supported, so just GET and check status
        # -s for silent, -o /dev/null (or NUL on windows) to verify execution
        # -w "%{http_code}" to get status code
        cmd = [
            curl_path,
            "-x", f"socks5h://127.0.0.1:{port}",
            target_url,
            "--connect-timeout", str(timeout),
            "-s",
            "-o", "NUL",
            "-w", "%{http_code}"
        ]

        try:
            # CREATE_NO_WINDOW for windows consistency if run from valid env
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                startupinfo=startupinfo,
                check=False
            )
            
            if result.returncode == 0:
                code = result.stdout.strip()
                logger.info(f"Proxy check to {target_url} returned: {code}")
                if code in ["200", "204"]:
                    return True
            else:
                logger.warning(f"Proxy check curl failed: {result.stderr}")
                
            return False
        except Exception as e:
            logger.error(f"Proxy connectivity check error: {e}")
            # If check outright crashes, fail safe? Or block?
            # Let's return False to be safe as requested by user.
            return False
