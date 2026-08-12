# 🌌 XenRay

A modern, high-performance Xray & Sing-Box GUI / CLI client for Windows and Linux. XenRay focuses on visual excellence, modular software architecture, extreme resource efficiency, and a state-of-the-art VPN experience.

![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)
![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen.svg)
![RAM](https://img.shields.io/badge/RAM-~130MB%20(GUI)%20%7C%20~30MB%20(CLI)-blueviolet)
![Tests](https://img.shields.io/badge/tests-633%20passed-success.svg)

---

## ✨ Features

### ⚡ Zero-Flicker Partial DOM Architecture
- **Incremental List Updates**: Incremental node appends (`append_server_item`), in-place selection border updates, and targeted item removals.
- **Zero Full-Page Re-renders**: Adding, deleting, or selecting server profiles mutates ONLY the target controls in `ListView.controls` without unmounting background elements or flashing the window.
- **Hover & Focus Retention**: Active Flet control references are maintained across all user operations, preventing broken hover states or losing control focus.

### 🎨 Visual Excellence & Next-Gen Components
- **✨ Animated Neon Sweep Border Trace**: Hardware-accelerated rotating neon gradient border (`#A3A8FE` / `#00F2FE`) tracing config cards during background inspection and diagnostics (`animate_rotation`).
- **🛡️ Opaque Donut Masking**: Dual-layer `Stack` layout with a solid `#161922` background mask, allowing GPU-driven continuous rotation without card interior bleed or frame drops.
- **⚡ In-Page Overlay Modals**: Custom Stack layer overlays (Layer 1) for dialogs (`AddServerModalContainer`) that toggle visibility without touching the underlying list (Layer 0) or triggering `page._dialogs` rebuilds.
- **🎨 Glassmorphism & Bento Layouts**: Apple Glass aesthetic with blur effects, dynamic connection status glow, and full-height responsive container layouts.
- **🎛️ Compact Styled Controls**: Refined outlined controls (`ft.OutlinedButton`) with accent borders (`#A3A8FE`), 160x34px compact dimensions, and 12pt typography.

### 🌍 Networking & Protocol Support
- **📥 Protocol Support**: Full link parsing and generation for **VLESS**, **VMess**, **Trojan**, **ShadowSocks**, and **Hysteria2** (including TLS, REALITY, gRPC, WebSocket, XHTTP, and FinalMask transport parameters).
- **🔐 Dual Mode Engine**: Seamless switching between **VPN Mode** (Native WinTUN / TUN adapter injection) and **Proxy Mode** (SOCKS5 / HTTP inbound listeners).
- **📡 LAN Proxy Sharing**: Dynamic inbound binding to `0.0.0.0` paired with automated Windows Firewall rule configuration and local IP discovery.
- **🚩 GeoIP & Latency Diagnostics**: Real-time country flag resolution, city detection, multi-threaded TCP/HTTP latency testing, and one-tap per-card ping re-testing.
- **🔗 Proxy Chaining**: Drag-and-drop proxy chain builder creating multi-hop routing paths through consecutive egress nodes.

### 🚀 Resilience & Engine Core
- **🔄 Finite State Machine (FSM)**: Strict thread-safe state machine managing connection transitions (`DISCONNECTED` → `PREPARING` → `CONNECTED` → `STOPPING`).
- **📡 Signal-Based Health Monitoring**: Fact-based monitoring subsystem (`MonitorSignal`) using passive log analysis and active HTTP traffic probes for silent stall recovery.
- **🔄 Auto-Reconnect Engine**: Configurable recovery pipeline with exponential backoff for recovering broken tunnels.
- **⚡ Bounded Priority Ping Queue**: Deduped queue (`PingManager`) executing import inspections at `PRIORITY_IMPORT` without blocking manual latency checks.

---

## 📸 Screenshots

<p align="center">
  <img src="https://raw.githubusercontent.com/xenups/xenray/refs/heads/main/screenshots/main.png" width="400" alt="Main UI">
  <img src="https://raw.githubusercontent.com/xenups/xenray/refs/heads/main/screenshots/settings.png" width="400" alt="Settings">
</p>

---

## 🚀 Getting Started

### Installation (Poetry)

```bash
# Clone the repository
git clone https://github.com/xenups/xenray.git
cd xenray

# Install all dependencies (including CLI)
poetry install --with cli

# Run the GUI application
poetry run xenray

# Run the colorized CLI interface
poetry run xenray list
```

---

## 💻 CLI Usage

XenRay includes a standalone, zero-GUI CLI built with `typer` and `rich` for headless server deployments and terminal enthusiasts.

| Command | Description |
| :--- | :--- |
| `xenray list` | Display all saved profiles with country flags, latency, and status |
| `xenray connect [N]` | Establish connection to profile #N or active default profile |
| `xenray disconnect` | Gracefully terminate active Xray/Singbox core and restore system DNS |
| `xenray status` | Output live connection status, active profile, and traffic telemetry |
| `xenray ping [N]` | Execute multi-threaded latency checks on profiles |
| `xenray add "LINK"` | Import and parse a server profile from a protocol URL |
| `xenray update` | Trigger background core and rule database updates |

---

## 🏗️ Architecture & Software Design

XenRay adopts a clean, layered architecture separating core infrastructure, repositories, business logic, UI components, and presentation handlers.

```text
src/
├── core/
│   ├── app_context.py               # Central Dependency Injection & Singleton Container
│   ├── config_manager.py            # Application settings & environment persistence
│   ├── connection_manager.py        # High-level connection facade & state authority
│   ├── connection_orchestrator.py   # Core coordinator (Core Process, WinTUN, System DNS)
│   ├── constants.py                 # Centralized configuration, ports & versioning
│   ├── event_bus.py                 # Thread-safe Pub/Sub EventBus for decoupled messaging
│   ├── i18n.py                      # Lazy-loaded internationalization engine (EN/FA/ZH)
│   ├── logger.py                    # Loguru logging pipeline with rotation & sanitization
│   ├── startup_warmup_manager.py    # Startup pipeline for zero-latency UI initialization
│   ├── subscription_manager.py      # Background subscription fetcher & cron updater
│   └── fsm/                         # Connection Finite State Machine
│       ├── connection_fsm.py        # FSM state transition coordinator
│       ├── states.py                # FSM state definitions (Disconnected, Preparing, Connected, Stopping)
│       └── events.py                # FSM state transition triggers
│
├── repositories/
│   ├── profile_repository.py        # Atomic JSON persistence for profiles (`get_by_id`)
│   └── file_utils.py                # Thread-safe atomic JSON file operations with locking
│
├── services/
│   ├── xray_service.py              # Xray core binary lifecycle & process supervisor
│   ├── singbox_service.py           # Singbox TUN/Proxy core lifecycle supervisor
│   ├── xray_config_processor.py     # Dynamic JSON config compiler (Outbounds, Rules, Freedom)
│   ├── server_inspector.py          # Background auto-inspection (Ping + GeoIP location)
│   ├── ping_manager.py              # Priority-queued ping queue with bounded concurrency
│   ├── ping_service.py              # Thread-safe ping execution workers
│   ├── dns_configurator.py          # System DNS & Windows NRPT table configurator
│   ├── tun_injector.py              # Native WinTUN adapter injector & routing table modifier
│   ├── latency_tester.py            # Multi-threaded TCP/HTTP ping engine
│   ├── connection_tester.py         # Connectivity & real-world HTTP health verification
│   ├── rule_update_service.py       # GeoIP / Geosite asset database auto-updater
│   └── monitoring/                  # Signal-based Health Monitoring Subsystem
│       ├── signals.py               # Fact-based MonitorSignal definitions
│       ├── service.py               # ConnectionMonitoringService facade
│       ├── passive_log_monitor.py   # Real-time log monitoring (Core crashes, handshake drops)
│       ├── active_connectivity_monitor.py # Periodic HTTP health probe (Traffic stalls)
│       └── auto_reconnect_service.py # Signal-driven auto-reconnection pipeline
│
├── ui/
│   ├── main_window.py               # Main Flet GUI entry point & window frame builder
│   ├── builders/                    # Reactive layout builders
│   │   └── ui_builder.py            # Window branding header, version baseline & splash screen
│   ├── controllers/                 # View Controllers
│   │   ├── dashboard_controller.py  # Dashboard page logic
│   │   ├── settings_controller.py   # Settings drawer/page logic
│   │   ├── navigation_controller.py# Page navigation logic
│   │   ├── logger_controller.py    # Log drawer logic
│   │   ├── routing_controller.py   # Custom routing logic
│   │   └── dns_controller.py       # DNS configuration logic
│   ├── managers/                    # UI Subsystem Managers
│   │   ├── drawer_manager.py        # Navigation drawer coordinator (Settings, Logs)
│   │   └── toast_manager.py         # Non-intrusive floating toast notifications
│   ├── pages/                       # Full-Height View Pages
│   │   ├── dashboard_page.py        # Main connection dashboard
│   │   ├── servers_page.py          # Server list view page
│   │   ├── settings_page.py         # Full-height settings card page
│   │   ├── dns_page.py              # DNS server management page
│   │   ├── routing_page.py          # Routing rule manager page
│   │   ├── statistics_page.py       # Traffic statistics & real-time analytics
│   │   └── chain_builder_page.py    # Egress proxy chain visual editor
│   ├── components/                  # Component Library
│   │   ├── config/                  # ConfigCard component & animated neon sweep trace
│   │   ├── servers/                 # Modularized ServerList & In-Page Stack Modals
│   │   │   ├── server_list.py       # ServerList layout container
│   │   │   ├── server_list_loader.py# Profile loading mixin
│   │   │   ├── server_list_actions.py# Incremental append, select, delete mixin
│   │   │   ├── server_list_events.py# Auto-inspection live update handler mixin
│   │   │   ├── server_list_latency.py# Latency test batch handler mixin
│   │   │   ├── server_list_sort.py   # Sorting mixin (Name, Ping)
│   │   │   ├── server_list_subscriptions.py # Subscription folder navigation mixin
│   │   │   └── server_list_chains.py# Egress chain handling mixin
│   │   ├── dashboard/               # Connection button, status glow & traffic charts
│   │   ├── settings/                # Bento cards & compact outlined update cards
│   │   ├── common/                  # Container, Navbar, Header & PageHeader
│   │   ├── lan/                     # LAN sharing cards & QR code generator
│   │   ├── logs/                    # Log viewer drawer & terminal window
│   │   ├── chain/                   # Chain list item & node rows
│   │   ├── routing/                 # Routing rule items & toggle rows
│   │   ├── dns/                     # DNS server row controls
│   │   └── statistics/              # Stat cards & wave visualization widgets
│   ├── services/                    # UI Navigation & Event Services
│   │   ├── navigation_service.py    # View switcher & modal dialog orchestrator
│   │   └── ui_event_handler.py      # EventBus topic to UI dispatcher
│   └── helpers/                     # UI Helper Utilities
│       └── gradient_helper.py       # Country flag color gradient helper
│
├── utils/
│   ├── admin_utils.py               # Windows UAC elevation & privilege detection
│   ├── firewall_manager.py          # Windows Firewall rule automation
│   ├── link_parser.py               # Strict protocol link parser (VLESS/VMess/Trojan/Hysteria)
│   ├── network_interface.py         # Local IP detection & interface discovery
│   ├── process_utils.py             # Cross-platform process management & mutex locking
│   └── platform_utils.py            # Executable path resolution & asset loading
│
└── cli.py                           # Colorized Typer CLI application entry point
```

### Key Architectural Patterns
1. **Decoupled EventBus Messaging**: Thread-safe publish/subscribe bus (`EventBus`) handles cross-layer communication, eliminating direct coupling between views and core services.
2. **Modular Mixin Composition**: Complex components like `ServerList` are broken down into single-responsibility mixins (`ServerListLoaderMixin`, `ServerListActionsMixin`, `ServerListSortMixin`), maintaining strict maintainability standards.
3. **Canonical Repository Access**: All profile persistence is funneled through `ProfileRepository` with atomic JSON writes and a single canonical accessor (`get_by_id`).
4. **Hardware-Accelerated Control Animations**: Controls requiring high-frequency visual updates (like the neon sweep border trace) delegate rotation to Flutter's native GPU engine (`animate_rotation`), keeping Python event loops unblocked.

---

## 🧪 Development & Quality Assurance

XenRay maintains strict code quality standards backed by an automated unit test suite with **630+ tests**.

```bash
# Run the full pytest test suite
poetry run pytest

# Run tests with detailed verbose output
poetry run pytest -v

# Run specific test module
poetry run pytest tests/test_config_card.py -v

# Generate HTML coverage report
poetry run pytest --cov=src --cov-report=html
```

### Code Formatting & Linting

```bash
# Format code using Black
poetry run black src tests

# Sort imports with isort
poetry run isort src tests

# Check code formatting with Flake8
poetry run flake8 src tests --max-line-length=120
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a clean feature branch (`git checkout -b feature/amazing-feature`)
3. Ensure all tests pass (`poetry run pytest`)
4. Format code using `black` and `isort`
5. Submit a detailed Pull Request

See [`docs/CODE_QUALITY.md`](docs/CODE_QUALITY.md) for full development guidelines.

---

## ⚖️ License

Distributed under the [AGPL-3.0-or-later](LICENSE) License.

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/xenups">Xenups</a>
</p>
