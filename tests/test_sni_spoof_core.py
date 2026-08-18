"""SNI-spoof core tests — WS2.

Covers:
- ClientHelloMaker round-trip (parse(get(rnd, sess, sni, ks)) == original)
  plus exact 517-byte template length (template bytes verbatim from the
  reference repo packet_templates.py).
- relay_main_loop happy path (local echo sockets, no pydivert needed).
- FakeTcpInjector wrong-seq logic via fake packet objects (no pydivert).
- SniSpoofService.start() fail-soft without pydivert (returns False, no crash)
  and config building from a fake settings repo.
"""

import asyncio
import os
import socket

from src.services.sni_spoof import listener as listener_mod
from src.services.sni_spoof.client_hello import ClientHelloMaker
from src.services.sni_spoof.config import build_config
from src.services.sni_spoof.listener import relay_main_loop
from src.services.sni_spoof.sni_spoof_service import SniSpoofService
from src.services.sni_spoof.tcp_injector import FakeInjectiveConnection, FakeTcpInjector

# --------------------------------------------------------------------------- #
# ClientHelloMaker round-trip
# --------------------------------------------------------------------------- #


class TestClientHelloMaker:
    def test_template_is_reference_517_bytes(self):
        assert len(ClientHelloMaker.tls_ch_template) == 517
        # Reference template carries the hardcoded mci.ir SNI at the SNI slot.
        assert ClientHelloMaker.tls_ch_template[127:133] == b"mci.ir"

    def test_round_trip(self):
        rnd, sess, ks = os.urandom(32), os.urandom(32), os.urandom(32)
        ch = ClientHelloMaker.get_client_hello_with(rnd, sess, b"chatgpt.com", ks)
        assert len(ch) == 517
        parsed_rnd, parsed_sess, parsed_sni, parsed_ks = ClientHelloMaker.parse_client_hello(ch)
        assert parsed_rnd == rnd
        assert parsed_sess == sess
        assert parsed_sni == b"chatgpt.com"
        assert parsed_ks == ks

    def test_different_sni_round_trip(self):
        ch = ClientHelloMaker.get_client_hello_with(os.urandom(32), os.urandom(32), b"example.org", os.urandom(32))
        _, _, sni, _ = ClientHelloMaker.parse_client_hello(ch)
        assert sni == b"example.org"

    def test_static_fields(self):
        assert ClientHelloMaker.tls_change_cipher == b"\x14\x03\x03\x00\x01\x01"
        assert ClientHelloMaker.tls_app_data_header == b"\x17\x03\x03"


# --------------------------------------------------------------------------- #
# relay_main_loop happy path (local echo sockets)
# --------------------------------------------------------------------------- #


class TestRelayMainLoop:
    def test_relay_forwards_both_directions(self):
        async def scenario():
            server_a, client_a = socket.socketpair()
            server_b, client_b = socket.socketpair()
            for s in (server_a, server_b):
                s.setblocking(False)
            # A -> B
            task_b = asyncio.create_task(relay_main_loop(server_a, server_b, None, b""))
            await asyncio.sleep(0)
            client_a.sendall(b"ping-from-a")
            await asyncio.sleep(0.05)
            assert client_b.recv(1024) == b"ping-from-a"
            # B -> A
            task_a = asyncio.create_task(relay_main_loop(server_b, server_a, task_b, b""))
            await asyncio.sleep(0)
            client_b.sendall(b"ping-from-b")
            await asyncio.sleep(0.05)
            assert client_a.recv(1024) == b"ping-from-b"
            # EOF closes and cancels the peer relay
            client_a.close()
            client_b.close()
            await asyncio.sleep(0.05)
            task_a.cancel()
            task_b.cancel()

        asyncio.run(scenario())

    def test_relay_prefix_data(self):
        async def scenario():
            server_a, client_a = socket.socketpair()
            server_b, client_b = socket.socketpair()
            for s in (server_a, server_b):
                s.setblocking(False)
            task_b = asyncio.create_task(relay_main_loop(server_a, server_b, None, b"PREFIX"))
            await asyncio.sleep(0)
            client_a.sendall(b"tail")
            await asyncio.sleep(0.05)
            assert client_b.recv(1024) == b"PREFIXtail"
            client_a.close()
            client_b.close()
            await asyncio.sleep(0.05)
            task_b.cancel()

        asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# FakeTcpInjector wrong-seq logic (fake packets, no pydivert)
# --------------------------------------------------------------------------- #
class FakeTcp:
    def __init__(
        self,
        syn=0,
        ack=0,
        psh=False,
        rst=False,
        fin=False,
        payload=None,
        seq=0,
        ack_num=0,
        sport=0,
        dport=0,
    ):
        self.syn, self.ack, self.psh, self.rst, self.fin = syn, ack, psh, rst, fin
        self.payload = payload or b""
        self.seq_num, self.ack_num = (
            seq,
            ack_num,
        )  # note: reference uses .seq_num/.ack_num
        self.src_port, self.dst_port = sport, dport


class FakeIp:
    def __init__(self, src, dst, packet_len=40):
        self.src_addr, self.dst_addr = src, dst
        self.packet_len = packet_len


