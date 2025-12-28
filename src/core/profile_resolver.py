"""Profile Resolver - Cross-domain profile lookup."""
from typing import Optional, Protocol


class ProfileResolverProtocol(Protocol):
    """Protocol for profile resolution - used by validators."""

    def resolve(self, profile_id: str, include_chains: bool = True) -> Optional[dict]:
        """Find profile by ID across all sources."""
        ...

    def resolve_for_validation(self, profile_id: str) -> Optional[dict]:
        """Find profile for chain validation (excludes chain search)."""
        ...


class ProfileResolver:
    """Resolves profiles across profiles, subscriptions, and chains."""

    def __init__(self, profiles_repo, subscriptions_repo, chains_repo):
        """Initialize with repository dependencies."""
        self._profiles = profiles_repo
        self._subscriptions = subscriptions_repo
        self._chains = chains_repo

    def resolve(self, profile_id: str, include_chains: bool = True) -> Optional[dict]:
        """
        Find profile by ID across all sources.

        Args:
            profile_id: ID to search for
            include_chains: Whether to include chains in search

        Returns:
            Profile dict or None
        """
        if not profile_id:
            return None

        # 1. Search local profiles
        for p in self._profiles.load_all():
            if p.get("id") == profile_id:
                return p

        # 2. Search subscriptions
        for sub in self._subscriptions.load_all():
            for p in sub.get("profiles", []):
                if p.get("id") == profile_id:
                    return p

        # 3. Search chains (optional)
        if include_chains:
            for chain in self._chains.load_all():
                if chain.get("id") == profile_id:
                    return self._enrich_chain(chain)

        return None

    def resolve_for_validation(self, profile_id: str) -> Optional[dict]:
        """Find profile for chain validation (excludes chain search)."""
        return self.resolve(profile_id, include_chains=False)

    def _enrich_chain(self, chain: dict) -> dict:
        """Enrich chain with metadata."""
        chain_match = chain.copy()
        chain_match["_is_chain"] = True

        # Populate country info from exit node
        items = chain_match.get("items", [])
        if items:
            last_id = items[-1]
            exit_profile = self.resolve_for_validation(last_id)
            if exit_profile:
                chain_match["country_code"] = exit_profile.get("country_code")
                chain_match["country_name"] = exit_profile.get("country_name")

        return chain_match
