"""Windows INetworkAdapter — physical NIC discovery via IP Helper API.

All networking / DNS / physical-NIC logic that used to live in
``PlatformUtils`` and ``NetworkInterfaceDetector`` lives here, backed by the
IP Helper API (``get_physical_nic_candidates`` from ``nic_detect``) — no
adapter-name blacklists, no /24 heuristics.  Callers use
``src.platform.factory.get_network_adapter()``.
"""

from __future__ import annotations

import ctypes
import ipaddress
import os
import re
import socket
import subprocess
import threading
import time
from ctypes import wintypes
from typing import Callable, Optional, Tuple

from loguru import logger

from src.platform.constants import CMD_IPCONFIG, CMD_POWERSHELL, CMD_ROUTE
from src.platform.factory import get_process_adapter
from src.platform.interfaces import INetworkAdapter

# Windows IP Helper API constants (GetAdaptersAddresses)
GAA_FLAG_INCLUDE_PREFIX = 0x10
GAA_FLAG_SKIP_ANYCAST = 0x02
GAA_FLAG_SKIP_MULTICAST = 0x04
MAX_ADAPTER_ADDRESS_LENGTH = 8

# IF_TYPE values (from ipifcons.h)
IF_TYPE_ETHERNET_CSMACD = 6
IF_TYPE_IEEE80211 = 71
IF_TYPE_TUNNEL = 131

# MIB_IF_OPER_STATUS
IfOperStatusUp = 1


class _SOCKADDR(ctypes.Structure):
    _fields_ = [("sa_family", ctypes.c_ushort), ("sa_data", ctypes.c_char * 14)]


class _SOCKET_ADDRESS(ctypes.Structure):
    _fields_ = [("lpSockaddr", ctypes.POINTER(_SOCKADDR)), ("iSockaddrLength", ctypes.c_int)]


class _IP_ADAPTER_UNICAST_ADDRESS(ctypes.Structure):
    pass


_IP_ADAPTER_UNICAST_ADDRESS._fields_ = [
    ("Length", ctypes.c_ulong),
    ("Flags", ctypes.c_ulong),
    ("Next", ctypes.POINTER(_IP_ADAPTER_UNICAST_ADDRESS)),
    ("Address", _SOCKET_ADDRESS),
    ("PrefixOrigin", ctypes.c_int),
    ("SuffixOrigin", ctypes.c_int),
    ("DadState", ctypes.c_int),
    ("ValidLifetime", ctypes.c_ulong),
    ("PreferredLifetime", ctypes.c_ulong),
    ("LeaseLifetime", ctypes.c_ulong),
    ("OnLinkPrefixLength", ctypes.c_ubyte),
]


class _IP_ADAPTER_ADDRESSES(ctypes.Structure):
    pass


_IP_ADAPTER_ADDRESSES._fields_ = [
    ("Length", ctypes.c_ulong),
    ("IfIndex", ctypes.c_ulong),
    ("Next", ctypes.POINTER(_IP_ADAPTER_ADDRESSES)),
    ("AdapterName", ctypes.c_char_p),
    ("FirstUnicastAddress", ctypes.POINTER(_IP_ADAPTER_UNICAST_ADDRESS)),
    ("FirstAnycastAddress", ctypes.c_void_p),
    ("FirstMulticastAddress", ctypes.c_void_p),
    ("FirstDnsServerAddress", ctypes.c_void_p),
    ("DnsSuffix", ctypes.c_wchar_p),
    ("Description", ctypes.c_wchar_p),
    ("FriendlyName", ctypes.c_wchar_p),
    ("PhysicalAddress", ctypes.c_ubyte * MAX_ADAPTER_ADDRESS_LENGTH),
    ("PhysicalAddressLength", ctypes.c_ulong),
    ("Flags", ctypes.c_ulong),
    ("Mtu", ctypes.c_ulong),
    ("IfType", ctypes.c_int),
    ("OperStatus", ctypes.c_int),
    ("Ipv6IfIndex", ctypes.c_ulong),
    ("ZoneIndices", ctypes.c_ulong * 16),
    ("FirstPrefix", ctypes.c_void_p),
    ("TransmitLinkSpeed", ctypes.c_ulonglong),
    ("ReceiveLinkSpeed", ctypes.c_ulonglong),
    ("FirstWinsServerAddress", ctypes.c_void_p),
    ("FirstGatewayAddress", ctypes.c_void_p),
    ("Ipv4Metric", ctypes.c_ulong),
    ("Ipv6Metric", ctypes.c_ulong),
    ("Luid", ctypes.c_ulonglong),
    ("Dhcpv4Server", _SOCKET_ADDRESS),
    ("CompartmentId", ctypes.c_ulong),
    ("NetworkGuid", ctypes.c_ubyte * 16),
    ("ConnectionType", ctypes.c_int),
    ("TunnelType", ctypes.c_int),
    ("Dhcpv6Server", _SOCKET_ADDRESS),
    ("Dhcpv6ClientDuid", ctypes.c_ubyte * 130),
    ("Dhcpv6ClientDuidLength", ctypes.c_ulong),
    ("Dhcpv6Iaid", ctypes.c_ulong),
]