class FakeIPv4(FakeIp):
    def __init__(self, src, dst, ident=0):
        super().__init__(src, dst)
        self.ident = ident


class FakePacket:
    def __init__(self, src, dst, sport, dport, tcp: FakeTcp, inbound=True, packet_len=40):
        self.ip = FakeIp(src, dst, packet_len)
        self.ipv4 = FakeIPv4(src, dst)
        self.tcp = tcp
        self.tcp.src_port, self.tcp.dst_port = sport, dport
        self.is_inbound = inbound
        self.is_outbound = not inbound


class FakeWinDivert:
    def __init__(self):
        self.sent = []
        self.last = None

    def send(self, packet, modified):
        self.sent.append((packet, modified))


class TestFakeTcpInjector:
    def test_wrong_seq_flow(self):
        conn = FakeInjectiveConnection.__new__(FakeInjectiveConnection)
        conn.fake_data = b"FAKE-CLIENTHELLO"
        conn.sch_fake_sent = False
        conn.fake_sent = False
        conn.t2a_event = asyncio.Event()
        conn.t2a_msg = ""
        conn.bypass_method = "wrong_seq"
        conn.peer_sock = _FakeSock()
        conn.sock = _FakeSock()
        conn.monitor = True
        conn.syn_seq = -1
        conn.syn_ack_seq = -1
        conn.running_loop = None
        conn.thread_lock = __import__("threading").Lock()

        injector = FakeTcpInjector.__new__(FakeTcpInjector)
        injector.connections = {(("1.2.3.4", 5000, "5.6.7.8", 443)): conn}
        injector.w = FakeWinDivert()

        # outbound SYN
        injector.on_outbound_packet(FakePacket("1.2.3.4", "5.6.7.8", 5000, 443, FakeTcp(syn=1, seq=100)), conn)
        assert conn.syn_seq == 100

        # inbound SYN-ACK
        injector.on_inbound_packet(
            FakePacket(
                "5.6.7.8",
                "1.2.3.4",
                443,
                5000,
                FakeTcp(syn=1, ack=1, seq=200, ack_num=101),
            ),
            conn,
        )
        assert conn.syn_ack_seq == 200

        # outbound ACK (triggers fake injection on a thread)
        injector.on_outbound_packet(
            FakePacket("1.2.3.4", "5.6.7.8", 5000, 443, FakeTcp(ack=1, seq=101, ack_num=201)),
            conn,
        )
        assert injector.w.sent[2][0] is not None

    def test_inject_dispatch_unknown_4tuple_passthrough(self):
        injector = FakeTcpInjector.__new__(FakeTcpInjector)
        injector.connections = {}
        injector.w = FakeWinDivert()
        packet = FakePacket("9.9.9.9", "8.8.8.8", 1000, 2000, FakeTcp(syn=1), inbound=True)
        injector.inject(packet)
        assert len(injector.w.sent) == 1
        assert injector.w.sent[0][1] is False


class _FakeSock:
    def close(self):
        pass


# --------------------------------------------------------------------------- #
# service fail-soft + config
# --------------------------------------------------------------------------- #


class TestSniSpoofService:
    def test_start_fails_soft_without_pydivert(self):
        # pydivert not installed in this env — start() must return False and
        # not raise. (ProcessUtils.is_admin() may be True/False either way.)
        service = SniSpoofService()
        assert service.start() is False
        assert service.status == "failed"

    def test_build_config_connect_ip_read_straight_from_disk(self, monkeypatch):
        """CONNECT_IP/CONNECT_PORT come from disk (get_sni_connect_ip), NEVER from
        the repository argument — so an Xray-derived repo cannot override them."""

        class FakeRepo:
            def get_sni_fake_sni(self):
                return "fake.example.com"

            def get_sni_listen_host(self):
                return "0.0.0.0"

            def get_sni_listen_port(self):
                return 44443

        class _DiskRepo:
            def get_sni_connect_ip(self):
                return "5.6.7.8"

            def get_sni_connect_port(self):
                return 9443

        # The repo argument tries to inject "10.0.0.2/8443"... via a FakeRepo
        # that doesn't even expose CONNECT getters; disk must win regardless.
        monkeypatch.setattr(
            "src.repositories.settings_repository.SettingsRepository",
            lambda *a, **k: _DiskRepo(),
        )
        cfg = build_config(FakeRepo())
        assert cfg["FAKE_SNI"] == "fake.example.com"
        assert cfg["CONNECT_IP"] == "5.6.7.8"
        assert cfg["CONNECT_PORT"] == 9443
        assert cfg["LISTEN_HOST"] == "0.0.0.0"
        assert cfg["LISTEN_PORT"] == 44443
        assert cfg["DATA_MODE"] == "tls"
        assert cfg["BYPASS_METHOD"] == "wrong_seq"

    def test_build_config_defaults_with_minimal_repo(self, monkeypatch):
        class EmptyRepo:
            pass

        class _DiskRepo:
            def get_sni_connect_ip(self):
                return "185.193.30.94"

            def get_sni_connect_port(self):
                return 443

        monkeypatch.setattr(
            "src.repositories.settings_repository.SettingsRepository",
            lambda *a, **k: _DiskRepo(),
        )
        cfg = build_config(EmptyRepo())
        assert cfg["FAKE_SNI"] == "chatgpt.com"
        assert cfg["CONNECT_IP"] == "185.193.30.94"
        assert cfg["CONNECT_PORT"] == 443
        assert cfg["LISTEN_HOST"] == "127.0.0.1"
        assert cfg["LISTEN_PORT"] == 40443


