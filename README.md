# 🌌 XenRay

A modern, high-performance Xray GUI & CLI client for Windows and Linux. XenRay focuses on visual excellence, simplicity, and a premium VPN experience.

![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)
![Coverage](https://img.shields.io/badge/coverage-80%25-yellowgreen.svg)
![RAM](https://img.shields.io/badge/RAM-~130MB%20(GUI)%20%7C%20~30MB%20(CLI)-blueviolet)

---

## ✨ Features

### 🚀 Performance & Architecture
- **Unified Engine**: Single executable for both **GUI** and **Headless CLI** modes.
- **Extreme RAM Optimization**: GUI footprint reduced to ~130MB; CLI mode runs at a lean **~30MB**.
- **Connection Orchestrator**: Decoupled `ConnectionOrchestrator` layer coordinating core processes, TUN adapter injection, and system DNS management.
- **Lazy Load Architecture**: Core frameworks (like Flet) are only loaded when the UI is requested.
- **DI Lifecycle Management**: Production-grade dependency injection with zero memory leaks.
- **Signal-Based Monitoring**: Clean separation - monitors emit facts, ConnectionManager decides actions.

### 🌍 Connection & Visuals
- **🚩 Global Flags**: Automatic country flag emojis for all servers.
- **📍 Smart GeoIP**: Real-time detection of server **Country** and **City**.
- **⚡ Unified Ping**: Concurrent batch testing with visual latency feedback.
- **🎨 Apple Glass UI**: Modern glassmorphism design with dynamic connection status glow.
- **🔐 Dual Mode**: Intelligent switching between **VPN** (TUN) and **Proxy** (SOCKS5/HTTP) modes.
- **📡 LAN Proxy Sharing**: Share proxy connections across local network devices with automatic Windows Firewall rule configuration and local IP detection.
- **🖼️ Native Window & Taskbar**: Explicit AppUserModelID registration and Flet 0.86+ window icon isolation on Windows.
- **🔄 Auto-Reconnect**: Automatic connection recovery with hybrid detection (log + traffic analysis).
- **🔋 Battery Saver**: Optional monitoring toggle to disable auto-reconnect and save resources.

### 🛠️ Management
- **📥 One-Click Import**: Support for VLESS, VMess, Trojan, ShadowSocks, and Hysteria2.
- **🔄 State Adoption**: CLI automatically detects and manages connections started by the GUI (and vice versa).
- **📝 Real-time Diagnostics**: Live log streaming with passive log monitoring and automatic console hiding.
- **⚡ Auto-Updates**: Seamless GitHub integration for updating Xray core and the app.
- **🚀 Startup on Boot**: Optional Windows Task Scheduler integration for auto-start.

---

## 📸 Gallery

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

# Run the GUI
poetry run xenray

# Run the CLI
poetry run xenray list
```

---

## 💻 CLI Usage

XenRay features a powerful, colorized CLI for headless environments.

| Command | Description |
| :--- | :--- |
| `xenray list` | List all profiles with flags and location info |
| `xenray connect [N]` | Connect to profile #N or the default one |
| `xenray ping [N]` | Batch test all profiles or a specific one |
| `xenray disconnect` | Safely terminate the connection |
| `xenray status` | Show real-time connection status |
| `xenray add "LINK"` | Add a server from a share link |

---

## 🛠️ Architecture

XenRay is built with a modular, service-oriented architecture designed for efficiency, maintainability, and cross-platform flexibility.

```text
src/
├── core/
│   ├── container.py               # Dependency Injection (DI) Root
│   ├── config_manager.py          # Profile & settings persistence
│   ├── connection_manager.py      # High-level connection facade (event authority)
│   ├── connection_orchestrator.py # Core service coordinator (Xray, Singbox, DNS, TUN)
│   ├── constants.py               # Centralized configuration & versioning
│   ├── i18n.py                    # Lazy-loaded internationalization
│   └── logger.py                  # Unified logging system
│
├── services/
│   ├── xray_service.py            # Xray core lifecycle management
│   ├── singbox_service.py         # Singbox TUN/Proxy core lifecycle
│   ├── xray_config_processor.py   # Xray JSON configuration builder
│   ├── dns_configurator.py        # System & NRPT DNS rules management
│   ├── tun_injector.py            # Native TUN adapter injection
│   ├── latency_tester.py          # Multi-threaded ping engine
│   ├── connection_tester.py       # Real-world connectivity validation
│   └── monitoring/                # Signal-based monitoring subsystem
│       ├── signals.py             # MonitorSignal enum (facts, not events)
│       ├── service.py             # ConnectionMonitoringService facade
│       ├── passive_log_monitor.py # Log-based failure detection
│       ├── active_connectivity_monitor.py # Traffic stall detection
│       └── auto_reconnect_service.py # Automatic reconnection
│
├── ui/
│   ├── main_window.py             # GUI entry point (Apple Glass UI)
│   ├── builders/                  # Reactive UI builders & layout assemblers
│   ├── components/                # Custom Flet widgets (LAN Sharing, Cards, Dialogs)
│   ├── drawers/                   # Settings & Logs slide-out drawers
│   └── handlers/                  # UI-to-Service event handling
│
├── utils/
│   ├── admin_utils.py             # UAC & Root elevation management
│   ├── firewall_manager.py        # Windows Firewall rule automation
│   ├── network_interface.py       # Local IP & network interface discovery
│   ├── link_parser.py             # VLESS/VMess/Trojan/Hysteria parser
│   ├── process_utils.py           # Cross-platform process management & mutex
│   └── platform_utils.py          # Asset path resolution & OS abstractions
│
└── cli.py                         # High-performance Typer CLI interface
```

### Core Principles
- **Orchestration Layer**: `ConnectionOrchestrator` coordinates core process lifecycles, TUN adapter injection, and system DNS configuration, keeping UI and CLI handlers purely presentational.
- **LAN Proxy Sharing**: Inbounds dynamically bind to `0.0.0.0` when LAN sharing is enabled, paired with automated `FirewallManager` rule provisioning for seamless local network access.
- **Dependency Injection**: Centralized container lifecycle management via `dependency-injector`.
- **Signal-Based Architecture**: Passive log monitors and active traffic probes emit facts (`MonitorSignal`), processed strictly by `ConnectionManager`.
- **Session-Scoped Lifecycle**: All monitoring and background tasks are tied to active connection sessions - eliminating stale events after disconnection.
- **Process & Window Specs**: Windows `AppUserModelID` registered at startup for native OS Taskbar process grouping and icon isolation in Flet 0.86+.

---

## 🧪 Development

### Testing

XenRay maintains high test coverage for core components:

```bash
# Run all tests with coverage
poetry run pytest

# Run specific test file
poetry run pytest tests/test_link_parser.py -v

# Generate HTML coverage report
poetry run pytest --cov=src --cov-report=html
```

### Code Quality

We use automated tools to maintain code quality:

```bash
# Format code with Black
poetry run black src tests

# Sort imports with isort
poetry run isort src tests

# Lint with Flake8
poetry run flake8 src tests --max-line-length=120
```

**Pre-commit Hooks** (Recommended):
```bash
poetry run pre-commit install
poetry run pre-commit run --all-files
```

See [`docs/CODE_QUALITY.md`](docs/CODE_QUALITY.md) for detailed information.

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Run tests and code quality checks
4. Submit a pull request

See [`docs/CODE_QUALITY.md`](docs/CODE_QUALITY.md) for development setup.

---

## ⚖️ License

[AGPL-3.0-or-later](LICENSE)

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/xenups">Xenups</a>
</p>
