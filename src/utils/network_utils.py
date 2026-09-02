import ipaddress
import os
import shutil
import socket
import subprocess
from typing import List, Union

from src.core.constants import DNS_IP_GOOGLE
from src.core.logger import logger
from src.platform.factory import get_network_adapter, get_process_adapter


class NetworkUtils:
    """Utilities for network operations."""

    @staticmethod
    def normalize_list(value: Union[str, List[str], None]) -> List[str]:
        """Normalize input to a cleaned list of lowercase strings."""
        if not value:
            return []
        if isinstance(value, str):
            value = [value]
        return [
            item.strip().lower().replace("'", "").replace('"', "").replace("[", "").replace("]", "")
            for item in value
            if isinstance(item, str)
        ]

    @staticmethod
    def filter_real_ips(lst: List[str]) -> List[str]:
        """Return only the entries that are valid IP addresses."""
        result = []
        for item in lst:
            try:
                ipaddress.ip_address(item)
                result.append(item)
            except (ValueError, ipaddress.AddressValueError):
                continue
        return result

    @staticmethod
    def filter_domains(lst: List[str]) -> List[str]:
        """Return only the entries that are domain names (not IPs)."""
        valid_ips: set = set(NetworkUtils.filter_real_ips(lst))
        return [item for item in lst if item not in valid_ips]

    @staticmethod
    def is_valid_ip_cidr(val: str) -> bool:
        """Check if string is a valid IP or CIDR network notation."""
        try:
            ipaddress.ip_network(val, strict=False)
            return True
        except ValueError:
            return False

    @staticmethod
    def is_ipv4(val: str) -> bool:
        """True when val is a literal IPv4 (not a domain or IPv6)."""
        try:
            ipaddress.ip_address(val)
            return val.count(".") == 3
        except ValueError:
            return False

    @staticmethod
    def check_internet_connection(host=DNS_IP_GOOGLE, port=53, timeout=3, retries=3):
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
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(timeout)
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
        timeout=2.5,
        retries=2,
    ) -> bool:
        """
        Check connectivity through a local SOCKS5 proxy using curl with fallback target URLs.

        Each endpoint gets exactly 1 attempt — if it fails, failover immediately
        to the next fallback endpoint (no retrying the same dead URL).

        Args:
            port: SOCKS5 proxy port
            target_url: Optional URL to test. If None, uses robust HTTPS/HTTP fallbacks.
            timeout: Max seconds per request (default 2.5)
            retries: Number of fallback endpoints to try (default 2)

        Returns:
            True if connectivity is confirmed through the proxy, False otherwise
        """
        curl_path = shutil.which("curl")
        if not curl_path:
            # Fail-CLOSED: without curl the heavy probe cannot verify
            # end-to-end routing through the proxy, so report the probe as
            # FAILED rather than pretending connectivity is fine. A missing
            # curl must never mask real connectivity loss.
            logger.warning("curl not found — proxy connectivity check FAILED (fail-closed)")
            return False

        default_targets = [
            "https://cp.cloudflare.com/generate_204",
            "https://www.gstatic.com/generate_204",
            "http://www.gstatic.com/generate_204",
        ]

        if target_url and target_url not in default_targets:
            targets = [target_url] + default_targets
        else:
            targets = default_targets

        connect_timeout = str(max(timeout, 2))

        for url in targets[:retries]:
            cmd = [
                curl_path,
                "-x",
                f"socks5h://127.0.0.1:{port}",
                url,
                "--connect-timeout",
                connect_timeout,
                "--max-time",
                connect_timeout,
                "-s",
                "-o",
                os.devnull,
                "-w",
                "%{http_code}",
            ]

            try:
                startupinfo = get_process_adapter().get_startupinfo()

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    creationflags=get_process_adapter().get_subprocess_flags(),
                    startupinfo=startupinfo,
                    check=False,
                )

                if result.returncode == 0:
                    code = result.stdout.strip()
                    logger.info(f"Proxy check to {url} returned: {code}")
                    if code.isdigit() and int(code) > 0:
                        return True
                else:
                    logger.debug(f"Proxy check to {url} failed: {result.stderr}")

            except Exception as e:
                logger.debug(f"Proxy check error to {url}: {e}")

        return False

    @staticmethod
    def detect_optimal_mtu(host=DNS_IP_GOOGLE, min_mtu=1280, max_mtu=1480, timeout=2, mtu_mode="auto") -> int:
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
        default_mtu = 1420

        # QUIC-safe mode: skip detection and return fixed MTU
        if mtu_mode == "quic_safe":
            logger.info("MTU mode: quic_safe - using fixed MTU 1420")
            return default_mtu

        # Auto mode: perform ICMP-based detection
        logger.info(f"MTU mode: auto - detecting optimal MTU (range: {min_mtu}-{max_mtu})...")

        network_adapter = get_network_adapter()

        def test_mtu(mtu_size: int) -> bool:
            """Test if a specific MTU size works."""
            # Calculate payload size (MTU - IP header (20) - ICMP header (8))
            payload_size = mtu_size - 28
            if payload_size <= 0:
                return False
            return network_adapter.ping_mtu(host, payload_size, timeout)

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
