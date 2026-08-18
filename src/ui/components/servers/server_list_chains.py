"""Chain management actions for the ServerList component."""

from __future__ import annotations

from typing import Optional

from src.core.i18n import t
from src.core.logger import logger


class ServerListChainsMixin:
    """Mixin providing ServerList methods — no state of its own."""

    def _select_chain(self, chain: dict):
        """Handle chain selection for connection."""
        # Check if chain is valid
        if not chain.get("valid", True):
            if self._toast:
                self._toast.error(t("chain.toast.invalid_chain"))
            return

        self._selected_profile_id = chain["id"]

        # Pass chain to parent with a special marker and exit server's country info
        chain_with_marker = chain.copy()
        chain_with_marker["_is_chain"] = True

        # Get exit server (last in chain) for country/flag display
        if chain.get("items"):
            last_profile_id = chain["items"][-1]
            exit_profile = self._app_context.get_profile_by_id(last_profile_id)
            if exit_profile:
                chain_with_marker["country_code"] = exit_profile.get("country_code")
                chain_with_marker["country_name"] = exit_profile.get("country_name")

        if self._on_server_selected:
            self._on_server_selected(chain_with_marker)
        self._load_profiles(update_ui=True)

    def _edit_chain(self, chain: dict):
        """Open chain builder view for editing."""
        self.show_chain_builder(existing_chain=chain)

    def _delete_chain(self, chain_id: str):
        """Delete a chain."""
        self._app_context.chains.delete(chain_id)
        self._load_profiles(update_ui=True)
        if self._toast:
            self._toast.success(t("chain.toast.deleted"))

    def _handle_chain_saved(self, name: str, profile_ids: list):
        """Handle a new chain being saved."""
        chain_id = self._app_context.save_chain(name, profile_ids)
        if chain_id:
            if self._toast:
                self._toast.success(t("chain.toast.created", name=name))
            self._load_profiles(update_ui=True)

    def _handle_chain_updated(self, chain_id: str, name: str, profile_ids: list):
        """Handle a chain being updated."""
        success = self._app_context.update_chain(
            chain_id,
            {
                "name": name,
                "items": profile_ids,
            },
        )
        if success:
            if self._toast:
                self._toast.success(t("chain.toast.updated"))
            self._load_profiles(update_ui=True)

    def show_chain_builder(self, existing_chain: Optional[dict] = None):
        """Show the chain builder page for creating/editing a chain."""
        # Lazy import: ChainBuilderPage pulls in common/__init__ (Header,
        # NavSidebar, ...). Importing it at module level created a circular
        # import chain (server_list -> server_list_chains -> chain_builder_page
        # -> common -> ...) that stalled first-render of unrelated pages like
        # Statistics. Only load it when the user actually opens the builder.
        from src.ui.pages.chain_builder_page import ChainBuilderPage

        if not self._navigate_to:
            logger.warning("No navigate_to callback available for chain builder")
            return

        # Close the server sheet first
        if self._close_sheet:
            self._close_sheet()

        logger.info("Opening chain builder page")

        def on_back(e=None):
            """Handle back navigation from chain builder."""
            logger.info("Navigating back from chain builder")
            if self._navigate_back:
                self._navigate_back()
            # Reload profiles after returning
            self._load_profiles(update_ui=True)

        def on_save(name: str, profile_ids: list):
            """Handle chain save."""
            if existing_chain:
                if self._toast:
                    self._toast.success(t("chain.toast.updated"))
            else:
                if self._toast:
                    self._toast.success(t("chain.toast.created", name=name))

        chain_page = ChainBuilderPage(
            app_context=self._app_context,
            on_back=on_back,
            on_save=on_save,
            existing_chain=existing_chain,
        )

        # Navigate to the chain builder page
        self._navigate_to(chain_page)
