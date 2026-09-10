"""macOS core release asset adapter."""

from __future__ import annotations

from src.platform.constants import (
    SINGBOX_CORE_DOWNLOAD_BASE_URL,
    XRAY_CORE_DOWNLOAD_BASE_URL,
)
from src.platform.interfaces.core_assets import CoreAssetInfo, ICoreAssetAdapter
from src.utils.platform_utils import PlatformUtils


class MacosCoreAssetAdapter(ICoreAssetAdapter):
    """Resolves macOS-specific core package names and download URLs."""

    def get_xray_asset_info(self, version: str) -> CoreAssetInfo:
        arch = PlatformUtils.get_architecture()
        arch_str = "arm64-v8a" if arch == "arm64" else "64"

        filename = f"Xray-macos-{arch_str}.zip"
        v = version.lstrip("v")
        url = f"{XRAY_CORE_DOWNLOAD_BASE_URL}/v{v}/{filename}"
        return CoreAssetInfo(
            filename=filename,
            download_url=url,
            archive_extension=".zip",
            binary_name="xray",
        )

    def get_singbox_asset_info(self, version: str) -> CoreAssetInfo:
        arch = PlatformUtils.get_architecture()
        sb_arch = "arm64" if arch == "arm64" else "amd64"

        v = version.lstrip("v")
        filename = f"sing-box-{v}-darwin-{sb_arch}.tar.gz"
        url = f"{SINGBOX_CORE_DOWNLOAD_BASE_URL}/v{v}/{filename}"
        return CoreAssetInfo(
            filename=filename,
            download_url=url,
            archive_extension=".tar.gz",
            binary_name="sing-box",
        )


__all__ = ["MacosCoreAssetAdapter"]
