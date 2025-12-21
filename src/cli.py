"""CLI interface for XenRay - Headless mode without UI.

This module provides command-line access to core XenRay functionality
without loading the Flet UI framework, saving ~104 MB of RAM.

Usage:
    xenray-cli connect --profile-id <id>
    xenray-cli disconnect
    xenray-cli status
    xenray-cli list
"""

import sys
from typing import Optional

try:
    import typer
except ImportError:
    print("Error: typer is not installed. Install it with: pip install typer")
    sys.exit(1)

from loguru import logger

from src.core.config_manager import ConfigManager
from src.core.connection_manager import ConnectionManager
from src.core.settings import Settings

# Create Typer app
app = typer.Typer(
    name="xenray-cli",
    help="XenRay headless CLI - Manage VPN connections without UI",
    add_completion=False,
)


def _init_core():
    """Initialize core services without UI."""
    # Skip i18n translation loading (CLI doesn't need it)
    import os

    os.environ["XENRAY_SKIP_I18N"] = "1"

    # Setup logging (no Flet, minimal overhead)
    Settings.create_temp_directories()
    Settings.create_log_files()

    # Set default level to INFO for CLI to avoid debug noise
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    # Still log to file at DEBUG if needed
    from src.core.constants import EARLY_LOG_FILE

    logger.add(EARLY_LOG_FILE, level="DEBUG", rotation="10 MB")

    # Initialize core managers
    config_mgr = ConfigManager()
    conn_mgr = ConnectionManager(config_manager=config_mgr)

    return config_mgr, conn_mgr


def _select_profile(config_mgr, profile_number: Optional[int]) -> dict:
    """Select profile by number or default."""
    profiles_data = config_mgr.load_profiles()

    if not profiles_data:
        typer.echo("❌ Error: No profiles found", err=True)
        raise typer.Exit(1)

    # Select profile by number or default
    if profile_number is not None:
        if profile_number < 1 or profile_number > len(profiles_data):
            typer.echo(
                f"❌ Error: Profile #{profile_number} not found. Valid range: 1-{len(profiles_data)}",
                err=True,
            )
            raise typer.Exit(1)
        selected_profile = profiles_data[profile_number - 1]
        typer.echo(f"📋 Using profile #{profile_number}: {selected_profile.get('name', 'Unknown')}")
    else:
        # Use default (last selected) profile
        last_profile_id = config_mgr.get_last_selected_profile_id()

        if last_profile_id:
            selected_profile = config_mgr.get_profile_by_id(last_profile_id)
            if not selected_profile:
                selected_profile = profiles_data[0]
        else:
            selected_profile = profiles_data[0]

        typer.echo(f"📋 Using default profile #1: {selected_profile.get('name', 'Unknown')}")

    return selected_profile


def _prepare_config_file(profile_config: dict) -> str:
    """Create temporary config file from profile config."""
    import json
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(profile_config, f)
        return f.name


def _cleanup_temp_file(file_path: str) -> None:
    """Clean up temporary config file."""
    import os

    try:
        os.unlink(file_path)
    except Exception:
        pass


def _perform_connection(conn_mgr, temp_config_path: str, mode: str) -> bool:
    """Execute the connection attempt."""
    typer.echo(f"🔄 Connecting in {mode} mode...")
    return conn_mgr.connect(temp_config_path, mode)


@app.command()
def connect(
    profile_number: Optional[int] = typer.Argument(
        None, help="Profile number (from list command) or leave empty for default"
    ),
    mode: str = typer.Option("vpn", "--mode", "-m", help="Connection mode: proxy or vpn"),
):
    """Connect to a VPN server using a profile number or default profile."""

    # Check admin privileges if needed (VPN mode only)
    from src.utils.admin_utils import check_and_request_admin

    check_and_request_admin(mode)

    config_mgr, conn_mgr = _init_core()

    # Select profile
    selected_profile = _select_profile(config_mgr, profile_number)

    # Get config
    profile_config = selected_profile.get("config")
    if not profile_config:
        typer.echo("❌ Error: Invalid profile configuration", err=True)
        raise typer.Exit(1)

    # Prepare temp config file
    temp_config_path = _prepare_config_file(profile_config)

    try:
        # Attempt connection
        success = _perform_connection(conn_mgr, temp_config_path, mode)

        if success:
            # Save as last selected profile
            config_mgr.set_last_selected_profile_id(selected_profile.get("id"))

            typer.echo("✅ Connected successfully!")
            typer.echo(f"   Profile: {selected_profile.get('name', 'Unknown')}")
            typer.echo(f"   Mode: {mode}")

            # Post-connection ping test
            typer.echo("\n⚡ Testing connection quality...")
            from src.services.connection_tester import ConnectionTester
            from src.utils.country_flags import country_code_to_flag

            p_success, p_result, p_country = ConnectionTester.test_connection_sync(profile_config, fetch_country=True)
            if p_success:
                typer.echo(f"   Latency: {p_result}")
                if p_country:
                    flag = country_code_to_flag(p_country.get("country_code"))
                    typer.echo(f"   Location: {flag} {p_country.get('country_name')} ({p_country.get('country_code')})")
                    typer.echo(f"   City: {p_country.get('city')}")
            else:
                typer.echo(f"   ⚠️  Ping test failed: {p_result}")
        else:
            typer.echo("❌ Connection failed")
            raise typer.Exit(1)
    finally:
        # Cleanup
        _cleanup_temp_file(temp_config_path)


