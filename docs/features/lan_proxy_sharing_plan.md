# Feature Plan: LAN Proxy Sharing System (Allow LAN Architecture)

## 1. Executive Summary & Objective

Implement a robust, cross-platform **LAN Proxy Sharing** system in XenRay. When enabled by the user, this feature allows other devices on the same local area network (LAN) — such as mobile phones, Smart TVs, consoles, or other PCs — to route their internet traffic through XenRay's active connection (in both **Proxy** and **TUN/VPN** modes) via local **SOCKS5** and **HTTP** proxy endpoints.

---

## 2. Core Architecture & Engineering Principles

### A. Listen Address Strategy

- **LAN Sharing Disabled (Default):**
  - Inbounds bind exclusively to `127.0.0.1` (Localhost).
  - External network interfaces do **not** accept proxy connections.

- **LAN Sharing Enabled:**
  - Inbounds bind to `0.0.0.0` (All Interfaces / Any IP).
  - Allows incoming connections on the designated SOCKS (`10805`) and HTTP (`10809` or `10806`) ports from private IP subnets:
    - `192.168.0.0/16`
    - `10.0.0.0/8`
    - `172.16.0.0/12`

### B. Core vs TUN Engine Integration Logic

1. **Proxy Mode:**
   - Xray SOCKS (`10805`) & HTTP (`10809`) inbounds listen on `0.0.0.0`.

2. **TUN Mode (Xray Engine):**
   - Xray handles both TUN inbound and SOCKS/HTTP sharing inbounds on `0.0.0.0`.

3. **TUN Mode (Dual-Engine: Xray + sing-box):**
   - **Xray Core** (Proxy Engine) opens SOCKS (`10805`) & HTTP (`10809`) inbounds listening on `0.0.0.0`.
   - **sing-box TUN** captures local OS traffic and routes it to Xray SOCKS (`127.0.0.1:10805`).
   - External LAN devices connect directly to Xray's `0.0.0.0:10805` or `0.0.0.0:10809` **without** entering the sing-box TUN loop.

### C. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Host Machine                             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    XenRay Application                     │   │
│  │                                                           │   │
│  │  ┌─────────────────┐   ┌──────────────────────────────┐  │   │
│  │  │  Settings/UI     │   │   Xray Core                  │  │   │
│  │  │  allow_lan=True  │──▶│   SOCKS5  ─ 0.0.0.0:10805   │  │   │
│  │  │                  │   │   HTTP    ─ 0.0.0.0:10809    │  │   │
│  │  └─────────────────┘   │                               │  │   │
│  │                         │   Outbound ──▶ VPN Server     │  │   │
│  │                         └──────────────────────────────┘  │   │
│  │                                                           │   │
│  │  ┌──────────────────────────────────────────────────────┐ │   │
│  │  │  sing-box TUN (if TUN mode)                          │ │   │
│  │  │  Captures local OS traffic ──▶ 127.0.0.1:10805       │ │   │
│  │  └──────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Windows Firewall Rule: "XenRay Inbound LAN Proxy"       │   │
│  │  Allow TCP Inbound on ports 10805, 10809                  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         ▲                          ▲                     ▲
         │ SOCKS5 :10805            │ HTTP :10809          │
    ┌────┴────┐              ┌──────┴──────┐        ┌─────┴─────┐
    │  Phone  │              │  Smart TV   │        │  Laptop   │
    │ Android │              │             │        │  (Other)  │
    └─────────┘              └─────────────┘        └───────────┘
              LAN Devices (192.168.1.0/24)
```

---

## 3. Windows Firewall Automation Specs

On Windows, binding to `0.0.0.0` is blocked by default by **Windows Defender Firewall** for incoming TCP/UDP traffic on ports `10805` and `10809`.

### Execution Flow

#### 1. Pre-flight Firewall Rule Check

Check if the rule `XenRay Inbound LAN Proxy` exists:

```cmd
netsh advfirewall firewall show rule name="XenRay Inbound LAN Proxy"
```

#### 2. Dynamic Creation (Elevated / PowerShell)

```powershell
New-NetFirewallRule -DisplayName "XenRay Inbound LAN Proxy" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 10805,10809 `
    -Enabled True
```

