"""Application Context - Lightweight container for repositories and services."""
import os
from typing import Optional, Tuple

from src.core.constants import RECENT_FILES_PATH
from src.core.logger import logger


class AppContext:
    """
    Application context - dependency container exposing repositories as public attributes.

    Usage:
        ctx = AppContext.create()
        profiles = ctx.profiles.load_all()
        ctx.settings.set_theme_mode("dark")
    """

    def __init__(
        self,
        config_dir: str,
        profiles,
        subscriptions,
        chains,
        settings,
        routing,
        dns,
        recent_files,
        config_loader,
        profile_resolver,
    ):
        """Initialize with all dependencies."""
        self.config_dir = config_dir

        # Repositories (public)
        self.profiles = profiles
        self.subscriptions = subscriptions
        self.chains = chains
        self.settings = settings
        self.routing = routing
        self.dns = dns
        self.recent_files = recent_files
        self.config_loader = config_loader

        # Services (public)
        self.profile_resolver = profile_resolver

        self._ensure_config_dir()

    @classmethod
    def create(cls) -> "AppContext":
        """Factory method to create AppContext with default dependencies."""
        from src.core.profile_resolver import ProfileResolver
        from src.repositories import (
            ChainRepository,
            ConfigFileLoader,
            DNSRepository,
            ProfileRepository,
            RecentFilesRepository,
            RoutingRepository,
            SettingsRepository,
            SubscriptionRepository,
        )

        config_dir = os.path.dirname(RECENT_FILES_PATH)
        profiles = ProfileRepository(config_dir)
        subscriptions = SubscriptionRepository(config_dir)
        chains = ChainRepository(config_dir)

        return cls(
            config_dir=config_dir,
            profiles=profiles,
            subscriptions=subscriptions,
            chains=chains,
            settings=SettingsRepository(config_dir),
            routing=RoutingRepository(config_dir),
            dns=DNSRepository(config_dir),
            recent_files=RecentFilesRepository(),
            config_loader=ConfigFileLoader(),
            profile_resolver=ProfileResolver(profiles, subscriptions, chains),
        )

    def _ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to create config directory: {e}")
            raise

    # --- Convenience methods for common operations ---

    def get_profile_by_id(self, profile_id: str, search_chains: bool = True) -> Optional[dict]:
        """Resolve profile by ID across all sources."""
        return self.profile_resolver.resolve(profile_id, include_chains=search_chains)


    def load_config(self, file_path: str) -> Tuple[Optional[dict], bool]:
        """Load xray config from file."""
        return self.config_loader.load(file_path)


    # --- Chain convenience methods (need profile_resolver) ---

    def load_chains(self) -> list[dict]:
        """Load chains with validation status."""
        return self.chains.load_enriched(self.profile_resolver)

    def save_chain(self, name: str, profile_ids: list[str]) -> Optional[str]:
        """Save a new chain with validation."""
        return self.chains.save_validated(name, profile_ids, self.profile_resolver)

    def update_chain(self, chain_id: str, updates: dict) -> bool:
        """Update an existing chain with validation."""
        return self.chains.update_validated(chain_id, updates, self.profile_resolver)

    def get_chain_by_id(self, chain_id: str) -> Optional[dict]:
        """Get a chain by ID with validation status."""
        return self.chains.get_enriched_by_id(chain_id, self.profile_resolver)


    def validate_chain(self, profile_ids: list[str]) -> tuple[bool, str]:
        """Validate a chain configuration."""
        return self.chains.validate(profile_ids, self.profile_resolver)
