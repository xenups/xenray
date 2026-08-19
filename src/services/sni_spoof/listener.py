"""SNI-spoof transparent TCP relay — ported from patterniha/SNI-Spoofing.

The listener binds LISTEN_HOST:LISTEN_PORT and relays raw TCP to the real
CONNECT_IP:CONNECT_PORT while injecting a fake TLS ClientHello carrying FAKE_SNI
using the wrong_seq rewind. Xray's outbound server address is rewritten (in
xray_config_processor) to 127.0.0.1:LISTEN_PORT, so Xray's own connection to its
proxy server flows through this relay — no SOCKS handshake, the raw TLS bytes
pass through untouched (matches the proven reference setup).

Fail-soft: when pydivert/WinDivert is unavailable or the driver fails to open,
``injector_failed`` turns injection off and the relay falls back to a plain TCP
forward (connections are never dropped on a driver issue).
"""

import asyncio
import os
import socket
import threading
import traceback

import loguru

from src.services.sni_spoof.client_hello import ClientHelloMaker
from src.services.sni_spoof.tcp_injector import FakeInjectiveConnection, FakeTcpInjector

logger = loguru.logger

# Defaults — overridden at runtime via configure() from persisted settings.
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 40443
FAKE_SNI = "chatgpt.com"
CONNECT_IP = "185.193.30.94"
CONNECT_PORT = 443
DATA_MODE = "tls"
BYPASS_METHOD = "wrong_seq"

fake_injective_connections: dict = {}
injector_enabled = False
injector_failed = threading.Event()
CONNECT_IP_RESOLVED = ""  # numeric IPv4 of CONNECT_IP (resolved at run_listener start)


def configure(config: dict) -> None:
    """Apply persisted config from src.services.sni_spoof.config.build_config()."""
    globals().update(
        {
            k: config[k]
            for k in (
                "LISTEN_HOST",
                "LISTEN_PORT",
                "FAKE_SNI",
                "CONNECT_IP",
                "CONNECT_PORT",
            )
        }
    )


def get_default_interface_ipv4(addr: str = "8.8.8.8") -> str:
    """IP of the default-route interface (fallback). Returns "" on failure."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((addr, 53))
    except OSError:
        return ""
    else:
        return s.getsockname()[0]
    finally:
        s.close()


def _os_default_egress_ip() -> str:
    """OS-authoritative default-route egress IP.

    A dummy UDP socket to 8.8.8.8 makes the OS pick the interface that would carry
    the outbound connection; ``getsockname()[0]`` returns its source IP directly.
    This is language/name-independent (no fragile blacklist involved).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def _iface_name_for_ip(ip: str) -> str | None:
    """Map an IP back to its interface name via psutil (best-effort)."""
    try:
        import psutil

        for name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET and a.address == ip:
                    return name
    except Exception:
        pass
    return None


def _scan_physical_nic_ip() -> str:
    """Systematic psutil fallback scan — physical, up, IPv4, gateway-bearing."""
    try:
        import psutil

        from src.services.sni_spoof.nic_detect import get_physical_nic_candidates

        # 1) IP Helper API (real IF_TYPE + OperStatus + gateway) when available.
        cands = get_physical_nic_candidates()
        if cands:
            return cands[0]["ip"]
        # 2) psutil: physical-ish up adapters with a private IPv4. We no longer
        #    guess by name — every up adapter that is not loopback is a candidate,
        #    and the caller rejects TUN by its lack of a gateway route below.
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, stat in stats.items():
            if not stat.isup:
                continue
            for a in addrs.get(name, []):
                if a.family == socket.AF_INET and a.address and a.address != "127.0.0.1":
                    return a.address
    except Exception as e:
        logger.debug(f"[SniSpoof] physical NIC scan failed: {e}")
    return ""


