"""WinDivert TCP injection — ported from patterniha/SNI-Spoofing
(``fake_tcp.py`` + ``injecter.py`` + ``monitor_connection.py``).

The ``wrong_seq`` bypass: the fake TLS ClientHello is injected as a fresh TCP
payload whose sequence number is rewound to ``syn_seq + 1 - len(payload)``, so
DPI sees the fake SNI while the server reassembles the real handshake.

``pydivert`` is imported LAZILY inside ``run()``: the package must import
cleanly on machines without pydivert / without admin rights (tests,
non-Windows dev). WinDivert.dll ships with pip's ``pydivert`` wheel and the
kernel driver requires an elevated shell. Guarded callers get failure from
``run()`` rather than an ImportError at import time.
"""

import asyncio
import threading

import loguru

logger = loguru.logger

__all__ = ["FakeInjectiveConnection", "FakeTcpInjector"]


class FakeInjectiveConnection:
    """Tracked TCP 4-tuple + injection state machine for one relayed connection."""

    def __init__(
        self,
        sock,
        src_ip,
        dst_ip,
        src_port,
        dst_port,
        fake_data: bytes,
        bypass_method: str,
        peer_sock,
    ):
        self.sock = sock
        self.monitor = True
        self.syn_seq = -1
        self.syn_ack_seq = -1
        self.id = (src_ip, src_port, dst_ip, dst_port)
        self.thread_lock = threading.Lock()
        # Fake-injection state (FakeInjectiveConnection extras)
        self.fake_data = fake_data
        self.sch_fake_sent = False
        self.fake_sent = False
        self.t2a_event = asyncio.Event()
        self.t2a_msg = ""
        self.bypass_method = bypass_method
        self.peer_sock = peer_sock
        self.running_loop = asyncio.get_running_loop()


