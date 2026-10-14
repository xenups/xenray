"""Tests for build_pyinstaller script failure modes and verification."""

import os
from unittest.mock import MagicMock, patch

import pytest

import build_pyinstaller


def test_ensure_xray_parser_built_fails_on_compiler_error(monkeypatch):
    """ensure_xray_parser_built must exit with non-zero if go build fails."""
    monkeypatch.setattr(os.path, "exists", lambda p: False if "bin" in p else True)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/go" if cmd == "go" else None)

    mock_res = MagicMock()
    mock_res.returncode = 2

    with patch("subprocess.run", return_value=mock_res):
        with pytest.raises(SystemExit) as excinfo:
            build_pyinstaller.ensure_xray_parser_built()
        assert excinfo.value.code == 2


def test_main_exits_when_output_binary_missing(monkeypatch):
    """build_pyinstaller.main must exit with code 1 if PyInstaller succeeds but binary is missing."""
    monkeypatch.setattr("build_pyinstaller.ensure_xray_parser_built", lambda: None)
    monkeypatch.setattr("shutil.rmtree", lambda *a, **kw: None)

    mock_res = MagicMock()
    mock_res.returncode = 0

    with patch("subprocess.run", return_value=mock_res):
        with patch("os.path.exists", return_value=False):
            with pytest.raises(SystemExit) as excinfo:
                build_pyinstaller.main()
            assert excinfo.value.code == 1


def test_main_exits_when_output_binary_is_empty(monkeypatch):
    """build_pyinstaller.main must exit with code 1 if output binary is 0 bytes."""
    monkeypatch.setattr("build_pyinstaller.ensure_xray_parser_built", lambda: None)
    monkeypatch.setattr("shutil.rmtree", lambda *a, **kw: None)

    mock_res = MagicMock()
    mock_res.returncode = 0

    with patch("subprocess.run", return_value=mock_res):
        with patch("os.path.exists", return_value=True):
            with patch("os.path.getsize", return_value=0):
                with pytest.raises(SystemExit) as excinfo:
                    build_pyinstaller.main()
                assert excinfo.value.code == 1
