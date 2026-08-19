# Changelog

All notable changes to XenRay will be documented in this file.

## [0.3.1] - 2026-08-19

### Added
- **OS Abstraction Layer** (`src/platform/`): a clean cross-platform contract isolating the app from the operating system.
  - `interfaces/` — typed ABC/`Protocol` contracts: `INetworkAdapter`, `ITunDnsConfigurator`, `IFirewallAdapter`, `ISystemSettingsAdapter`, `IProcessAdapter`.
  - `windows/` — one file per component (network, tun_dns, firewall, settings, process); all ctypes / winreg / netsh / PowerShell / IP Helper code lives behind the interfaces.
  - `posix/` — no-op / minimal stubs for Linux & macOS so the app imports and runs without Windows-only dependencies.
  - `factory.py` — single entry point (`get_network_adapter()`, `get_tun_dns_configurator()`, `get_firewall_adapter()`, ...) so business logic never touches the OS directly.
- **Type-safe platform enums** (`src/platform/enums.py`): `PlatformType` (WINDOWS/MACOS/LINUX) and `ArchType` — str-based so legacy string comparisons stay valid while new code is enum-safe.
- **Zero platform-awareness in business logic**: services, controllers, orchestrators and UI route OS calls exclusively through the factory and interfaces.
- **SNI Spoofing transparent TCP relay**: raw packet capture/injection via WinDivert (Windows) with a wrong-sequence SNI-spoof engine, wired into connection teardown with fail-safe relays.
- **TUN DNS service**: NRPT rules + TUN-adapter DNS + SMHR registry state, fully behind `ITunDnsConfigurator`.
- **SOCKS/HTTP inbounds bind to `0.0.0.0`** for LAN proxy sharing (was `127.0.0.1`).

### Changed
- **PlatformUtils → pure system-metadata container**: DNS, SMHR, subprocess flags/startupinfo and physical-NIC discovery moved into the platform adapters with the real OS code (IP Helper `GetAdaptersAddresses`, winreg, netsh).
- **`WindowsTunDnsManager` → `TunDnsService`**: no Windows-prefixed class name leaks into the business layer; OS adapters resolve lazily so non-Windows test runners behave deterministically.
- **Connection button redesign**: bolder solid/glass lilac core with a soft lilac gradient, a per-state rotating neon sweep ring (connecting=amber, connected=purple/cyan, disconnected=faint), and a blurred radial glow (purple→cyan) behind the disc. The hard neon ring pulse of earlier builds became a soft cloud fade that breathes with traffic.
- **Sidebar-aware centered layout** and ultra-light, airy config-name typography on the dashboard hero.
- **CI / code quality**: standard `isort` config (`src_paths`, `known_first_party`) for the Linux runner; all `flake8`/`black`/`isort` gates green.

### Fixed
- **Cross-platform test flakiness**: `TunDnsService` and `LanSharingCard` now resolve OS adapters lazily so the Windows TUN-DNS and LAN-badge tests pass deterministically on the Linux CI runner.
- **`BrokenPipeError` in the relay main loop**: a peer socket closing (Linux `EPIPE`) is treated as normal relay termination instead of crashing the task; each test direction uses its own socketpair.
- **`WaveVisualizer` init & `dispose` guard** on the dashboard page.
- **Dependency updates** (dependabot) landed cleanly against the test suite.

### Technical
- Test suite grown to **950 passing** (up from 633 in 0.3.0-beta) with flake8/black/isort clean.

## [0.3.0-beta] - 2026-08-12

### Added
- **Native GPU Neon Sweep Animations**: Config cards and the main Connect button now render a thin neon border trace via Flet's `animate_rotation` (60 FPS on the GPU) during ping/inspection.
  - Instant frame-0 start (baseline arming on `did_mount` + frame-flush before the first nudge).
  - Opaque mask layer keeps the gradient confined to a thin outer ring (no solid radar wedge).
  - Mask/disc hidden post-ping so buttons keep their native colors.
  - Only the 3 servers actively inside the inspection Semaphore animate at once.