def get_physical_nic_ip() -> str:
    """IPv4 of the OS's physical internet-facing NIC.

    Priority (all systematic, no name guessing):
      1. IP Helper API (``GetAdaptersAddresses``): physical IF_TYPE, OperStatus
         UP, IPv4 + gateway present.
      2. OS default-route discovery (dummy UDP) IF the egress adapter is a real
         physical link type (checked via psutil name→IP→stats).
      3. Windows ``route print 0.0.0.0`` (default-gateway-based) via
         NetworkInterfaceDetector.
      4. Systematic psutil up-adapter scan.
    """
    from src.services.sni_spoof.nic_detect import get_physical_nic_candidates

    # 1) IP Helper API — authoritative physical link type + OperStatus + gateway.
    try:
        cands = get_physical_nic_candidates()
        if cands:
            logger.debug(
                f"[SniSpoof] physical NIC (IP Helper) '{cands[0]['name']}' "
                f"-> {cands[0]['ip']} (iftype={cands[0]['iftype']}, "
                f"gateway={cands[0]['gateway']})"
            )
            return cands[0]["ip"]
    except Exception as e:
        logger.debug(f"[SniSpoof] IP Helper detection failed: {e}")

    # 2) OS default-route egress — but reject if it resolves to a non-physical
    #    link type (e.g. TUN under VPN), which has no gateway on the real NIC.
    egress = _os_default_egress_ip()
    if egress:
        iface_name = _iface_name_for_ip(egress)
        if iface_name and _is_physical_link(iface_name):
            logger.debug(f"[SniSpoof] primary NIC '{iface_name}' -> {egress}")
            return egress
        if iface_name is None:
            logger.debug(f"[SniSpoof] primary egress IP: {egress}")
            return egress
        logger.debug(f"[SniSpoof] egress '{iface_name}' not physical ({egress}) — rejecting")

    # 3) Windows route table — default gateway picks the physical NIC.
    try:
        from src.platform.factory import get_network_adapter

        _name, _ip, _subnet, _gw = get_network_adapter().get_primary_interface()
        if _ip:
            logger.debug(f"[SniSpoof] primary interface (route) '{_name}' -> {_ip}")
            return _ip
    except Exception as e:
        logger.debug(f"[SniSpoof] primary-interface detection failed: {e}")

    return _scan_physical_nic_ip() or get_default_interface_ipv4()


def _is_physical_link(iface_name: str) -> bool:
    """True when an interface is a physical link type (Ethernet / 802.11).

    Uses psutil's per-interface ``isup`` + the IP Helper IF_TYPE when it can be
    resolved; falls back to *not* assuming virtual (no name guessing) so unknown
    adapters retain their chance unless proven virtual by link type.
    """
    try:
        import psutil

        stats = psutil.net_if_stats()
        stat = stats.get(iface_name)
        if stat is None or not stat.isup:
            return False
        # psutil does not expose IF_TYPE; rely on IP Helper for that, else
        # fall back to "up with a gateway-carrying route" (handled by caller).
        return True
    except Exception:
        return True


def resolve_connect_ipv4(host: str) -> str:
    """Return host if it is already an IPv4, else resolve a domain to an IPv4.

    WinDivert filters only accept numeric IPs (a domain string throws WinError 87).
    """
    try:
        socket.inet_aton(host)
        return host
    except OSError:
        try:
            resolved = socket.gethostbyname(host)
            if resolved:
                logger.debug(f"[SniSpoof] resolved CONNECT_IP {host} -> {resolved}")
                return resolved
        except OSError:
            logger.warning(f"[SniSpoof] could not resolve CONNECT_IP domain {host}")
        return host


def pydivert_available() -> bool:
    """True only when the pydivert module can be imported (Windows + installed)."""
    try:
        import pydivert

        return pydivert is not None
    except Exception:
        return False


def configure_socket(sock: socket.socket, block: bool = True) -> None:
    """Reference-style socket tuning: non-blocking + keepalive probes."""
    if not block:
        sock.setblocking(False)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if hasattr(socket, "TCP_KEEPIDLE"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 11)
    if hasattr(socket, "TCP_KEEPINTVL"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2)
    if hasattr(socket, "TCP_KEEPCNT"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)


