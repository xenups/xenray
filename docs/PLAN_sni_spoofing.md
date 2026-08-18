# SNI Spoofing Integration — Architecture & Implementation Plan (XenRay)

## 1. Core mechanics of `patterniha/SNI-Spoofing` (byte/TLS layer)

**What it does:** Bypass DPI (Deep Packet Inspection) by spoofing the TLS SNI
(Server Name Indication) — sending a FAKE SNI in the ClientHello, then tricking
the proxy server into accepting the connection via a **TCP wrong-sequence**
injection so the REAL SNI never traverses the DPI'd path.

**Reference flow (from the repo, verified):**
1. A client connects to a local listener (`LISTEN_HOST:LISTEN_PORT`, default
   `127.0.0.1:40443`).
2. `main.py` builds a **fake TLS ClientHello** via `ClientHelloMaker
   .get_client_hello_with(random, sess_id, FAKE_SNI, key_share)` — a 517-byte
   TLS record carrying `FAKE_SNI` (e.g. `mci.ir`/`chatgpt.com`) in the SNI ext.
3. It opens a real TCP socket to `CONNECT_IP:CONNECT_PORT` and binds it to the
   interface's local IP.
4. **`FakeTcpInjector` (WinDivert via `pydivert`) filters live TCP packets** for
   that 4-tuple (`src_ip, src_port, dst_ip, dst_port`). It:
   - Tracks the SYN/SYN-ACK/ACK sequence numbers (`sync_seq`, `syn_ack_seq`).
   - On the first outbound ACK, it **injects the fake ClientHello as a new
     TCP payload** with a deliberately **wrong sequence number**
     (`seq = syn_seq + 1 - len(payload)`), setting the PSH flag. This is the
     `wrong_seq` bypass method — the payload is sent "back in sequence" so the
     DPI sees one thing and the server reassembles another.
   - Waits for the server's ACK of the fake data (`t2a_event`), then relaying
     real traffic both ways (`relay_main_loop`).
5. **`DATA_MODE = "tls"`** — only TLS ClientHello spoofing is implemented; the
   VLESS/HTTP branches are commented out.

**Why it defeats DPI:** The DPI box sees a TLS ClientHello to `FAKE_SNI`
(a benign domain) and lets the TCP flow through. The real destination
(`CONNECT_IP`) is hidden. The wrong-seq trick makes the server-side TCP stack
reassemble the injected ClientHello as the very first bytes, so TLS proceeds to
`CONNECT_IP` with a plausible handshake.

**Hard dependencies:**
- `pydivert` (**WinDivert user-mode DLL**) — raw packet capture/injection.
  **NOT installed in XenRay's venv** (verified). Requires **administrator
  privileges** (WinDivert opens a kernel driver).
- Windows-only (WinDivert is a Windows driver).
- `ClientHelloMaker` builds a valid TLS 1.3 ClientHello with only the SNI +
  padding + key-share extensions.

---

## 2. UI layout & data-persistence schema

### 2a. Sidebar entry
Add a nav item in `src/ui/components/common/nav_sidebar.py` `_nav_items`
(between Logs and Settings):
```python
("sni_spoof", t("nav.sni_spoof", default="SNI Spoof"),
 ft.Icons.SHIELD_ROUNDED),
```
Icon: `ft.Icons.SHIELD_ROUNDED` (matches security theme). The active-indicator
glide + `set_active_tab` machinery already handles new tab ids generically —
only the `view_map` in `ui_builder.py` needs a new key:
```python
"sni_spoof": self._main._stitch_sni_spoof_view,
```

### 2b. Settings view `src/ui/views/sni_spoof_view.py`
A `SniSpoofView(ft.Container)` with:
1. **Header**: title "SNI Spoof" + subtitle.
2. **Enable toggle** — `ft.Switch`, master on/off (persisted `sni_spoof_enabled.txt`).
3. **Top-priority fields** with `ft.TextField` + save-on-change (persisted):
   - `FAKE_SNI` — default `chatgpt.com` (`sni_fake_sni.txt`)
   - `CONNECT_IP` — default `185.193.30.94` (`sni_connect_ip.txt`)