@app.command()
def disconnect():
    """Disconnect from current VPN connection."""
    config_mgr, conn_mgr = _init_core()

    if not conn_mgr._current_connection:
        typer.echo("ℹ️  Not connected")
        return

    typer.echo("🔄 Disconnecting...")
    conn_mgr.disconnect()
    typer.echo("✅ Disconnected")


@app.command()
def status():
    """Show current connection status."""
    config_mgr, conn_mgr = _init_core()

    # Check if connection exists (handles adoption automatically)
    if conn_mgr._current_connection:
        mode = conn_mgr._current_connection.get("mode", "Unknown")
        typer.echo("📊 Connection Status:")
        typer.echo("   Status: ✅ Connected")
        typer.echo(f"   Mode: {mode}")

        # Double check if processes are actually running
        x_running = conn_mgr._orchestrator._xray_service.is_running()
        s_running = True
        if mode == "vpn":
            s_running = conn_mgr._orchestrator._singbox_service.is_running()

        if not x_running or not s_running:
            typer.echo("   ⚠️  Warning: Connection is in an inconsistent state.")
    else:
        typer.echo("📊 Connection Status:")
        typer.echo("   Status: ❌ Disconnected")


@app.command("list")
def list_profiles():
    """List all available profiles with numbers for easy selection."""
    config_mgr, _ = _init_core()

    # Get profiles using config manager method
    profiles_data = config_mgr.load_profiles()

    if not profiles_data:
        typer.echo("ℹ️  No profiles found")
        return

    # Get last selected profile for highlighting
    last_profile_id = config_mgr.get_last_selected_profile_id()

    typer.echo(f"📋 Available Profiles ({len(profiles_data)}):\n")

    from src.utils.country_flags import get_country_flag

    for idx, profile in enumerate(profiles_data, 1):
        profile_id = profile.get("id", "Unknown")
        name = profile.get("name", "Unnamed")

        # Extract server address from nested config
        config = profile.get("config", {})
        server = "Unknown"

        # 1. Try common top-level location
        if "address" in config:
            server = config["address"]
        # 2. Try Xray structure (vnext for vless/vmess)
        elif "outbounds" in config and len(config["outbounds"]) > 0:
            outbound = config["outbounds"][0]
            settings = outbound.get("settings", {})
            vnext = settings.get("vnext", [])
            if vnext and len(vnext) > 0:
                server = vnext[0].get("address", "Unknown")
            # 3. Try Xray servers (trojan)
            elif "servers" in settings and len(settings["servers"]) > 0:
                server = settings["servers"][0].get("address", "Unknown")

        # Get country flag from name
        flag = get_country_flag(name)

        # Mark default profile
        is_default = " (default)" if profile_id == last_profile_id else ""

        typer.echo(f"  {idx}. {flag} {name}{is_default}")

        # Show address and location info
        location_info = []
        if profile.get("country_name"):
            location_info.append(profile.get("country_name"))
        if profile.get("city"):
            location_info.append(profile.get("city"))

        location_str = f" ({', '.join(location_info)})" if location_info else ""
        typer.echo(f"     Server: {server}{location_str}")
        typer.echo(f"     ID: {profile_id}")
        typer.echo()

    typer.echo("💡 Tip: Use 'xenray-cli connect <number>' to connect")
    typer.echo("        Or just 'xenray-cli connect' for default profile")


