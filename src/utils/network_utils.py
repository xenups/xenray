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
    def check_internet_connection(host=None, port=None, timeout=2, retries=2):
        """
        Check if there is an active internet connection by connecting to reliable HTTPS/HTTP endpoints.
        Uses Cloudflare (1.1.1.1:443) and Google (8.8.8.8:443) to prevent Windows WinError 10013 socket errors.

        Args:
            host: Optional specific host to connect to
            port: Optional specific port to connect to
            timeout: Timeout in seconds for each attempt (default: 2)
            retries: Number of retry attempts (default: 2)

        Returns:
            True if connection succeeds, False otherwise
        """
        targets = [(host, port)] if host and port else [("1.1.1.1", 443), ("8.8.8.8", 443), ("1.0.0.1", 80)]
        for attempt in range(retries):
            for target_host, target_port in targets:
                try:
                    socket.setdefaulttimeout(timeout)
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((target_host, target_port))
                    return True
                except Exception as e:
                    logger.debug(f"Internet check attempt {attempt + 1} ({target_host}:{target_port}) failed: {e}")
                    continue
            if attempt < retries - 1:
                import time

                time.sleep(0.3)
        logger.debug(f"Internet connection check failed after {retries} attempts")
        return False

    @staticmethod
    def check_proxy_connectivity(
        port: int,
        target_url=None,
        timeout=2,
        retries=1,
    ) -> bool:
        """
        Check connectivity through a local SOCKS5 proxy using concurrent curl requests.

        Args:
            port: SOCKS5 proxy port
            target_url: Optional URL to test connectivity.
            timeout: Timeout in seconds for each attempt (default: 2)
            retries: Number of retry attempts (default: 1)

        Returns:
            True if connectivity is confirmed through the proxy, False otherwise
        """
        curl_path = shutil.which("curl")
        if not curl_path:
            logger.warning("curl not found, skipping proxy connectivity check")
            return True

        default_targets = [
            "https://cp.cloudflare.com/generate_204",
            "https://www.gstatic.com/generate_204",
            "http://www.gstatic.com/generate_204",
        ]

        if target_url and target_url not in default_targets:
            targets = [target_url] + default_targets
        else:
            targets = default_targets

        conn_timeout_str = str(min(timeout, 2))
        max_time_str = str(min(timeout, 2))

        def _test_single_url(url: str) -> bool:
            cmd = [
                curl_path,
                "-x",
                f"socks5h://127.0.0.1:{port}",
                url,
                "--connect-timeout",
                conn_timeout_str,
                "--max-time",
                max_time_str,
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
                        if code.isdigit() and int(code) > 0:
                            logger.info(f"[NetworkUtils] Proxy check to {url} returned: {code}")
                            return True
                except Exception as e:
                    logger.debug(f"[NetworkUtils] Single proxy check to {url} error: {e}")
            return False

        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=len(targets)) as executor:
            futures = [executor.submit(_test_single_url, u) for u in targets]
            for future in as_completed(futures):
                if future.result():
                    executor.shutdown(wait=False, cancel_futures=True)
                    return True

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
