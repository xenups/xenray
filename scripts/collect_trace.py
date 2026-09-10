"""Standalone connection trace collector.

Run this script ONCE per connection attempt. It exercises the full
connection flow through the same code paths as the GUI and writes
results to stdout.

Usage:
    cd xenray
    .venv/Scripts/python scripts/collect_trace.py

Collect 10-15 runs and paste the output into baseline-trace-results.md.
"""

from __future__ import annotations

import json
import os
import sys
import time

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.utils.connection_trace import ConnectionTrace  # noqa: E402


def _trace_step(trace: ConnectionTrace, name: str, fn, *args, **kwargs):
    """Run *fn*, mark START/END around it, return result."""
    trace.mark(f"{name}_START")
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:
        trace.mark(f"{name}_ERROR: {exc}")
        raise
    trace.mark(f"{name}_END")
    return result


def collect_one() -> dict:
    """Run one full connection flow through the orchestration layer."""
    trace = ConnectionTrace.start()

    # --- Step 1: Internet check ---
    from src.utils.network_utils import NetworkUtils
    _trace_step(trace, "INTERNET_CHECK", NetworkUtils.check_internet_connection)

    # --- Step 2: Pre-connection checks (would normally be in orchestrator) ---
    trace.mark("PRE_CHECKS_START")
    has_internet = NetworkUtils.check_internet_connection()
    trace.mark("PRE_CHECKS_END")
    if not has_internet:
        trace.mark("ABORTED_NO_INTERNET")
        return trace.summary()

    # --- Step 3: Load config ---
    # Use the same temp config path the GUI would write to
    from src.core.constants import TMPDIR, OUTPUT_CONFIG_PATH
    os.makedirs(TMPDIR, exist_ok=True)

    # Try to load an existing config if available, otherwise skip engine start
    config_path = os.path.join(TMPDIR, "current_config.json")
    if not os.path.exists(config_path):
        trace.mark("NO_CONFIG_FILE")
        print("[TRACE] No config file found — skipping engine start.")
        print("[TRACE] Run the GUI connect flow at least once first to create a config.")
        return trace.summary()

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    trace.mark("CONFIG_LOADED")

    # --- Step 4: Xray service start (if xray binary exists) ---
    from src.core.constants import CORE_XRAY, CORE_SINGBOX

    try:
        from src.services.core_engines.xray_service import XrayService
        xray_svc = XrayService()
        trace.mark("XRAY_START")
        xray_pid = xray_svc.start(OUTPUT_CONFIG_PATH)
        trace.mark("XRAY_READY")
        if xray_pid:
            print(f"[TRACE] Xray PID: {xray_pid}")
        else:
            print("[TRACE] Xray failed to start")
    except Exception as e:
        trace.mark(f"XRAY_ERROR: {e}")
        xray_pid = None

    # --- Step 5: Singbox service start (if VPN mode) ---
    singbox_pid = None
    try:
        from src.services.core_engines.singbox_service import SingboxService
        from src.core.config_builders.singbox_config_builder import SingboxConfigBuilder
        from src.platform.factory import get_network_adapter

        adapter = get_network_adapter()
        iface_name, _, _, gateway = adapter.get_primary_interface()
        dns_servers = adapter.get_system_dns_servers()
        local_dns = dns_servers[0] if dns_servers else None

        sb_config = SingboxConfigBuilder().build(
            socks_port=10805,
            proxy_server_ip="188.114.98.180",
            interface_name=iface_name,
            routing_rules={},
            routing_country="",
            mtu=1420,
            local_dns_server=local_dns,
        )

        sb_svc = SingboxService()
        trace.mark("SINGBOX_START")
        singbox_pid = sb_svc.start(
            xray_socks_port=10805,
            proxy_server_ip="188.114.98.180",
            routing_country="",
            routing_rules={},
            mtu=1420,
        )
        trace.mark("SINGBOX_STARTED")
        if singbox_pid:
            print(f"[TRACE] Singbox PID: {singbox_pid}")
        else:
            print("[TRACE] Singbox failed to start")
    except Exception as e:
        trace.mark(f"SINGBOX_ERROR: {e}")

    # --- Step 6: TUN warmup (blind sleep as baseline) ---
    is_tun = singbox_pid is not None
    if is_tun:
        trace.mark("TUN_PROBE_START")
        time.sleep(3.5)  # current blind sleep
        trace.mark("TUN_PROBE_END")

    # --- Step 7: Health check ---
    from src.services.connection.connection_tester import ConnectionTester
    trace.mark("HEALTH_CHECK_START")
    for attempt in range(1, 4):
        socks_port = 10805 if singbox_pid else 0
        success, latency, _ = ConnectionTester.test_connection_sync(config, socks_port=socks_port)
        if success:
            trace.mark(f"HEALTH_CHECK_OK_attempt{attempt}")
            trace.mark("HEALTH_CHECK_END")
            break
        trace.mark(f"HEALTH_CHECK_FAIL_attempt{attempt}")
        if attempt < 3:
            time.sleep(1.0)
    else:
        trace.mark("HEALTH_CHECK_END")

    # --- Step 8: Post-verification (blind sleep) ---
    trace.mark("POST_VERIFIED_START")
    time.sleep(2.0)
    trace.mark("POST_VERIFIED_END")

    trace.mark("CONNECTED")

    # --- Cleanup ---
    try:
        if singbox_pid:
            sb_svc.stop()
        if xray_pid:
            xray_svc.stop()
    except Exception:
        pass

    return trace.summary()


def main():
    print("=" * 60)
    print("Connection Trace Collector")
    print("Run this script once per connection attempt.")
    print("=" * 60)
    print()

    result = collect_one()

    # Append to results file
    results_file = os.path.join(ROOT, ".hermes", "plans", "trace-raw.jsonl")
    os.makedirs(os.path.dirname(results_file), exist_ok=True)
    with open(results_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, default=str) + "\n")
    print(f"\n[TRACE] Results appended to {results_file}")


if __name__ == "__main__":
    main()
