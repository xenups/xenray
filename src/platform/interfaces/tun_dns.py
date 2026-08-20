"""TUN DNS and name resolution abstraction contract."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ITunDnsConfigurator(ABC):
    """Windows TUN DNS + NRPT: keeps all netsh/powershell behind this wall."""

    @abstractmethod
    def configure_tun_dns(self, config_file_path: str, adapter_name: str) -> bool:
        """Configure DNS + NRPT on the TUN adapter for a TUN profile."""

    @abstractmethod
    def cleanup_tun_dns(self, adapter_name: str) -> None:
        """Restore system DNS / remove NRPT rules (idempotent)."""