#### 3. Teardown / State Reset

On application exit or when LAN Sharing is toggled **OFF**, safely disable or remove the firewall rule if created by XenRay:

```powershell
Remove-NetFirewallRule -DisplayName "XenRay Inbound LAN Proxy"
```

### Error Handling

| Scenario | Behavior |
|---|---|
| Rule already exists | Skip creation, log info |
| Elevation denied (UAC rejected) | Show user-friendly error with manual instructions |
| Rule removal fails on exit | Log warning, do not crash |
| Non-Windows platform | Skip firewall automation entirely |

---

## 4. IP Discovery & User Guidance (Network Utils)

Add a helper in `src/utils/network_interface.py` to discover the host's primary local IP address.

### Discovery Logic

1. **Ignore** the following interfaces:
   - Loopback (`127.0.0.1`)
   - TUN/TAP virtual adapters (`SINGTUN`, `xenray-tun`)
   - Docker bridges (`docker0`, `vEthernet`)
   - VirtualBox/VMware host-only adapters

2. **Return** the active LAN IPv4 address (e.g., `192.168.1.15` or `10.57.20.22`).

### Implementation Approach

```python
# Pseudocode — NOT production code
import socket
import psutil  # or netifaces

def get_primary_lan_ip() -> str | None:
    """
    Discover the host's primary LAN IPv4 address.
    Ignores loopback, TUN/TAP, Docker, and virtual adapters.
    Returns the first valid private IPv4 or None.
    """
    IGNORED_PREFIXES = ("lo", "tun", "tap", "docker", "veth", "vEthernet", "SINGTUN", "xenray")
    
    for iface_name, addrs in psutil.net_if_addrs().items():
        if any(iface_name.startswith(prefix) for prefix in IGNORED_PREFIXES):
            continue
        for addr in addrs:
            if addr.family == socket.AF_INET:
                ip = addr.address
                if ip.startswith("127."):
                    continue
                if is_private_ip(ip):
                    return ip
    return None
```

---

## 5. UI / UX Design Specifications

### A. Settings UI (Toggle & Config)

| Property | Value |
|---|---|
| **Setting Name** | `allow_lan` |
| **Type** | `Boolean` |
| **Default** | `False` |
| **UI Element** | Toggle switch |
| **Title (EN)** | "Allow LAN Sharing" |
| **Title (FA)** | "اشتراک‌گذاری در شبکه محلی" |
| **Description (FA)** | "به بقیه دستگاه‌های موجود در شبکه محلی اجازه می‌دهد از پروکسی این سیستم استفاده کنند." |

### B. Active Connection Info Card (LAN Sharing Overlay/Modal or Card)

When connected **AND** LAN Sharing is `True`, display a small helper card:

```
┌───────────────────────────────────────────────┐
│  🌐 LAN Proxy Sharing — Active                │
│                                                │
│  Local IP:     192.168.1.X  (Auto-detected)    │
│  SOCKS5 Port:  10805                           │
│  HTTP Port:    10809                           │
│                                                │
│  ─── Quick Setup Guide ───                     │
│                                                │
│  📱 Telegram:                                  │
│  https://t.me/socks?server=192.168.1.X         │
│                    &port=10805                  │
│                                                │
│  📶 Android/iOS Wi-Fi Proxy:                   │
│  Server: 192.168.1.X                           │
│  Port:   10809                                 │
│  Type:   HTTP                                  │
│                                                │
│  🖥️ Desktop Browser (SOCKS5):                  │
│  Server: 192.168.1.X                           │
│  Port:   10805                                 │
│  Type:   SOCKS5                                │
└───────────────────────────────────────────────┘
```

### C. Connection State Awareness

| State | LAN Card Visibility |
|---|---|
| Disconnected | Hidden |
| Connected + `allow_lan=False` | Hidden |
| Connected + `allow_lan=True` | **Visible** |
| Reconnecting | Hidden (until stable connection) |

---

