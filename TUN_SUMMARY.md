# TUN Mode Development & Engineering Summary (v0.1.17-beta to Present)

This document provides a comprehensive analysis of all changes, engineering effort, technical challenges, root cause diagnoses, and recommendations regarding the TUN (VPN) mode implementation in XenRay from version `0.1.17-beta` up to `v0.2.1-beta` (current state).

---

## 1. Overview & Key Commits (Timeline of Changes)

From `v0.1.17-beta` to the current release, TUN mode underwent a complete architectural shift—transitioning from legacy/mocked sing-box implementations to dual-engine support (`TunEngine.XRAY` and `TunEngine.SING_BOX`), direct `wintun.dll` driver integration, dynamic route patching, and emergency crash recovery pipelines.

### Key Commits Summary
| Commit | Date | Subject & Scope | Effort / Impact |
|---|---|---|---|
| `dca38bc` | Jul 22, 2026 | **add xray tun** — Introduced native Xray TUN inbound injection, `TunInjector`, `ConfigPatcher`, `DnsConfigurator`, `wintun.dll` handling, and routing rules injection. | Major feature addition (~39k lines modified across core & assets). |
| `dfa19f3` | Jul 22, 2026 | **fix wintun.dll duplicate download** — Optimized `scripts/download_geo_files.py` to prevent redundant driver downloads. | Infrastructure stability. |
| `cf3d9c7` | Jul 22, 2026 | **fix 'charmap' codec can't encode character** — Resolved UTF-8 file stream encoding crashes on Windows non-UTF8 locales. | System compatibility. |
| `89fa45c` / `4a635ac` | Jul 22, 2026 | **remove singbox mocks** — Cleaned up stubbed/mocked sing-box interfaces to pave way for clean integration. | Code hygiene. |
| `1c2bf83` | Jul 23, 2026 | **implement core configuration processor** — Refactored `XrayConfigProcessor` to modularize DNS, TUN, and stream patching. | Architectural modularization. |
| `835e4c9` | Jul 24, 2026 | **Fix 'XrayConfigProcessor' object has no attribute '_TunEngine'** — Resolved engine configuration attribute missing crash. | Bug fix. |
| `05e1158` | Jul 24, 2026 | **implement sing-box TUN service** — Re-introduced dedicated `SingboxTunService` sidecar process, configuration generator, and multi-language support. | Dual TUN Engine capability. |
| `6d243f7` | Jul 25, 2026 | **fix(tun): resolve CDN and ECH routing loop deadlock in TUN mode** — Implemented physical NIC binding (`bind_interface`), pre-connection DNS resolution of proxy IPs, and NCSI bypass rules. | Critical stability fix. |
| `75174e5` | Jul 25, 2026 | **feat(tun): implement Subprocess Death Watcher & Emergency Cleanup Pipeline** — Added `TUNProcessWatcher` to detect unexpected binary crashes and clean up orphaned OS network routing & DNS settings. | Reliability & network protection. |

---

## 2. Technical Engineering Effort

The development effort for TUN mode focused on four main subsystems:

### A. Dual TUN Engine Architecture
1. **Xray Native TUN (`TunEngine.XRAY`)**:
   - Injects a `tun` inbound (`protocol: "tun"`, `name: "xenray-tun"`) directly into Xray's `config.json`.
   - Delegates system routing (`autoSystemRoutingTable: ["0.0.0.0/0", "::/0"]`) and packet processing to Xray's internal gVisor / LWIP network stack.
   - Configured in [src/services/tun_injector.py](file:///c:/Users/Xenups/Desktop/gorzer/pub/xenray/src/services/tun_injector.py).

2. **Sing-Box TUN Service (`TunEngine.SING_BOX`)**:
   - Operates as a secondary sidecar service via [src/services/singbox_tun_service.py](file:///c:/Users/Xenups/Desktop/gorzer/pub/xenray/src/services/singbox_tun_service.py).
   - Sing-box captures TUN interface traffic and forwards proxy traffic over SOCKS5 (`127.0.0.1:10808`) to Xray, while bypassing local/direct traffic.
   - Generates dedicated JSON configurations with DNS hijacking, pre-downloaded country rule-sets, and process-level direct routing.

### B. Route Bypass & Direct Interface Binding
- Implemented `NetworkInterfaceDetector.get_primary_interface()` ([src/utils/network_interface.py](file:///c:/Users/Xenups/Desktop/gorzer/pub/xenray/src/utils/network_interface.py)) to identify the active physical network adapter (IP, gateway, interface name).
- Injected `bind_interface` or `sockopt.interface` settings into outbound direct connections to force outbound proxy traffic out through the physical NIC rather than the TUN adapter.

### C. System Resiliency & Subprocess Monitoring
- Created `TUNProcessWatcher` ([src/services/tun_process_watcher.py](file:///c:/Users/Xenups/Desktop/gorzer/pub/xenray/src/services/tun_process_watcher.py)) operating on a background polling thread (`POLL_INTERVAL = 0.5s`).
- Triggers emergency crash callbacks (`set_on_crash_callback`) if Xray or Sing-box process exits unexpectedly, preventing system internet lockouts.

---

## 3. Key Challenges & Technical Roadblocks

During the implementation from `v0.1.17-beta` onwards, several critical network-level challenges surfaced:

### 1. TUN Routing Loop & CDN / ECH Deadlocks
* **The Problem**: When TUN mode captures global traffic (`0.0.0.0/0`), Xray/Sing-box outbound connections to the proxy server (e.g. Cloudflare, CloudFront, or remote VLESS endpoints) were captured by the TUN interface itself. This created an infinite loop (TUN -> Xray Outbound -> TUN -> Xray Outbound), causing total network freeze and high CPU utilization.
* **Encrypted Client Hello (ECH) Complication**: When ECH or TLS SNI domain fronting was enabled, domain-based routing failed because initial TCP/TLS handshakes were attempted over IPs that weren't yet routed outside the TUN.
* **How It Was Solved**:
  1. Pre-resolving proxy server domains to IPv4 addresses *prior* to enabling TUN mode using host DNS.
  2. Injecting static OS routes (`route add <ip> mask 255.255.255.255 <gateway>`) targeting proxy server IPs and bootstrap DNS servers (`1.1.1.1`, `8.8.8.8`).
  3. Binding direct outbounds explicitly to the physical NIC interface name.

### 2. Windows NCSI "No Internet Access" Yellow Warning
* **The Problem**: Windows Network Connectivity Status Indicator (NCSI) periodically checks `msftconnecttest.com` and `msftncsi.com`. When `strict_route` captured these probes, Windows marked the network adapter as having "No Internet Access", causing Windows apps (Outlook, Store, Edge) to block network calls.
* **How It Was Solved**:
  - Injected explicit bypass rules for `msftconnecttest.com` and `msftncsi.com` in both Sing-Box DNS rules and Xray routing tables, directing them through `bootstrap` DNS and `direct` outbound.

### 3. Orphaned Wintun Adapters & DNS Corruption on Subprocess Crash
* **The Problem**: If `xray.exe` or `sing-box.exe` crashed (e.g., memory panic, bad config, unexpected SIGKILL), the Wintun adapter remained open in the OS, system DNS remained pointed to non-responsive `127.0.0.1`, and all host internet access ceased.
* **How It Was Solved**:
  - Added `TUNProcessWatcher` thread and an emergency teardown sequence in `ConnectionOrchestrator` that cleans up static OS routes and terminates leftover orphan processes upon app exit or crash.

---

## 4. Why TUN Mode May Still Fail (Current Issues & Root Causes)

Despite extensive improvements, TUN mode can still fail or behave unexpectedly under specific environments. Here is an analysis of why issues persist:

### 1. Insufficient Process Elevation (Windows UAC Privileges) — **Primary Failure Cause**
* **Root Cause**: Creating network interfaces via `wintun.dll`, adding Windows OS routes (`route add`), or executing netsh commands strictly requires **Administrator privileges**.
* **Symptom**: When XenRay is launched as a standard non-elevated user:
  - `wintun.dll` fails to create the virtual network adapter (`xenray-tun` or `singbox-tun`).
  - Sing-box or Xray logs output `panic: failed to create tun interface: access is denied` or `operation not permitted`.
  - Connection status changes to connected in UI, but no traffic flows (or fails immediately).

### 2. Dynamic CDN IP Rotation & Single Pre-Resolved IP Caching
* **Root Cause**: Cloudflare and other CDNs use huge IP pools and dynamic DNS round-robin. `SingboxTunService._resolve_ips()` resolves proxy IPs *once* at connection startup and adds static routes for those specific IPs.
* **Symptom**: If the proxy domain resolves to a *new* IP during an active session (e.g., due to DNS re-query or fallback), traffic to the new IP bypasses the static route and gets trapped in the TUN routing loop, causing connection stalls after minutes of operation.

### 3. Misidentified Primary Network Interface (Virtual Adapters)
* **Root Cause**: `NetworkInterfaceDetector.get_primary_interface()` relies on default gateway detection. Systems running WSL2, VMware, VirtualBox, Tailscale, ZeroTier, or Hyper-V often have multiple default gateways or active virtual adapters.
* **Symptom**: If `NetworkInterfaceDetector` selects a virtual interface (e.g. `vEthernet (WSL)`) as the primary interface:
  - `bind_interface` binds direct outbound traffic to the wrong adapter.
  - All direct and proxy traffic gets dropped, breaking connectivity completely.

### 4. Windows Smart Multi-Homed Name Resolution (SMHNR) & DNS Leak Conflicts
* **Root Cause**: Windows 10/11 sends parallel DNS queries across *all* active adapters simultaneously via SMHNR.
* **Symptom**: Even when `strict_route` and DNS hijacking are active, Windows may send DNS requests over physical NICs or secondary interfaces, leading to DNS leaks or sporadic connection resets when proxying domain traffic.

### 5. Stale / Locked Wintun Adapters from Prior Runs
* **Root Cause**: If the process or OS unexpectedly reboots, `wintun.dll` adapter handles can remain locked by Windows system kernel services.
* **Symptom**: Subsequent attempts to initialize TUN mode fail with `adapter name already exists` or `device busy`.

---

## 5. Suggested Solutions & Recommendations

To bring TUN mode to 100% production stability, the following steps are recommended:

1. **UAC Administrator Elevation Verification & UI Prompt**:
   - Add an explicit privilege check (`PlatformUtils.is_admin()`) before enabling TUN mode.
   - If not elevated, present a prompt requesting the user to restart XenRay as Administrator.

2. **Interface Detection Hardening**:
   - Exclude known virtual adapter keywords (`vEthernet`, `VMware`, `VirtualBox`, `WSL`, `Tailscale`, `ZeroTier`, `Loopback`) in `NetworkInterfaceDetector.get_primary_interface()`.
   - Allow users to manually select their physical network adapter in UI Settings as a fallback.

3. **Dynamic Route Refreshing / Socket Mark Routing**:
   - Instead of static IP host routes for CDN domains, periodically re-verify proxy IP resolutions during active sessions or utilize OS socket marking (`fwmark` on Linux, WinDivert/SO_BINDTODEVICE where available).

4. **Pre-Flight Wintun Driver & Adapter Cleanup**:
   - Before starting `SingboxTunService` or `TunInjector`, check for and forcibly remove any leftover `xenray-tun` network adapters from previous crashes using `netsh interface delete interface "xenray-tun"`.
