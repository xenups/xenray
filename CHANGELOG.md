# Changelog

All notable changes to XenRay will be documented in this file.

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
