"""Tests for the fortified update infrastructure (file-lock-safe core extraction
and the interactive UpdateDialog)."""

from __future__ import annotations

import zipfile

import src.services.xray_installer as xi
from src.ui.components.dialogs.update_dialog import UpdateDialog


def _make_zip(zip_path, contents):
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in contents.items():
            zf.writestr(name, data)


def test_extract_core_safe_rename_replaces_binary(tmp_path, monkeypatch):
    """Existing xray.exe must be safely renamed away, replaced, and the .old
    backup cleaned up on success (no PermissionError on locked files)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(xi, "BIN_DIR", str(bin_dir))
    monkeypatch.setattr(xi.XrayInstallerService, "_kill_xray_processes", lambda: None)

    old = bin_dir / "xray.exe"
    old.write_bytes(b"OLD_BINARY")

    zip_path = tmp_path / "xray_update.zip"
    _make_zip(zip_path, {"xray.exe": b"NEW_BINARY"})

    assert xi.XrayInstallerService._extract_core(str(zip_path)) is True
    assert (bin_dir / "xray.exe").read_bytes() == b"NEW_BINARY"
    assert not (bin_dir / "xray.exe.old").exists(), ".old backup must be cleaned up"


def test_extract_core_rolls_back_on_failure(tmp_path, monkeypatch):
    """If extraction fails, the previous binary must be restored (rollback)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(xi, "BIN_DIR", str(bin_dir))
    monkeypatch.setattr(xi.XrayInstallerService, "_kill_xray_processes", lambda: None)

    old = bin_dir / "xray.exe"
    old.write_bytes(b"OLD_BINARY")

    zip_path = tmp_path / "xray_update.zip"
    _make_zip(zip_path, {"xray.exe": b"NEW_BINARY"})

    real_extractall = zipfile.ZipFile.extractall

    def _failing_extractall(self, *a, **k):
        raise OSError("Permission denied")

    monkeypatch.setattr(zipfile.ZipFile, "extractall", _failing_extractall)
    try:
        assert xi.XrayInstallerService._extract_core(str(zip_path)) is False
    finally:
        monkeypatch.setattr(zipfile.ZipFile, "extractall", real_extractall)

    assert (bin_dir / "xray.exe").read_bytes() == b"OLD_BINARY", "old binary restored"
    assert not (bin_dir / "xray.exe.old").exists(), ".old backup consumed by rollback"


def test_extract_core_calls_kill_before_replacing(tmp_path, monkeypatch):
    """Active xray processes must be killed before the binary is replaced."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(xi, "BIN_DIR", str(bin_dir))
    killed = []

    def _fake_kill():
        killed.append(True)

    monkeypatch.setattr(xi.XrayInstallerService, "_kill_xray_processes", _fake_kill)

    zip_path = tmp_path / "xray_update.zip"
    _make_zip(zip_path, {"xray.exe": b"NEW"})

    assert xi.XrayInstallerService._extract_core(str(zip_path)) is True
    assert killed, "_kill_xray_processes must be called before extraction"


def test_update_dialog_version_comparison_and_progress_in_place():
    """The UpdateDialog shows a version comparison and updates its progress bar
    and status line in place (no page re-render)."""
    dlg = UpdateDialog(
        current_version="2.4.0",
        latest_version="2.5.0",
        release_notes="Fixes the neon border crash",
    )

    assert dlg._version_text.value == "v2.4.0  ->  v2.5.0"
    assert dlg._progress.value == 0.0

    dlg.set_progress(0.5)
    assert dlg._progress.value == 0.5

    dlg.set_progress_status(0.8, "Downloading... 80%")
    assert dlg._progress.value == 0.8
    assert dlg._status_text.value == "Downloading... 80%"

    # Progress clamps to [0, 1]
    dlg.set_progress(1.5)
    assert dlg._progress.value == 1.0
    dlg.set_progress(-0.2)
    assert dlg._progress.value == 0.0
