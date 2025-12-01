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
        self._log_text = ft.TextField(
            value="",
            multiline=True,
            read_only=True,
            expand=True,  # Expand to fill container
            text_style=ft.TextStyle(font_family="Consolas", size=12),
            border_color=ft.colors.TRANSPARENT,
            focused_border_color=ft.colors.TRANSPARENT,
        )

        self._container = ft.Container(
            content=self._log_text, expand=True  # Make container expand too
        )

        self._log_thread: Optional[threading.Thread] = None
        self._stop_flag: Optional[threading.Event] = None
        self._page: Optional[ft.Page] = None

    @property
    def control(self) -> ft.Container:
        """Get the Flet control."""
        return self._container

    def set_page(self, page: ft.Page):
        """Set the page reference for updates."""
        self._page = page

    def start_tailing(self, *filepaths: str) -> None:
        """Start tailing one or more log files."""
        # Ensure previous thread is stopped before starting a new one
        self.stop_tailing()

        # Create a new event for this specific thread
        stop_event = threading.Event()
        self._stop_flag = stop_event

        def tail_log():
            file_handles = {}
            last_inodes = {}

            # Use the local stop_event, NOT self._stop_flag
            # This prevents race conditions if self._stop_flag is overwritten
            while not stop_event.is_set():
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
        if self._log_thread:
            logger.debug("[DEBUG] Joining log thread...")
            self._log_thread.join(timeout=1)
            if self._log_thread.is_alive():
                logger.debug("[DEBUG] Log thread did not exit in time")
            else:
                logger.debug("[DEBUG] Log thread joined")

    def _append_text(self, text: str):
        """Append text to log viewer."""
        if self._page:

            async def update_ui():
                current = self._log_text.value or ""
                # Keep last 10000 chars for better history viewing
                if len(current) > 12000:
                    current = current[-10000:]
                self._log_text.value = current + text
                self._page.update()

            try:
                self._page.run_task(update_ui)
            except:
                pass