## 6. Detailed Implementation Checklist for Agent

### Settings Layer

- [ ] `src/core/settings.py`: Add `allow_lan` setting parameter (default: `False`).

### Core Engine Configuration

- [ ] `src/services/xray_config_processor.py`: Update `_ensure_inbounds()` to set `"listen": "0.0.0.0"` if `settings.get_allow_lan()` is `True`, else `"127.0.0.1"`.

### sing-box Integration

- [ ] `src/services/singbox_service.py`: Ensure sing-box route bypass includes system static routes for private LAN ranges (`192.168.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`) to prevent LAN loopbacks when LAN devices send packets.

### Platform Utilities

- [ ] `src/utils/platform_utils.py` / `firewall_manager.py`: Add automated Windows Firewall rule manager:
  - `add_lan_firewall_rule()` — Creates the inbound allow rule (elevated).
  - `remove_lan_firewall_rule()` — Removes the rule on toggle-off or app exit.
  - `check_lan_firewall_rule()` — Checks if the rule already exists.

### Network Utilities

- [ ] `src/utils/network_interface.py`: Implement `get_primary_lan_ip()` to auto-detect the host's LAN IP address.

### UI Layer

- [ ] `src/ui/` (Views & Handlers): Add LAN toggle in Settings view.
- [ ] `src/ui/` (Views & Handlers): Display LAN connection info card on main dashboard when connected and `allow_lan=True`.

---

## 7. Quality Assurance & Verification Criteria

### Functional Tests

- [ ] Verify SOCKS (`10805`) and HTTP (`10809`) bind to `0.0.0.0` when LAN sharing is **ON**.
- [ ] Verify SOCKS and HTTP bind to `127.0.0.1` when LAN sharing is **OFF**.
- [ ] Test connection from a second device (mobile phone or secondary laptop) using SOCKS5 / HTTP settings.
- [ ] Ensure Windows Firewall popup is either handled automatically or clean instructions are provided.
- [ ] Verify zero regressions in TUN/VPN mode for the host machine.

### Edge Cases

- [ ] Toggle LAN sharing ON/OFF rapidly without crash.
- [ ] Enable LAN sharing with no active network connection — graceful handling.
- [ ] Multiple network interfaces present (Wi-Fi + Ethernet) — correct IP displayed.
- [ ] Firewall rule cleanup on unexpected application termination (crash recovery).

### Security Considerations

- [ ] Only private IP ranges should be able to connect (no public internet exposure).
- [ ] Consider optional authentication for SOCKS5 proxy (future enhancement).
- [ ] Log all LAN connection attempts for transparency.

---

## 8. Data Flow Summary

```
LAN Device (Phone/TV/PC)
    │
    │  Connect to 192.168.1.X:10805 (SOCKS5)
    │       or    192.168.1.X:10809 (HTTP Proxy)
    ▼
┌──────────────────────────┐
│  Host Machine NIC        │
│  (192.168.1.X)           │
│  Firewall Rule: ALLOW    │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Xray Core Inbound       │
│  0.0.0.0:10805 (SOCKS5)  │
│  0.0.0.0:10809 (HTTP)    │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Xray Core Outbound      │
│  (VPN/Proxy Protocol)    │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Remote VPN/Proxy Server │
│  (Internet Access)       │
└──────────────────────────┘
```

---

## 9. Future Enhancements (Out of Scope for v1)

- **mDNS/Bonjour auto-discovery**: Allow LAN devices to automatically discover XenRay proxy.
- **QR Code generation**: Generate QR codes for easy mobile device configuration.
- **SOCKS5 authentication**: Optional username/password for LAN proxy access.
- **Per-device access control**: Whitelist/blacklist specific LAN devices by MAC/IP.
- **Bandwidth monitoring**: Show per-device bandwidth usage on the dashboard.
- **UDP relay support**: Extend SOCKS5 UDP associate for gaming/streaming devices.

---

> **Document Version:** 1.0  
> **Last Updated:** 2026-08-05  
> **Status:** Draft — Pending Implementation  
> **Author:** XenRay Development Team