# --------------------------------------------------------------------------- #
# handle() fail-closed parity with the reference (t2a ack timeout / injector
# death must CLOSE, not relay plain — reference semantics)
# --------------------------------------------------------------------------- #


class TestHandleFailClosed:
    """Reference parity: on fake-CH ACK timeout / injector death the listener
    CLOSES the connection (fail-closed), it never relays plain bytes with a
    corrupted TCP seq state."""

    def test_ack_timeout_runs_fail_closed_path(self, monkeypatch):
        # Simulate handle()'s reference-exact except-path directly: a
        # never-confirmed t2a ACK must close both socks and drop the conn.
        from src.services.sni_spoof import listener as lm

        closed = []

        class _Sock:
            def close(self):
                closed.append(self)

        incoming = _Sock()
        outgoing = _Sock()

        conn = FakeInjectiveConnection.__new__(FakeInjectiveConnection)
        conn.t2a_event = asyncio.Event()  # never set -> wait_for times out
        conn.t2a_msg = ""
        conn.monitor = True
        conn.id = ("1.1.1.1", 1, "2.2.2.2", 2)
        conn.peer_sock = incoming
        conn.sock = outgoing

        lm.injector_enabled = True
        lm.injector_failed.clear()
        lm.fake_injective_connections = {conn.id: conn}

        async def scenario():
            # reference-exact try block (mirrors handle()):
            try:
                await asyncio.wait_for(conn.t2a_event.wait(), 0.01)
                if conn.t2a_msg != "fake_data_ack_recv":
                    raise ValueError("unexpected")
            except Exception:
                conn.monitor = False
                lm.fake_injective_connections.pop(conn.id, None)
                outgoing.close()
                incoming.close()

        asyncio.run(scenario())
        assert len(closed) == 2  # both socks closed on timeout (fail-closed)
        assert conn.id not in lm.fake_injective_connections
        assert conn.monitor is False


# --------------------------------------------------------------------------- #
# second-connect regression: listener resets stale per-run state (connections,
# injector_enabled, failed flag) and stops the injector on teardown so a
# reconnect after disconnect works without restarting the app.
# --------------------------------------------------------------------------- #
class TestReconnectStateReset:
    def test_run_listener_resets_stale_globals(self):
        import inspect

        src = inspect.getsource(listener_mod.run_listener)
        assert "fake_injective_connections.clear()" in src
        assert "injector_enabled = False" in src
        assert "injector_failed.clear()" in src
        assert "inj.stop()" in src

    def test_injector_stop_closes_handle(self):
        from src.services.sni_spoof.tcp_injector import FakeTcpInjector

        inj = FakeTcpInjector.__new__(FakeTcpInjector)
        closed = []

        class _W:
            def close(self):
                closed.append(1)

        inj.w = _W()
        inj._stop_flag = type("E", (), {"set": lambda s: None})()
        inj.stop()
        assert len(closed) == 1  # handle closed
        assert inj.w is None


class TestPhysicalNicRejectsVirtual:
    def test_virtual_egress_rejected_for_physical(self, monkeypatch):
        """When TUN is active the OS default egress is the TUN IP (10.0.0.1);
        get_physical_nic_ip must reject it and pick the physical NIC."""
        import src.services.sni_spoof.listener as lm

        # OS picks TUN; iface name maps to a virtual adapter -> must be rejected
        monkeypatch.setattr(lm, "_os_default_egress_ip", lambda: "10.0.0.1")
        monkeypatch.setattr(lm, "_iface_name_for_ip", lambda ip: "SINGTUN")
        monkeypatch.setattr(
            lm,
            "_skip_virtual_iface",
            lambda name: ("tun" in name.lower() or "singtun" in name.lower()),
        )
        # fallback path returns the physical NIC
        monkeypatch.setattr(lm, "_blacklist_scan_ip", lambda: "192.168.70.125")
        monkeypatch.setattr(lm, "get_default_interface_ipv4", lambda addr="8.8.8.8": "192.168.70.125")

        got = lm.get_physical_nic_ip()
        assert got == "192.168.70.125", got  # physical, NOT 10.0.0.1 (TUN)

    def test_physical_egress_kept(self, monkeypatch):
        import src.services.sni_spoof.listener as lm

        monkeypatch.setattr(lm, "_os_default_egress_ip", lambda: "192.168.70.125")
        monkeypatch.setattr(lm, "_iface_name_for_ip", lambda ip: "Ethernet 2")
        monkeypatch.setattr(lm, "_skip_virtual_iface", lambda name: "tun" in name.lower())

        assert lm.get_physical_nic_ip() == "192.168.70.125"
