"""LAN Sharing Controller - manages settings state retrieval and LAN toggle synchronization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.services.lan_service import LanService

if TYPE_CHECKING:
    from src.core.app_context import AppContext


class LanSharingController:
    """Controller handling LAN sharing configuration state and IP detection."""

    def __init__(self, app_context: Optional[AppContext] = None) -> None:
        self._app_context = app_context

    def get_local_ip(self) -> str:
        """Probe real local physical LAN IP."""
        return LanService.get_real_physical_lan_ip()

    def get_http_port(self) -> str:
        """Get configured HTTP proxy port."""

        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                return str(self._app_context.settings.get_http_port())
        except Exception:
            pass
        return "10809"

    def get_socks_port(self) -> str:
        """Get configured SOCKS5 proxy port."""
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                return str(self._app_context.settings.get_proxy_port())
        except Exception:
            pass
        return "10808"

    def get_allow_lan(self) -> bool:
        """Get configured allow LAN state."""
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                return self._app_context.settings.get_allow_lan()
        except Exception:
            pass
        return True

    def set_allow_lan(self, enabled: bool) -> None:
        """Update configured allow LAN state."""
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                self._app_context.settings.set_allow_lan(enabled)
        except Exception:
            pass

    def generate_qr(self, local_ip: str, http_port: str) -> str | None:
        """Generate base64 QR PNG string for HTTP proxy URL."""
        return LanService.generate_qr_base64(f"http://{local_ip}:{http_port}")
