"""Sort-mode persistence across restarts (WS2).

Verifies that ``SettingsRepository.set_sort_mode`` writes ``sort_mode.txt`` to
disk, that a fresh repository instance (simulating an app restart) reads the
persisted value back, and that ``ServerListSortMixin._on_sort_changed`` drives
the same persistence path.
"""

from __future__ import annotations

import os
import types

from src.repositories.settings_repository import SettingsRepository
from src.ui.components.servers.server_list_sort import ServerListSortMixin

VALID_MODES = ("name_asc", "ping_asc", "ping_desc")


def _write_sort_mode(repo: SettingsRepository, mode: str) -> None:
    """Persist a sort mode and assert the flat file landed on disk."""
    repo.set_sort_mode(mode)
    path = os.path.join(repo._config_dir, "sort_mode.txt")
    assert os.path.exists(path), "set_sort_mode must write sort_mode.txt to disk"
    with open(path, "r", encoding="utf-8") as f:
        assert f.read().strip() == mode


def test_set_sort_mode_persists_file(tmp_path):
    """set_sort_mode writes the mode to disk (sort_mode.txt)."""
    repo = SettingsRepository(str(tmp_path))
    _write_sort_mode(repo, "ping_asc")


def test_restart_returns_persisted_sort_mode(tmp_path):
    """A new repository instance (restart) reads the persisted sort mode."""
    repo1 = SettingsRepository(str(tmp_path))
    repo1.set_sort_mode("ping_asc")

    repo2 = SettingsRepository(str(tmp_path))  # simulate app restart
    assert repo2.get_sort_mode() == "ping_asc"


def test_all_valid_modes_survive_restart(tmp_path):
    """Every supported mode round-trips through disk."""
    for mode in VALID_MODES:
        repo1 = SettingsRepository(str(tmp_path))
        repo1.set_sort_mode(mode)
        repo2 = SettingsRepository(str(tmp_path))
        assert repo2.get_sort_mode() == mode


def test_default_sort_mode_is_name_asc(tmp_path):
    """No file yet -> default name_asc (never None)."""
    repo = SettingsRepository(str(tmp_path))
    assert repo.get_sort_mode() == "name_asc"


def test_invalid_sort_mode_ignored(tmp_path):
    """Unknown modes are rejected; the persisted value stays."""
    repo = SettingsRepository(str(tmp_path))
    repo.set_sort_mode("ping_asc")
    repo.set_sort_mode("latency")  # not a valid mode
    assert repo.get_sort_mode() == "ping_asc"
    with open(os.path.join(str(tmp_path), "sort_mode.txt"), "r", encoding="utf-8") as f:
        assert f.read().strip() == "ping_asc"


def test_on_sort_changed_persists(tmp_path):
    """ServerListSortMixin._on_sort_changed writes the mode through the settings repo."""

    class FakeServerList(ServerListSortMixin):
        """Minimal mixin host: real settings repo, no-op list re-sort."""

        def __init__(self, repo):
            self._app_context = types.SimpleNamespace(settings=repo)
            self._active_subscription = None
            self._profiles = []

        def _resort_profiles_in_place(self):
            pass

    repo = SettingsRepository(str(tmp_path))
    host = FakeServerList(repo)

    host._on_sort_changed("ping_asc")

    # Persisted to disk immediately...
    path = os.path.join(str(tmp_path), "sort_mode.txt")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        assert f.read().strip() == "ping_asc"
    # ...and a fresh instance (restart) returns it.
    assert SettingsRepository(str(tmp_path)).get_sort_mode() == "ping_asc"
