"""Command-line interface for xenray."""

import sys
from pathlib import Path
from typing import Optional

import click

from xenray import __version__
from xenray.core.config import Config
from xenray.core.xray_manager import XrayManager


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    help="Path to configuration file",
)
@click.pass_context
def main(ctx, config: Optional[Path]):
    """Xenray - A modern, lightweight Xray client."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = Config(config)
    ctx.obj["manager"] = XrayManager(ctx.obj["config"])


@main.command()
@click.pass_context
def start(ctx):
    """Start Xray connection."""
    manager: XrayManager = ctx.obj["manager"]
    config: Config = ctx.obj["config"]

    active_server = config.get_active_server()
    if not active_server:
        click.echo("Error: No active server configured. Use 'xenray server set <id>' first.")
        sys.exit(1)

    click.echo(f"Starting Xray connection to {active_server.get('name', 'server')}...")

    if manager.start():
        click.echo("✓ Xray started successfully")
        status = manager.get_status()
        click.echo(f"  PID: {status['pid']}")
        click.echo(f"  Listening on: {config.get('inbound.listen')}:{config.get('inbound.port')}")
    else:
        click.echo("✗ Failed to start Xray", err=True)
        sys.exit(1)


@main.command()
@click.pass_context
def stop(ctx):
    """Stop Xray connection."""
    manager: XrayManager = ctx.obj["manager"]

    if not manager.is_running():
        click.echo("Xray is not running")
        return

    click.echo("Stopping Xray...")
    if manager.stop():
        click.echo("✓ Xray stopped successfully")
    else:
        click.echo("✗ Failed to stop Xray", err=True)
        sys.exit(1)


@main.command()
@click.pass_context
def restart(ctx):
    """Restart Xray connection."""
    manager: XrayManager = ctx.obj["manager"]
    config: Config = ctx.obj["config"]

    active_server = config.get_active_server()
    if not active_server:
        click.echo("Error: No active server configured")
        sys.exit(1)

    click.echo("Restarting Xray...")
    if manager.restart():
        click.echo("✓ Xray restarted successfully")
    else:
        click.echo("✗ Failed to restart Xray", err=True)
        sys.exit(1)


@main.command()
@click.pass_context
def status(ctx):
    """Show Xray connection status."""
    manager: XrayManager = ctx.obj["manager"]
    config: Config = ctx.obj["config"]

    status = manager.get_status()

    if status["running"]:
        click.echo("Status: ✓ Running")
        click.echo(f"  PID: {status['pid']}")
        if "cpu_percent" in status:
            click.echo(f"  CPU: {status['cpu_percent']:.1f}%")
        if "memory_mb" in status:
            click.echo(f"  Memory: {status['memory_mb']:.1f} MB")

        active_server = config.get_active_server()
        if active_server:
            click.echo(f"  Server: {active_server.get('name', 'Unknown')}")
            click.echo(f"  Address: {active_server.get('address')}:{active_server.get('port')}")
    else:
        click.echo("Status: ✗ Not running")


@main.group()
def server():
    """Manage servers."""
    pass


@server.command("list")
@click.pass_context
def server_list(ctx):
    """List all configured servers."""
    config: Config = ctx.obj["config"]
    servers = config.get_servers()

    if not servers:
        click.echo("No servers configured")
        return

    active_server_id = config.get("active_server")

    click.echo("Configured servers:")
    for server in servers:
        server_id = server.get("id", "unknown")
        name = server.get("name", "Unnamed")
        address = server.get("address", "unknown")
        port = server.get("port", "unknown")
        protocol = server.get("protocol", "unknown")

        marker = "→" if server_id == active_server_id else " "
        click.echo(f"{marker} [{server_id}] {name}")
        click.echo(f"    {protocol}://{address}:{port}")


@server.command("add")
@click.option("--id", "server_id", required=True, help="Server ID")
@click.option("--name", required=True, help="Server name")
@click.option("--address", required=True, help="Server address")
@click.option("--port", required=True, type=int, help="Server port")
@click.option(
    "--protocol",
    type=click.Choice(["vless", "vmess", "trojan", "shadowsocks"]),
    default="vless",
    help="Protocol",
)
@click.option("--uuid", help="UUID (for VLESS/VMess)")
@click.option("--password", help="Password (for Trojan/Shadowsocks)")
@click.option("--network", default="tcp", help="Network type (tcp, ws, grpc, h2)")
@click.option("--tls", type=click.Choice(["none", "tls"]), default="none", help="TLS setting")
@click.option("--sni", help="TLS Server Name Indication")
@click.pass_context
def server_add(ctx, server_id, name, address, port, protocol, uuid, password, network, tls, sni):
    """Add a new server."""
    config: Config = ctx.obj["config"]

    server = {
        "id": server_id,
        "name": name,
        "address": address,
        "port": port,
        "protocol": protocol,
        "network": network,
        "tls": tls,
    }

    if uuid:
        server["uuid"] = uuid
    if password:
        server["password"] = password
    if sni:
        server["sni"] = sni

    config.add_server(server)
    click.echo(f"✓ Server '{name}' added successfully")


@server.command("remove")
@click.argument("server_id")
@click.pass_context
def server_remove(ctx, server_id):
    """Remove a server."""
    config: Config = ctx.obj["config"]

    if config.remove_server(server_id):
        click.echo(f"✓ Server '{server_id}' removed successfully")
    else:
        click.echo(f"✗ Server '{server_id}' not found", err=True)
        sys.exit(1)


@server.command("set")
@click.argument("server_id")
@click.pass_context
def server_set(ctx, server_id):
    """Set active server."""
    config: Config = ctx.obj["config"]
    manager: XrayManager = ctx.obj["manager"]

    servers = config.get_servers()
    server = next((s for s in servers if s.get("id") == server_id), None)

    if not server:
        click.echo(f"✗ Server '{server_id}' not found", err=True)
        sys.exit(1)

    config.set_active_server(server_id)
    click.echo(f"✓ Active server set to '{server.get('name')}'")

    if manager.is_running():
        click.echo("Restarting Xray with new server...")
        manager.restart()


@main.group()
def config():
    """Manage configuration."""
    pass


@config.command("show")
@click.pass_context
def config_show(ctx):
    """Show current configuration."""
    config: Config = ctx.obj["config"]
    click.echo(f"Configuration file: {config.config_path}")
    click.echo(f"Xray binary: {config.get('xray_binary')}")
    click.echo(f"Log level: {config.get('log_level')}")
    click.echo(f"Auto-reconnect: {config.get('auto_reconnect')}")
    click.echo(
        f"Inbound: {config.get('inbound.protocol')}://{config.get('inbound.listen')}:{config.get('inbound.port')}"
    )


@config.command("import")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "file_format",
    type=click.Choice(["json", "yaml"]),
    default="json",
    help="File format",
)
@click.pass_context
def config_import(ctx, file, file_format):
    """Import configuration from file."""
    config: Config = ctx.obj["config"]

    if config.import_config(file, file_format):
        click.echo(f"✓ Configuration imported from {file}")
    else:
        click.echo("✗ Failed to import configuration", err=True)
        sys.exit(1)


@config.command("export")
@click.argument("file", type=click.Path(path_type=Path))
@click.option(
    "--format",
    "file_format",
    type=click.Choice(["json", "yaml"]),
    default="json",
    help="File format",
)
@click.pass_context
def config_export(ctx, file, file_format):
    """Export configuration to file."""
    config: Config = ctx.obj["config"]

    if config.export_config(file, file_format):
        click.echo(f"✓ Configuration exported to {file}")
    else:
        click.echo("✗ Failed to export configuration", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
