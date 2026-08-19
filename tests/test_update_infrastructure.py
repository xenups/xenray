"""Tests for the fortified update infrastructure (file-lock-safe core extraction
and the interactive UpdateDialog)."""

from __future__ import annotations

import zipfile

from src.services.installer.archive_extractor import OLD_SUFFIX, ArchiveExtractor


def _make_zip(zip_path, contents):
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in contents.items():
            zf.writestr(name, data)


def test_extract_core_safe_rename_replaces_binary(tmp_path, monkeypatch):
    """Existing xray.exe must be safely renamed away, replaced, and the .old
    backup cleaned up on success (no PermissionError on locked files)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(ArchiveExtractor, "_kill_active_core", lambda self: None)

    old = bin_dir / "xray.exe"
    old.write_bytes(b"OLD_BINARY")

    zip_path = tmp_path / "xray_update.zip"
    _make_zip(zip_path, {"xray.exe": b"NEW_BINARY"})

    assert ArchiveExtractor(str(bin_dir)).extract_core(str(zip_path)) is True
    assert (bin_dir / "xray.exe").read_bytes() == b"NEW_BINARY"
    assert not (bin_dir / ("xray.exe" + OLD_SUFFIX)).exists(), ".old backup must be cleaned up"


def test_extract_core_rolls_back_on_failure(tmp_path, monkeypatch):
    """If extraction fails, the previous binary must be restored (rollback)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(ArchiveExtractor, "_kill_active_core", lambda self: None)

    old = bin_dir / "xray.exe"
    old.write_bytes(b"OLD_BINARY")

    zip_path = tmp_path / "xray_update.zip"
    _make_zip(zip_path, {"xray.exe": b"NEW_BINARY"})

    real_extractall = zipfile.ZipFile.extractall

    def _failing_extractall(self, *a, **k):
        raise OSError("Permission denied")

    monkeypatch.setattr(zipfile.ZipFile, "extractall", _failing_extractall)
    try:
        assert ArchiveExtractor(str(bin_dir)).extract_core(str(zip_path)) is False
    finally:
        monkeypatch.setattr(zipfile.ZipFile, "extractall", real_extractall)

    assert (bin_dir / "xray.exe").read_bytes() == b"OLD_BINARY", "old binary restored"
    assert not (bin_dir / ("xray.exe" + OLD_SUFFIX)).exists(), ".old backup consumed by rollback"


def test_extract_core_calls_kill_before_replacing(tmp_path, monkeypatch):
    """Active xray processes must be killed before the binary is replaced."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    killed = []

    def _fake_kill(self):
        killed.append(True)

    monkeypatch.setattr(ArchiveExtractor, "_kill_active_core", _fake_kill)

    zip_path = tmp_path / "xray_update.zip"
    _make_zip(zip_path, {"xray.exe": b"NEW_BINARY"})

    ArchiveExtractor(str(bin_dir)).extract_core(str(zip_path))
    assert killed, "_kill_active_core must be called before extraction"


def test_extract_core_missing_zip_returns_false(tmp_path):
    """A missing zip must yield False, not raise."""
    assert ArchiveExtractor(str(tmp_path / "bin")).extract_core(str(tmp_path / "nope.zip")) is False
