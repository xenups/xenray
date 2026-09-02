"""Sort handling for the ServerList component (single-responsibility mixin)."""

from __future__ import annotations


class ServerListSortMixin:
    """Mixin providing ServerList methods — no state of its own."""

    # Cache of localized country names keyed by country code (pycountry lookups
    # are slow; reuse across the 1000+ items of a large list).
    _localized_country_cache: dict = {}

    def _localized_country_name(self, country_code: str) -> str:
        """Return the country's name in the CURRENT app language (e.g. Persian
        "فنلاند" for FI), falling back to an empty string."""
        if not country_code:
            return ""
        key = country_code.upper()
        if key not in self._localized_country_cache:
            try:
                from src.core.country_translator import translate_country

                self._localized_country_cache[key] = translate_country(key) or ""
            except Exception:
                self._localized_country_cache[key] = ""
        return self._localized_country_cache[key]

    def _on_sort_changed(self, mode: str):
        """Handle sort mode change.

        Re-sorts the in-memory profiles (which carry freshly resolved RAM
        latency values) — it NEVER re-reads the profile list from disk, because
        ping results are volatile in-memory state and would be lost.
        """
        self._app_context.settings.set_sort_mode(mode)
        if self._active_subscription:
            self._enter_subscription_view(self._active_subscription, preserve_tests=True)
        else:
            self._resort_profiles_in_place()

    def _resort_profiles_in_place(self):
        """Re-order the existing profile cards in the current list view using the
        in-memory profile latency values (no disk reload, single list update)."""
        from src.ui.components.servers.server_list_item import ServerListItem

        list_view = self._current_list_view
        if list_view is None:
            return

        sorted_profiles = self._apply_sort(self._profiles)
        order = {str(p.get("id")): i for i, p in enumerate(sorted_profiles)}
        # Map id -> resolved latency (from the in-memory model, which carries
        # volatile ping results that are NOT on disk).
        latency_by_id = {}
        for p in self._profiles:
            pid = str(p.get("id"))
            val = p.get("last_latency_val")
            if val is not None:
                latency_by_id[pid] = val

        fixed = [c for c in list_view.controls if not isinstance(c, ServerListItem)]
        cards = [c for c in list_view.controls if isinstance(c, ServerListItem)]
        cards.sort(key=lambda c: order.get(str(c._profile.get("id")), 999999))

        list_view.controls[:] = fixed + cards

        # Re-apply the ping badge on every moved card. Reordering the ListView
        # controls can re-mount children on the client, which would rebuild the
        # card from its construction-time cached_ping (usually None) and show
        # "..." even though the in-memory model has the fresh latency.
        for card in cards:
            pid = str(card._profile.get("id"))
            val = latency_by_id.get(pid)
            if val is not None and hasattr(card, "update_ping"):
                try:
                    from src.core.i18n import t

                    card.update_ping(
                        t("connection.latency_ms", default=f"{val} ms", value=val),
                        card._get_ping_color(val) if hasattr(card, "_get_ping_color") else None,
                    )
                except Exception:
                    pass

        try:
            list_view.update()
        except Exception:
            pass

    def _apply_sort(self, items: list) -> list:
        """Apply current sort mode to items."""
        mode = self._app_context.settings.get_sort_mode()

        def get_latency(item):
            # Fresh in-memory latency (synced from inspection results) wins.
            val = item.get("last_latency_val")
            if val is not None:
                return val
            # Fallback: tester cache, then uninspected -> bottom.
            pid = item.get("id")
            cached = self._latency_tester.get_cached_result(pid)
            if cached:
                return cached[2]
            return 999999

        if mode == "name_asc":
            return sorted(items, key=lambda x: x.get("name", "").lower())
        if mode == "ping_asc":
            return sorted(items, key=get_latency)
        return items

    def _matches_query(self, item: dict) -> bool:
        """Check if an item matches the current search query.

        Matches against: name, address/host, country (English), country code,
        AND the localized country name (e.g. Persian "فنلاند" for FI).
        """
        query = self._search_query
        if not query:
            return True

        haystack = [item.get("name", "")]

        # Location metadata: English country name + code.
        region = item.get("region") or item.get("country") or item.get("country_name")
        if region:
            haystack.append(str(region))
        cc = item.get("country_code")
        if cc:
            haystack.append(str(cc))
            localized = self._localized_country_name(cc)
            if localized:
                haystack.append(str(localized))

        # Top-level address/host fields.
        host = item.get("address") or item.get("host") or item.get("server")
        if host:
            haystack.append(str(host))

        config = item.get("config", {})
        for outbound in config.get("outbounds", []):
            settings = outbound.get("settings", {})
            for group in ("vnext", "servers"):
                for server in settings.get(group, []):
                    address = server.get("address")
                    if address:
                        haystack.append(str(address))
            address = outbound.get("address")
            if address:
                haystack.append(str(address))

        return any(query in text.lower() for text in haystack)
