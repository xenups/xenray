"""LAN Proxy Sharing Service - encapsulation of physical IP detection & QR code generation."""

from __future__ import annotations

import base64
import io


class LanService:
    """Service handling network IP detection and QR code image generation."""

    @staticmethod
    def get_real_physical_lan_ip() -> str | None:
        """Detect the physical LAN IP from the OS abstraction only.

        Delegates to the platform ``INetworkAdapter`` (IP Helper + OS
        default-route). Returns ``None`` when no physical interface is
        available — never a fabricated IP.
        """
        try:
            from src.platform.factory import get_network_adapter

            return get_network_adapter().get_physical_lan_ip()
        except Exception:
            return None

    @staticmethod
    def generate_qr_base64(data: str) -> str | None:
        """Generate QR code base64 PNG string."""
        if not data:
            return None
        try:
            import qrcode  # noqa: PLC0415

            qr = qrcode.QRCode(version=1, box_size=5, border=2)
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = io.BytesIO()
            img.save(buffered)
            return base64.b64encode(buffered.getvalue()).decode()
        except Exception:
            return None
