"""Linux System Proxy Configuration."""
import os
import subprocess

from loguru import logger


class SystemProxyLinux:
    """Manages system proxy settings on Linux."""

    @staticmethod
    def detect_desktop_environment() -> str:
        """
        Detect the current desktop environment.

        Returns:
            'gnome', 'kde', 'xfce', or 'unknown'
        """
        # Check environment variables
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

        if "gnome" in desktop or "unity" in desktop:
            return "gnome"
        elif "kde" in desktop:
            return "kde"
        elif "xfce" in desktop:
            return "xfce"

        # Fallback: check running processes
        try:
            result = subprocess.run(["ps", "-A"], capture_output=True, text=True, timeout=2)

            output = result.stdout.lower()
            if "gnome-session" in output:
                return "gnome"
            elif "kded" in output or "plasmashell" in output:
                return "kde"
            elif "xfce4-session" in output:
                return "xfce"
        except Exception:
            pass

        return "unknown"

    @staticmethod
    def set_gnome_proxy(host: str, port: int, proxy_type: str = "http") -> bool:
        """
        Set proxy for GNOME desktop environment.

        Args:
            host: Proxy host
            port: Proxy port
            proxy_type: Type of proxy ('http', 'https', 'socks')

        Returns:
            True if successful, False otherwise
        """
        try:
            schema = "org.gnome.system.proxy"

            # Enable manual proxy
            subprocess.run(
                ["gsettings", "set", schema, "mode", "manual"],
                check=True,
                capture_output=True,
            )

            # Set proxy based on type
            if proxy_type == "http":
                subprocess.run(
                    ["gsettings", "set", f"{schema}.http", "host", host],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["gsettings", "set", f"{schema}.http", "port", str(port)],
                    check=True,
                    capture_output=True,
                )
            elif proxy_type == "https":
                subprocess.run(
                    ["gsettings", "set", f"{schema}.https", "host", host],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["gsettings", "set", f"{schema}.https", "port", str(port)],
                    check=True,
                    capture_output=True,
                )
            elif proxy_type == "socks":
                subprocess.run(
                    ["gsettings", "set", f"{schema}.socks", "host", host],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["gsettings", "set", f"{schema}.socks", "port", str(port)],
                    check=True,
                    capture_output=True,
                )

            logger.info(f"GNOME {proxy_type} proxy set: {host}:{port}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set GNOME proxy: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting GNOME proxy: {e}")
            return False

    @staticmethod
    def clear_gnome_proxy() -> bool:
        """
        Clear proxy settings for GNOME.

        Returns:
            True if successful, False otherwise
        """
        try:
            schema = "org.gnome.system.proxy"

            # Set to 'none' to disable proxy
            subprocess.run(
                ["gsettings", "set", schema, "mode", "none"],
                check=True,
                capture_output=True,
            )

            logger.info("GNOME proxy cleared")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clear GNOME proxy: {e}")
            return False

    @staticmethod
    def set_kde_proxy(host: str, port: int, proxy_type: str = "http") -> bool:
        """
        Set proxy for KDE desktop environment.

        Args:
            host: Proxy host
            port: Proxy port
            proxy_type: Type of proxy ('http', 'https', 'socks')

        Returns:
            True if successful, False otherwise
        """
        try:
            # KDE uses kioslaverc configuration file
            os.path.expanduser("~/.config/kioslaverc")
            # Set proxy mode to manual
            subprocess.run(
                [
                    "kwriteconfig5",
                    "--file",
                    "kioslaverc",
                    "--group",
                    "Proxy Settings",
                    "--key",
                    "ProxyType",
                    "1",
                ],
                check=True,
                capture_output=True,
            )

            # Set proxy URL
            if proxy_type in ["http", "https"]:
                proxy_url = f"http://{host}:{port}"
                subprocess.run(
                    [
                        "kwriteconfig5",
                        "--file",
                        "kioslaverc",
                        "--group",
                        "Proxy Settings",
                        "--key",
                        "httpProxy",
                        proxy_url,
                    ],
                    check=True,
                    capture_output=True,
                )
            elif proxy_type == "socks":
                proxy_url = f"socks://{host}:{port}"
                subprocess.run(
                    [
                        "kwriteconfig5",
                        "--file",
                        "kioslaverc",
                        "--group",
                        "Proxy Settings",
                        "--key",
                        "socksProxy",
                        proxy_url,
                    ],
                    check=True,
                    capture_output=True,
                )

            # Reload KDE proxy settings
            subprocess.run(
                [
                    "dbus-send",
                    "--type=signal",
                    "/KIO/Scheduler",
                    "org.kde.KIO.Scheduler.reparseSlaveConfiguration",
                    "string:",
                ],
                check=False,  # Don't fail if dbus not available
                capture_output=True,
            )

            logger.info(f"KDE {proxy_type} proxy set: {host}:{port}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set KDE proxy: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting KDE proxy: {e}")
            return False

    @staticmethod
    def clear_kde_proxy() -> bool:
        """
        Clear proxy settings for KDE.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Set proxy mode to 0 (no proxy)
            subprocess.run(
                [
                    "kwriteconfig5",
                    "--file",
                    "kioslaverc",
                    "--group",
                    "Proxy Settings",
                    "--key",
                    "ProxyType",
                    "0",
                ],
                check=True,
                capture_output=True,
            )

            # Reload KDE proxy settings
            subprocess.run(
                [
                    "dbus-send",
                    "--type=signal",
                    "/KIO/Scheduler",
                    "org.kde.KIO.Scheduler.reparseSlaveConfiguration",
                    "string:",
                ],
                check=False,
                capture_output=True,
            )

            logger.info("KDE proxy cleared")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clear KDE proxy: {e}")
            return False

    @staticmethod
    def set_environment_proxy(host: str, port: int) -> bool:
        """
        Set proxy via environment variables (fallback method).
        Works for most command-line tools and some GUI apps.

        Args:
            host: Proxy host
            port: Proxy port

        Returns:
            True if successful, False otherwise
        """
        try:
            proxy_url = f"http://{host}:{port}"

            # Set environment variables
            os.environ["HTTP_PROXY"] = proxy_url
            os.environ["HTTPS_PROXY"] = proxy_url
            os.environ["http_proxy"] = proxy_url
            os.environ["https_proxy"] = proxy_url

            # Write to shell config files for persistence
            shell_configs = [
                os.path.expanduser("~/.bashrc"),
                os.path.expanduser("~/.profile"),
                os.path.expanduser("~/.zshrc"),
            ]

            proxy_lines = [
                "\n# XenRay Proxy Settings\n",
                f'export HTTP_PROXY="{proxy_url}"\n',
                f'export HTTPS_PROXY="{proxy_url}"\n',
                f'export http_proxy="{proxy_url}"\n',
                f'export https_proxy="{proxy_url}"\n',
            ]

            for config_file in shell_configs:
                if os.path.exists(config_file):
                    try:
                        with open(config_file, "a") as f:
                            f.writelines(proxy_lines)
                    except Exception as e:
                        logger.debug(f"Could not write to {config_file}: {e}")

            logger.info(f"Environment proxy set: {host}:{port}")
            return True

        except Exception as e:
            logger.error(f"Failed to set environment proxy: {e}")
            return False

    @staticmethod
    def clear_environment_proxy() -> bool:
        """
        Clear proxy environment variables.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear environment variables
            for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
                os.environ.pop(var, None)

            logger.info("Environment proxy cleared")
            return True

        except Exception as e:
            logger.error(f"Failed to clear environment proxy: {e}")
            return False

    @staticmethod
    def set_proxy(host: str, port: int, proxy_type: str = "http") -> bool:
        """
        Set system proxy (auto-detect desktop environment).

        Args:
            host: Proxy host
            port: Proxy port
            proxy_type: Type of proxy ('http', 'https', 'socks')

        Returns:
            True if successful, False otherwise
        """
        de = SystemProxyLinux.detect_desktop_environment()
        logger.info(f"Detected desktop environment: {de}")

        if de == "gnome":
            return SystemProxyLinux.set_gnome_proxy(host, port, proxy_type)
        elif de == "kde":
            return SystemProxyLinux.set_kde_proxy(host, port, proxy_type)
        else:
            logger.warning(f"Unknown desktop environment '{de}', using environment variables")
            return SystemProxyLinux.set_environment_proxy(host, port)

    @staticmethod
    def clear_proxy() -> bool:
        """
        Clear system proxy (auto-detect desktop environment).

        Returns:
            True if successful, False otherwise
        """
        de = SystemProxyLinux.detect_desktop_environment()

        if de == "gnome":
            return SystemProxyLinux.clear_gnome_proxy()
        elif de == "kde":
            return SystemProxyLinux.clear_kde_proxy()
        else:
            return SystemProxyLinux.clear_environment_proxy()
