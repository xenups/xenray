"""Tun2Proxy Service."""

import os
import platform
import time
from typing import List, Optional

from src.core.constants import APPDIR, TEMP_ROOT, TUN2PROXY_EXECUTABLE, TUN_LOG_FILE
from src.utils.process_utils import ProcessUtils


class Tun2ProxyService:
    """Service for managing Tun2proxy process."""

    def __init__(self):
        """Initialize Tun2proxy service."""
        self._process = None
        self._pid: Optional[int] = None

    def start(self, socks_port: int, bypass_ips: List[str]) -> Optional[int]:
        """
        Start Tun2proxy with the given configuration.

        Args:
            socks_port: SOCKS5 port to use
            bypass_ips: List of IPs/subnets to bypass

        Returns:
            Process ID or None if start failed
        """
        # Check for admin privileges
        if not ProcessUtils.is_admin():
            print("[tun2proxy] Error: Admin privileges required for VPN mode")
            return None

        tun2proxy_bin = TUN2PROXY_EXECUTABLE

        if not os.path.exists(tun2proxy_bin):
            print(f"Tun2proxy binary not found at {tun2proxy_bin}")
            return None

        if os.name == "nt":
            return self._start_windows(tun2proxy_bin, socks_port, bypass_ips)
        else:
            return self._start_linux(socks_port, bypass_ips)

    def _start_windows(
        self, bin_path: str, socks_port: int, bypass_ips: List[str]
    ) -> Optional[int]:
        """Start Tun2proxy on Windows."""
        cmd = [
            bin_path,
            "--setup",
            "--proxy",
            f"socks5://127.0.0.1:{socks_port}",
            "--dns",
            "virtual",
            "-v",
            "trace",  # Increased verbosity for debugging
        ]

        # Bypass IPs
        for ip in bypass_ips:
            cmd.extend(["--bypass", ip])

        print(f"[tun2proxy] Starting: {' '.join(cmd)}")

        self._process = ProcessUtils.run_command(
            cmd, stdout_file=TUN_LOG_FILE, stderr_file=TUN_LOG_FILE
        )

        if self._process:
            self._pid = self._process.pid
            print(f"[tun2proxy] Started with PID {self._pid}")

            # Verify it stays running for a moment
            time.sleep(1)
            if not self.is_running(self._pid):
                print("[tun2proxy] Process exited immediately - check logs")
                self._pid = None
                self._process = None
                return None

            return self._pid
        else:
            print("[tun2proxy] Failed to start")
            return None

    def _start_linux(self, socks_port: int, bypass_ips: List[str]) -> Optional[int]:
        """Start Tun2proxy on Linux using pkexec."""
        # Create run_vpn.sh script
        self._write_run_vpn_sh(socks_port, bypass_ips)

        # Run via pkexec
        cmd = ["pkexec", os.path.join(TEMP_ROOT, "run_vpn.sh"), "start"]

        result = ProcessUtils.run_command_sync(cmd, timeout=10)

        if not result:
            print("[tun2proxy] Failed to start")
            return None

        stdout, stderr = result
        pid_str = stdout.strip()

        if pid_str.isdigit():
            self._pid = int(pid_str)
            print(f"[tun2proxy] Started with PID {self._pid}")
            return self._pid
        else:
            print(f"[tun2proxy] Failed to get PID: {stdout} {stderr}")
            return None

    def stop(self, pid: int) -> bool:
        """
        Stop Tun2proxy process.

        Args:
            pid: Process ID to stop

        Returns:
            True if successful, False otherwise
        """
        if not ProcessUtils.is_running(pid):
            return True

        if os.name == "nt":
            return self._stop_windows(pid)
        else:
            return self._stop_linux(pid)

    def _stop_windows(self, pid: int) -> bool:
        """Stop Tun2proxy on Windows."""
        print(f"[tun2proxy] Stopping PID {pid}...")
        success = ProcessUtils.kill_process(pid)
        if success:
            self._pid = None
            self._process = None
        return success

    def _stop_linux(self, pid: int) -> bool:
        """Stop Tun2proxy on Linux."""
        cmd = ["pkexec", os.path.join(TEMP_ROOT, "run_vpn.sh"), "stop", str(pid)]

        result = ProcessUtils.run_command_sync(cmd, timeout=10)

        if result:
            stdout, stderr = result
            print(f"[tun2proxy] {stdout}")

        # Wait for process to exit
        for _ in range(10):
            if not ProcessUtils.is_running(pid):
                print("[tun2proxy] Stopped")
                self._pid = None
                return True
            time.sleep(0.3)

        print("[tun2proxy] Failed to stop gracefully")
        return False

    def is_running(self, pid: int) -> bool:
        """Check if Tun2proxy is running."""
        return ProcessUtils.is_running(pid)

    @property
    def pid(self) -> Optional[int]:
        """Get Tun2proxy process ID."""
        return self._pid

    def _write_run_vpn_sh(self, socks_port: int, ip_list: List[str]) -> None:
        """
        Write run_vpn.sh script (Linux only).
        """
        bypass_lines = "\\n".join(
            [f"      --bypass {ip} \\\\" for ip in sorted(ip_list)]
        )

        script = f"""#!/bin/bash

set -e

APPDIR="$(dirname "$(readlink -f "$0")")"

LOGFILE="{TUN_LOG_FILE}"
chmod 644 "$LOGFILE"

start_vpn() {{
    echo "Connecting in VPN Mode ..." >> "$LOGFILE"

    exec "$APPDIR/usr/bin/tun2proxy-bin" \\\\
{bypass_lines}
      --setup -6 \\\\
      --proxy socks5://127.0.0.1:{socks_port} \\\\
      --dns virtual \\\\
      --exit-on-fatal-error \\\\
      -v info > "$LOGFILE" 2>&1 &

    echo "$!"
    disown
}}

stop_vpn() {{
    PID="$1"

    if [[ -z "$PID" ]]; then
        echo "Usage: $0 stop <PID>"
        exit 1
    fi

    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "Process $PID not found"
        exit 1
    fi

    CMD=$(ps -p "$PID" -o comm= 2>/dev/null)
    if [[ "$CMD" != "tun2proxy-bin" ]]; then
        echo "Process $PID is not tun2proxy-bin"
        exit 1
    fi

    kill -TERM "$PID"
    echo "Sent SIGTERM to tun2proxy-bin (PID $PID)"

    for i in {{1..10}}; do
        sleep 0.5
        if ! ps -p "$PID" > /dev/null 2>&1; then
            echo "Process $PID has exited"
            exit 0
        fi
    done

    echo "Process $PID did not exit, sending SIGKILL"
    kill -KILL "$PID"
    umount -l /etc/resolv.conf
    exit 0
}}

case "$1" in
    start)
        start_vpn
        ;;
    stop)
        stop_vpn "$2"
        ;;
    *)
        echo "Usage: $0 {{start|stop <PID>}}"
        exit 1
        ;;
esac
"""

        os.makedirs(
            os.path.dirname(os.path.join(TEMP_ROOT, "run_vpn.sh")), exist_ok=True
        )
        with open(os.path.join(TEMP_ROOT, "run_vpn.sh"), "w") as f:
            f.write(script)
        os.chmod(os.path.join(TEMP_ROOT, "run_vpn.sh"), 0o755)
