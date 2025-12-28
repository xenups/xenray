"""Validators - Pure functions for validation (exception-based)."""


class ValidationError(ValueError):
    """Raised when validation fails."""

    pass


def validate_port(port: int) -> None:
    """Validate proxy port is in valid range."""
    if not isinstance(port, int):
        raise ValidationError("Port must be an integer")
    if not (1024 <= port <= 65535):
        raise ValidationError(f"Port must be between 1024 and 65535, got {port}")


def validate_chain_items(items: list[str], is_chain_fn, profile_resolver) -> None:
    """
    Validate chain configuration.

    Args:
        items: List of profile IDs
        is_chain_fn: Callable to check if ID is a chain
        profile_resolver: Object with resolve_for_validation(profile_id) method

    Raises:
        ValidationError: If validation fails
    """
    if not items or not isinstance(items, list):
        raise ValidationError("Invalid chain items")

    if len(items) < 2:
        raise ValidationError("Chain must have at least 2 items")

    if len(items) != len(set(items)):
        raise ValidationError("Duplicate server in chain")

    chainable = {"vless", "vmess", "trojan", "shadowsocks"}
    blocked = {"freedom", "blackhole", "dns", "loopback"}

    for idx, profile_id in enumerate(items):
        if is_chain_fn(profile_id):
            raise ValidationError("Chains cannot contain other chains")

        profile = profile_resolver.resolve_for_validation(profile_id)
        if not profile:
            raise ValidationError(f"Server not found: {profile_id[:8]}...")

        config = profile.get("config", {})
        outbound = _get_chain_outbound(config, chainable)

        if not outbound:
            raise ValidationError("No valid proxy outbound in profile")

        protocol = outbound.get("protocol", "")

        if protocol in blocked:
            raise ValidationError(f"{protocol} cannot be used in chains")

        if protocol not in chainable:
            raise ValidationError(f"{protocol} does not support chaining")

        # Last item check
        if idx == len(items) - 1:
            sockopt = outbound.get("streamSettings", {}).get("sockopt", {})
            if sockopt.get("dialerProxy"):
                raise ValidationError("Last server already has dialerProxy configured")


def _get_chain_outbound(config: dict, chainable: set) -> dict | None:
    """Extract chainable outbound from config."""
    for outbound in config.get("outbounds", []):
        if outbound.get("protocol", "") in chainable:
            return outbound
    return None


def validate_profile_name(name: str) -> None:
    """Validate profile name."""
    if not name or not isinstance(name, str):
        raise ValidationError("Profile name is required")


def validate_profile_config(config: dict) -> None:
    """Validate profile config structure."""
    if not isinstance(config, dict):
        raise ValidationError("Profile config must be a dictionary")
