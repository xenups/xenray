"""Central color palette and theme constants matching Slate Dark & Deep Apple Purple System Design."""
from __future__ import annotations

import flet as ft


class AppColors:
    """Define Slate Dark & Deep Apple Purple color constants for application theme."""

    # Background gradient
    BACKGROUND_GRADIENT_START = "#0b0e14"
    BACKGROUND_GRADIENT_CENTER = "#10141d"
    BACKGROUND_GRADIENT_END = "#151a23"

    # Frosted glass overlay & borders
    GLASS_OVERLAY = "#00000000"
    GLASS_BORDER = "#212836"
    GLASS_BG_OPACITY = 0.85

    # Slate Dark & Deep Apple Purple Design Tokens
    BACKGROUND = "#0b0e14"
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
