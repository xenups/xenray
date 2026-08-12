"""Interactive update modal for client / Xray-core updates.

A reusable ``ft.AlertDialog`` that shows a version comparison, optional release
notes, a real-time download ``ft.ProgressBar``, and the standard action buttons
(Update Now / Remind Later / Cancel). Progress is updated IN-PLACE via
``set_progress()`` / ``set_status()`` without any page re-render.
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from src.core.i18n import t

ACCENT = "#A3A8FE"


class UpdateDialog(ft.AlertDialog):
    """Modal dialog for client / core updates with live download progress."""

    def __init__(
        self,
        *,
        current_version: str,
        latest_version: str,
        release_notes: str = "",
        on_update_now: Optional[Callable] = None,
        on_remind_later: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
        title_text: Optional[str] = None,
    ):
        self._on_update_now = on_update_now
        self._on_remind_later = on_remind_later
        self._on_cancel = on_cancel

        # Version comparison row:  v2.4.0  ->  v2.5.0
        current_label = current_version if current_version.startswith("v") else f"v{current_version}"
        latest_label = latest_version if latest_version.startswith("v") else f"v{latest_version}"

        self._version_text = ft.Text(
            f"{current_label}  ->  {latest_label}",
            size=14,
            weight=ft.FontWeight.BOLD,
            color=ACCENT,
        )

        # Optional release notes / changelog.
        self._notes_text = (
            ft.Text(
                release_notes,
                size=11,
                color=ft.Colors.ON_SURFACE_VARIANT,
                selectable=True,
            )
            if release_notes
            else ft.Text(
                t("update.no_release_notes", default="No release notes provided."),
                size=11,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )

        # Real-time download progress bar.
        self._progress = ft.ProgressBar(
            value=0.0,
            color=ACCENT,
            bgcolor=ft.Colors.with_opacity(0.15, ACCENT),
            height=6,
            border_radius=3,
        )
        self._status_text = ft.Text(
            t("update.ready", default="Ready to update."),
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )

        self._update_now_btn = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, size=16, color=ft.Colors.WHITE),
                    ft.Text(
                        t("update.update_now", default="Update Now"),
                        color=ft.Colors.WHITE,
                    ),
                ],
                spacing=6,
                tight=True,
            ),
            bgcolor="#6D28D9",
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            on_click=self._on_update_clicked,
        )

        self._remind_btn = ft.TextButton(
            t("update.remind_later", default="Remind Later"),
            on_click=self._on_remind_clicked,
        )
        self._cancel_btn = ft.TextButton(
            t("update.cancel", default="Cancel"),
            on_click=self._on_cancel_clicked,
        )

        super().__init__(
            modal=True,
            title=ft.Text(
                title_text or t("update.title", default="Update Available"),
                size=16,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE,
            ),
            content=ft.Column(
                [
                    self._version_text,
                    ft.Container(height=4),
                    self._notes_text,
                    ft.Container(height=12),
                    ft.Row(
                        [self._status_text, self._progress],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                width=360,
                tight=True,
                spacing=6,
            ),
            actions=[
                self._remind_btn,
                self._cancel_btn,
                self._update_now_btn,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    # ------------------------------------------------------------------
    # In-place updates (no page re-render)
    # ------------------------------------------------------------------
    def set_progress(self, percent: float) -> None:
        """Update the download progress bar in place (0.0 - 1.0)."""
        self._progress.value = max(0.0, min(1.0, percent))
        try:
            self._progress.update()
        except Exception:
            pass

    def set_status(self, message: str) -> None:
        """Update the status line under the progress bar in place."""
        self._status_text.value = message
        try:
            self._status_text.update()
        except Exception:
            pass

    def set_progress_status(self, percent: float, message: str) -> None:
        """Convenience: update progress bar + status line together."""
        self.set_progress(percent)
        self.set_status(message)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_update_clicked(self, e) -> None:
        if self._on_update_now:
            self._on_update_now(e)

    def _on_remind_clicked(self, e) -> None:
        if self._on_remind_later:
            self._on_remind_later(e)

    def _on_cancel_clicked(self, e) -> None:
        if self._on_cancel:
            self._on_cancel(e)
