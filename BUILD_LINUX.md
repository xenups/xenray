# Linux Build and Distribution Guide

This guide covers building, packaging, and distributing XenRay for Linux.

## Prerequisites

### Required

- **Linux** (Ubuntu 20.04+, Debian 11+, Fedora 35+, Arch, etc.)
- **Python 3.10-3.13**
- **Poetry**: Package manager
  ```bash
  curl -sSL https://install.python-poetry.org | python3 -
  ```

### Optional (for AppImage)

- **appimagetool**: For creating AppImage (downloaded automatically)
- **ImageMagick**: For icon conversion
  ```bash
  # Ubuntu/Debian
  sudo apt install imagemagick
  
  # Fedora
  sudo dnf install ImageMagick
  
  # Arch
  sudo pacman -S imagemagick
  ```

## Building for Linux

### 1. Install Dependencies

```bash
# Clone the repository
cd xenray

# Install system dependencies (Ubuntu/Debian)
sudo apt install python3-pip python3-dev build-essential

# Install Python dependencies
poetry install

# Activate virtual environment
poetry shell
```

### 2. Download Platform Binaries

Download Linux versions of Xray and Sing-box:

**For x86_64:**
```bash
mkdir -p bin/linux-x86_64

# Download Xray
curl -L -o xray.zip \
  https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip
unzip xray.zip -d bin/linux-x86_64/
rm xray.zip
chmod +x bin/linux-x86_64/xray

# Download Sing-box
SINGBOX_VERSION="1.10.6"
curl -L -o singbox.tar.gz \
  https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VERSION}/sing-box-${SINGBOX_VERSION}-linux-amd64.tar.gz
tar -xzf singbox.tar.gz
mv sing-box-*/sing-box bin/linux-x86_64/
rm -rf singbox.tar.gz sing-box-*
chmod +x bin/linux-x86_64/sing-box
```

**For ARM64:**
```bash
mkdir -p bin/linux-arm64

# Download Xray
curl -L -o xray.zip \
  https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-arm64-v8a.zip
unzip xray.zip -d bin/linux-arm64/
rm xray.zip
chmod +x bin/linux-arm64/xray

# Download Sing-box
SINGBOX_VERSION="1.10.6"
curl -L -o singbox.tar.gz \
  https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VERSION}/sing-box-${SINGBOX_VERSION}-linux-arm64.tar.gz
tar -xzf singbox.tar.gz
mv sing-box-*/sing-box bin/linux-arm64/
rm -rf singbox.tar.gz sing-box-*
chmod +x bin/linux-arm64/sing-box
```

### 3. Create Icon

Prepare a PNG icon for Linux:

```bash
# If you have icon.ico, convert it to PNG
convert assets/icon.ico -resize 256x256 assets/icon.png

# Or extract the largest size from ico
convert 'assets/icon.ico[0]' -resize 256x256 assets/icon.png
```

### 4. Build the Application

```bash
poetry run python build_pyinstaller.py
```

This creates `dist/XenRay` executable.

### 5. Test the Build

```bash
# Run the executable
./dist/XenRay

# Or for VPN mode (requires root)
sudo ./dist/XenRay
```

## Creating AppImage

AppImage is the recommended distribution format for Linux - it works on any distro!

### Build AppImage

```bash
chmod +x scripts/build_appimage.sh
./scripts/build_appimage.sh 2.0.0
```

This creates:
- `XenRay-2.0.0-x86_64.AppImage` - Portable application
- `XenRay-2.0.0-x86_64` - Standalone executable
- `XenRay-2.0.0-x86_64.tar.gz` - Tarball package

### Test the AppImage

```bash
# Make it executable
chmod +x XenRay-2.0.0-x86_64.AppImage

# Run it
./XenRay-2.0.0-x86_64.AppImage

# For VPN mode
sudo ./XenRay-2.0.0-x86_64.AppImage
```

### Install AppImage System-Wide

```bash
# Option 1: Move to /usr/local/bin
sudo mv XenRay-2.0.0-x86_64.AppImage /usr/local/bin/xenray

# Option 2: Create desktop entry
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/xenray.desktop << EOF
[Desktop Entry]
Name=XenRay
Comment=Xray VPN Client
Exec=/path/to/XenRay-2.0.0-x86_64.AppImage
Icon=xenray
Type=Application
Categories=Network;Security;
Terminal=false
EOF
```

## Creating DEB Package (Debian/Ubuntu)

### 1. Install dpkg tools

```bash
sudo apt install dpkg-dev fakeroot
```

### 2. Create package structure

```bash
mkdir -p xenray-deb/DEBIAN
mkdir -p xenray-deb/usr/bin
mkdir -p xenray-deb/usr/share/applications
mkdir -p xenray-deb/usr/share/icons/hicolor/256x256/apps
mkdir -p xenray-deb/usr/share/doc/xenray

# Copy files
cp dist/XenRay xenray-deb/usr/bin/
cp -r dist/assets xenray-deb/usr/bin/
cp -r dist/bin xenray-deb/usr/bin/

# Desktop entry
cp scripts/xenray.desktop xenray-deb/usr/share/applications/

# Icon
cp assets/icon.png xenray-deb/usr/share/icons/hicolor/256x256/apps/xenray.png
```

### 3. Create control file

