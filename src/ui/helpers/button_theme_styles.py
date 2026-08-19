"""Theme styles and formatting helpers for ConnectionButton."""

from __future__ import annotations

import flet as ft

# ---------------------------------------------------------------------------
# Colors and Palette
# ---------------------------------------------------------------------------
COLOR_CONNECTED_BG = "#8b5cf6"
COLOR_CONNECTED_BORDER = "#a78bfa"
COLOR_CONNECTED_TEXT = "#4ADE80"

COLOR_DISCONNECTED_BG = "#1e293b"
COLOR_DISCONNECTED_BORDER = ft.Colors.WHITE
COLOR_DISCONNECTED_TEXT = ft.Colors.WHITE_70

COLOR_CONNECTING_BG = "#f59e0b"
COLOR_CONNECTING_BORDER = "#fbbf24"
COLOR_CONNECTING_TEXT = ft.Colors.WHITE

COLOR_DISCONNECTING_BG = ft.Colors.RED_700
COLOR_DISCONNECTING_BORDER = ft.Colors.RED_400
COLOR_DISCONNECTING_TEXT = ft.Colors.WHITE


def get_sweep_gradient() -> ft.SweepGradient:
    """Return the sweep gradient for the rotating neon ping disc."""
    return ft.SweepGradient(
        center=ft.Alignment.CENTER,
        colors=["#A3A8FE", "#00F2FE", "#00000000", "#00000000"],
        stops=[0.0, 0.10, 0.22, 1.0],
        rotation=0.0,
    )


def get_connected_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=30,
        color=ft.Colors.with_opacity(0.7, "#8b5cf6"),
        offset=ft.Offset(0, 0),
    )


def get_disconnected_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=20,
        color=ft.Colors.with_opacity(0.15, ft.Colors.BLACK),
        offset=ft.Offset(0, 0),
    )


def get_connecting_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=28,
        color=ft.Colors.with_opacity(0.35, "#f59e0b"),
        offset=ft.Offset(0, 0),
    )


def get_disconnecting_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=28,
        color=ft.Colors.with_opacity(0.35, ft.Colors.RED_400),
        offset=ft.Offset(0, 0),
    )


def format_uptime(elapsed: int | float | str) -> str:
    """Format elapsed seconds into HH:MM:SS format."""
    if isinstance(elapsed, (int, float)):
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return str(elapsed)
