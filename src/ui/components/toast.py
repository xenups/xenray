"""Toast notification component with glassy effect."""
from __future__ import annotations

import asyncio

import flet as ft


class Toast(ft.Container):
    """A glassy toast notification that appears at the top center of the screen."""

    def __init__(
        self,
        message: str,
        message_type: str = "info",  # "info", "success", "error", "warning"
        duration: int = 3000,  # milliseconds
    ):
        # Icon map
        icon_map = {
            "info": ft.Icons.INFO_ROUNDED,
            "success": ft.Icons.CHECK_CIRCLE_ROUNDED,
            "error": ft.Icons.ERROR_ROUNDED,
            "warning": ft.Icons.WARNING_ROUNDED,
        }

        icon = icon_map.get(message_type, ft.Icons.INFO_ROUNDED)

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(icon, color=ft.Colors.BLUE_400, size=15),
                    ft.Text(
                        message,
                        size=11,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.WHITE,
                    ),
                ],
                spacing=8,
                tight=True,
            ),
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.SURFACE),  # More transparent
            blur=30,  # More blur
            border_radius=10,
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK),
                offset=ft.Offset(0, 2),
            ),
            animate_opacity=300,
            opacity=1,
        )

        self.duration = duration


class ToastManager:
    """Manages toast notifications for the application."""

    def __init__(self, page: ft.Page):
        self._page = page

    def show(
        self,
        message: str,
        message_type: str = "info",
        duration: int = 3000,
    ):
        """Show a toast notification."""
        toast = Toast(message, message_type, duration)

        # Create a positioned container - positioned above connect button
        toast_container = ft.Container(
            content=toast,
            top=75,  # Position higher - above connect button with margin from header
            left=0,
            right=0,
            alignment=ft.Alignment.TOP_CENTER,
        )

        # Add to overlay
        self._page.overlay.append(toast_container)
        self._page.update()

        # Auto-dismiss
        async def auto_dismiss():
            try:
                await asyncio.sleep(duration / 1000)

                # Fade out
                toast.opacity = 0
                self._page.update()

                # Wait for fade animation
                await asyncio.sleep(0.3)

                # Remove from overlay
                if toast_container in self._page.overlay:
                    self._page.overlay.remove(toast_container)
                    self._page.update()
            except Exception:
                # Cleanup on error
                try:
                    if toast_container in self._page.overlay:
                        self._page.overlay.remove(toast_container)
                        self._page.update()
                except Exception:
                    # Ignore errors during cleanup
                    pass

        # Use page.run_task for proper async execution
        self._page.run_task(auto_dismiss)

    def info(self, message: str, duration: int = 3000):
        """Show an info toast."""
        self.show(message, "info", duration)

    def success(self, message: str, duration: int = 3000):
        """Show a success toast."""
        self.show(message, "success", duration)

    def error(self, message: str, duration: int = 3000):
        """Show an error toast."""
        self.show(message, "error", duration)

    def warning(self, message: str, duration: int = 3000):
        """Show a warning toast."""
        self.show(message, "warning", duration)
