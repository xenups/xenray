"""macOS System Proxy Configuration using networksetup."""

from __future__ import annotations

import subprocess
from typing import List

from loguru import logger


class SystemProxyMacOS:
    """Manages system proxy settings on macOS using networksetup command."""

    @staticmethod
    def get_active_network_services() -> List[str]:
        """Get list of active network services."""
        try:
            result = subprocess.run(
                ["networksetup", "-listallnetworkservices"],
                capture_output=True,
                text=True,
                check=True,
            )
            lines = result.stdout.strip().split("\n")[1:]
            services = [line.strip() for line in lines if line and not line.startswith("*")]
            logger.debug(f"Found network services: {services}")
            return services
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get network services: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting network services: {e}")
            return []

    @staticmethod
    def set_http_proxy(service: str, host: str, port: int) -> bool:
        """Set HTTP proxy for a network service."""
        try:
            subprocess.run(
                ["networksetup", "-setwebproxy", service, host, str(port)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["networksetup", "-setwebproxystate", service, "on"],
                check=True,
                capture_output=True,
            )
            logger.info(f"HTTP proxy set for {service}: {host}:{port}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set HTTP proxy for {service}: {e}")
            return False

    @staticmethod
    def set_https_proxy(service: str, host: str, port: int) -> bool:
        """Set HTTPS proxy for a network service."""
        try:
            subprocess.run(
                ["networksetup", "-setsecurewebproxy", service, host, str(port)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["networksetup", "-setsecurewebproxystate", service, "on"],
                check=True,
                capture_output=True,
            )
            logger.info(f"HTTPS proxy set for {service}: {host}:{port}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set HTTPS proxy for {service}: {e}")
            return False

    @staticmethod
    def set_socks_proxy(service: str, host: str, port: int) -> bool:
        """Set SOCKS proxy for a network service."""
        try:
            subprocess.run(
                ["networksetup", "-setsocksfirewallproxy", service, host, str(port)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["networksetup", "-setsocksfirewallproxystate", service, "on"],
                check=True,
                capture_output=True,
            )
            logger.info(f"SOCKS proxy set for {service}: {host}:{port}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set SOCKS proxy for {service}: {e}")
            return False

    @staticmethod
    def clear_http_proxy(service: str) -> bool:
        """Clear HTTP proxy for a network service."""
        try:
            subprocess.run(
                ["networksetup", "-setwebproxystate", service, "off"],
                check=True,
                capture_output=True,
            )
            logger.info(f"HTTP proxy cleared for {service}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clear HTTP proxy for {service}: {e}")
            return False

    @staticmethod
    def clear_https_proxy(service: str) -> bool:
        """Clear HTTPS proxy for a network service."""
        try:
            subprocess.run(
                ["networksetup", "-setsecurewebproxystate", service, "off"],
                check=True,
                capture_output=True,
            )
            logger.info(f"HTTPS proxy cleared for {service}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clear HTTPS proxy for {service}: {e}")
            return False

    @staticmethod
    def clear_socks_proxy(service: str) -> bool:
        """Clear SOCKS proxy for a network service."""
        try:
            subprocess.run(
                ["networksetup", "-setsocksfirewallproxystate", service, "off"],
                check=True,
                capture_output=True,
            )
            logger.info(f"SOCKS proxy cleared for {service}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clear SOCKS proxy for {service}: {e}")
            return False

    @staticmethod
    def set_proxy_for_all_services(host: str, port: int, proxy_type: str = "http") -> bool:
        """Set proxy for all active network services."""
        services = SystemProxyMacOS.get_active_network_services()
        if not services:
            logger.warning("No active network services found")
            return False

        success_count = 0
        for service in services:
            if proxy_type == "http":
                if SystemProxyMacOS.set_http_proxy(service, host, port):
                    success_count += 1
            elif proxy_type == "https":
                if SystemProxyMacOS.set_https_proxy(service, host, port):
                    success_count += 1
            elif proxy_type == "socks":
                if SystemProxyMacOS.set_socks_proxy(service, host, port):
                    success_count += 1
        return success_count > 0

    @staticmethod
    def clear_proxy_for_all_services(proxy_type: str = "http") -> bool:
        """Clear proxy for all active network services."""
        services = SystemProxyMacOS.get_active_network_services()
        if not services:
            logger.warning("No active network services found")
            return False

        success_count = 0
        for service in services:
            if proxy_type == "http":
                if SystemProxyMacOS.clear_http_proxy(service):
                    success_count += 1
            elif proxy_type == "https":
                if SystemProxyMacOS.clear_https_proxy(service):
                    success_count += 1
            elif proxy_type == "socks":
                if SystemProxyMacOS.clear_socks_proxy(service):
                    success_count += 1
        return success_count > 0

    @staticmethod
    def get_proxy_settings(service: str) -> dict:
        """Get current proxy settings for a network service."""
        settings = {
            "http": {"enabled": False, "host": None, "port": None},
            "https": {"enabled": False, "host": None, "port": None},
            "socks": {"enabled": False, "host": None, "port": None},
        }

        try:
            result = subprocess.run(
                ["networksetup", "-getwebproxy", service],
                capture_output=True,
                text=True,
                check=True,
            )
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if "Enabled:" in line and "Yes" in line:
                    settings["http"]["enabled"] = True
                elif "Server:" in line:
                    settings["http"]["host"] = line.split(":")[1].strip()
                elif "Port:" in line:
                    settings["http"]["port"] = int(line.split(":")[1].strip())

            result = subprocess.run(
                ["networksetup", "-getsecurewebproxy", service],
                capture_output=True,
                text=True,
                check=True,
            )
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if "Enabled:" in line and "Yes" in line:
                    settings["https"]["enabled"] = True
                elif "Server:" in line:
                    settings["https"]["host"] = line.split(":")[1].strip()
                elif "Port:" in line:
                    settings["https"]["port"] = int(line.split(":")[1].strip())

            result = subprocess.run(
                ["networksetup", "-getsocksfirewallproxy", service],
                capture_output=True,
                text=True,
                check=True,
            )
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if "Enabled:" in line and "Yes" in line:
                    settings["socks"]["enabled"] = True
                elif "Server:" in line:
                    settings["socks"]["host"] = line.split(":")[1].strip()
                elif "Port:" in line:
                    settings["socks"]["port"] = int(line.split(":")[1].strip())

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get proxy settings for {service}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting proxy settings: {e}")

        return settings
