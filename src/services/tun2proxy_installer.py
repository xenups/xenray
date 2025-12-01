"""Tun2Proxy Installer Service.

Provides utilities to check for the presence of the Tun2Proxy binary and to download/install it if missing.
"""

import os
import platform
import shutil
import stat

import requests

from src.core.constants import BIN_DIR, TUN2PROXY_EXECUTABLE


class Tun2ProxyInstallerService:
    """Manages Tun2Proxy installation."""

    @staticmethod
    def is_installed() -> bool:
        """Return True if the Tun2Proxy executable exists on the system."""
        return os.path.exists(TUN2PROXY_EXECUTABLE)

    @staticmethod
    def install(progress_callback=None) -> bool:
        """Download and install Tun2Proxy.

        The function attempts to download a known stable version (v0.7.16) first.
        If that fails, it falls back to the latest release URL.
        ``progress_callback`` can be a callable that receives a status string.
        Returns ``True`` on success, ``False`` otherwise.
        """
        try:
            # Ensure the binary directory exists
            os.makedirs(BIN_DIR, exist_ok=True)

            if progress_callback:
                progress_callback("Downloading Tun2Proxy...")

            # Determine platform and architecture
            os_name = "windows" if os.name == "nt" else "linux"
            arch = platform.machine().lower()
            if arch in ("amd64", "x86_64"):
                arch_str = "x86_64"
            elif "aarch64" in arch or "arm64" in arch:
                arch_str = "aarch64"
            else:
                raise Exception(f"Unsupported architecture: {arch}")

            ext = ".exe" if os_name == "windows" else ""
            filename = f"tun2proxy-{os_name}-{arch_str}{ext}"

            # URLs – try a stable version first, then the latest release
            stable_version = "v0.7.16"
            primary_url = f"https://github.com/tun2proxy/tun2proxy/releases/download/{stable_version}/{filename}"
            fallback_url = f"https://github.com/tun2proxy/tun2proxy/releases/latest/download/{filename}"

            temp_path = os.path.join(BIN_DIR, f"tun2proxy_temp{ext}")

            # Attempt download with fallback
            for url in (primary_url, fallback_url):
                try:
                    with requests.get(url, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        with open(temp_path, "wb") as f:
                            shutil.copyfileobj(r.raw, f)
                    break  # Success
                except Exception as e:
                    last_err = e
                    continue
            else:
                # Both attempts failed
                raise last_err

            # Replace any existing binary
            if os.path.exists(TUN2PROXY_EXECUTABLE):
                os.remove(TUN2PROXY_EXECUTABLE)
            os.rename(temp_path, TUN2PROXY_EXECUTABLE)

            # Ensure executable permission on non‑Windows platforms
            if os.name != "nt":
                st = os.stat(TUN2PROXY_EXECUTABLE)
                os.chmod(TUN2PROXY_EXECUTABLE, st.st_mode | stat.S_IEXEC)

            return True
        except Exception as e:
            print(f"Tun2Proxy install failed: {e}")
            return False
