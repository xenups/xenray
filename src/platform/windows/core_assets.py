"""Windows core release asset adapter."""

from __future__ import annotations

from src.platform.constants import (
    SINGBOX_CORE_DOWNLOAD_BASE_URL,
    XRAY_CORE_DOWNLOAD_BASE_URL,
)
from src.platform.interfaces.core_assets import CoreAssetInfo, ICoreAssetAdapter
from src.utils.platform_utils import PlatformUtils


class WindowsCoreAssetAdapter(ICoreAssetAdapter):
    """Resolves Windows-specific core package names and download URLs."""

    def get_xray_asset_info(self, version: str) -> CoreAssetInfo:
        arch = PlatformUtils.get_architecture()
        if arch == "x86_64":
            arch_str = "64"
        elif arch == "arm64":
            arch_str = "arm64-v8a"
        else:
            arch_str = "32"

        filename = f"Xray-windows-{arch_str}.zip"
        v = version.lstrip("v")
        url = f"{XRAY_CORE_DOWNLOAD_BASE_URL}/v{v}/{filename}"
        return CoreAssetInfo(
            filename=filename,
            download_url=url,
            archive_extension=".zip",
            binary_name="xray.exe",
        )

    def get_singbox_asset_info(self, version: str) -> CoreAssetInfo:
        arch = PlatformUtils.get_architecture()
        if arch == "x86_64":
            sb_arch = "amd64"
        elif arch == "arm64":
            sb_arch = "arm64"
        else:
            sb_arch = "386"

        v = version.lstrip("v")
        filename = f"sing-box-{v}-windows-{sb_arch}.zip"
        url = f"{SINGBOX_CORE_DOWNLOAD_BASE_URL}/v{v}/{filename}"
        return CoreAssetInfo(
            filename=filename,
            download_url=url,
            archive_extension=".zip",
            binary_name="sing-box.exe",
        )


__all__ = ["WindowsCoreAssetAdapter"]
