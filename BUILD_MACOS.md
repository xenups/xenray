# macOS Build and Distribution Guide

This guide covers building, packaging, and distributing XenRay for macOS.

## Prerequisites

### Required

- **macOS** 10.13 (High Sierra) or later
- **Xcode Command Line Tools**: `xcode-select --install`
- **Python 3.10-3.13**
- **Poetry**: Package manager
  ```bash
  curl -sSL https://install.python-poetry.org | python3 -
  ```

### Optional (for Distribution)

- **Apple Developer Account** ($99/year) - Required for:
  - Code signing
  - App notarization
  - Distribution outside the App Store

## Building for macOS

### 1. Install Dependencies

```bash
# Clone the repository
cd xenray

# Install Python dependencies
poetry install

# Activate virtual environment
poetry shell
```

### 2. Download Platform Binaries

Download macOS versions of Xray and Sing-box:

**For Intel Macs (x86_64):**
```bash
mkdir -p bin/darwin-x86_64

# Download Xray
curl -L -o xray.zip \
  https://github.com/XTLS/Xray-core/releases/latest/download/Xray-macos-64.zip
unzip xray.zip -d bin/darwin-x86_64/
rm xray.zip

# Download Sing-box
SINGBOX_VERSION="1.10.6"  # Check latest version
curl -L -o singbox.tar.gz \
  https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VERSION}/sing-box-${SINGBOX_VERSION}-darwin-amd64.tar.gz
tar -xzf singbox.tar.gz
mv sing-box-*/sing-box bin/darwin-x86_64/
rm -rf singbox.tar.gz sing-box-*
```

**For Apple Silicon (arm64/M1/M2/M3):**
```bash
mkdir -p bin/darwin-arm64

# Download Xray
curl -L -o xray.zip \
  https://github.com/XTLS/Xray-core/releases/latest/download/Xray-macos-arm64-v8a.zip
unzip xray.zip -d bin/darwin-arm64/
rm xray.zip

# Download Sing-box
SINGBOX_VERSION="1.10.6"
curl -L -o singbox.tar.gz \
  https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VERSION}/sing-box-${SINGBOX_VERSION}-darwin-arm64.tar.gz
tar -xzf singbox.tar.gz
mv sing-box-*/sing-box bin/darwin-arm64/
rm -rf singbox.tar.gz sing-box-*
```

### 3. Create macOS Icon

Convert the Windows `.ico` to macOS `.icns` format:

**Option A: Online Converter**
- Upload `assets/icon.ico` to https://cloudconvert.com/ico-to-icns
- Download and save as `assets/icon.icns`

**Option B: Using iconutil (macOS only)**
```bash
# Create iconset directory
mkdir icon.iconset

# Generate required sizes (you'll need to extract from ico or resize)
sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png
sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32     icon.png --out icon.iconset/icon_32x32.png
sips -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png
sips -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png
sips -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png
sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png

# Create icns file
iconutil -c icns icon.iconset -o assets/icon.icns

# Clean up
rm -rf icon.iconset
```

### 4. Build the Application

```bash
poetry run python build_pyinstaller.py
```

This will create `dist/XenRay.app`.

### 5. Test the Build

```bash
# Test the app
open dist/XenRay.app

# Or run from command line to see logs
./dist/XenRay.app/Contents/MacOS/XenRay
```

## Creating DMG Installer

### 1. Create Custom Background (Optional)

Create a 600x400 PNG image for the DMG background:
```bash
# Save your custom background as
assets/dmg_background.png
```

### 2. Run DMG Build Script

```bash
chmod +x scripts/create_dmg.sh
./scripts/create_dmg.sh 2.0.0
```

This creates `XenRay-2.0.0-macOS.dmg`.

### 3. Test the DMG

```bash
open XenRay-2.0.0-macOS.dmg
```

Drag the app to Applications and test it.

## Code Signing & Notarization

