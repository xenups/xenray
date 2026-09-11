"""Core binary and release asset abstraction interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CoreAssetInfo:
    """Metadata and download URL for platform-specific core binaries."""

    filename: str
    download_url: str
    archive_extension: str
    binary_name: str


class ICoreAssetAdapter(ABC):
    """Platform-specific asset packaging and URL resolution for proxy cores."""

    @abstractmethod
    def get_xray_asset_info(self, version: str) -> CoreAssetInfo:
        """Return platform-specific Xray release asset information."""
        pass

    @abstractmethod
    def get_singbox_asset_info(self, version: str) -> CoreAssetInfo:
        """Return platform-specific sing-box release asset information."""
        pass