VIRTUAL_ADAPTER_KEYWORDS = (
    "tap",
    "wintun",
    "wireguard",
    "tailscale",
    "zerotier",
    "warp",
    "cloudflare",
    "nordlynx",
    "openvpn",
    "sing-box",
    "xray",
    "hyper-v",
    "virtualbox",
    "vmware",
    "vethernet",
    "npcap",
    "loopback",
    "vpn",
    "tunnel",
    "dummy",
    "xenray",
    "xenray-tun",
)


def _is_virtual_adapter(name: str, desc: str) -> bool:
    """True if adapter name or description contains virtual/tunnel device markers."""
    target = f"{name} {desc}".lower()
    return any(kw in target for kw in VIRTUAL_ADAPTER_KEYWORDS)


def _is_physical_iftype(iftype: int) -> bool:
    """True for genuinely physical link types (Ethernet / IEEE 802.11)."""
    return iftype in (IF_TYPE_ETHERNET_CSMACD, IF_TYPE_IEEE80211)


def get_physical_nic_candidates() -> list[dict]:
    """Enumerate genuinely physical, up, gateway-bearing adapters via IP Helper API.

    Explicitly excludes virtual adapters (TAP, WinTUN, WireGuard, Tailscale, Hyper-V).
    Returns a list of ``{"name", "ip", "iftype", "operstatus", "gateway", "metric"}``
    sorted by IPv4 metric.
    """
    if not hasattr(ctypes, "windll"):
        return []
    try:
        iphlpapi = ctypes.windll.iphlpapi
    except Exception:
        return []

    get_adapters = iphlpapi.GetAdaptersAddresses
    get_adapters.restype = wintypes.DWORD
    get_adapters.argtypes = [
        wintypes.ULONG,  # Family (AF_INET = 2)
        wintypes.DWORD,  # Flags
        ctypes.c_void_p,  # Reserved
        ctypes.POINTER(_IP_ADAPTER_ADDRESSES),
        ctypes.POINTER(wintypes.ULONG),
    ]

    AF_INET = socket.AF_INET  # 2
    buflen = wintypes.ULONG(15000)
    buf = ctypes.create_string_buffer(buflen.value)
    iters = 0
    while True:
        r = get_adapters(
            AF_INET,
            GAA_FLAG_INCLUDE_PREFIX | GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST,
            None,
            ctypes.cast(buf, ctypes.POINTER(_IP_ADAPTER_ADDRESSES)),
            ctypes.byref(buflen),
        )
        if r == 0:
            break
        if r == 111:  # ERROR_BUFFER_OVERFLOW
            buf = ctypes.create_string_buffer(buflen.value)
            iters += 1
            if iters > 4:
                return []
            continue
        return []  # other error

    result = []
    adapter = ctypes.cast(buf, ctypes.POINTER(_IP_ADAPTER_ADDRESSES))
    while adapter:
        a = adapter.contents
        name = a.FriendlyName or a.AdapterName or ""
        desc = a.Description or ""

        # Physical link type only (Ethernet / 802.11) AND not an enumerated virtual/VPN adapter
        if _is_physical_iftype(a.IfType) and a.OperStatus == IfOperStatusUp and not _is_virtual_adapter(name, desc):
            # First usable IPv4 unicast address
            ip = None
            ua = a.FirstUnicastAddress
            while ua:
                u = ua.contents
                sock = u.Address.lpSockaddr
                if sock and sock.contents.sa_family == AF_INET:
                    raw = ctypes.string_at(ctypes.addressof(sock.contents) + 4, 4)
                    cand_ip = socket.inet_ntoa(raw)
                    if not _is_loopback_or_nonlan(cand_ip):
                        ip = cand_ip
                        break
                ua = u.Next

            # Extract default gateway IP string
            gateway_ip = None
            ga = a.FirstGatewayAddress
            while ga:
                g = ga.contents
                sock = g.Address.lpSockaddr
                if sock and sock.contents.sa_family == AF_INET:
                    raw = ctypes.string_at(ctypes.addressof(sock.contents) + 4, 4)
                    cand_gw = socket.inet_ntoa(raw)
                    if not _is_loopback_or_nonlan(cand_gw):
                        gateway_ip = cand_gw
                        break
                ga = g.Next

            if ip and gateway_ip:
                result.append(
                    {
                        "name": name,
                        "ip": ip,
                        "iftype": a.IfType,
                        "operstatus": a.OperStatus,
                        "gateway": gateway_ip,
                        "metric": getattr(a, "Ipv4Metric", 999),
                    }
                )
        adapter = a.Next

    result.sort(key=lambda c: c.get("metric", 999))
    return result


