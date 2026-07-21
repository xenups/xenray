"""Network utilities."""
import os
import shutil
import socket
import subprocess

from src.core.logger import logger
from src.utils.platform_utils import PlatformUtils


class NetworkUtils:
    """Utilities for network operations."""

    @staticmethod
    def check_internet_connection(host="8.8.8.8", port=53, timeout=3, retries=3):
        """
        Check if there is an active internet connection by connecting to a reliable host.
        Default is Google DNS (8.8.8.8) on port 53 (DNS).

        Args:
            host: Host to connect to
            port: Port to connect to
            timeout: Timeout in seconds for each attempt
            retries: Number of retry attempts (default: 3)

        Returns:
            True if connection succeeds, False otherwise
        """
        for attempt in range(retries):
            try:
                socket.setdefaulttimeout(timeout)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((host, port))
                return True
            except Exception as e:
                if attempt < retries - 1:
                    logger.debug(f"Internet check attempt {attempt + 1}/{retries} failed: {e}")
                    import time

                    time.sleep(0.5)  # Brief delay between retries
                else:
                    logger.warning(f"Internet connection check failed after {retries} attempts: {e}")
        return False

    @staticmethod
    def check_proxy_connectivity(
        port: int,
        target_url=None,
        timeout=5,
        retries=2,
    ) -> bool:
        """
        Check connectivity through a local SOCKS5 proxy using curl with fallback target URLs.

        Args:
            port: SOCKS5 proxy port
            target_url: Optional URL to test connectivity. If None or default, uses robust HTTPS/HTTP fallbacks.
            timeout: Timeout in seconds for each attempt
            retries: Number of retry attempts (default: 2)

        Returns:
            True if connectivity is confirmed through the proxy, False otherwise
        """
        curl_path = shutil.which("curl")
        if not curl_path:
            logger.warning("curl not found, skipping proxy connectivity check")
            return True

        # Candidate targets: Encrypted HTTPS first (avoids ISP HTTP port 80 resets on DPI/fragmented links),
        # followed by plain HTTP fallbacks.
        default_targets = [
            "https://cp.cloudflare.com/generate_204",
            "https://www.gstatic.com/generate_204",
            "http://www.gstatic.com/generate_204",
        ]

        if target_url and target_url not in default_targets:
            targets = [target_url] + default_targets
        else:
            targets = default_targets

        max_time = str(max(timeout, 6))
        connect_timeout = str(min(timeout, 5))

        for url in targets:
            cmd = [
                curl_path,
                "-x",
                f"socks5h://127.0.0.1:{port}",
                url,
                "--connect-timeout",
                connect_timeout,
                "--max-time",
                max_time,
                "-s",
                "-o",
                os.devnull,
                "-w",
                "%{http_code}",
            ]

            for attempt in range(retries):
                try:
                    startupinfo = PlatformUtils.get_startupinfo()

                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        creationflags=PlatformUtils.get_subprocess_flags(),
                        startupinfo=startupinfo,
                        check=False,
                    )

                    if result.returncode == 0:
                        code = result.stdout.strip()
                        logger.info(f"Proxy check to {url} returned: {code}")
                        # Any valid HTTP status code (2xx, 3xx, 4xx, 5xx) proves the proxy tunnel is intact
                        if code.isdigit() and int(code) > 0:
                            return True
                    else:
                        logger.debug(f"Proxy check to {url} attempt {attempt + 1}/{retries} failed: {result.stderr}")

                    if attempt < retries - 1:
                        import time

                        time.sleep(0.5)

                except Exception as e:
                    logger.debug(f"Proxy check error to {url}: {e}")
                    if attempt < retries - 1:
                        import time

                        time.sleep(0.5)

        return False

    @staticmethod
    def detect_optimal_mtu(host="8.8.8.8", min_mtu=1280, max_mtu=1480, timeout=2, mtu_mode="auto") -> int:
        """
        Detect optimal MTU using ping with Don't Fragment flag.
        Uses binary search to find the largest non-fragmented MTU.

        IMPORTANT: This detects ICMP MTU only. Real-world VPN/tunnel overhead
        means the actual safe MTU for TCP/UDP/QUIC may be lower.

        MTU Strategy:
        - max_mtu = 1480 (not 1500) to account for VPN/tunnel overhead
        - min_mtu = 1280 for IPv6 compatibility
        - Only even MTU values are tested (odd values are invalid)
        - Result is treated as an upper bound, not guaranteed optimal
        - For QUIC transports, use mtu_mode="quic_safe" for fixed 1420

        Args:
            host: Host to ping for MTU detection (default: 8.8.8.8)
            min_mtu: Minimum MTU to test (default: 1280 for IPv6)
            max_mtu: Maximum MTU to test (default: 1480 for VPN safety)
            timeout: Timeout for each ping attempt in seconds
            mtu_mode: Detection mode - "auto" for ICMP detection, "quic_safe" for fixed 1420

        Returns:
            Optimal MTU value (defaults to 1420 if detection fails)
        """
        import platform

        # Default safe MTU if detection fails
        default_mtu = 1420

        # QUIC-safe mode: skip detection and return fixed MTU
        if mtu_mode == "quic_safe":
            logger.info("MTU mode: quic_safe - using fixed MTU 1420")
            return default_mtu

        # Auto mode: perform ICMP-based detection
        logger.info(f"MTU mode: auto - detecting optimal MTU (range: {min_mtu}-{max_mtu})...")

        # Platform-specific ping commands
        system = platform.system().lower()

        def test_mtu(mtu_size: int) -> bool:
            """Test if a specific MTU size works."""
            try:
                # Calculate payload size (MTU - IP header - ICMP header)
                # IP header: 20 bytes, ICMP header: 8 bytes
                payload_size = mtu_size - 28

                if payload_size <= 0:
                    return False

                # Build ping command based on platform
                if system == "windows":
                    # Windows: ping -n 1 -w timeout -f -l size host
                    cmd = [
                        "ping",
                        "-n",
                        "1",  # Send 1 packet
                        "-w",
                        str(timeout * 1000),  # Timeout in milliseconds
                        "-f",  # Don't fragment
                        "-l",
                        str(payload_size),  # Packet size
                        host,
                    ]
                else:
                    # Linux/Mac: ping -c 1 -W timeout -M do -s size host
                    cmd = [
                        "ping",
                        "-c",
                        "1",  # Send 1 packet
                        "-W",
                        str(timeout),  # Timeout in seconds
                        "-M",
                        "do",  # Don't fragment
                        "-s",
                        str(payload_size),  # Packet size
                        host,
                    ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout + 1,
                    creationflags=PlatformUtils.get_subprocess_flags(),
                    startupinfo=PlatformUtils.get_startupinfo(),
                )

                # Success if return code is 0 (ping succeeded)
                return result.returncode == 0

            except Exception as e:
                logger.debug(f"MTU test for {mtu_size} failed: {e}")
                return False

        try:
            # Binary search for optimal MTU
            low = min_mtu
            high = max_mtu
            optimal_mtu = default_mtu

            while low <= high:
                # Calculate midpoint and normalize to even value
                # MTU values must be even; odd values are invalid
                mid = ((low + high) // 2) & ~1

                if test_mtu(mid):
                    # This MTU works, try larger
                    optimal_mtu = mid
                    low = mid + 2  # Jump by 2 to stay on even values
                else:
                    # This MTU is too large, try smaller
                    high = mid - 2  # Jump by 2 to stay on even values

            logger.info(f"Detected optimal MTU: {optimal_mtu}")
            return optimal_mtu

        except Exception as e:
            logger.warning(f"MTU detection failed: {e}, using default {default_mtu}")
            return default_mtu
