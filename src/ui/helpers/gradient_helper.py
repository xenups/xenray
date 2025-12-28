"""Gradient Helper for XenRay UI."""
import flet as ft

from src.core.flag_colors import FLAG_COLORS


class GradientHelper:
    """Centralized utility for generating XenRay standard gradients."""

    @staticmethod
    def get_flag_gradient(country_code: str = None) -> ft.LinearGradient:
        """
        Generate a linear gradient based on country flag colors.

        Args:
            country_code: The ISO 2rd-letter country code.

        Returns:
            ft.LinearGradient: The generated gradient.
        """
        cc = country_code.lower() if country_code else "default"

        # New default fallback: Black with White/Grey
        if cc == "default" or cc not in FLAG_COLORS:
            color1, color2 = "#000000", "#4d4d4d"
        else:
            color1, color2 = FLAG_COLORS[cc]

        return ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[
                ft.Colors.with_opacity(0.25, color1),
                ft.Colors.with_opacity(0.15, color2),
                ft.Colors.with_opacity(0.08, color1),
            ],
            tile_mode=ft.GradientTileMode.CLAMP,
        )