# DNS probe target for the default-route egress source address (any routable
# destination; the kernel answers with the real source IP).
EGRESS_PROBE_TARGET = ("8.8.8.8", 80)
EGRESS_PROBE_TIMEOUT = 0.5

ROUTE_COMMAND_TIMEOUT = 5  # seconds
IPCONFIG_COMMAND_TIMEOUT = 5  # seconds

# TUN gateway subnet — skip the TUN adapter's own DNS if present (that loops
# back into sing-box).  Systemic via ``ipaddress``, never a string prefix.
_TUN_DNS_SUBNET = "10.0.0.0/24"


def _is_tun_subnet_ip(ip: str) -> bool:
    """True if *ip* falls inside the XenRay TUN subnet."""
    try:
        addr = ipaddress.ip_address(ip)
        net = ipaddress.ip_network(_TUN_DNS_SUBNET, strict=False)
        return addr in net
    except ValueError:
        return False


def _is_loopback_or_nonlan(ip: str) -> bool:
    """True when *ip* is not a usable unicast site-local LAN address.

    Systemic via ``ipaddress`` — loopback / link-local / multicast excluded;
    ordinary private LANs kept.  Never string-prefix matching.
    """
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return True
    if a.version != 4:
        return True
    if a.is_loopback or a.is_link_local or a.is_multicast:
        return True
    return False


def _is_valid_ip(ip: str) -> bool:
    """Check if string is a valid IPv4 address (systemic via ipaddress)."""
    try:
        return ipaddress.ip_address(ip).version == 4
    except ValueError:
        return False


def _get_subnet(ip: str) -> str:
    """IPv4 /24 subnet for *ip* (``x.y.z.0/24``); ``ip/32`` when invalid.

    The old NetworkInterfaceDetector assumed /24 for route-table candidates;
    kept for backward-compatible get_primary_interface output shape.
    """
    try:
        a = ipaddress.ip_address(ip)
        if a.version != 4:
            return f"{ip}/32"
    except ValueError:
        return f"{ip}/32"
    parts = ip.split(".")
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"


