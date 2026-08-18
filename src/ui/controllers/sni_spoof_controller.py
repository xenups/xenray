"""SNI Spoof Controller - manages SNI spoof settings persistence and change broadcasting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.core.event_bus import TOPIC_SNI_SPOOF_CHANGED, event_bus

if TYPE_CHECKING:
    from src.core.app_context import AppContext


class SniSpoofController:
    """Controller handling SNI spoof configuration state and change notification."""

    def __init__(self, app_context: Optional[AppContext] = None) -> None:
        self._app_context = app_context
        self.enabled = self._get("get_sni_spoof_enabled", False)
        self.fake_sni = self._get("get_sni_fake_sni", "chatgpt.com")
        self.connect_ip = self._get("get_sni_connect_ip", "185.193.30.94")
        self.connect_port = self._get("get_sni_connect_port", 443)
        self.listen_host = self._get("get_sni_listen_host", "127.0.0.1")
        self.listen_port = self._get("get_sni_listen_port", 40443)

    def _get(self, method: str, default):
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                return getattr(self._app_context.settings, method)()
        except Exception:
            pass
        return default

    def _set(self, method: str, value, **extra) -> None:
        try:
            if self._app_context and hasattr(self._app_context, "settings"):
                getattr(self._app_context.settings, method)(value)
        except Exception:
            pass
        self._publish(**extra)

    def _publish(self, **extra) -> None:
        try:
            payload = {
                "enabled": self.enabled,
                "fake_sni": self.fake_sni,
                "connect_ip": self.connect_ip,
                "connect_port": self.connect_port,
                "listen_host": self.listen_host,
                "listen_port": self.listen_port,
            }
            payload.update(extra)
            event_bus.publish(TOPIC_SNI_SPOOF_CHANGED, payload)
        except Exception:
            pass

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        # Marker lets the lifecycle bridge act on a real toggle rather than on
        # every field edit (every publish still carries "enabled" as a snapshot).
        self._set("set_sni_spoof_enabled", self.enabled, enabled_changed=True)

    def set_fake_sni(self, value: str) -> None:
        self.fake_sni = value
        self._set("set_sni_fake_sni", self.fake_sni)

    def set_connect_ip(self, value: str) -> None:
        self.connect_ip = value
        self._set("set_sni_connect_ip", self.connect_ip)

    def set_connect_port(self, port: int) -> None:
        self.connect_port = int(port)
        self._set("set_sni_connect_port", self.connect_port)

    def set_listen_host(self, value: str) -> None:
        self.listen_host = value
        self._set("set_sni_listen_host", self.listen_host)

    def set_listen_port(self, port: int) -> None:
        self.listen_port = int(port)
        self._set("set_sni_listen_port", self.listen_port)
