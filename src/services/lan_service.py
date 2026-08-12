"""LAN Proxy Sharing Service - encapsulation of physical IP detection & QR code generation."""

from __future__ import annotations

import base64
import io
import socket


class LanService:
    """Service handling network IP detection and QR code image generation."""

    @staticmethod
    def get_real_physical_lan_ip() -> str:
        """Detect actual physical LAN IP address, excluding TUN/TAP (10.0.0.x), loopback, and virtual adapters."""
        try:
            hostname = socket.gethostname()
            ip_list = socket.gethostbyname_ex(hostname)[2]

            valid_ips = []
            for ip in ip_list:
                if (
                    ip.startswith("127.")
                    or ip.startswith("10.0.0.")
                    or ip.startswith("198.18.")
                    or ip.startswith("169.254.")
                ):
                    continue
                if ip.startswith("192.168."):
                    return ip
                valid_ips.append(ip)

            if valid_ips:
                return valid_ips[0]
        except Exception:
            pass

        for target in ["192.168.1.1", "192.168.0.1", "1.1.1.1"]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.5)
                s.connect((target, 80))
                ip = s.getsockname()[0]
                s.close()
                if (
                    not ip.startswith("127.")
                    and not ip.startswith("10.0.0.")
                    and not ip.startswith("198.18.")
                    and not ip.startswith("169.254.")
                ):
                    return ip
            except Exception:
                pass

        return "192.168.1.1"

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
            img.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode()
        except Exception:
            return None
