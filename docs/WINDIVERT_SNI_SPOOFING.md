# WinDivert / SNI Spoofing — Driver & Bundle Requirements

## What you need
SNI spoofing uses **pydivert** → the **WinDivert** user-mode DLL + **kernel driver**.

| File | Purpose | Where it ships |
|---|---|---|
| `WinDivert64.dll` | user-mode packet capture/injection | bundled inside the `pydivert` wheel (`pydivert/windivert_dll/`) |
| `WinDivert64.sys` | the actual kernel driver loaded by Windows | bundled inside the `pydivert` wheel (`pydivert/windivert_dll/`) |

> Note: pydivert ships the **64-bit** pair only (`WinDivert64.*`), not the
> 32-bit `WinDivert.dll`. XenRay is x64, so this is correct.

## Dependencies declared
- `pyproject.toml` adds:
  `pydivert = { version = "^3.1.0", markers = "sys_platform == 'win32'" }`
  → **Windows-only**, guarded so Linux/macOS installs stay lean and import clean.
- Runtime: run `.venv/Scripts/python.exe -m pip install pydivert` (or
  `poetry install`), which also places `pydivert/windivert_dll/{WinDivert64.dll, WinDivert64.sys}`.

## Admin requirement (hard)
WinDivert loads a **kernel driver**. Opening a handle (`WinDivertOpen`, called
from `src/services/sni_spoof/tcp_injector.py`) **requires administrator
privileges**. Behavior is **fail-soft**:

| State | `SniSpoofService.start()` |
|---|---|
| non-admin OR pydivert missing | returns `False`, status=`failed`, logs warning — **nothing spawned, no crash** |
| admin + pydivert present | starts the listener, status=`running` |

The admin gate reuses `ProcessUtils.is_admin()` (same path the VPN/admin-restart
dialog uses). See `tests/test_sni_spoof_failsoft.py`.

## Bundling into the XenRay executable
`build_pyinstaller.py` gains `get_windivert_args()` which emits:

```
--add-binary=...\pydivert\windivert_dll\WinDivert64.dll;pydivert\windivert_dll
--add-binary=...\pydivert\windivert_dll\WinDivert64.sys;pydivert\windivert_dll
```

**Why this exact destination:** pydivert resolves the DLL at runtime from
`os.path.dirname(__file__)` (`pydivert/windivert_dll/__init__.py:185` →
`DLL_PATH = os.path.join(os.path.dirname(__file__), "WinDivert64.dll")`).
In a `--onefile` build, `__file__` points into PyInstaller's temp extraction
dir, so the DLL/.sys must land at `pydivert/windivert_dll/` inside that
extraction. PyInstaller does **not** auto-collect package data files — the
explicit `--add-binary` is required.

The driver itself is installed system-wide by pydivert when a handle opens
(registers the `WinDivert` service + loads `WinDivert64.sys` from `System32`).
The `.sys` bundled in the app is the source copy; admin applies it.

## Verification (smoke)
1. **Non-admin fail-soft** (default dev shell):
   `src/services/sni_spoof/sni_spoof_service.py` → `_prerequisites_ok()` returns
   `(False, "administrator privileges required ...")`, `start()` returns `False`.
   Covered by `tests/test_sni_spoof_failsoft.py`.
2. **Bundle args** on Windows with pydivert installed:
   `python -c "import build_pyinstaller as b; print(b.get_windivert_args())"`
   → two `--add-binary` flags pointing at `windivert_dll/`.
3. **Real capture** (admin shell): `with pydivert.WinDivert('false') as w: ...`
   requires elevation; skip in normal test runs.