- **Ping "Stop" Toggle**: The Ping All header button now switches to "Stop Ping" while a batch runs; clicking it cancels all in-flight inspection tasks (master-task cancellation), releases the worker/semaphore immediately, and allows an instant new Ping All.
- **Auto-Inspection Threshold**: Subscriptions/batches larger than 20 servers skip automatic pinging (stay idle) — pings only run on manual trigger.
- **Strict Batch Concurrency**: Inspections run through `asyncio.Semaphore(3)` — never more than 3 Xray/socket runners at once.
- **Interactive Update Modal** (`UpdateDialog`): version comparison (`v2.4.0 -> v2.5.0`), release-notes area, in-place live `ProgressBar`, and Update Now / Remind Later / Cancel buttons. Update button now shows a notification when up to date and opens the modal when an update is available.
- **File-Lock-Safe Xray Core Extraction**: kills active `xray.exe` before replacing, safely renames locked binaries to `.old`, and rolls back on failure.
- **Search by Country**: Search now matches `country_name`, `country_code`, and the localized country name (e.g. Persian `فنلاند` for FI) via pycountry.
- **In-Memory Latency Sorting**: "Sort by Ping" reads freshly resolved in-memory latency (never stale disk values); uninspected/timeout servers sort to the bottom.
- **Traffic Metrics Zero-Reset on Disconnect**: Download/Upload badges reset to `0 B/s` in place when the FSM reaches DISCONNECTED/STOPPING/ERROR, and the stats buffer is flushed.
- **`PINGING` FSM State**: Pre-connection latency check registered in the connection FSM, with clean `PINGING -> CONNECTING` interruption.

### Changed
- **Add-Server Modal Isolation**: The Add modal is now a custom in-page Stack overlay (`AddServerModalContainer`) — opening/closing it never touches the server list or `page._dialogs`.
- **Chunked List Rendering**: Large subscriptions (1000+ servers) render the first 30 cards instantly and append the rest in background micro-chunks — no more UI freeze or dataclass crash.
- **Zero Per-Card EventBus Subscribers**: Cards no longer subscribe to `server_inspecting`/`server_inspected`; the ServerList is the single subscriber and delegates via `_item_map` (was 2000+ subscribers for a 1000-server list).
- **New Servers Insert at Top**: Adding a server places its card at index 0 (in place, no re-render).
- **Toast Pipeline**: `ToastManager` now renders into a persistent isolated top-center overlay layer (fixes toasts being silently dropped); settings toasts dispatch through exactly one path (no double toasts).
- **Blocking DNS Off The Event Loop**: `resolve_server_ip` is non-blocking; DNS resolves in a background thread and refreshes the display.
- **Ping Results Stay In-Memory**: Latency is no longer written to `profiles.json` on every ping (avoids `profiles.json.tmp` PermissionError); `atomic_write` is protected by a thread lock.
- **"Revving Up" Emitted Once**: A single engine `connecting` event now drives exactly one PREPARING state transition (previously 3 duplicate dispatches).

### Fixed
- **FSM Warning**: `disconnected -> stopping` no longer logs a blocked-transition warning (defensive disconnect flow accepted).
- **`PermissionError [Errno 13]`**: Concurrent batch-ping disk writes and `xray.exe` replacement no longer collide on Windows file locks.
- **Headless CI**: `pystray`/Xlib are lazily imported (fixes `Xlib.error.DisplayNameError` during test collection).
- **Missing Import**: `ServerListItem` import in the server-list subscription mixin.
- **Flet 0.86 syntax**: `ft.Border.all` / `ft.BoxFit.CONTAIN` fixes across components.

### Performance & Architecture
- **SRP Refactors**: `settings_drawer.py` (854 → ~300 lines) split into a `SettingsHandler` + `sections/` package; `server_list.py` (829 → ~200 lines) split into single-responsibility mixins (loader, sort, events, latency, subscriptions, chains, actions).
- **No `page.update()` for Local Changes**: 24 global `page.update()` calls reduced to 12 (only bootstrap/window/theme); local state changes use targeted `control.update()`.
- **Removed Diagnostic Stack-Trace Logging** from the server list loader (single-line logs only).

### Technical
- 633 unit tests passing.
- `black --check src tests` clean.

## [0.2.5-beta] - 2026-08-06