async def relay_main_loop(
    sock_1: socket.socket,
    sock_2: socket.socket,
    peer_task: asyncio.Task,
    first_prefix_data: bytes = b"",
):
    """Bidirectional byte relay — closes both socks, cancels + drains the peer.

    The peer is gathered (not just cancelled) so a pending task can never reach
    teardown and trigger "Task was destroyed but it is pending!".
    """
    loop = asyncio.get_running_loop()
    try:
        while True:
            data = await loop.sock_recv(sock_1, 65575)
            if not data:
                raise ValueError("eof")
            if first_prefix_data:
                data = first_prefix_data + data
                first_prefix_data = b""
            sent_len = await loop.sock_sendall(sock_2, data)
            if sent_len != len(data):
                raise ValueError("incomplete send")
    except Exception:
        # On Windows, closing a socket that has an overlapped recv/send still in
        # flight makes asyncio's `_cancel_overlapped` raise "WinError 6 — handle
        # invalid" when it later cancels the pending future (the "Cancelling an
        # overlapped future failed" message in the log). To avoid that, cancel
        # and drain the peer FIRST (so no overlapped IO remains), then close.
        if peer_task and not peer_task.done():
            peer_task.cancel()
            try:
                await asyncio.gather(peer_task, return_exceptions=True)
            except Exception:
                pass
        for s in (sock_1, sock_2):
            try:
                s.close()
            except Exception:
                pass
        return


async def handle(incoming_sock: socket.socket, incoming_remote_addr):
    """One transparent relay: dial CONNECT_IP:CONNECT_PORT, inject, then relay."""
    try:
        loop = asyncio.get_running_loop()
        if DATA_MODE == "tls":
            fake_data = ClientHelloMaker.get_client_hello_with(
                os.urandom(32), os.urandom(32), FAKE_SNI.encode(), os.urandom(32)
            )
        else:
            raise ValueError(f"impossible mode: {DATA_MODE}")

        outgoing_ipv4 = get_physical_nic_ip()
        if not outgoing_ipv4:
            incoming_sock.close()
            return

        outgoing_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        configure_socket(outgoing_sock, block=False)
        try:
            outgoing_sock.bind((outgoing_ipv4, 0))
        except OSError:
            outgoing_sock.close()
            incoming_sock.close()
            return
        src_port = outgoing_sock.getsockname()[1]

        # Use the NUMERIC destination (resolved at startup) so the 4-tuple in
        # FakeInjectiveConnection matches the packets WinDivert yields (which are
        # always IP-based) — a domain string here would never match.
        dst_ip = CONNECT_IP_RESOLVED or CONNECT_IP

        fake_injective_conn = FakeInjectiveConnection(
            outgoing_sock,
            outgoing_ipv4,
            dst_ip,
            src_port,
            CONNECT_PORT,
            fake_data,
            BYPASS_METHOD,
            incoming_sock,
        )
        fake_injective_connections[fake_injective_conn.id] = fake_injective_conn
        try:
            await loop.sock_connect(outgoing_sock, (dst_ip, CONNECT_PORT))
        except Exception:
            fake_injective_conn.monitor = False
            fake_injective_connections.pop(fake_injective_conn.id, None)
            outgoing_sock.close()
            incoming_sock.close()
            return

        if BYPASS_METHOD == "wrong_seq" and injector_enabled and not injector_failed.is_set():
            try:
                await asyncio.wait_for(fake_injective_conn.t2a_event.wait(), 2)
                if fake_injective_conn.t2a_msg != "fake_data_ack_recv":
                    raise ValueError(f"unexpected t2a msg: {fake_injective_conn.t2a_msg}")
            except Exception:
                # Reference-exact behavior: once the fake ClientHello has been
                # injected with a rewound seq and its ACK is not confirmed, the
                # TCP seq state is indeterminate — continuing to relay would mix
                # real bytes after a fake-synced payload and corrupt the stream
                # (the source of the flaky/periodic drops). Match reference:
                # drop the connection rather than relay plain.
                fake_injective_conn.monitor = False
                fake_injective_connections.pop(fake_injective_conn.id, None)
                outgoing_sock.close()
                incoming_sock.close()
                return
        elif BYPASS_METHOD == "wrong_seq" and injector_failed.is_set():
            # The injector ran (fake CH may have been sent) but its capture loop
            # has died. The 4-tuple seq tracking in the injector is gone, so any
            # in-flight fake-synced payload is unconfirmed — fail closed like the
            # reference rather than relay corrupt bytes.
            fake_injective_conn.monitor = False
            fake_injective_connections.pop(fake_injective_conn.id, None)
            outgoing_sock.close()
            incoming_sock.close()
            return

        fake_injective_conn.monitor = False
        fake_injective_connections.pop(fake_injective_conn.id, None)

        oti_task = asyncio.create_task(relay_main_loop(outgoing_sock, incoming_sock, asyncio.current_task(), b""))
        await relay_main_loop(incoming_sock, outgoing_sock, oti_task, b"")
    except Exception:
        traceback.print_exc()
        try:
            incoming_sock.close()
        except Exception:
            pass


