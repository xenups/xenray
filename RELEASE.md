# Release Process

This document describes how to create a new release of XenRay.

## Prerequisites

- Push access to the repository
- All changes merged to `master` branch
- Updated CHANGELOG.md

## Release Steps

### 1. Update Version

Update `.env` file with new version:
```env
APP_VERSION=x.y.z
```

### 2. Commit Version Changes

```bash
git add .env
git commit -m "chore: bump version to x.y.z"
git push origin master
```

### 3. Create Version Tag

```bash
git tag -a vx.y.z -m "Release vx.y.z"
git push origin vx.y.z
```

This will trigger the GitHub Actions workflow automatically.

### 4. Monitor Build

1. Go to **Actions** tab on GitHub
2. Watch the "Release Build" workflow
3. Ensure all steps complete successfully

### 5. Verify Release

1. Go to **Releases** tab
2. Find the new release `vx.y.z`
3. Download `XenRay-vx.y.z-windows-x64.zip`
4. Extract and test the executable

## What Happens During Release

The GitHub Actions workflow will:

1. ✅ Checkout code
2. ✅ Setup Python 3.12
3. ✅ Install Poetry and dependencies
4. ✅ Download Xray v{XRAY_VERSION} (64-bit, Windows 7+)
5. ✅ Download Singbox v{SINGBOX_VERSION} (64-bit, Windows 7+)
6. ✅ Download Xray geo files (geoip.dat, geosite.dat)
7. ✅ Build city database with translations
8. ✅ Build executable with PyInstaller
9. ✅ Package everything into zip file
10. ✅ Create GitHub release
11. ✅ Upload zip as release asset

## Release Package Contents

```
XenRay-vx.y.z-windows-x64.zip
├── XenRay.exe              # Main application
├── assets/                  # UI resources
│   ├── locales/            # Translations (en, fa, ru, zh)
│   ├── flags/              # SVG country flags
│   ├── data/               # City database
│   └── icon.ico            # App icon
├── bin/                    # Binaries
│   ├── xray.exe           # Xray Core
│   └── sing-box.exe       # Singbox
└── scripts/                # Support scripts
    └── xenray_updater.ps1 # Auto-updater (Windows)
```

## Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality
- **PATCH** version for backwards-compatible bug fixes

## Rollback

If a release has issues:

1. Delete the tag locally and remotely:
   ```bash
   git tag -d vx.y.z
   git push origin :refs/tags/vx.y.z
   ```

2. Delete the GitHub release from the web interface

3. Fix issues and create a new patch release

## Configuration

Binary versions are controlled in `.env`:

```env
XRAY_VERSION=1.8.24          # Latest Windows 7+ compatible
SINGBOX_VERSION=1.10.6       # Latest Windows 7+ compatible
ARCH=64                      # 64-bit only for now
```

To update to newer binaries, update these values and create a new release.

## Troubleshooting

### Build Fails

Check the Actions log for errors. Common issues:
- Missing dependencies
- Network issues downloading binaries
- PyInstaller build errors

### Binary Download Fails

- Verify versions exist on GitHub releases
- Check if download URLs are correct
- Ensure versions are Windows 7+ compatible

### Package Too Large

- Ensure `bin/` directory only contains required executables
- Check if any temp files are being included
- Verify `--onefile` mode if needed