### Changed
- **Version Bump**: Updated application version across project to `0.2.5-beta`.
- **Flet v0.86.1 Window Controller & Taskbar Icon**:
  - Registered explicit Windows AppUserModelID (`xenray.desktop.client.v1`) before Flet app initialization for native process icon grouping.
  - Resolved absolute icon file paths for both development and compiled PyInstaller (`sys._MEIPASS`) environments via `get_absolute_icon_path()`.

## [0.2.2-beta] - 2026-07-31

### Added
- **TLS Cipher Suites Support**: Custom cipherSuites for TLS/REALITY connections
  - Extract `cs`/`cipherSuites` query param from VLESS/VMess/Trojan/Hysteria2 links
  - Inject into `tlsSettings`/`realitySettings` as colon-separated string
  - Global default cipherSuites via settings repository with runtime fallback
- **`unsafe` Fingerprint Support**: Recognized as valid fingerprint value (disables uTLS, plain Go TLS)
- **xHTTP `extra` Object**: Strict Xray-core v26.7.28 compliance for xhttpSettings
  - Advanced params (`noSSEHeader`, `downloadProxy`, `xPaddingBytes`, `scMax*`, `headers`, `xmux`) nested inside `extra` dict
  - Root level: only `host`, `path`, `mode`
  - Auto-migration of legacy root-level fields into `extra`
  - Share links encode `extra` as single JSON param, maintain round-trip fidelity
- **New XHTTP Query Params**: `downloadProxy`, `uplinkHTTPMethod`, `downlinkHTTPMethod`, `scMaxEachGetBytes`, `scMinPostsIntervalMs`
- **Share Link `fp` Round-trip**: VMess generator now includes `fingerprint` in output

### Changed
- **Connectivity Verification**: Consolidated dual verification into single pass
  - VPN mode now uses existing SOCKS proxy instead of spawning second Xray
  - Connection tester warm-up increased 0.5s → 2.5s
  - `check_proxy_connectivity` timeout reduced 5s → 2.5s, no retries on dead URLs
- **xHTTP Link Encoding**: `cs` (not `cipherSuites`) used as share-link query key (v2rayN/v2rayNG convention)
- **Flet Clipboard API**: `page.set_clipboard()` → `page.run_task(page.clipboard.set, ...)` for API compatibility
- **i18n**: Added cipherSuites translations for zh/ru/fa locales
- **Version bumped**: 0.1.18-beta → 0.2.2-beta

### Cleaned Up
- **Dead Code Removal**: Removed 10 unused functions/methods:
  - `validators.py`: `validate_port`, `validate_profile_name`, `validate_profile_config`
  - `xray_config_processor.py`: `validate_config`, `_add_outbound_dns_entries`, `_resolve_outbound_addresses`
  - `settings_repository.py`: `get_custom_dns`, `set_custom_dns`, `get_startup_enabled`
  - `country_flags.py`: `get_country_from_ip`
- **Unused variables**: Fixed 7 unused variables (`app_context`, `reg_msg`, `i`, `profile_id`, `name`, `msg`)
- **Settings UI Row**: Removed cipherSuites input row from settings drawer (backend kept)

### Fixed
- **ImportError**: `DEFAULT_NETWORK` missing from constants import in `legacy_config_service.py` — now 351 tests passing
- **Deprecated Splithttp**: Auto-migrated to xhttp in link parser, config patcher, and legacy service

## [0.2.1-beta] - 2026-07-22

### Fixed
- **WinTUN DLL Download**: Fixed duplicate download issue for `wintun.dll`
- **Unicode Encoding**: Fixed `charmap` codec error on Windows for non-ASCII characters

## [0.2.0-beta] - 2026-07-22

### Added
- **Xray TUN Mode**: Full Xray-based TUN implementation replacing Sing-box
  - Removed Sing-box TUN (singbox no longer maintained)
  - Xray native TUN with proper routing rules
  - Direct IP/domain bypass rules
  - DNS configuration for TUN interface

### Changed
- **Sing-box Removal**: All Sing-box TUN code and tests removed
- **Core Engine**: Xray is now the single core engine for both proxy and VPN modes

### Technical
- Updated all mocks and tests for Xray-only architecture
- Cleaned up Sing-box service module completely

## [0.1.17-beta] - 2026-07-22

### Added
- **Xray Installation Service**: Automatic download and installation of Xray core
  - Version detection and comparison
  - Platform-specific binary paths
  - UI integration for installation progress