### Prerequisites

- Apple Developer Account
- Developer ID Application certificate installed in Keychain

### 1. Sign the Application

```bash
# Sign the app bundle
codesign --deep --force --sign "Developer ID Application: Your Name (TEAM_ID)" \
  --options runtime \
  --entitlements entitlements.plist \
  dist/XenRay.app

# Verify the signature
codesign --verify --verbose dist/XenRay.app
spctl --assess --verbose dist/XenRay.app
```

### 2. Create Entitlements File

Create `entitlements.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.automation.apple-events</key>
    <true/>
    <key>com.apple.security.network.client</key>
    <true/>
    <key>com.apple.security.network.server</key>
    <true/>
</dict>
</plist>
```

### 3. Notarize the DMG

```bash
# Create a ZIP for notarization
ditto -c -k --keepParent dist/XenRay.app XenRay.zip

# Submit for notarization
xcrun notarytool submit XenRay.zip \
  --apple-id your@email.com \
  --team-id TEAM_ID \
  --password APP_SPECIFIC_PASSWORD \
  --wait

# If successful, staple the ticket
xcrun stapler staple dist/XenRay.app

# Now create the DMG with the stapled app
./scripts/create_dmg.sh 2.0.0
```

## Running with Privileges

### VPN Mode (Requires Admin)

VPN mode uses TUN interfaces which require root privileges:

```bash
# Run with sudo
sudo open -a /Applications/XenRay.app

# Or from command line
sudo ./XenRay.app/Contents/MacOS/XenRay
```

### Proxy Mode (No Admin Required)

Proxy mode works without admin privileges and can be run normally:

```bash
open -a /Applications/XenRay.app
```

## Troubleshooting

### "XenRay.app is damaged and can't be opened"

This happens with unsigned apps. Solutions:

**Option 1: Remove quarantine attribute**
```bash
xattr -cr /Applications/XenRay.app
```

**Option 2: Allow in System Settings**
1. Go to System Settings → Privacy & Security
2. Scroll down to "Security"
3. Click "Open Anyway" next to the blocked app warning

### "Permission denied" when running binaries

Make binaries executable:
```bash
chmod +x dist/XenRay.app/Contents/MacOS/bin/darwin-*/xray
chmod +x dist/XenRay.app/Contents/MacOS/bin/darwin-*/sing-box
```

### TUN interface creation fails

VPN mode requires admin privileges:
```bash
sudo ./XenRay.app/Contents/MacOS/XenRay
```

### Logs Location

Check logs for debugging:
```bash
# Application logs
tail -f ~/Library/Caches/xenray/xenray_app.log

# Xray logs
tail -f ~/Library/Caches/xenray/xenray_xray.log

# Sing-box logs
tail -f ~/Library/Caches/xenray/xenray_singbox.log
```

## Distribution Checklist

- [ ] Build app for both Intel and ARM
- [ ] Create `.icns` icon
- [ ] Sign the application
- [ ] Notarize the application
- [ ] Create DMG installer
- [ ] Test on Intel Mac
- [ ] Test on Apple Silicon Mac
- [ ] Upload to GitHub Releases
- [ ] Update appcast.xml for auto-updater

## Architecture-Specific Builds

### Building Universal Binary (Intel + ARM)

This is advanced and requires building on both architectures, then using `lipo`:

```bash
# Build on Intel Mac
python build_pyinstaller.py
mv dist/XenRay.app dist/XenRay-x86_64.app

# Build on ARM Mac
python build_pyinstaller.py
mv dist/XenRay.app dist/XenRay-arm64.app

# Combine (requires both builds)
lipo -create \
  dist/XenRay-x86_64.app/Contents/MacOS/XenRay \
  dist/XenRay-arm64.app/Contents/MacOS/XenRay \
  -output dist/XenRay.app/Contents/MacOS/XenRay
```

For simplicity, distribute separate builds for each architecture.
