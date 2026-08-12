"""Unit tests for the thread-safe atomic file writes."""

from __future__ import annotations

import threading

from src.repositories.file_utils import atomic_write, atomic_write_json


def test_atomic_write_basic(tmp_path):
    """A normal atomic write produces the file with the right content."""
    target = tmp_path / "profiles.json"
    assert atomic_write(str(target), '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'
    # No leftover .tmp file
    assert not (tmp_path / "profiles.json.tmp").exists()


def test_atomic_write_concurrent_threads(tmp_path):
    """Concurrent atomic writes must serialize (no PermissionError collision on
    the shared .tmp handle) and all succeed."""
    target = tmp_path / "profiles.json"
    errors = []

    def writer(i):
        try:
            atomic_write(str(target), f"content-{i}")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent writes raised: {errors}"
    assert target.exists()
    # Exactly one valid final write.
    assert target.read_text(encoding="utf-8") in {f"content-{i}" for i in range(20)}
    assert not (tmp_path / "profiles.json.tmp").exists()


def test_atomic_write_json_concurrent(tmp_path):
    """atomic_write_json is also collision-free under concurrent threads."""
    target = tmp_path / "data.json"
    errors = []

    def writer(i):
        try:
            atomic_write_json(str(target), {"index": i})
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent JSON writes raised: {errors}"
    assert target.exists()