## [0.1.16-alpha] - 2026-07-21

### Added
- **Connection Orchestrator**: Centralized workflow for connection establishment, health verification, and teardown
- **Latency Tester**: Per-server latency testing with geo-location data
- **Server List UI**: Individual server cards with ping display, share, and delete actions
- **Core Configuration Module**: Centralized constants and configuration management

## [0.1.15-alpha] - 2026-07-21

### Changed
- **Flet Desktop Mode**: Migrated to Flet desktop runtime for native window management
- **Dependency Lock**: Updated Poetry lock file

## [0.1.14-alpha] - 2026-07-21

### Changed
- **Flet Upgrade**: Upgraded to latest Flet version with breaking API changes
- **Code Formatting**: Full reformat with updated linter rules

## [0.1.12-alpha] - 2026-07-20

### Added
- **Core Upgrade**: Updated Xray and Sing-box to latest versions
- **DNS Fixes**: Proper DNS configuration for TUN mode, fixed auto-injecting default values

### Fixed
- **Lint & Format**: CI/CD code quality fixes across multiple files

## [0.1.11-alpha] - 2026-02-25

### Fixed
- **Xray Bugs**: Various bug fixes for Xray core integration
- **Code Quality**: Linting and formatting fixes across codebase

## [0.1.10-alpha] - 2025-12-28

### Added
- **Signal-Based Monitoring Architecture**: Complete refactor of connection monitoring
  - `MonitorSignal` enum - monitors emit facts, not events
  - `ConnectionManager` is now the single event authority
  - Session-scoped lifecycle prevents stale events after disconnect
- **Auto-Reconnect**: Automatic connection recovery with hybrid detection
  - Passive log monitoring for Xray error patterns
  - Active traffic stall detection with Clash API metrics
  - Smart warmup handling for xhttp/splithttp transports
- **Battery Saver Mode**: Optional toggle to disable monitoring and save resources
- **Startup on Boot**: Windows Task Scheduler integration for auto-start
- **Self-Contained Settings Components**: `StartupToggleRow`, `AutoReconnectToggleRow`

### Changed
- **ConnectionMonitoringService**: Now creates its own dependencies internally
  - Simplified ConnectionManager init from ~70 to ~40 lines
  - Single `on_signal` callback replaces multiple callbacks
- **ConnectionOrchestrator**: Removed unused `observer` and `log_monitor` parameters
  - Monitoring now handled entirely by ConnectionMonitoringService
- **Settings Drawer**: Extracted toggle components for better maintainability

### Technical
- New `services/monitoring/` subpackage with:
  - `signals.py` - MonitorSignal enum
  - `service.py` - ConnectionMonitoringService facade
  - `passive_log_monitor.py` - Log-based failure detection
  - `active_connectivity_monitor.py` - Traffic stall detection
  - `auto_reconnect_service.py` - Reconnection handling
- Removed 50+ lines of dead code from settings_drawer.py
- All 140 tests passing

## [0.1.9-alpha] - 2025-12-21

### Added
- **CI/CD Code Quality Pipeline**: Automated GitHub Actions workflow for code quality enforcement
  - Black formatting checks
  - isort import sorting validation
  - Flake8 linting with max line length 120
- **Pre-commit Hooks**: Local git hooks for automatic code quality checks before commits
- **Code Quality Documentation**: Comprehensive guide in `docs/CODE_QUALITY.md`
- **Setup Scripts**: PowerShell and Bash scripts for easy code quality tools setup

### Changed
- **Test Coverage Expansion**: Significantly improved test coverage for core modules
  - `LinkParser`: 88% coverage (25 tests)
  - `SingboxService`: 83% coverage (15 tests)
  - `ConfigManager`: 73% coverage (22 tests)
- **Code Formatting**: All source and test files formatted with Black and isort
- **Import Organization**: Consistent import ordering across the entire codebase

### Fixed
- **Path Traversal Vulnerability**: Fixed security issue in ConfigManager path validation
- **Route Cleanup Robustness**: Enhanced SingboxService route cleanup with proper exception handling
- **CLI Bug**: Fixed incorrect LinkParser method call in CLI connect command
- **Missing Imports**: Added missing i18n translation imports in connection modules

