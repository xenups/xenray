"""Routing Controller - manages domain and IP routing rules and quick toggles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from src.core.app_context import AppContext


class RoutingController:
    """Controller handling routing rules persistence and toggle modifications."""

    def __init__(self, app_context: AppContext) -> None:
        self._app_context = app_context
        self._rules: Dict[str, List[str]] = self._app_context.routing.load_rules()
        self._toggles: Dict[str, bool] = self._app_context.routing.load_toggles()

    @property
    def rules(self) -> Dict[str, List[str]]:
        """Current routing rules dictionary."""
        return self._rules

    @property
    def toggles(self) -> Dict[str, bool]:
        """Current routing toggles dictionary."""
        return self._toggles

    def update_toggle(self, key: str, value: bool) -> None:
        """Update toggle state and save to app settings."""
        self._toggles[key] = value
        self._app_context.routing.save_toggle(key, value)

    def add_rule(self, tab_key: str, rule: str) -> bool:
        """Add a domain or IP rule to target tab list if not already present."""
        clean_rule = rule.strip()
        if not clean_rule:
            return False

        tab_list = self._rules.setdefault(tab_key, [])
        if clean_rule not in tab_list:
            tab_list.append(clean_rule)
            self.save_rules()
            return True
        return False

    def delete_rule(self, tab_key: str, rule: str) -> bool:
        """Delete a rule from target tab list."""
        tab_list = self._rules.get(tab_key, [])
        if rule in tab_list:
            tab_list.remove(rule)
            self.save_rules()
            return True
        return False

    def save_rules(self) -> None:
        """Persist routing rules."""
        self._app_context.routing.save_rules(self._rules)
