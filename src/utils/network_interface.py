"""Network interface utilities - Cross-platform support."""
import re
import subprocess
from typing import Optional, Tuple

from loguru import logger

from src.utils.platform_utils import Platform, PlatformUtils

# Constants
ROUTE_COMMAND_TIMEOUT = 5  # seconds
IPCONFIG_COMMAND_TIMEOUT = 5  # seconds
TUN_INTERFACE_KEYWORDS = {"SING", "TUN", "TAP", "tun", "utun"}


class NetworkInterfaceDetector:
    """Detects primary network interface - cross-platform."""

    @staticmethod
    def get_primary_interface() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Get primary network interface details.

        Returns:
            Tuple of (interface_name, interface_ip, subnet, gateway)
            e.g., ("Wi-Fi", "192.168.1.10", "192.168.1.0/24", "192.168.1.1")
        """
        platform = PlatformUtils.get_platform()

        if platform == Platform.WINDOWS:
            return NetworkInterfaceDetector._get_primary_interface_windows()
        elif platform == Platform.LINUX:
            return NetworkInterfaceDetector._get_primary_interface_linux()
        elif platform == Platform.MACOS:
            return NetworkInterfaceDetector._get_primary_interface_macos()
        else:
            logger.warning(f"Unsupported platform for interface detection: {platform}")
            return None, None, None, None

    @staticmethod
    def _get_primary_interface_linux() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Get primary interface on Linux using 'ip' command."""
        try:
            # Get default route to find primary interface and gateway
            # ip route show default
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True,
                text=True,
                timeout=ROUTE_COMMAND_TIMEOUT,
                check=False,
            )

            if result.returncode != 0:
                logger.error(f"Failed to get route table on Linux: {result.stderr}")
                return None, None, None, None

            # Parse output like: "default via 192.168.1.1 dev wlp3s0 proto dhcp metric 600"
            for line in result.stdout.strip().split("\n"):
                if "default" in line:
                    parts = line.split()

                    # Find gateway (after "via") and interface (after "dev")
                    gateway = None
                    interface_name = None

                    for i, part in enumerate(parts):
                        if part == "via" and i + 1 < len(parts):
                            gateway = parts[i + 1]
                        elif part == "dev" and i + 1 < len(parts):
                            interface_name = parts[i + 1]

                    if not interface_name:
                        continue

                    # Skip TUN interfaces
                    if any(keyword in interface_name for keyword in TUN_INTERFACE_KEYWORDS):
                        logger.warning(f"Ignored TUN interface: {interface_name}")
                        continue

                    # Get interface IP using ip addr show
                    interface_ip = NetworkInterfaceDetector._get_interface_ip_linux(interface_name)

                    if interface_ip:
                        subnet = NetworkInterfaceDetector._calculate_subnet(interface_ip)
                        logger.info(
                            f"Detected primary interface: {interface_name} ({interface_ip}, {subnet}, {gateway})"
                        )
                        return interface_name, interface_ip, subnet, gateway

            logger.warning("Could not detect primary interface on Linux")
            return None, None, None, None

        except subprocess.TimeoutExpired:
            logger.error("Timeout while getting route table on Linux")
            return None, None, None, None
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Error detecting primary interface on Linux: {e}")
            return None, None, None, None
        except Exception as e:
            logger.error(f"Unexpected error detecting primary interface on Linux: {e}")
            return None, None, None, None

    @staticmethod
    def _get_interface_ip_linux(interface_name: str) -> Optional[str]:
        """Get IP address of a network interface on Linux."""
        try:
            result = subprocess.run(
                ["ip", "addr", "show", interface_name],
                capture_output=True,
                text=True,
                timeout=IPCONFIG_COMMAND_TIMEOUT,
                check=False,
            )

            if result.returncode != 0:
                return None

            # Parse output for inet (IPv4) address
            # Looking for: "inet 192.168.1.10/24 brd 192.168.1.255 scope global dynamic noprefixroute wlp3s0"
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line.startswith("inet "):
                    parts = line.split()
                    if len(parts) >= 2:
                        # Extract IP from CIDR notation (e.g., "192.168.1.10/24")
                        ip_cidr = parts[1]
                        ip = ip_cidr.split("/")[0]
                        if NetworkInterfaceDetector._is_valid_ip(ip):
                            return ip

            return None

        except Exception as e:
            logger.debug(f"Error getting IP for {interface_name}: {e}")
            return None

    @staticmethod
    def _get_primary_interface_macos() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Get primary interface on macOS using 'route' and 'ifconfig'."""
        try:
            # Get default route
            result = subprocess.run(
                ["route", "-n", "get", "default"],
                capture_output=True,
                text=True,
                timeout=ROUTE_COMMAND_TIMEOUT,
                check=False,
            )

            if result.returncode != 0:
                logger.error(f"Failed to get route on macOS: {result.stderr}")
                return None, None, None, None

            # Parse output for gateway and interface
            gateway = None
            interface_name = None

            for line in result.stdout.split("\n"):
                line = line.strip()
                if line.startswith("gateway:"):
                    gateway = line.split(":")[1].strip()
                elif line.startswith("interface:"):
                    interface_name = line.split(":")[1].strip()

            if not interface_name:
                return None, None, None, None

            # Skip TUN interfaces
            if any(keyword in interface_name for keyword in TUN_INTERFACE_KEYWORDS):
                logger.warning(f"Ignored TUN interface: {interface_name}")
                return None, None, None, None

            # Get IP using ifconfig
            result = subprocess.run(
                ["ifconfig", interface_name],
                capture_output=True,
                text=True,
                timeout=IPCONFIG_COMMAND_TIMEOUT,
                check=False,
            )

            interface_ip = None
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "inet " in line and "inet6" not in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "inet" and i + 1 < len(parts):
                                interface_ip = parts[i + 1]
                                break

            if interface_ip:
                subnet = NetworkInterfaceDetector._calculate_subnet(interface_ip)
                logger.info(
                    f"Detected primary interface: {interface_name} ({interface_ip}, {subnet}, {gateway})"
                )
                return interface_name, interface_ip, subnet, gateway

            return None, None, None, None

        except Exception as e:
            logger.error(f"Error detecting primary interface on macOS: {e}")
            return None, None, None, None

    @staticmethod
    def _get_primary_interface_windows() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Get primary interface on Windows using 'route' and 'ipconfig'."""
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
                        interface_name = NetworkInterfaceDetector._get_interface_name_windows(interface_ip)

                        # Fix: Ignore Sing-box TUN interface to prevent loops
                        if interface_name:
                            interface_upper = interface_name.upper()
                            if any(keyword in interface_upper for keyword in TUN_INTERFACE_KEYWORDS):
                                logger.warning(f"Ignored potential TUN interface: {interface_name}")
                                continue

                        # Calculate subnet (assume /24 for simplicity)
                        subnet = NetworkInterfaceDetector._calculate_subnet(interface_ip)

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
    def _get_interface_name_windows(ip: str) -> Optional[str]:
        """Get interface name from IP address using ipconfig (Windows only)."""
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
