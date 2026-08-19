"""Admin privilege utilities for CLI operations."""

from __future__ import annotations

import sys

try:
    import typer
except ImportError:
    print("Error: typer is not installed.")
    sys.exit(1)

from src.core.constants import MODE_VPN
from src.platform.factory import get_process_adapter


def check_and_request_admin(mode: str) -> None:
    """Check for admin privileges when needed and request elevation.

    Args:
        mode: Connection mode (vpn requires admin, proxy doesn't)

    Raises:
        typer.Exit: If admin is required but not available
    """
    # Only VPN mode requires admin
    if mode != MODE_VPN:
        return

    proc_adapter = get_process_adapter()
    if proc_adapter.is_elevated():
        return  # Already admin, continue

    # Not admin - show appropriate message and handle elevation
    typer.echo("⚠️  VPN mode requires administrator privileges", err=True)
    typer.echo()

    if not proc_adapter.supports_interactive_elevation():
        hint = proc_adapter.get_elevation_hint()
        if hint:
            typer.echo(hint)
        raise typer.Exit(1)

    typer.echo("Would you like to restart as administrator? [y/N]: ", nl=False)

    if not sys.stdin.isatty():
        typer.echo()
        hint = proc_adapter.get_elevation_hint()
        if hint:
            typer.echo(hint)
        raise typer.Exit(1)

    response = input().strip().lower()

    if response not in ("y", "yes"):
        typer.echo("❌ VPN mode cancelled", err=True)
        raise typer.Exit(1)

    # Relaunch as admin via process adapter
    params = " ".join(sys.argv)
    if proc_adapter.request_elevation(params=params):
        typer.echo("✅ Relaunching as administrator...")
        raise typer.Exit(0)
    else:
        typer.echo("❌ Failed to elevate privileges or cancelled by user", err=True)
        raise typer.Exit(1)
