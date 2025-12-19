"""Flet-based log viewer component."""

import os
import threading
import time
from typing import Optional

import flet as ft

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
            text_style=ft.TextStyle(font_family="Consolas", size=12),
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=ft.Colors.TRANSPARENT,
        )

        self._container = ft.Container(content=self._log_text, expand=True)

        self._log_thread: Optional[threading.Thread] = None
        self._stop_flag: Optional[threading.Event] = None
        self._page: Optional[ft.Page] = None
        self.MAX_CHARS = 10000

    @property
    def control(self) -> ft.Container:
        """Get the Flet control."""
        return self._container

    def set_page(self, page: ft.Page):
        """Set the page reference for updates."""
        self._page = page

    def start_tailing(self, *filepaths: str) -> None:
        """Start tailing one or more log files."""
        self.stop_tailing()

        stop_event = threading.Event()
        self._stop_flag = stop_event

        # بازنشانی وضعیت مکث به حالت فعال
        self._is_paused = False
        self._pause_blocker.set()

        def tail_log():
            file_handles = {}
            last_inodes = {}

            while not stop_event.is_set():
                # --- تغییر ۱: چک کردن وضعیت مکث ---
                # اگر self._pause_blocker.is_set() نباشد، ترد در اینجا مسدود می شود
                self._pause_blocker.wait()

                for filepath in filepaths:
                    try:
                        if not os.path.exists(filepath):
                            continue

                        stat = os.stat(filepath)
                        if last_inodes.get(filepath) != stat.st_ino:
                            if filepath in file_handles:
                                file_handles[filepath].close()
                            file_handles[filepath] = open(
                                filepath, "r", encoding="utf-8", errors="replace"
                            )
                            file_handles[filepath].seek(0, os.SEEK_END)
                            last_inodes[filepath] = stat.st_ino

                        if filepath in file_handles:
                            line = file_handles[filepath].readline()
                            if line:
                                self._append_text(line)

                    except Exception as e:
                        logger.error(f"Error reading log file {filepath}: {e}")
                        if filepath in file_handles:
                            file_handles[filepath].close()
                            del file_handles[filepath]
                        if filepath in last_inodes:
                            del last_inodes[filepath]

                time.sleep(0.5)

            for f in file_handles.values():
                f.close()

        self._log_thread = threading.Thread(target=tail_log, daemon=True)
        self._log_thread.start()

    def stop_tailing(self) -> None:
        """Stop tailing the log file."""
        logger.debug("[DEBUG] LogViewer.stop_tailing called")
        if self._stop_flag:
            self._stop_flag.set()
        # در صورت توقف کامل، از حالت مکث خارج می شویم تا ترد بتواند join شود.
        self._pause_blocker.set()
        if self._log_thread:
            logger.debug("[DEBUG] Joining log thread...")
            self._log_thread.join(timeout=1)
            if self._log_thread.is_alive():
                logger.debug("[DEBUG] Log thread did not exit in time")
            else:
                logger.debug("[DEBUG] Log thread joined")

    # --- متد عمومی جدید برای LogsDrawer ---
    def toggle_pause(self) -> bool:
        """Toggle between paused and running states and returns the new state (is_paused)."""
        self._is_paused = not self._is_paused

        if self._is_paused:
            # حالت مکث: ترد را مسدود کن (Clear the event)
            self._pause_blocker.clear()
        else:
            # حالت ادامه: ترد را آزاد کن (Set the event)
            self._pause_blocker.set()

        return self._is_paused  # وضعیت جدید را به LogsDrawer برمی‌گرداند

    def _append_text(self, text: str):
        """Append text to log viewer (New line at the top)."""
        if self._page:

            async def update_ui():
                current = self._log_text.value or ""
                cleaned_text = text.rstrip()

                # نمایش معکوس (جدیدترین در بالا)
                if current:
                    self._log_text.value = cleaned_text + "\n" + current
                else:
                    self._log_text.value = cleaned_text

                # مدیریت تاریخچه
                if len(self._log_text.value) > self.MAX_CHARS + 2000:
                    self._log_text.value = self._log_text.value[: self.MAX_CHARS]

                self._page.update()

            try:
                self._page.run_task(update_ui)
            except Exception:
                pass
