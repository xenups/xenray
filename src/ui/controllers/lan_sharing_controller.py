"""LAN Sharing Controller - manages settings state retrieval and LAN toggle synchronization."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from src.core.event_bus import TOPIC_LAN_SHARING_CHANGED, event_bus
from src.services.system.lan_service import LanService

if TYPE_CHECKING:
    from src.core.app_context import AppContext


class LanSharingController:
    """Controller handling LAN sharing configuration state and IP detection."""

    # Process-wide cache so repeated page constructions / toggles never re-run the
    # blocking DNS/socket probe on the UI thread after the first resolution.
    _cached_ip: Optional[str] = None
    _ip_cache_time: float = 0.0
    _IP_CACHE_TTL: float = 60.0

    def __init__(self, app_context: Optional[AppContext] = None) -> None:
        self._app_context = app_context

    def get_local_ip(self) -> str:
        """Return the resolved local LAN IP, reusing a short-lived process cache."""
        now = time.time()
        if (
            LanSharingController._cached_ip
            and (now - LanSharingController._ip_cache_time) < LanSharingController._IP_CACHE_TTL
        ):
            return LanSharingController._cached_ip
        LanSharingController._cached_ip = LanService.get_real_physical_lan_ip()
        LanSharingController._ip_cache_time = now
        return LanSharingController._cached_ip

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
        """Alias for :meth:`set_lan_sharing_enabled` (kept for API compatibility)."""
        self.set_lan_sharing_enabled(enabled)

    def set_lan_sharing_enabled(self, enabled: bool) -> None:
        """
        Single source of truth for LAN sharing mutations.

        Persists the preference, applies/removes the Windows firewall rule, and
        broadcasts ``lan_sharing_changed`` on the EventBus so every toggle UI
        (settings + LAN page + sidebar) stays in sync.
        """
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                self._app_context.settings.set_allow_lan(enabled)
        except Exception:
            pass

        try:
            from src.utils.firewall_manager import FirewallManager

            if enabled:
                port = self._get_proxy_port_int()
                FirewallManager.add_lan_firewall_rule([port, port + 4])
            else:
                FirewallManager.remove_lan_firewall_rule()
        except Exception:
            pass

        try:
            event_bus.publish(TOPIC_LAN_SHARING_CHANGED, {"enabled": bool(enabled)})
        except Exception:
            pass

    def _get_proxy_port_int(self) -> int:
        """Return the configured SOCKS/HTTP proxy port as an int."""
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                return int(self._app_context.settings.get_proxy_port())
        except Exception:
            pass
        return 10808

    def generate_qr(self, local_ip: str, http_port: str) -> str | None:
        """Generate base64 QR PNG string for HTTP proxy URL."""
        return LanService.generate_qr_base64(f"http://{local_ip}:{http_port}")