### Technical
- Added `pytest-cov`, `isort`, `flake8`, and `pre-commit` to dev dependencies
- Configured Black, isort, and pytest in `pyproject.toml`
- Created `.flake8` configuration file
- All 62 tests passing with 0 linting errors

## [0.1.8-alpha] - 2025-12-20

### Added
- **Smart MTU Detection**: Automatically detects optional MTU for network stability (Auto/QUIC Safe modes)
- **Refined QUIC Logic**: Strictly enforces 1420 MTU only for proper QUIC transports (h3, quic, xhttp, splithttp)
- **Robust ALPN Check**: Detects h3 in TLS/Reality settings regardless of network label

### Fixed
- **PlatformUtils Error**: Fixed `NameError` preventing connection on some systems
- **Toast Notifications**: Fixed Z-order issue where toasts appeared behind drawers
- **Log System**: Reverted experimental log segregation features to restore stability

## [0.1.7-alpha] - 2025-12-20


### Added
- **UI Redesign**: Complete "Apple Glass" overhaul with glassmorphism, dynamic connection status glow, and professional animations
- **System Tray**: Full integration with background running, taskbar controls, and improved lifecycle
- **Internationalization**: Complete support for English, Persian, Russian, and Chinese across all menus/toasts

### Changed
- **Core Updates**: Updated Sing-box to v1.12.13 and Xray to v25.12.8
- **Startup**: Improved window centering and minimized startup flash
- **Toasts**: Replaced SnackBars with unified multilingual toast system
- **Executable**: Optimized build size (reduced by ~30 MB)
- **Update Logic**: Improved semantic version comparison and avoided redundant downloads

### Fixed
- **Stealth Mode**: Completely hidden black console windows (CMD/PowerShell) for all subprocesses
- **Connectivity**: Fixed internet connection/gateway detection and binary path resolution
- **Build System**: Fixed PyInstaller bundling for PyCountry and GeoIP file locations
- **Assets**: Restored Geo file downloads and fixed Network Stats opacity error

## [0.1.6-alpha] - 2025-12-12

### Added
- **Multi-config input**: Paste multiple server configs (vless://, vmess://, trojan://, ss://, hysteria2://) separated by newlines in Add Server dialog - all valid configs are added automatically with count feedback
- **VLESS encryption support**: Enhanced link parser with full VLESS Reality, XTLS, and encryption protocol support
- **Routing management page**: New "General" tab with toggles for Block UDP 443 (QUIC), Block Ads, Direct Private IPs, and Direct Local Domains
- **Comprehensive flag colors**: 180+ country codes with flag-based gradient colors for server card
- **Glass-themed server card**: Apple-like appearance with country-based gradient colors
- **App update service**: Check and download application updates from GitHub releases
- **PowerShell updater script**: Automated update installer for Windows (`scripts/xenray_updater.ps1`)
- **Linux build support**: AppImage build script and comprehensive Linux build guide
- **macOS build support**: DMG creation script and macOS build documentation
- **Platform utilities**: Enhanced platform detection and system integration

### Changed
- **Default connection mode**: First-time startup now defaults to VPN mode instead of Proxy mode
- **Default proxy port**: Changed from 10808 to 10805 to avoid conflicts with v2rayN
- **Port migration**: Automatic migration for users with old 10808 port setting
- **Routing tab renamed**: "Quick Settings" → "General" (shorter, cleaner)
- **Status fonts improved**: Country name 16→18px, status text 12→13px for better readability
- **Settings drawer enhanced**: Added app update checker with version display
- **Connection tester improved**: Better latency testing with geo-location support
- **Singbox service enhanced**: Improved routing rules and platform-specific configurations
- **Translation updates**: Added translations for update feature, routing toggles in EN/FA/ZH/RU

### Fixed
- **Status animation removed**: Cleaned up status display - no more animated dots, just clean text
- **Translation dots removed**: Removed static `...` from "Verifying" and "Checking" that were duplicating
- **Config manager cleanup**: Improved file handling and error recovery
- **UI component fixes**: Various fixes for server list, settings, and connection button

### Technical
- Code formatting with Black
- Import organization with isort
- Enhanced error handling across services
- Better process management utilities

---

## [0.1.5-alpha] - Previous Release

Initial alpha release with core VPN/Proxy functionality.