4. **Optional fields**:
   - `CONNECT_PORT` — default `443` (`sni_connect_port.txt`), `ft.TextField` numeric.
   - `LISTEN_HOST` — default `127.0.0.1` (`sni_listen_host.txt`)
   - `LISTEN_PORT` — default `40443` (`sni_listen_port.txt`), numeric.
5. **Status chip**: shows `Running / Stopped` (heartbeat from the service).

### 2c. Persistence (follow existing `SettingsRepository` pattern)
The repo uses per-key `_read("x.txt", default)` / `_write("x.txt", value)`
flat files (verified). Add symmetric getters/setters:
```python
# src/repositories/settings_repository.py  (flat-file pattern: _read :37, _write :48, atomic_write :7)
def get_sni_spoof_enabled() -> bool      # default FALSE -> use == "true" (NOT != "false")
def set_sni_spoof_enabled(v: bool)
def get_sni_fake_sni() -> str            # default "chatgpt.com"
def set_sni_fake_sni(v: str)
def get_sni_connect_ip() -> str          # default "185.193.30.94"
def set_sni_connect_ip(v: str)
def get_sni_connect_port() -> int        # default 443; range-check 1024-65535 like get_proxy_port :54
def set_sni_connect_port(v: int)
def get_sni_listen_host() -> str         # default "127.0.0.1"
def set_sni_listen_host(v: str)
def get_sni_listen_port() -> int         # default 40443; range-check
def set_sni_listen_port(v: int)
```
File names: `sni_spoof_enabled.txt`, `sni_fake_sni.txt`, `sni_connect_ip.txt`,
`sni_connect_port.txt`, `sni_listen_host.txt`, `sni_listen_port.txt`.
Controller `SniSpoofController` mirrors `RoutingController`: reads repo on init,
`set_*` methods persist + publish `EventBus` topic `sni_spoof_changed` for the
sidebar/view status sync.

---

## 3. Traffic-flow design — Proxy Mode vs TUN Mode

### 3a. System Proxy Mode
**Current XenRay proxy pipeline:** apps → WinINET/system proxy
(`127.0.0.1:<http_port>`) → Xray SOCKS (`10805`) → remote server.

**SNI-spoof integration in proxy mode** — the cleanest hook is **NOT to spawn
WinDivert** (expensive, admin-only) but to make the **proxy's outbound dial
reach the spoof listener**:

```
App ──┬─(http)──> Xray http-in :<http_port>
      └─(socks)─> Xray socks-in :10805
                    └─ routing.direct / proxy ──> SNI Spoof LISTENER 127.0.0.1:40443
                                                      └─ FakeTcpInject(WinDivert)
                                                            └─> CONNECT_IP:443 (real, SNI hidden)
```

Concretely in **Xray**: add a route rule that sends traffic destined for
destinations matching the spoof set to a new **freedom outbound whose
`address`/`port` is rewritten to `127.0.0.1:40443`** — i.e. Xray acts as a
pre-router: it receives the app's request (host = target domain), rewrites the
destination to the local spoof listener, and the listener does the DPI-safe
handshake to `CONNECT_IP`. The fake SNI is injected by the WinDivert layer; the
real hostname is carried inside the (encrypted) TLS/tunnel so the egress proxy
knows the true destination.

> **Caveat & honest assessment:** This only genuinely helps if the *egress
> server's* SNI would otherwise be DPI-flagged. For a standard VLESS/xhttp
> tunnel the SNI is already randomized via `serverName`/finalmask. SNI-spoofing
> is most valuable when (a) you dial a **raw TLS to a fixed IP** (e.g. a
> direct-connect CDN) whose SNI is visible to DPI, or (b) you want to hide the
> SNI of `CONNECT_IP` from the ISP. The plan therefore wires it as an
> **optional per-rule bypass** (`direct_sni_*` routing_rules action), not the
> default path.

