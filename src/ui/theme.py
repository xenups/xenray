"""Central color palette and theme constants matching Slate Dark & Deep Apple Purple System Design."""

from __future__ import annotations

import flet as ft


class AppColors:
    """Define Slate Dark & Deep Apple Purple color constants for application theme."""

    # Background gradient
    BACKGROUND_GRADIENT_START = "#0B0813"
    BACKGROUND_GRADIENT_CENTER = "#0B0813"
    BACKGROUND_GRADIENT_END = "#0B0813"

    # Frosted glass overlay & borders
    GLASS_OVERLAY = "#00000000"
    GLASS_BORDER = "#212836"
    GLASS_BG_OPACITY = 0.85

    # Slate Dark & Deep Apple Purple Design Tokens
    BACKGROUND = "#0B0813"
    SURFACE_CONTAINER_LOW = "#10141d"
    SURFACE_CONTAINER = "#151a23"
    SURFACE_CONTAINER_HIGH = "#1c2330"
    SURFACE_CONTAINER_HIGHEST = "#252e3e"

    PRIMARY = "#6d28d9"  # Deep Apple Purple
    PRIMARY_CONTAINER = "#5b21b6"
    ON_PRIMARY = "#ffffff"

    SECONDARY = "#7c3aed"
    SECONDARY_CONTAINER = "#4c1d95"

    TERTIARY = "#5b21b6"
    TERTIARY_CONTAINER = "#3b0764"

    ON_BACKGROUND = "#ffffff"
    ON_SURFACE = "#ffffff"
    ON_SURFACE_VARIANT = "#e5e7eb"  # Apple Muted White

    OUTLINE = "#6d28d9"
    OUTLINE_VARIANT = "#212836"

    ERROR = "#f87171"
    ERROR_CONTAINER = "#991b1b"


class GlassTokens:
    """Apple-style translucent glass tokens used consistently across views."""

    BG_PAGE = "#0B0813"
    BG_CARD = "rgba(255, 255, 255, 0.03)"
    BG_CARD_SUBTLE = "rgba(255, 255, 255, 0.02)"
    BG_DIALOG = "rgba(20, 16, 35, 0.95)"
    BG_ACTIVE = "rgba(168, 85, 247, 0.18)"

    BORDER_DEFAULT = "rgba(255, 255, 255, 0.06)"
    BORDER_SUBTLE = "rgba(255, 255, 255, 0.04)"
    BORDER_ACTIVE = "rgba(168, 85, 247, 0.35)"

    TEXT_MUTED = "#94A3B8"
    TEXT_MUTED_LIGHT = "rgba(255, 255, 255, 0.45)"
    TEXT_PRIMARY = "#FFFFFF"

    ACCENT_LILAC = "#A855F7"
    ACCENT_GREEN = "#4ADE80"
    ACCENT_RED = "#F87171"


class GlassContainer(ft.Container):
    """Reusable Apple-style Glassmorphism container."""

    def __init__(
        self,
        content: ft.Control | None = None,
        padding: int | ft.Padding = 12,
        border_radius: int = 12,
        border_color: str = GlassTokens.BORDER_DEFAULT,
        bgcolor: str = GlassTokens.BG_CARD,
        expand: bool | int = False,
        width: int | float | None = None,
        height: int | float | None = None,
        alignment: ft.Alignment | None = None,
        on_click=None,
        ink: bool = False,
        tooltip: str | None = None,
        shadow: ft.BoxShadow | None = None,
        **kwargs,
    ):
        super().__init__(
            content=content,
            padding=padding,
            border_radius=border_radius,
            border=ft.Border.all(1, border_color) if border_color else None,
            bgcolor=bgcolor,
            expand=expand,
            width=width,
            height=height,
            alignment=alignment,
            on_click=on_click,
            ink=ink,
            tooltip=tooltip,
            shadow=shadow,
            **kwargs,
        )


def create_glass_container(
    content: ft.Control,
    padding: int | ft.Padding = 16,
    border_radius: int = 16,
    border_color: str = AppColors.GLASS_BORDER,
    bgcolor: str = AppColors.SURFACE_CONTAINER,
    expand: bool | int = False,
    width: int | float | None = None,
    height: int | float | None = None,
) -> ft.Container:
    """Create a styled dark slate navy container."""
    return ft.Container(
        content=content,
        padding=padding,
        border_radius=border_radius,
        border=ft.Border.all(1, border_color),
        bgcolor=bgcolor,
        expand=expand,
        width=width,
        height=height,
    )
