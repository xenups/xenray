"""DNS Controller - manages DNS server entries, priority reordering, and configuration persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from src.core.app_context import AppContext


class DNSController:
    """Controller handling DNS server entries and order modifications."""

    def __init__(self, app_context: AppContext) -> None:
        self._app_context = app_context
        self._dns_list: List[Dict[str, str]] = self._app_context.dns.load()

    @property
    def dns_list(self) -> List[Dict[str, str]]:
        """Current DNS server entries list."""
        return self._dns_list

    def add_server(self, address: str, protocol: str) -> bool:
        """Add a DNS server entry."""
        clean_addr = address.strip()
        if not clean_addr:
            return False

        entry = {"address": clean_addr, "protocol": protocol, "domains": []}
        self._dns_list.append(entry)
        self.save()
        return True

    def delete_server(self, idx: int) -> bool:
        """Delete a DNS server entry by index."""
        if 0 <= idx < len(self._dns_list):
            self._dns_list.pop(idx)
            self.save()
            return True
        return False

    def move_up(self, idx: int) -> bool:
        """Move a DNS server entry up in priority order."""
        if idx > 0 and idx < len(self._dns_list):
            self._dns_list[idx], self._dns_list[idx - 1] = (
                self._dns_list[idx - 1],
                self._dns_list[idx],
            )
            self.save()
            return True
        return False

    def save(self) -> None:
        """Persist DNS server entries."""
        self._app_context.dns.save(self._dns_list)