### 3b. Native TUN Mode
**Current XenRay TUN:** apps → SINGTUN (10.0.0.1/16) → sing-box TUN-in → routing
rules → `direct` (bind_interface=real NIC) or proxy (Xray socks) → egress.

**SNI-spoof in TUN mode** must avoid a **routing loop**. The loop risk: if TUN
routes `CONNECT_IP` into the spoof pipeline and the spoof pipeline's outgoing
socket re-enters the TUN, you get a cycle.

**Loop-free design (pre-route classification):**
1. sing-box TUN-in receives the packet for a spoof-matched dest.
2. Route rule: `CONNECT_IP` (or `direct`-classified SNI dest) → **`direct`**
   outbound bound to the REAL interface (Ethernet/Wi-Fi), NOT back into TUN —
   exactly the existing `bind_interface` mechanism (which we already fixed for
   the ikco.ir case). This exits on the physical NIC.
3. The **SNI spoof listener runs as a SEPARATE process** that owns the WinDivert
   handle. Its outgoing socket is explicitly **bound to the physical interface
   IP** (`get_default_interface_ipv4`), so it never sends down the TUN route.
4. To inject the fake ClientHello, WinDivert filters only the 4-tuple of the
   listener's real socket; because that socket is bound to the physical NIC IP
   (not 10.0.0.x), the filter never sees the TUN-internal traffic → **no loop**.

```
App → TUN(10.0.0.1) → sing-box route: sni-match → direct(bind real NIC)
        └─ real NIC ──> SNI Spoof listener 127.0.0.1:40443 (separate proc, WinDivert)
                          └─ fake ClientHello(wrong_seq) ──> CONNECT_IP:443
```

**Key anti-loop invariants (MUST implement):**
- The spoof listener binds its upstream socket to the **physical NIC IP** and
  never to `10.0.0.x`/TUN.
- sing-box routes the spoof dest to `direct` + the NIC `bind_interface`;
  `CONNECT_IP` is added to the existing `bind_interface` direct rules.
- WinDivert filter scoped tightly: `tcp and (SrcAddr == <phy_ip> or DstAddr ==
  <phy_ip>)` plus the 4-tuple, so TUN-internal packets (10.0.0.x) are ignored.

---

## 4. Required code adjustments

### 4a. `src/services/xray_config_processor.py` (NOT src/core/config_builders — that dir only has singbox)
- Correct path: **`src/services/xray_config_processor.py`** (`process_config` at `:92`, `_ensure_inbounds` at `:274`, imported `connection_orchestrator.py:357`).
- **Honest assessment — single-CONNECT_IP vs arbitrary domains:** Xray routing is server-dest based; a freedom-outbound rewrite to a fixed `127.0.0.1:LISTEN_PORT` **loses the original host**, so the listener can't know CONNECT_IP unless it is a single fixed target. The plan's default use-case (single `CONNECT_IP`, e.g. one CDN/server) is fine. For arbitrary domains this under-specifies — the listener would need the real host passed out-of-band. **Decision:** scope v1 to a single `CONNECT_IP` (+ its domains via `direct_sni` DNS), matching the reference's fixed-target design.
- Mechanic: add an Xray `routing` rule + outbound that sends `CONNECT_IP` (and spoof-matched dests) through the SNI path. Simplest correct hook (per validator): route `CONNECT_IP` → `TAG_DIRECT`, and have the SNI helper own the listener dial to `CONNECT_IP`. Do NOT do a freedom-dest-rewrite (loses host).