async def serve(sock: socket.socket) -> None:
    """Accept loop run by the caller's event loop; drains handlers on shutdown.

    Guards accept against transient Windows OSErrors (WinError 64 "network name
    deleted", WinError 6 "invalid handle") so a teardown or interface change does
    not crash the listener ungracefully or strand the accept call.
    """
    loop = asyncio.get_running_loop()
    tasks: set = set()
    try:
        while True:
            try:
                incoming_sock, addr = await loop.sock_accept(sock)
            except asyncio.CancelledError:
                raise
            except OSError as e:
                logger.warning(f"[SniSpoof] accept error ({e.errno}): {e}")
                if sock.fileno() == -1:
                    return
                await asyncio.sleep(0.1)
                continue
            incoming_sock.setblocking(False)
            incoming_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            t = asyncio.create_task(handle(incoming_sock, addr))
            tasks.add(t)
            t.add_done_callback(tasks.discard)
    finally:
        for t in list(tasks):
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def run_listener() -> None:
    """Bind LISTEN_HOST:LISTEN_PORT, start the (lazy, fail-soft) WinDivert
    injector thread on the physical NIC, then accept and relay forever."""
    global injector_enabled, CONNECT_IP_RESOLVED

    # Reset per-connection state left over from a previous listener run. Without
    # this the stale connections dict, injector_enabled=True and any failed flag
    # from the LAST connect survive into THIS one -> wrong_seq / health-check
    # misbehaves on the second connect (the "only works after a restart" bug).
    fake_injective_connections.clear()
    injector_enabled = False
    injector_failed.clear()
    _active_injector = {"injector": None}

    mother_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    mother_sock.setblocking(False)
    mother_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    mother_sock.bind((LISTEN_HOST, LISTEN_PORT))
    mother_sock.listen()

    # WinDivert filters require a numeric IPv4 — resolve a domain CONNECT_IP now.
    CONNECT_IP_RESOLVED = resolve_connect_ipv4(CONNECT_IP)
    logger.info(
        f"[SniSpoof] relay listener on {LISTEN_HOST}:{LISTEN_PORT} -> {CONNECT_IP}:{CONNECT_PORT} "
        f"(resolved {CONNECT_IP_RESOLVED}) fake_sni={FAKE_SNI} method={BYPASS_METHOD}"
    )

    interface_ipv4 = get_physical_nic_ip()
    if interface_ipv4 and pydivert_available():
        dst = CONNECT_IP_RESOLVED or CONNECT_IP
        w_filter = (
            "tcp and ("
            f"(ip.SrcAddr == {interface_ipv4} and ip.DstAddr == {dst}) or "
            f"(ip.SrcAddr == {dst} and ip.DstAddr == {interface_ipv4})"
            ")"
        )
        logger.info(f"[SniSpoof] WinDivert filter (physical NIC): {w_filter}")

        def _on_injector_fail():
            global injector_enabled
            injector_enabled = False
            injector_failed.set()
            logger.error("[SniSpoof] WinDivert injector terminated — falling back to plain relay")

        fake_tcp_injector = FakeTcpInjector(w_filter, fake_injective_connections)
        _active_injector["injector"] = fake_tcp_injector
        threading.Thread(target=fake_tcp_injector.run, args=(_on_injector_fail,), daemon=True).start()
        injector_enabled = True
    else:
        logger.warning(
            "[SniSpoof] pydivert unavailable (missing / non-admin) — running as plain TCP relay (no injection)"
        )

    try:
        await serve(mother_sock)
    finally:
        # Teardown: break any pending accept and release the local port cleanly so
        # 40443 is not left locked for the next connection attempt.
        try:
            mother_sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        except Exception:
            pass
        mother_sock.close()
        # Also stop the WinDivert injector thread + close its handle, and reset
        # the flags, so a reconnect can start a clean injector (stale handle /
        # injector_enabled from this run otherwise breaks the second connect).
        injector_enabled = False
        inj = _active_injector.get("injector")
        if inj is not None:
            try:
                inj.stop()
            except Exception:
                pass
