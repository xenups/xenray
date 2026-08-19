"""Theme styles and formatting helpers for ConnectionButton."""

from __future__ import annotations

import flet as ft

# ---------------------------------------------------------------------------
# Colors and Palette (Frosted White / Lilac Glassmorphism)
# ---------------------------------------------------------------------------
COLOR_CONNECTED_BG = "#EDE9FE"
COLOR_CONNECTED_BORDER = "#FFFFFF"
COLOR_CONNECTED_TEXT = "#1E1B4B"

COLOR_DISCONNECTED_BG = "#EDE9FE"
COLOR_DISCONNECTED_BORDER = "#FFFFFF"
COLOR_DISCONNECTED_TEXT = "#1E1B4B"

COLOR_CONNECTING_BG = "#FEF3C7"
COLOR_CONNECTING_BORDER = "#FFFFFF"
COLOR_CONNECTING_TEXT = "#1E1B4B"

COLOR_DISCONNECTING_BG = "#FEE2E2"
COLOR_DISCONNECTING_BORDER = "#FFFFFF"
COLOR_DISCONNECTING_TEXT = "#1E1B4B"


def get_sweep_gradient() -> ft.SweepGradient:
    """Return the wide sweep gradient for the rotating neon ping / connected disc."""
    return ft.SweepGradient(
        center=ft.Alignment.CENTER,
        colors=["#C084FC", "#A855F7", "#38BDF8", "#00000000"],
        stops=[0.0, 0.22, 0.45, 1.0],
        rotation=0.0,
    )


def get_connecting_sweep_gradient() -> ft.SweepGradient:
    """Return amber sweep gradient for the rotating connecting disc."""
    return ft.SweepGradient(
        center=ft.Alignment.CENTER,
        colors=["#FBBF24", "#F59E0B", "#D97706", "#00000000"],
        stops=[0.0, 0.22, 0.45, 1.0],
        rotation=0.0,
    )


def get_connected_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=12,
        blur_radius=65,
        color=ft.Colors.with_opacity(0.50, "#A855F7"),
        offset=ft.Offset(0, 0),
    )


def get_glow_gradient_colors(dim: bool = False):
    """Bi-color aurora gradient (top purple → bottom cyan) for the glow layer.

    Connected state uses the bright rendering; ``dim=True`` (disconnected)
    returns a faint, low-opacity violet.
    """
    if dim:
        return [
            ft.Colors.with_opacity(0.28, "#8B5CF6"),
            ft.Colors.with_opacity(0.16, "#6366F1"),
            ft.Colors.with_opacity(0.0, "#00000000"),
        ]
    return [
        ft.Colors.with_opacity(0.85, "#A575FE"),
        ft.Colors.with_opacity(0.55, "#60A0FF"),
        ft.Colors.with_opacity(0.0, "#00000000"),
    ]


def get_connecting_glow_gradient_colors():
    """Amber/orange aurora for the connecting state."""
    return [
        ft.Colors.with_opacity(0.85, "#FBBF24"),
        ft.Colors.with_opacity(0.55, "#F97316"),
        ft.Colors.with_opacity(0.0, "#00000000"),
    ]


def get_disconnected_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=4,
        blur_radius=30,
        color=ft.Colors.with_opacity(0.15, "#C084FC"),
        offset=ft.Offset(0, 0),
    )


def get_connecting_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=10,
        blur_radius=55,
        color=ft.Colors.with_opacity(0.50, "#6366F1"),
        offset=ft.Offset(0, 0),
    )


def get_disconnecting_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=10,
        blur_radius=55,
        color=ft.Colors.with_opacity(0.45, ft.Colors.RED_400),
        offset=ft.Offset(0, 0),
    )


def format_uptime(elapsed: int | float | str) -> str:
    """Format elapsed seconds into HH:MM:SS format."""
    if isinstance(elapsed, (int, float)):
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return str(elapsed)