```bash
cat > xenray-deb/DEBIAN/control << EOF
Package: xenray
Version: 2.0.0
Section: net
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.10)
Maintainer: Your Name <your@email.com>
Description: Xray VPN Client
 A simple and powerful Xray VPN client for Linux.
 Supports both proxy mode and VPN mode with TUN interface.
EOF
```

### 4. Build DEB

```bash
dpkg-deb --build xenray-deb
mv xenray-deb.deb xenray_2.0.0_amd64.deb
```

### 5. Install DEB

```bash
sudo dpkg -i xenray_2.0.0_amd64.deb
```

## Creating RPM Package (Fedora/RHEL)

### 1. Install rpmbuild tools

```bash
sudo dnf install rpm-build rpmdevtools
```

### 2. Create RPM structure

```bash
rpmdev-setuptree
```

### 3. Create spec file

```bash
cat > ~/rpmbuild/SPECS/xenray.spec << EOF
Name:           xenray
Version:        2.0.0
Release:        1%{?dist}
Summary:        Xray VPN Client

License:        AGPL-3.0-or-later
URL:            https://github.com/xenups/xenray
Source0:        %{name}-%{version}.tar.gz

Requires:       python3 >= 3.10

%description
A simple and powerful Xray VPN client for Linux.
Supports both proxy mode and VPN mode with TUN interface.

%prep
%setup -q

%build

%install
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/256x256/apps

cp dist/XenRay %{buildroot}/usr/bin/
cp -r dist/assets %{buildroot}/usr/bin/
cp -r dist/bin %{buildroot}/usr/bin/
cp scripts/xenray.desktop %{buildroot}/usr/share/applications/
cp assets/icon.png %{buildroot}/usr/share/icons/hicolor/256x256/apps/xenray.png

%files
/usr/bin/XenRay
/usr/bin/assets
/usr/bin/bin
/usr/share/applications/xenray.desktop
/usr/share/icons/hicolor/256x256/apps/xenray.png

%changelog
* $(date +'%a %b %d %Y') Your Name <your@email.com> - 2.0.0-1
- Initial package
EOF
```

### 4. Build RPM

```bash
rpmbuild -ba ~/rpmbuild/SPECS/xenray.spec
```

## Running XenRay on Linux

### Proxy Mode (No Root Required)

```bash
./XenRay
# or
xenray  # if installed system-wide
```

### VPN Mode (Requires Root)

VPN mode uses TUN interfaces which require root privileges:

```bash
sudo ./XenRay
# or
sudo xenray  # if installed system-wide
```

## System Integration

### Create systemd Service (for VPN mode auto-start)

```bash
sudo nano /etc/systemd/system/xenray.service
```

```ini
[Unit]
Description=XenRay VPN Client
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/xenray
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable xenray
sudo systemctl start xenray
```

### Desktop Integration

The AppImage and DEB/RPM packages automatically integrate with the desktop environment. You can find XenRay in your application menu under "Network" or "Internet".

## Troubleshooting

### "Permission denied" when running

Make the file executable:
```bash
chmod +x XenRay-2.0.0-x86_64.AppImage
# or
chmod +x dist/XenRay
```

### TUN interface creation fails

VPN mode requires root privileges:
```bash
sudo ./XenRay-2.0.0-x86_64.AppImage
```

### Missing dependencies

Install required system libraries:
```bash
# Ubuntu/Debian
sudo apt install libgl1-mesa-glx libx11-6 libxext6

# Fedora
sudo dnf install mesa-libGL libX11 libXext

# Arch
sudo pacman -S mesa libx11 libxext
```

### AppImage won't run

Try extracting and running directly:
```bash
./XenRay-2.0.0-x86_64.AppImage --appimage-extract
cd squashfs-root
./AppRun
```

### Logs Location

Check logs for debugging:
```bash
# Application logs
tail -f /tmp/xenray/xenray_app.log

# Xray logs
tail -f /tmp/xenray/xenray_xray.log

# Sing-box logs
tail -f /tmp/xenray/xenray_singbox.log
```

## Distribution Checklist

- [ ] Build executable with PyInstaller
- [ ] Create icon.png from icon.ico
- [ ] Build AppImage for x86_64
- [ ] Build AppImage for ARM64 (if needed)
- [ ] Create DEB package (optional)
- [ ] Create RPM package (optional)
- [ ] Test on Ubuntu/Debian
- [ ] Test on Fedora/RHEL
- [ ] Test on Arch Linux
- [ ] Upload to GitHub Releases

## Multi-Architecture Support

### Building for Different Architectures

**x86_64 (Intel/AMD):**
```bash
./scripts/build_appimage.sh 2.0.0
```

**ARM64 (Raspberry Pi, ARM servers):**
```bash
# Must be run on ARM64 hardware
./scripts/build_appimage.sh 2.0.0
```

### Cross-Compilation

For cross-architecture builds, use Docker:

```bash
# Build for ARM64 on x86_64
docker run --rm -v $(pwd):/work -w /work \
  arm64v8/python:3.11 \
  bash -c "pip install poetry && poetry install && poetry run python build_pyinstaller.py"
```

## Quick Start

```bash
# 1. Install dependencies
poetry install

# 2. Download Linux binaries (see above)

# 3. Create icon
convert assets/icon.ico -resize 256x256 assets/icon.png

# 4. Build
python build_pyinstaller.py

# 5. Create AppImage
./scripts/build_appimage.sh 2.0.0

# 6. Run
./XenRay-2.0.0-x86_64.AppImage
```

That's it! You now have a portable Linux application.
