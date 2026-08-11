"""SystemInfoCache - thread-safe pre-warmed cache for hardware, OS, and network diagnostic headers."""

from __future__ import annotations

import os
import platform
import socket
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import psutil

from src.core.logger import logger


@dataclass
class SystemInfoSnapshot:
    """Snapshot of pre-warmed system metrics and hardware diagnostic headers."""

    os_name: str = ""
    os_version: str = ""
    architecture: str = ""
    hostname: str = ""
    total_memory_mb: float = 0.0
    available_memory_mb: float = 0.0
    cpu_cores_physical: int = 0
    cpu_cores_logical: int = 0
    cpu_freq_mhz: float = 0.0
    network_interfaces: List[str] = field(default_factory=list)
    ip_addresses: List[str] = field(default_factory=list)
    system_headers: Dict[str, str] = field(default_factory=dict)
    is_warmed_up: bool = False


class SystemInfoCache:
    """Thread-safe singleton caching system diagnostic headers and baseline hardware metrics."""

    _instance: Optional[SystemInfoCache] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._snapshot = SystemInfoSnapshot()
        self._cache_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> SystemInfoCache:
        """Get singleton instance of SystemInfoCache."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def warmup_system_info(self) -> SystemInfoSnapshot:
        """Execute baseline queries to pre-populate hardware and network system headers."""
        try:
            os_name = platform.system()
            os_version = f"{platform.release()} (Build {platform.version()})"
            arch = platform.machine()
            hostname = socket.gethostname()

            mem = psutil.virtual_memory()
            total_mem_mb = mem.total / (1024 * 1024)
            avail_mem_mb = mem.available / (1024 * 1024)

            cpu_phys = psutil.cpu_count(logical=False) or 1
            cpu_log = psutil.cpu_count(logical=True) or 1
            cpu_freq_info = psutil.cpu_freq()
            cpu_freq_mhz = cpu_freq_info.current if cpu_freq_info else 0.0

            interfaces: List[str] = []
            ip_addresses: List[str] = []
            try:
                for iface, addrs in psutil.net_if_addrs().items():
                    interfaces.append(iface)
                    for addr in addrs:
                        if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                            ip_addresses.append(f"{iface}: {addr.address}")
            except Exception as e:
                logger.debug(f"[SystemInfoCache] Could not enumerate network adapters: {e}")

            headers = {
                "OS": f"{os_name} {os_version}",
                "Arch": arch,
                "Host": hostname,
                "CPU": f"{cpu_phys}P/{cpu_log}L @ {cpu_freq_mhz:.0f}MHz",
                "RAM": f"{avail_mem_mb:.0f}MB / {total_mem_mb:.0f}MB",
                "Active Ifaces": ", ".join(interfaces[:3]) if interfaces else "Default",
            }

            snapshot = SystemInfoSnapshot(
                os_name=os_name,
                os_version=os_version,
                architecture=arch,
                hostname=hostname,
                total_memory_mb=total_mem_mb,
                available_memory_mb=avail_mem_mb,
                cpu_cores_physical=cpu_phys,
                cpu_cores_logical=cpu_log,
                cpu_freq_mhz=cpu_freq_mhz,
                network_interfaces=interfaces,
                ip_addresses=ip_addresses,
                system_headers=headers,
                is_warmed_up=True,
            )

            with self._cache_lock:
                self._snapshot = snapshot

            logger.debug("[SystemInfoCache] System info baseline pre-warmed successfully")
            return snapshot
        except Exception as e:
            logger.error(f"[SystemInfoCache] Error during system info warmup: {e}")
            return self.get_snapshot()

    def get_snapshot(self) -> SystemInfoSnapshot:
        """Get the cached system info snapshot."""
        with self._cache_lock:
            return self._snapshot

    def clear(self) -> None:
        """Clear cache (used for test resets)."""
        with self._cache_lock:
            self._snapshot = SystemInfoSnapshot()


system_info_cache = SystemInfoCache.get_instance()
