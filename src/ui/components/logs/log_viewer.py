"""Flet-based log viewer component."""

import os
import threading
import time
from typing import Optional

import flet as ft

from src.core.constants import TMPDIR
from src.core.logger import logger


class LogViewer:
    """Component for viewing log files in real-time using Flet."""

    def __init__(self, title: str):
        """Initialize log viewer."""
        self._title = title

        # --- وضعیت مکث (جدید و ضروری) ---
        self._is_paused = False
        # Event که در حالت Play ست (Set) و در حالت Pause پاک (Clear) می شود.
        self._pause_blocker = threading.Event()
        self._pause_blocker.set()  # به صورت پیش‌فرض، شروع به کار (Play)

        # 1. تنظیم کنترل نمایشگر لاگ
        self._log_text = ft.TextField(
            value="",
            multiline=True,
            read_only=True,
            expand=True,
            text_style=ft.TextStyle(
                font_family="JetBrains Mono, Fira Code, ui-monospace, Consolas, monospace",
                size=11,
                color="#CBD5E1",
            ),
            bgcolor=ft.Colors.TRANSPARENT,
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=ft.Colors.TRANSPARENT,
        )

        self._container = ft.Container(content=self._log_text, expand=True)

        self._is_visible = False
        self._log_thread: Optional[threading.Thread] = None
        self._stop_flag: Optional[threading.Event] = None
        self._page: Optional[ft.Page] = None
        self.MAX_CHARS = 10000
        # Polling interval (seconds) between reads — keeps CPU low; the user
        # can adjust it (LogsDrawer exposes a control for this).
        self.tail_interval = 1.0

    @property
    def control(self) -> ft.Container:
        """Get the Flet control."""
        return self._container

    def set_page(self, page: ft.Page):
        """Set the page reference for updates."""
        self._page = page

    def set_visible(self, visible: bool):
        """Enable or disable live UI updates for log viewer."""
        was_visible = self._is_visible
        self._is_visible = visible
        if visible and not was_visible and self._page:
            try:
                if self._log_text.page:
                    self._log_text.update()
            except Exception:
                pass

    def start_tailing(self, *filepaths: str) -> None:
        """Start tailing one or more log files.

        The viewer starts OFF (no tailing) — callers must explicitly enable it
        (e.g. the user picks a source in the logs drawer). This keeps CPU usage
        at zero while the logs panel is unused.
        """
        self.stop_tailing()

        stop_event = threading.Event()
        self._stop_flag = stop_event

        # بازنشانی وضعیت مکث به حالت فعال
        self._is_paused = False
        self._pause_blocker.set()

        # Pre-open the files synchronously so the tail offset is captured NOW.
        # A line written right after start_tailing() would otherwise be missed
        # (the thread's first tick would seek to END past it).
        file_handles = {}
        last_inodes = {}
        for filepath in filepaths:
            try:
                if os.path.exists(filepath):
                    f = open(filepath, "r", encoding="utf-8", errors="replace")
                    f.seek(0, os.SEEK_END)
                    file_handles[filepath] = f
                    last_inodes[filepath] = os.stat(filepath).st_ino
            except Exception as e:
                logger.error(f"Error opening log file {filepath}: {e}")

        def tail_log():
            while not stop_event.is_set():
                self._pause_blocker.wait()

                for filepath in filepaths:
                    try:
                        if not os.path.exists(filepath):
                            continue

                        stat = os.stat(filepath)
                        if last_inodes.get(filepath) != stat.st_ino:
                            if filepath in file_handles:
                                file_handles[filepath].close()
                            file_handles[filepath] = open(filepath, "r", encoding="utf-8", errors="replace")
                            file_handles[filepath].seek(0, os.SEEK_END)
                            last_inodes[filepath] = stat.st_ino

                        if filepath in file_handles:
                            lines = []
                            while True:
                                line = file_handles[filepath].readline()
                                if not line:
                                    break
                                lines.append(line)
                            if lines:
                                self._append_batch(lines)

                    except Exception as e:
                        logger.error(f"Error reading log file {filepath}: {e}")
                        if filepath in file_handles:
                            file_handles[filepath].close()
                            del file_handles[filepath]
                        if filepath in last_inodes:
                            del last_inodes[filepath]

                # Respect the user-configured polling interval (low CPU by default)
                time.sleep(max(0.1, self.tail_interval))

            for f in file_handles.values():
                f.close()

        self._log_thread = threading.Thread(target=tail_log, daemon=True)
        self._log_thread.start()

    def stop_tailing(self) -> None:
        """Stop tailing the log file."""
        logger.debug("[DEBUG] LogViewer.stop_tailing called")
        if self._stop_flag:
            self._stop_flag.set()
        self._pause_blocker.set()
        if self._log_thread:
            logger.debug("[DEBUG] Joining log thread...")
            self._log_thread.join(timeout=1)
            if self._log_thread.is_alive():
                logger.debug("[DEBUG] Log thread did not exit in time")
            else:
                logger.debug("[DEBUG] Log thread joined")

    def toggle_pause(self) -> bool:
        """Toggle between paused and running states and returns the new state (is_paused)."""
        self._is_paused = not self._is_paused

        if self._is_paused:
            self._pause_blocker.clear()
        else:
            self._pause_blocker.set()

        return self._is_paused

    def export_logs(self):
        """Save logs to a file in TMPDIR."""
        try:
            path = os.path.join(TMPDIR, "xenray_exported.log")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._log_text.value or "")
            logger.info(f"[LogViewer] Logs exported to {path}")
            if self._page:
                try:
                    self._page.set_clipboard(path)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[LogViewer] Export failed: {e}")

    def copy_to_clipboard(self):
        """Copy current log text to clipboard."""
        if not self._page:
            return
        try:
            self._page.set_clipboard(self._log_text.value or "")
        except Exception:
            pass

    def clear_logs(self):
        """Clear all log text."""
        self._log_text.value = ""
        try:
            if self._log_text.page:
                self._log_text.update()
        except Exception:
            pass

    def _append_batch(self, lines: list[str]):
        """Append batch of lines to log viewer (Newest at top)."""
        new_text = "".join(lines).rstrip()
        if not new_text:
            return

        current = self._log_text.value or ""
        if current:
            self._log_text.value = new_text + "\n" + current
        else:
            self._log_text.value = new_text

        if len(self._log_text.value) > self.MAX_CHARS + 2000:
            self._log_text.value = self._log_text.value[: self.MAX_CHARS]

        # Only dispatch UI update if viewer is currently visible to user
        if self._is_visible and self._page:

            async def update_ui():
                try:
                    if self._log_text.page:
                        self._log_text.update()
                except Exception:
                    pass

            try:
                self._page.run_task(update_ui)
            except Exception:
                pass
