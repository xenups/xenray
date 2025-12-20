"""Network interface utilities for Windows."""
import re
import subprocess
from typing import Optional, Tuple

from loguru import logger

from src.utils.platform_utils import PlatformUtils

# Constants
ROUTE_COMMAND_TIMEOUT = 5  # seconds
IPCONFIG_COMMAND_TIMEOUT = 5  # seconds
TUN_INTERFACE_KEYWORDS = {"SING", "TUN", "TAP"}


class NetworkInterfaceDetector:
    """Detects primary network interface on Windows."""

    @staticmethod
    def get_primary_interface() -> (
        Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]
    ):
        """
        Get primary network interface details.

        Returns:
            Tuple of (interface_name, interface_ip, subnet, gateway)
            e.g., ("Wi-Fi", "192.168.1.10", "192.168.1.0/24", "192.168.1.1")
        """
        try:
            # Get default route to find primary interface
            result = subprocess.run(
                ["route", "print", "0.0.0.0"],
                capture_output=True,
                text=True,
                timeout=ROUTE_COMMAND_TIMEOUT,
                check=False,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )

            if result.returncode != 0:
                logger.error(f"Failed to get route table: {result.stderr}")
                return None, None, None, None

            # Parse route output to find default gateway
            # Looking for line like: "0.0.0.0          0.0.0.0     192.168.1.1    192.168.1.10     25"
            for line in result.stdout.split("\n"):
                if "0.0.0.0" in line and line.count("0.0.0.0") >= 2:
                    parts = line.split()
                    if len(parts) >= 4:
                        gateway = parts[2]
                        interface_ip = parts[3]

                        # Validate IP addresses
                        if not NetworkInterfaceDetector._is_valid_ip(gateway):
                            continue
                        if not NetworkInterfaceDetector._is_valid_ip(interface_ip):
                            continue

                        # Get interface name from IP
                        interface_name = NetworkInterfaceDetector._get_interface_name(
                            interface_ip
                        )

                        # Fix: Ignore Sing-box TUN interface to prevent loops
                        if interface_name:
                            interface_upper = interface_name.upper()
                            if any(
                                keyword in interface_upper
                                for keyword in TUN_INTERFACE_KEYWORDS
                            ):
                                logger.warning(
                                    f"Ignored potential TUN interface: {interface_name}"
                                )
                                continue

                        # Calculate subnet (assume /24 for simplicity)
                        subnet = NetworkInterfaceDetector._calculate_subnet(
                            interface_ip
                        )

                        logger.info(
                            f"Detected primary interface: {interface_name} ({interface_ip}, {subnet}, {gateway})"
                        )
                        return interface_name, interface_ip, subnet, gateway

            logger.warning("Could not detect primary interface from route table")
            return None, None, None, None

        except subprocess.TimeoutExpired:
            logger.error("Timeout while getting route table")
            return None, None, None, None
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Error detecting primary interface: {e}")
            return None, None, None, None
        except Exception as e:
            logger.error(f"Unexpected error detecting primary interface: {e}")
            return None, None, None, None

    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        """Check if string is a valid IP address."""
        if not ip:
            return False
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(part) <= 255 for part in parts)
        except ValueError:
            return False

    @staticmethod
    def _get_interface_name(ip: str) -> Optional[str]:
        """Get interface name from IP address using ipconfig."""
        if not NetworkInterfaceDetector._is_valid_ip(ip):
            return None

        try:
            result = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                timeout=IPCONFIG_COMMAND_TIMEOUT,
                check=False,
                creationflags=PlatformUtils.get_subprocess_flags(),
                startupinfo=PlatformUtils.get_startupinfo(),
            )

            if result.returncode != 0:
                logger.warning("Failed to run ipconfig")
                return None

            # Parse ipconfig output
            current_adapter = None
            for line in result.stdout.split("\n"):
                # Check for adapter name
                if "adapter" in line.lower():
                    # Extract adapter name
                    match = re.search(r"adapter (.+?):", line, re.IGNORECASE)
                    if match:
                        current_adapter = match.group(1).strip()

                # Check for IPv4 address
                if "IPv4 Address" in line and ip in line:
                    return current_adapter

            return None

        except subprocess.TimeoutExpired:
            logger.warning("Timeout while running ipconfig")
            return None
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Error getting interface name: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting interface name: {e}")
            return None

    @staticmethod
    def _calculate_subnet(ip: str) -> str:
        """Calculate subnet from IP (assumes /24)."""
        if not NetworkInterfaceDetector._is_valid_ip(ip):
            return f"{ip}/32"

        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        return f"{ip}/32"