### 4b. `tun_injector.py` (src/services/tun_injector.py) — loop-breaking correction
- **Validator's key correction (plan §4 was wrong on one point):** binding the helper's upstream socket to the physical NIC IP does **NOT** by itself prevent TUN re-capture on Windows — a bound socket still routes via the default table, and TUN (without `strict_route`, which the code doesn't set) captures the default route.
- **The actual loop-breaker is sing-box routing:** add a rule `CONNECT_IP → outboundTag TAG_DIRECT + bind_interface(NIC)` so sing-box sends it OUT the physical NIC, never down into TUN's internal routing. NIC-bind on the helper is kept as belt-and-suspenders only.
- In `_build_routing_rules`, classify `CONNECT_IP` (and `direct_sni` domains) as `TAG_DIRECT` BEFORE the generic rules, reusing the existing insert-before-default chain.

### 4c. `xray_service.py` (src/services/xray_service.py) — lifecycle correction
- **`_terminate_all` does NOT exist.** Real flow: `start` at `:466` builds cmd + `ProcessUtils.run_command` `:492`, writes PID `:499-503`, spawns TUN-DNS daemon `:507`. `stop` at `:523` kills PID (graceful→force `:547-553`), rm PID, publishes `EVENT_CORE_PROCESS_STOPPED` `:565`.
- **Hook the sni helper:** spawn alongside Xray in `start` after `:492` (own PID file); kill explicitly in `stop` around `:547`; **register it in `CoreHealthMonitor`'s cascading teardown** (`core_health_monitor.py:217-230`) so it doesn't orphan on Xray crash. Lock helper to Xray PID (helper exits if parent PID gone).
- Keep single-instance guard via a PID file (pattern at `xray_service.py:499-503`).

### 4d. New module: `src/services/sni_spoof/`
- `sni_spoof_service.py` — lifecycle: `start()/stop()`, subprocess spawn,
  heartbeat, status callback to UI.
- `listener.py` — port of the reference `main.py` relay (asyncio listener +
  `FakeInjectiveConnection` + relay loop), **without** the commented VLESS blocks.
- `tcp_injector.py` — port of `fake_tcp.py`/`injecter.py` (pydivert `TcpInjector`,
  `FakeTcpInjector` wrong-seq logic).
- `client_hello.py` — port of `ClientHelloMaker` (packet_templates).
- `config.py` — reads the persisted fields + builds `CONNECT_IP/PORT`,
  `FAKE_SNI`, `LISTEN_HOST/PORT`, `DATA_MODE="tls"`, `BYPASS_METHOD="wrong_seq"`.
- **Dependency:** add `pydivert` to `pyproject.toml` (Windows-only, guarded
  import so Linux/macOS dev/test still import).

---

## 5. Rollout / testing plan
1. **Add settings keys + repo methods** + unit tests (persist/round-trip).
2. **UI view + sidebar** + controller EventBus topic + tests.
3. **Port spoof helper** as a standalone subprocess, unit-test `ClientHelloMaker`
   round-trip (`parse_client_hello(get_client_hello_with(...)) == input`, from repo).
4. **Helper process unit test** with a fake `CONNECT_IP` (a local echo server);
   verify the fake ClientHello is injected + relay works (no live DPI needed).
5. **Proxy-mode wiring** (xray_config_processor rule) — integration test: route
   a test dest to `127.0.0.1:LISTEN_PORT`, assert outbound.
6. **TUN-mode wiring** (tun_injector) — assert `CONNECT_IP → direct + bind_interface`
   and no loop (helper binds NIC IP, not 10.0.0.x).
7. **Live smoke** (admin): connect to a real `CONNECT_IP`, confirm site loads.
8. **Full suite green** (current 796) + black/isort + flake8; `tests/conftest.py`
   untouched.

## 6. Risks / honest caveats
- **pydivert not installed; requires Windows admin** (kernel driver). On
  non-admin the feature must fail-soft (toast + disabled toggle).
- **Value is situational**: modern XenRay tunnels already randomize SNI
  (finalmask/serverName). SNI-spoof shines only for raw-TLS-to-fixed-IP or
  hiding `CONNECT_IP`'s SNI from the ISP. Should default OFF.
- **Wrong-seq injection + TLS** can break with middleboxes that reorder/validate
  seq — the reference returns "unexpected packet" and closes on any mismatch.
- **Loop safety in TUN** is the highest-risk area; the NIC-bind invariant must
  be enforced in the helper and covered by a test.
