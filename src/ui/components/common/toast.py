"""Toast notification component with glassy effect and bottom floating alignment."""

from __future__ import annotations

import asyncio
from typing import Optional

import flet as ft


class Toast(ft.Container):
    """A glassy toast notification that floats cleanly in the bottom corner of the screen."""

    def __init__(
        self,
        message: str,
        message_type: str = "info",  # "info", "success", "error", "warning"
        duration: int = 3000,  # milliseconds
    ):
        color_map = {
            "info": (ft.Icons.INFO_ROUNDED, ft.Colors.BLUE_400),
            "success": (ft.Icons.CHECK_CIRCLE_ROUNDED, ft.Colors.GREEN_400),
            "error": (ft.Icons.ERROR_ROUNDED, ft.Colors.RED_400),
            "warning": (ft.Icons.WARNING_ROUNDED, ft.Colors.AMBER_400),
        }

        icon, icon_color = color_map.get(message_type, (ft.Icons.INFO_ROUNDED, ft.Colors.BLUE_400))

        is_rtl = False
        try:
            from src.core.i18n import get_language  # noqa: PLC0415

            is_rtl = get_language() == "fa"
        except Exception:
            pass

        super().__init__(
            content=ft.Row(
                [
                    ft.Icon(icon, color=icon_color, size=18),
                    ft.Text(
                        message,
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.WHITE,
                        rtl=is_rtl,
                    ),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            bgcolor=ft.Colors.with_opacity(0.9, "#13141C"),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.WHITE)),
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=16,
                color=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
                offset=ft.Offset(0, 4),
            ),
            animate_opacity=300,
            animate_offset=300,
            opacity=1,
            offset=ft.Offset(0, 0),
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
        """Show a toast notification floating in the bottom corner of the main content view."""
        toast = Toast(message, message_type, duration)

        # Floating toast container at Top-Center with top margin
        toast_container = ft.Container(
            content=toast,
            top=20,
            left=0,
            right=0,
            alignment=ft.Alignment.TOP_CENTER,
            margin=ft.Margin.only(top=20),
        )

        # Add to overlay and update overlay layer target specifically to render without full page scroll flicker
        self._page.overlay.append(toast_container)
        try:
            self._page.update(self._page.overlay)
        except Exception:
            try:
                self._page.update(toast_container)
            except Exception:
                pass

        # Auto-dismiss with smooth entrance/exit slide animation
        async def auto_dismiss():
            try:
                await asyncio.sleep(duration / 1000)

                # Fade and slide up out
                toast.opacity = 0
                toast.offset = ft.Offset(0, -0.2)
                try:
                    toast.update()
                except Exception:
                    pass

                # Wait for animation
                await asyncio.sleep(0.3)

                # Remove from overlay and update overlay layer
                if toast_container in self._page.overlay:
                    self._page.overlay.remove(toast_container)
                    try:
                        self._page.update(self._page.overlay)
                    except Exception:
                        pass
            except Exception:
                # Cleanup on error
                try:
                    if toast_container in self._page.overlay:
                        self._page.overlay.remove(toast_container)
                        try:
                            self._page.update(self._page.overlay)
                        except Exception:
                            pass
                except Exception:
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

    @staticmethod
    def show_info(page: Optional[ft.Page], message: str, duration: int = 3000):
        """Static helper to safely display an info toast on page."""
        if not page:
            return
        try:
            if hasattr(page, "_toast_manager") and page._toast_manager:
                page._toast_manager.info(message, duration)
            else:
                ToastManager(page).info(message, duration)
        except Exception:
            pass

    @staticmethod
    def show_success(page: Optional[ft.Page], message: str, duration: int = 3000):
        """Static helper to safely display a success toast on page."""
        if not page:
            return
        try:
            if hasattr(page, "_toast_manager") and page._toast_manager:
                page._toast_manager.success(message, duration)
            else:
                ToastManager(page).success(message, duration)
        except Exception:
            pass

    @staticmethod
    def show_error(page: Optional[ft.Page], message: str, duration: int = 3000):
        """Static helper to safely display an error toast on page."""
        if not page:
            return
        try:
            if hasattr(page, "_toast_manager") and page._toast_manager:
                page._toast_manager.error(message, duration)
            else:
                ToastManager(page).error(message, duration)
        except Exception:
            pass

    @staticmethod
    def show_warning(page: Optional[ft.Page], message: str, duration: int = 3000):
        """Static helper to safely display a warning toast on page."""
        if not page:
            return
        try:
            if hasattr(page, "_toast_manager") and page._toast_manager:
                page._toast_manager.warning(message, duration)
            else:
                ToastManager(page).warning(message, duration)
        except Exception:
            pass