@app.command()
def add(
    share_link: str = typer.Argument(..., help="Share link (vless://, vmess://, trojan://, ss://, hysteria2://)"),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Custom profile name (auto-generated if not provided)",
    ),
):
    """Add a new profile from a share link."""
    config_mgr, _ = _init_core()

    # Import link parser
    from src.utils.link_parser import LinkParser

    typer.echo("📥 Parsing share link...")

    try:
        # Parse the share link
        result = LinkParser.parse_link(share_link)

        if not result or not result.get("config"):
            typer.echo("❌ Error: Failed to parse share link", err=True)
            raise typer.Exit(1)

        config = result["config"]
        profile_name = name or result.get("name", "Imported Profile")

        # Save profile
        config_mgr.save_profile(profile_name, config)

        typer.echo("✅ Profile added successfully!")
        typer.echo(f"   Name: {profile_name}")
        typer.echo(f"   Protocol: {result.get('protocol', 'Unknown')}")

        # Show in list
        profiles = config_mgr.load_profiles()
        profile_count = len(profiles)
        typer.echo(f"\n💡 Profile is now #{profile_count} in the list")
        typer.echo(f"   Use 'xenray-cli connect {profile_count}' to connect")

    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Error: Failed to add profile: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def ping(
    profile_number: Optional[int] = typer.Argument(
        None,
        help="Profile number (from list command) to test a specific profile, or leave empty to test all",
    ),
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum profiles to test when pinging all"),
    concurrency: int = typer.Option(3, "--concurrency", "-c", help="Batch workers for list ping"),
):
    """Test latency for profiles. Defaults to batch testing the entire list."""
    config_mgr, _ = _init_core()

    # CASE 1: Single Profile Ping
    if profile_number is not None:
        selected_profile = _select_profile(config_mgr, profile_number)
        profile_config = selected_profile.get("config")
        if not profile_config:
            typer.echo("❌ Error: Invalid profile configuration", err=True)
            raise typer.Exit(1)

        typer.echo(f"⚡ Testing latency for: {selected_profile.get('name')}...")
        from src.services.connection_tester import ConnectionTester
        from src.utils.country_flags import country_code_to_flag

        success, result_str, country_data = ConnectionTester.test_connection_sync(profile_config, fetch_country=True)
        if success:
            typer.echo(f"✅ Success! {result_str}")
            if country_data:
                flag = country_code_to_flag(country_data.get("country_code"))
                typer.echo(
                    f"   Location: {flag} {country_data.get('country_name')} ({country_data.get('country_code')})"
                )
                typer.echo(f"   City: {country_data.get('city')}")
        else:
            typer.echo(f"❌ Failed: {result_str}")
            raise typer.Exit(1)
        return

    # CASE 2: Batch List Ping
    profiles_data = config_mgr.load_profiles()
    if not profiles_data:
        typer.echo("ℹ️  No profiles found")
        return

    profiles_to_test = profiles_data[:limit]
    typer.echo(f"⚡ Batch testing {len(profiles_to_test)} profiles (concurrency: {concurrency})...\n")

    from concurrent.futures import ThreadPoolExecutor

    from src.services.connection_tester import ConnectionTester
    from src.utils.country_flags import country_code_to_flag, get_country_flag

    def test_single(idx_profile):
        idx, profile = idx_profile
        config = profile.get("config")
        name = profile.get("name", "Unnamed")
        if not config:
            return idx, name, False, "Invalid Config", None
        success, result, country = ConnectionTester.test_connection_sync(config, fetch_country=True)
        return idx, name, success, result, country

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(test_single, enumerate(profiles_to_test, 1)))

    results.sort(key=lambda x: x[0])
    for idx, name, success, result, country in results:
        status_icon = "✅" if success else "❌"
        item_flag = get_country_flag(name)
        typer.echo(f" {idx:2}. {status_icon} {item_flag} {name:25} | {result}")
        if success and country:
            flag = country_code_to_flag(country.get("country_code"))
            typer.echo(
                f"      Location: {flag} {country.get('country_name')} "
                f"({country.get('country_code')}) | City: {country.get('city')}"
            )

    typer.echo("\n✨ Batch test complete.")


@app.command()
def version():
    """Show XenRay version."""
    from src.core.constants import APP_VERSION

    typer.echo(f"XenRay CLI v{APP_VERSION}")


def main():
    """Entry point for CLI."""
    try:
        app()
    except KeyboardInterrupt:
        typer.echo("\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception("CLI error")
        typer.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