class WindowsNetworkAdapter(INetworkAdapter):
    """Physical NIC discovery via IP Helper API (GetAdaptersAddresses)."""

    def get_physical_nic_candidates(self) -> list[dict]:
        return get_physical_nic_candidates()

    def get_physical_lan_ip(self) -> Optional[str]:
        """Primary physical LAN IPv4 from IP Helper + default-route egress."""
        # 1. IP Helper physical candidates.
        try:
            for cand in self.get_physical_nic_candidates():
                ip = cand.get("ip")
                if ip and not _is_loopback_or_nonlan(ip):
                    logger.debug(f"[WindowsNetworkAdapter] LAN IP candidate: {ip} ({cand.get('name')})")
                    return ip
        except Exception as e:
            logger.debug(f"[WindowsNetworkAdapter] IP Helper LAN discovery unavailable: {e}")
        # 2. OS default-route source address.
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(EGRESS_PROBE_TIMEOUT)
            s.connect(EGRESS_PROBE_TARGET)
            ip = s.getsockname()[0]
            s.close()
            if not _is_loopback_or_nonlan(ip):
                logger.debug(f"[WindowsNetworkAdapter] LAN IP candidate (default route): {ip}")
                return ip
        except Exception as e:
            logger.debug(f"[WindowsNetworkAdapter] Default-route LAN discovery failed: {e}")
        return None

    def get_system_dns_servers(self) -> list[str]:
        """System DNS servers (IPv4) — used for DIRECT-routed domains.

        Reads the active adapter's DNS via ``Get-DnsClientServerAddress``
        (or ``ipconfig`` fallback); POSIX via resolv.conf / scutil.  These are
        LOCAL resolvers (router/gateway) — the right choice for direct domains
        on networks where foreign DNS (8.8.8.8 / 1.1.1.1) is blocked or
        tampered with (e.g. Iran).
        """
        servers: list = []
        try:
            if os.name == "nt":
                try:
                    out = subprocess.run(
                        [
                            CMD_POWERSHELL,
                            "-NoProfile",
                            "-Command",
                            "Get-DnsClientServerAddress -AddressFamily IPv4 | "
                            "Where-Object {$_.ServerAddresses.Count -gt 0} | "
                            "ForEach-Object {$_.ServerAddresses} | Select-Object -Unique",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        creationflags=get_process_adapter().get_subprocess_flags(),
                        startupinfo=get_process_adapter().get_startupinfo(),
                    )
                    for line in (out.stdout or "").splitlines():
                        line = line.strip()
                        # Skip the TUN adapter's own subnet DNS if present —
                        # that loops back into sing-box (systemic via the
                        # TUN subnet, never a string prefix).
                        if line and not _is_tun_subnet_ip(line):
                            servers.append(line)
                except Exception:
                    pass
                # Fallback: ipconfig
                if not servers:
                    out = subprocess.run(
                        [CMD_IPCONFIG, "/all"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        creationflags=get_process_adapter().get_subprocess_flags(),
                        startupinfo=get_process_adapter().get_startupinfo(),
                    )
                    lines = (out.stdout or "").splitlines()
                    for i, line in enumerate(lines):
                        if "DNS Servers" in line and i + 1 < len(lines):
                            nxt = lines[i + 1].strip()
                            if nxt and nxt[0].isdigit():
                                servers.append(nxt.split()[0])
            elif os.name == "posix":
                if os.uname().sysname == "Darwin":
                    out = subprocess.run(["scutil", "--dns"], capture_output=True, text=True, timeout=5)
                    for line in (out.stdout or "").splitlines():
                        line = line.strip()
                        if "nameserver" in line and "[" not in line:
                            parts = line.split()
                            if len(parts) >= 2:
                                servers.append(parts[-1])
                else:
                    with open("/etc/resolv.conf") as f:
                        for line in f:
                            parts = line.split()
                            if len(parts) >= 2 and parts[0] == "nameserver":
                                servers.append(parts[1])
        except Exception:
            pass
        return servers

    def get_primary_interface(self) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """(name, ip, subnet, gateway) of the default-route interface.

        IP Helper candidates first (systemic: IF_TYPE + OperStatus + gateway),
        then the OS route table for the default gateway.
        """
        # 1. IP Helper physical candidates — systemic, no name blacklists.
        try:
            for cand in self.get_physical_nic_candidates():
                ip = cand.get("ip")
                gateway = cand.get("gateway")
                if ip and gateway:
                    subnet = _get_subnet(ip)
                    logger.info(
                        f"[WindowsNetworkAdapter] Detected primary interface: "
                        f"{cand.get('name')} ({ip}, {subnet}, gateway)"
                    )
                    return cand.get("name"), ip, subnet, gateway
        except Exception as e:
            logger.debug(f"[WindowsNetworkAdapter] IP Helper primary-interface detection failed: {e}")

        # 2. OS route table — default gateway picks the physical NIC.
        try:
            result = subprocess.run(
                [CMD_ROUTE, "print", "0.0.0.0"],
                capture_output=True,
                text=True,
                timeout=ROUTE_COMMAND_TIMEOUT,
                check=False,
                creationflags=get_process_adapter().get_subprocess_flags(),
                startupinfo=get_process_adapter().get_startupinfo(),
            )
            if result.returncode != 0:
                logger.error(f"[WindowsNetworkAdapter] Failed to get route table: {result.stderr}")
                return None, None, None, None
            # Looking for line like: "0.0.0.0  0.0.0.0  192.168.1.1  192.168.1.10  25"
            for line in result.stdout.split("\n"):
                if "0.0.0.0" in line and line.count("0.0.0.0") >= 2:
                    parts = line.split()
                    if len(parts) >= 4:
                        gateway = parts[2]
                        interface_ip = parts[3]
                        if not _is_valid_ip(gateway) or not _is_valid_ip(interface_ip):
                            continue
                        # TUN adapters carry no default gateway (IP Helper
                        # already filtered them); skip if one slipped in.
                        if _is_tun_subnet_ip(interface_ip):
                            logger.warning(f"[WindowsNetworkAdapter] Ignored potential TUN interface: {interface_ip}")
                            continue
                        interface_name = self._get_interface_name(interface_ip)
                        subnet = _get_subnet(interface_ip)
                        logger.info(
                            f"[WindowsNetworkAdapter] Detected primary interface: "
                            f"{interface_name} ({interface_ip}, {subnet}, {gateway})"
                        )
                        return interface_name, interface_ip, subnet, gateway
            logger.warning("[WindowsNetworkAdapter] Could not detect primary interface from route table")
            return None, None, None, None
        except subprocess.TimeoutExpired:
            logger.error("[WindowsNetworkAdapter] Timeout while getting route table")
            return None, None, None, None
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[WindowsNetworkAdapter] Error detecting primary interface: {e}")
            return None, None, None, None
        except Exception as e:
            logger.error(f"[WindowsNetworkAdapter] Unexpected error detecting primary interface: {e}")
            return None, None, None, None

    # -- internals -----------------------------------------------------
    @staticmethod
    def _get_interface_name(ip: str) -> Optional[str]:
        """Get interface name from IP address using ipconfig."""
        if not _is_valid_ip(ip):
            return None

        try:
            result = subprocess.run(
                [CMD_IPCONFIG],
                capture_output=True,
                text=True,
                timeout=IPCONFIG_COMMAND_TIMEOUT,
                check=False,
                creationflags=get_process_adapter().get_subprocess_flags(),
                startupinfo=get_process_adapter().get_startupinfo(),
            )
            if result.returncode != 0:
                logger.warning("[WindowsNetworkAdapter] Failed to run ipconfig")
                return None

            # Parse ipconfig output
            current_adapter = None
            for line in result.stdout.split("\n"):
                # Check for adapter name
                if "adapter" in line.lower():
                    match = re.search(r"adapter (.+?):", line, re.IGNORECASE)
                    if match:
                        current_adapter = match.group(1).strip()
                # Check for IPv4 address
                if "IPv4 Address" in line and ip in line:
                    return current_adapter
            return None
        except subprocess.TimeoutExpired:
            logger.warning("[WindowsNetworkAdapter] Timeout while running ipconfig")
            return None
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"[WindowsNetworkAdapter] Error getting interface name: {e}")
            return None
        except Exception as e:
            logger.error(f"[WindowsNetworkAdapter] Unexpected error getting interface name: {e}")
            return None

    def ping_mtu(self, host: str, payload_size: int, timeout: int) -> bool:
        """Ping host with Don't Fragment (DF) flag set for the given payload size on Windows."""
        try:
            cmd = [
                "ping",
                "-n",
                "1",
                "-w",
                str(timeout * 1000),
                "-f",
                "-l",
                str(payload_size),
                host,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 1,
                creationflags=get_process_adapter().get_subprocess_flags(),
                startupinfo=get_process_adapter().get_startupinfo(),
                check=False,
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"[WindowsNetworkAdapter] MTU ping failed for size {payload_size}: {e}")
            return False

    def __init__(self):
        self._watcher: Optional[WindowsInterfaceWatcher] = None

    def start_interface_watcher(self, on_change_callback: Callable[[], None]) -> None:
        """Start background interface watcher using NotifyIpInterfaceChange (with polling fallback)."""
        self.stop_interface_watcher()
        self._watcher = WindowsInterfaceWatcher(on_change_callback)
        self._watcher.start()

    def stop_interface_watcher(self) -> None:
        """Stop background interface watcher."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None


class WindowsInterfaceWatcher:
    """Watches for network interface / IP / link status changes on Windows.

    Uses Win32 NotifyIpInterfaceChange for asynchronous, low-overhead event notification
    and falls back to 5-second polling if unavailable.
    """

    def __init__(self, callback: Callable[[], None]):
        self._callback = callback
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._notification_handle = ctypes.c_void_p(0)
        self._cb_func = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="WindowsInterfaceWatcher")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if hasattr(ctypes, "windll") and self._notification_handle.value:
            try:
                ctypes.windll.iphlpapi.CancelMibChangeNotify2(self._notification_handle)
            except Exception:
                pass
            self._notification_handle = ctypes.c_void_p(0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self):
        use_polling = True
        if hasattr(ctypes, "windll"):
            try:
                iphlpapi = ctypes.windll.iphlpapi
                if hasattr(iphlpapi, "NotifyIpInterfaceChange"):
                    PIPINTERFACE_CHANGE_CALLBACK = ctypes.WINFUNCTYPE(
                        None,
                        ctypes.c_void_p,
                        ctypes.c_void_p,
                        ctypes.c_int,
                    )

                    def _on_ip_change(caller_context, row, notif_type):
                        # 0.5s debounce to absorb transient link renegotiation
                        time.sleep(0.5)
                        try:
                            self._callback()
                        except Exception as e:
                            logger.debug(f"[WindowsInterfaceWatcher] Callback error: {e}")

                    self._cb_func = PIPINTERFACE_CHANGE_CALLBACK(_on_ip_change)
                    handle = ctypes.c_void_p(0)
                    ret = iphlpapi.NotifyIpInterfaceChange(
                        socket.AF_INET,
                        self._cb_func,
                        None,
                        False,
                        ctypes.byref(handle),
                    )
                    if ret == 0:
                        self._notification_handle = handle
                        use_polling = False
                        logger.info("[WindowsInterfaceWatcher] NotifyIpInterfaceChange registered successfully")
            except Exception as e:
                logger.debug(f"[WindowsInterfaceWatcher] Failed NotifyIpInterfaceChange setup: {e}")

        if use_polling:
            last_state = None
            while not self._stop_event.is_set():
                self._stop_event.wait(5.0)
                if self._stop_event.is_set():
                    break
                try:
                    candidates = get_physical_nic_candidates()
                    current = tuple((c.get("name"), c.get("ip"), c.get("gateway")) for c in candidates)
                    if last_state is not None and current != last_state:
                        logger.info("[WindowsInterfaceWatcher] Network change detected via polling fallback")
                        self._callback()
                    last_state = current
                except Exception as e:
                    logger.debug(f"[WindowsInterfaceWatcher] Polling error: {e}")
        else:
            while not self._stop_event.is_set():
                self._stop_event.wait(2.0)


__all__ = ["WindowsNetworkAdapter", "WindowsInterfaceWatcher"]
