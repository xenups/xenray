"""Admin privilege utilities for CLI operations."""
import sys

try:
    import typer
except ImportError:
    print("Error: typer is not installed.")
    sys.exit(1)


def check_and_request_admin(mode: str) -> None:
    """
    Check for admin privileges when needed and request elevation.

    Args:
        mode: Connection mode (vpn requires admin, proxy doesn't)

    Raises:
        typer.Exit: If admin is required but not available
    """
    # Only VPN mode requires admin
    if mode != "vpn":
        return

    import ctypes
    import os

    from src.utils.platform_utils import PlatformUtils

    # Check if already running as admin
    is_admin = False
    platform = PlatformUtils.get_platform()

    if platform == "windows":
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False
    else:  # macOS or Linux
        is_admin = os.geteuid() == 0

    if is_admin:
        return  # Already admin, continue

    # Not admin - show appropriate message and handle elevation
    typer.echo("⚠️  VPN mode requires administrator privileges", err=True)
    typer.echo()

    if platform == "windows":
        _handle_windows_elevation()
    else:
        _handle_unix_elevation()


def _handle_windows_elevation() -> None:
    """Handle Windows UAC elevation."""
    import ctypes

    typer.echo("Would you like to restart as administrator? [y/N]: ", nl=False)

    if not sys.stdin.isatty():
        typer.echo()
        typer.echo("💡 Please run from an Administrator PowerShell/CMD")
        raise typer.Exit(1)

    response = input().strip().lower()

    if response not in ("y", "yes"):
        typer.echo("❌ VPN mode cancelled", err=True)
        raise typer.Exit(1)

    # Relaunch as admin using ShellExecuteW
    script = sys.executable
    params = " ".join(sys.argv)

    # ShellExecuteW returns HINSTANCE
    # Values > 32 indicate success, <= 32 indicate error
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", script, params, None, 1)  # SW_SHOWNORMAL

    if result > 32:
        typer.echo("✅ Relaunching as administrator...")
        raise typer.Exit(0)
    else:
        # Common error codes:
        # 0 = out of memory/resources
        # 2 = file not found
        # 5 = access denied (UAC cancelled)
        # 8 = out of memory
        # 31 = no association
        if result == 5:
            typer.echo("❌ UAC elevation cancelled by user", err=True)
        else:
            typer.echo(f"❌ Failed to elevate (error code: {result})", err=True)
        raise typer.Exit(1)


def _handle_unix_elevation() -> None:
    """Handle macOS/Linux sudo elevation."""
    typer.echo("💡 Please run with sudo:")
    typer.echo(f"   sudo {' '.join(sys.argv)}")
    raise typer.Exit(1)
