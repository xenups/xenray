"""System clipboard utility for reading and writing text cross-platform."""

from __future__ import annotations

import subprocess
import sys


def get_clipboard_text() -> str:
    """Retrieve text from system clipboard (Windows native ctypes, macOS, Linux)."""
    if sys.platform == "win32":
        try:
            import ctypes

            cf_unicodetext = 13
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32

            u32.OpenClipboard.argtypes = [ctypes.c_void_p]
            u32.OpenClipboard.restype = ctypes.c_bool
            u32.GetClipboardData.argtypes = [ctypes.c_uint]
            u32.GetClipboardData.restype = ctypes.c_void_p
            u32.CloseClipboard.argtypes = []
            u32.CloseClipboard.restype = ctypes.c_bool
            u32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
            u32.IsClipboardFormatAvailable.restype = ctypes.c_bool
            k32.GlobalLock.argtypes = [ctypes.c_void_p]
            k32.GlobalLock.restype = ctypes.c_void_p
            k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            k32.GlobalUnlock.restype = ctypes.c_bool

            if not u32.OpenClipboard(None):
                return ""
            try:
                if not u32.IsClipboardFormatAvailable(cf_unicodetext):
                    return ""
                h = u32.GetClipboardData(cf_unicodetext)
                if not h:
                    return ""
                p = k32.GlobalLock(h)
                if not p:
                    return ""
                try:
                    return ctypes.c_wchar_p(p).value or ""
                finally:
                    k32.GlobalUnlock(h)
            finally:
                u32.CloseClipboard()
        except Exception:
            return ""

    try:
        if sys.platform == "darwin":
            return subprocess.check_output(["pbpaste"], text=True)
        elif sys.platform.startswith("linux"):
            for cmd in [["xclip", "-selection", "clipboard", "-o"], ["wl-paste"]]:
                try:
                    return subprocess.check_output(cmd, text=True)
                except Exception:
                    continue
    except Exception:
        pass

    return ""
