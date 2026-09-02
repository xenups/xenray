"""ThemeProvider — small reactive theme token store for the UI.

Consumers (NavSidebar, WindowTitleBar, ServerSearchBar, UIBuilder, ...) read
``theme_provider.palette`` (a :class:`ThemePalette`) and subscribe to changes via
``theme_provider.subscribe(handler)``.

:class:`ThemePalette` is a plain token bag whose ``__getattr__`` returns a safe
fallback for ANY token it has not explicitly defined, so a consumer referencing a
brand-new token never crashes the app at startup (it just renders the neutral
fallback colour until the token is added here).
"""

from __future__ import annotations

import threading
from typing import Callable, List


class ThemePalette:
    """A bag of colour/style tokens for one appearance (dark or light)."""

    def __init__(self, is_dark: bool, **tokens) -> None:
        self.is_dark = is_dark
        self._tokens: dict = dict(tokens)

    # ------------------------------------------------------------------ #
    # Known tokens
    # ------------------------------------------------------------------ #
    @property
    def gradient_bg(self) -> List[str]:
        return self._tokens.setdefault(
            "gradient_bg",
            (["#0B0813", "#0F1020", "#181333"] if self.is_dark else ["#F4F2FF", "#EFEDFF", "#F9F6FF"]),
        )

    @property
    def primary(self) -> str:
        return self._tokens.setdefault("primary", "#A855F7")

    @property
    def accent(self) -> str:
        return self._tokens.setdefault("accent", "#06B6D4")

    @property
    def text_primary(self) -> str:
        return self._tokens.setdefault("text_primary", "#F8FAFC" if self.is_dark else "#1E1B4B")

    @property
    def text_secondary(self) -> str:
        return self._tokens.setdefault("text_secondary", "#C7CBD8" if self.is_dark else "#4F4A78")

    @property
    def text_muted(self) -> str:
        return self._tokens.setdefault("text_muted", "#8A8F9E" if self.is_dark else "#6E6A96")

    @property
    def text_hint(self) -> str:
        return self._tokens.setdefault(
            "text_hint",
            ("rgba(255,255,255,0.35)" if self.is_dark else "rgba(30,27,75,0.4)"),
        )

    @property
    def bg_sidebar(self) -> str:
        return self._tokens.setdefault(
            "bg_sidebar",
            ("rgba(11,5,24,0.55)" if self.is_dark else "rgba(238,234,255,0.85)"),
        )

    @property
    def border_sidebar(self) -> str:
        return self._tokens.setdefault(
            "border_sidebar",
            ("rgba(168,85,247,0.12)" if self.is_dark else "rgba(168,85,247,0.25)"),
        )

    @property
    def bg_card(self) -> str:
        return self._tokens.setdefault("bg_card", "#151A2A" if self.is_dark else "#FFFFFF")

    @property
    def border_card(self) -> str:
        return self._tokens.setdefault(
            "border_card",
            ("rgba(255,255,255,0.07)" if self.is_dark else "rgba(30,27,75,0.08)"),
        )

    @property
    def bg_active_badge(self) -> str:
        return self._tokens.setdefault(
            "bg_active_badge",
            ("rgba(168,85,247,0.18)" if self.is_dark else "rgba(168,85,247,0.14)"),
        )

    @property
    def border_active(self) -> str:
        return self._tokens.setdefault("border_active", "rgba(168,85,247,0.35)")

    @property
    def border_divider(self) -> str:
        return self._tokens.setdefault(
            "border_divider",
            ("rgba(255,255,255,0.06)" if self.is_dark else "rgba(30,27,75,0.08)"),
        )

    @property
    def bg_button(self) -> str:
        return self._tokens.setdefault(
            "bg_button",
            ("rgba(255,255,255,0.35)" if self.is_dark else "rgba(168,85,247,0.12)"),
        )

    @property
    def border_button(self) -> str:
        return self._tokens.setdefault("border_button", "rgba(255,255,255,0.55)")

    # ------------------------------------------------------------------ #
    # Safety net: ANY token not defined above returns a neutral fallback so a
    # consumer referencing a brand-new token never crashes startup.
    # ------------------------------------------------------------------ #
    def __getattr__(self, name: str):
        if name.startswith("_") or name in _RESERVED:
            raise AttributeError(name)
        # Best-effort sensible colour for unknown tokens.
        if name.startswith("bg"):
            return self.bg_card
        if name.startswith("border"):
            return self.border_card
        if name.startswith("text"):
            return self.text_secondary
        return self.primary


_RESERVED = frozenset(
    {
        "palette",
        "subscribe",
        "unsubscribe",
        "set_dark",
        "toggle",
        "_lock",
        "_handlers",
        "palette",
    }
)


class ThemeProvider:
    """Process-wide singleton theme store with subscriber notifications."""

    def __init__(self, is_dark: bool = True) -> None:
        self._lock = threading.Lock()
        self._handlers: List[Callable[[ThemePalette], None]] = []
        self._palette = ThemePalette(is_dark=is_dark)

    @property
    def palette(self) -> ThemePalette:
        return self._palette

    def subscribe(self, handler: Callable[[ThemePalette], None]) -> None:
        with self._lock:
            if handler not in self._handlers:
                self._handlers.append(handler)

    def unsubscribe(self, handler: Callable[[ThemePalette], None]) -> None:
        with self._lock:
            if handler in self._handlers:
                self._handlers.remove(handler)

    def set_dark(self, is_dark: bool) -> None:
        with self._lock:
            if self._palette.is_dark is is_dark:
                return
            self._palette = ThemePalette(is_dark=is_dark)
            handlers = list(self._handlers)
        for fn in handlers:
            try:
                fn(self._palette)
            except Exception:
                pass

    def toggle(self) -> None:
        self.set_dark(not self._palette.is_dark)


theme_provider = ThemeProvider(is_dark=True)