class FakeTcpInjector:
    """Injects the fake ClientHello into the live TCP stream via WinDivert.

    Filter matches the physical-NIC 4-tuple only, so TUN-internal traffic
    (10.0.0.x) is never seen — the anti-loop invariant.
    """

    def __init__(self, w_filter: str, connections: dict):
        self.w_filter = w_filter
        self.connections = connections
        self.w = None
        self._stop_flag = threading.Event()

    def stop(self):
        """Ask the capture loop to exit and close the WinDivert handle.

        Closing ``self.w`` unblocks a pending ``recv()``; the loop then exits
        and the handle/driver resource is released. Call from the listener
        teardown so a reconnect can open a fresh WinDivert handle (otherwise
        the stale-daemon-thread handle + ``injector_enabled`` state from a
        previous connection survive, and the second connect misbehaves —
        the "only works after a full restart" bug).
        """
        self._stop_flag.set()
        w = self.w
        if w is not None:
            try:
                w.close()
            except Exception:
                pass
            self.w = None

    def fake_send_thread(self, packet, connection: FakeInjectiveConnection):
        import time

        time.sleep(0.001)
        with connection.thread_lock:
            if not connection.monitor:
                return
            packet.tcp.psh = True
            packet.ip.packet_len = packet.ip.packet_len + len(connection.fake_data)
            packet.tcp.payload = connection.fake_data
            if packet.ipv4:
                packet.ipv4.ident = (packet.ipv4.ident + 1) & 0xFFFF
            if connection.bypass_method == "wrong_seq":
                packet.tcp.seq_num = (connection.syn_seq + 1 - len(packet.tcp.payload)) & 0xFFFFFFFF
                connection.fake_sent = True
                self.w.send(packet, True)
            else:
                raise ValueError(f"not implemented bypass method: {connection.bypass_method}")

    def on_unexpected_packet(self, packet, connection: FakeInjectiveConnection, info_m: str):
        connection.sock.close()
        connection.peer_sock.close()
        connection.monitor = False
        connection.t2a_msg = "unexpected_close"
        connection.running_loop.call_soon_threadsafe(connection.t2a_event.set)
        self.w.send(packet, False)

    def on_inbound_packet(self, packet, connection: FakeInjectiveConnection):
        if connection.syn_seq == -1:
            self.on_unexpected_packet(packet, connection, "unexpected inbound packet, no syn sent!")
            return
        if (
            packet.tcp.ack
            and packet.tcp.syn
            and (not packet.tcp.rst)
            and (not packet.tcp.fin)
            and len(packet.tcp.payload) == 0
        ):
            seq_num = packet.tcp.seq_num
            ack_num = packet.tcp.ack_num
            if connection.syn_ack_seq != -1 and connection.syn_ack_seq != seq_num:
                self.on_unexpected_packet(
                    packet,
                    connection,
                    f"unexpected inbound syn-ack packet, seq change! {seq_num} {connection.syn_ack_seq}",
                )
                return
            if ack_num != ((connection.syn_seq + 1) & 0xFFFFFFFF):
                self.on_unexpected_packet(
                    packet,
                    connection,
                    f"unexpected inbound syn-ack packet, ack not matched! {ack_num} {connection.syn_seq}",
                )
                return
            connection.syn_ack_seq = seq_num
            self.w.send(packet, False)
            return
        if (
            packet.tcp.ack
            and (not packet.tcp.syn)
            and (not packet.tcp.rst)
            and (not packet.tcp.fin)
            and len(packet.tcp.payload) == 0
            and connection.fake_sent
        ):
            seq_num = packet.tcp.seq_num
            ack_num = packet.tcp.ack_num
            if connection.syn_ack_seq == -1 or ((connection.syn_ack_seq + 1) & 0xFFFFFFFF) != seq_num:
                self.on_unexpected_packet(
                    packet,
                    connection,
                    f"unexpected inbound ack packet, seq not matched! {seq_num} {connection.syn_ack_seq}",
                )
                return
            if ack_num != ((connection.syn_seq + 1) & 0xFFFFFFFF):
                self.on_unexpected_packet(
                    packet,
                    connection,
                    f"unexpected inbound ack packet, ack not matched! {ack_num} {connection.syn_seq}",
                )
                return
            connection.monitor = False
            connection.t2a_msg = "fake_data_ack_recv"
            connection.running_loop.call_soon_threadsafe(connection.t2a_event.set)
            return
        self.on_unexpected_packet(packet, connection, "unexpected inbound packet")

    def on_outbound_packet(self, packet, connection: FakeInjectiveConnection):
        if connection.sch_fake_sent:
            self.on_unexpected_packet(
                packet,
                connection,
                "unexpected outbound packet, recv packet after fake sent!",
            )
            return
        if (
            packet.tcp.syn
            and (not packet.tcp.ack)
            and (not packet.tcp.rst)
            and (not packet.tcp.fin)
            and len(packet.tcp.payload) == 0
        ):
            seq_num = packet.tcp.seq_num
            ack_num = packet.tcp.ack_num
            if ack_num != 0:
                self.on_unexpected_packet(
                    packet,
                    connection,
                    "unexpected outbound syn packet, ack_num is not zero!",
                )
                return
            if connection.syn_seq != -1 and connection.syn_seq != seq_num:
                self.on_unexpected_packet(
                    packet,
                    connection,
                    f"unexpected outbound syn packet, seq not matched! {seq_num} {connection.syn_seq}",
                )
                return
            connection.syn_seq = seq_num
            self.w.send(packet, False)
            return
        if (
            packet.tcp.ack
            and (not packet.tcp.syn)
            and (not packet.tcp.rst)
            and (not packet.tcp.fin)
            and len(packet.tcp.payload) == 0
        ):
            seq_num = packet.tcp.seq_num
            ack_num = packet.tcp.ack_num
            if connection.syn_seq == -1 or ((connection.syn_seq + 1) & 0xFFFFFFFF) != seq_num:
                self.on_unexpected_packet(
                    packet,
                    connection,
                    f"unexpected outbound ack packet, seq not matched! {seq_num} {connection.syn_seq}",
                )
                return
            if connection.syn_ack_seq == -1 or ack_num != ((connection.syn_ack_seq + 1) & 0xFFFFFFFF):
                self.on_unexpected_packet(
                    packet,
                    connection,
                    f"unexpected outbound ack packet, ack not matched! {ack_num} {connection.syn_ack_seq}",
                )
                return
            self.w.send(packet, False)
            connection.sch_fake_sent = True
            threading.Thread(target=self.fake_send_thread, args=(packet, connection), daemon=True).start()
            return
        self.on_unexpected_packet(packet, connection, "unexpected outbound packet")

    def inject(self, packet):
        if packet.is_inbound:
            c_id = (
                packet.ip.dst_addr,
                packet.tcp.dst_port,
                packet.ip.src_addr,
                packet.tcp.src_port,
            )
        elif packet.is_outbound:
            c_id = (
                packet.ip.src_addr,
                packet.tcp.src_port,
                packet.ip.dst_addr,
                packet.tcp.dst_port,
            )
        else:
            raise ValueError("impossible direction!")
        try:
            connection = self.connections[c_id]
        except KeyError:
            self.w.send(packet, False)
            return
        with connection.thread_lock:
            if not connection.monitor:
                self.w.send(packet, False)
                return
            if packet.is_inbound:
                self.on_inbound_packet(packet, connection)
            else:
                self.on_outbound_packet(packet, connection)

    def run(self, on_fail=None):
        """Blocking WinDivert capture loop.

        Returns False (and calls ``on_fail``) if pydivert is unavailable, the
        driver fails to open, or the capture loop crashes — so the caller can
        fall back to a plain relay instead of silently doing nothing. The
        original code let a driver-open error die in this daemon thread with no
        signal, leaving ``injector_enabled`` True and dropping connections.
        """
        try:
            from pydivert import WinDivert
        except ImportError:
            if on_fail:
                on_fail()
            return False
        try:
            self.w = WinDivert(self.w_filter)
        except Exception as e:
            logger.error(f"[SniSpoof] WinDivert open failed: {e}")
            if on_fail:
                on_fail()
            return False
        try:
            with self.w:
                while not self._stop_flag.is_set():
                    packet = self.w.recv(65575)
                    self.inject(packet)
        except Exception as e:
            if self._stop_flag.is_set():
                # Intentional teardown: stop() set the flag AND closed the handle,
                # so the pending recv() raising "WinDivert handle is not open" is
                # EXPECTED — a graceful exit, not a crash. Exit silently (Debug)
                # and NEVER call on_fail (which would flip to plain relay + ERROR).
                logger.debug(f"[SniSpoof] WinDivert capture loop exited during teardown: {e}")
                return False
            logger.error(f"[SniSpoof] WinDivert capture loop exited: {e}")
            if on_fail:
                on_fail()
            return False
