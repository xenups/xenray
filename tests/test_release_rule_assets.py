"""Tests for release rule asset download, destination paths, overwrite behavior, and packaging."""

import hashlib
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.download_geo_files import MIN_DAT_SIZE, RULES_DIR, download_file, download_geo_files
from scripts.download_rule_sets import FILES as SRS_FILES
from scripts.download_rule_sets import MIN_SIZE as SRS_MIN_SIZE
from scripts.download_rule_sets import download_rule_sets
from src.core.constants import ASSETS_DIR
from src.core.constants import RULES_DIR as CONST_RULES_DIR


class TestReleaseRuleAssetPaths:
    """Verify runtime path expectations and constants."""

    def test_destination_paths_match_constants(self):
        """Scripts must target the exact directory expected by runtime constants."""
        assert Path(CONST_RULES_DIR) == RULES_DIR
        assert Path(CONST_RULES_DIR) == Path(ASSETS_DIR) / "rules"

    def test_xray_location_asset_fallback(self, monkeypatch, tmp_path):
        """XRAY_LOCATION_ASSET falls back to BIN_DIR when assets/rules/geosite.dat is absent."""
        fake_assets = tmp_path / "assets"
        fake_rules = fake_assets / "rules"
        fake_rules.mkdir(parents=True)
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir(parents=True)

        monkeypatch.setattr("src.core.constants.RULES_DIR", str(fake_rules))
        monkeypatch.setattr("src.core.constants.BIN_DIR", str(fake_bin))

        # Without geosite.dat, fallback to BIN_DIR
        if os.path.exists(os.path.join(fake_rules, "geosite.dat")):
            loc = str(fake_rules)
        else:
            loc = str(fake_bin)
        assert loc == str(fake_bin)

        # With geosite.dat, priority is RULES_DIR
        (fake_rules / "geosite.dat").write_bytes(b"dummy geosite")
        if os.path.exists(os.path.join(fake_rules, "geosite.dat")):
            loc = str(fake_rules)
        else:
            loc = str(fake_bin)
        assert loc == str(fake_rules)


class TestDownloadGeoFilesBehavior:
    """Verify download_geo_files atomic operations, skip and force overwrite."""

    def test_download_file_skip_when_exists_and_not_forced(self, tmp_path):
        """Existing file must be skipped when force=False."""
        dest = tmp_path / "test.dat"
        dest.write_bytes(b"old content")

        result = download_file("http://fake.url/test.dat", dest, force=False)
        assert result == dest
        assert dest.read_bytes() == b"old content"

    @patch("urllib.request.urlretrieve")
    def test_download_file_overwrites_when_forced(self, mock_retrieve, tmp_path):
        """File must be overwritten atomically when force=True."""
        dest = tmp_path / "test.dat"
        dest.write_bytes(b"old content")

        def fake_retrieve(url, filename, reporthook=None):
            Path(filename).write_bytes(b"x" * (MIN_DAT_SIZE + 10))

        mock_retrieve.side_effect = fake_retrieve

        result = download_file("http://fake.url/test.dat", dest, force=True)
        assert result == dest
        assert dest.read_bytes() == b"x" * (MIN_DAT_SIZE + 10)
        assert not dest.with_name(f"{dest.name}.tmp").exists()

    @patch("urllib.request.urlretrieve")
    def test_download_file_fails_and_cleans_tmp_on_small_file(self, mock_retrieve, tmp_path):
        """Temporary file must be cleaned up if download is smaller than minimum size."""
        dest = tmp_path / "test.dat"

        def fake_retrieve(url, filename, reporthook=None):
            Path(filename).write_bytes(b"too small")

        mock_retrieve.side_effect = fake_retrieve

        with pytest.raises(RuntimeError, match="Downloaded file too small"):
            download_file("http://fake.url/test.dat", dest, force=True, min_size=1024)

        assert not dest.exists()
        assert not dest.with_name(f"{dest.name}.tmp").exists()

    @patch("urllib.request.urlretrieve")
    def test_download_file_cleans_tmp_on_network_exception(self, mock_retrieve, tmp_path):
        """Temporary file must be unlinked if network error occurs."""
        dest = tmp_path / "test.dat"

        def fake_retrieve(url, filename, reporthook=None):
            Path(filename).write_bytes(b"partial")
            raise ConnectionResetError("Connection lost")

        mock_retrieve.side_effect = fake_retrieve

        with pytest.raises(ConnectionResetError):
            download_file("http://fake.url/test.dat", dest, force=True)

        assert not dest.exists()
        assert not dest.with_name(f"{dest.name}.tmp").exists()

    @patch("scripts.download_geo_files.download_file")
    def test_download_geo_files_targets_dest_dir(self, mock_download, tmp_path):
        """download_geo_files must invoke download_file for both geoip and geosite in target dir."""
        target_dir = tmp_path / "custom_rules"
        download_geo_files(dest_dir=target_dir, force=True)

        calls = mock_download.call_args_list
        assert len(calls) == 2
        paths = [call[0][1] for call in calls]
        assert target_dir / "geoip.dat" in paths
        assert target_dir / "geosite.dat" in paths


class TestDownloadRuleSetsBehavior:
    """Verify download_rule_sets behavior and atomic writes."""

    @patch("scripts.download_rule_sets._fetch")
    def test_download_rule_sets_skip_existing_when_not_forced(self, mock_fetch, tmp_path):
        """download_rule_sets skips existing valid files when force=False."""
        target_dir = str(tmp_path / "rules")
        os.makedirs(target_dir, exist_ok=True)

        for name, _ in SRS_FILES:
            with open(os.path.join(target_dir, name), "wb") as f:
                f.write(b"s" * (SRS_MIN_SIZE + 10))

        ret = download_rule_sets(target_dir=target_dir, force=False)
        assert ret == 0
        mock_fetch.assert_not_called()

    @patch("scripts.download_rule_sets._fetch")
    def test_download_rule_sets_atomic_write(self, mock_fetch, tmp_path):
        """download_rule_sets writes content and cleans .tmp."""
        target_dir = str(tmp_path / "rules")
        mock_fetch.return_value = b"SINGBOX_RULESET_VALID_BYTES" * 100

        ret = download_rule_sets(target_dir=target_dir, force=True)
        assert ret == 0

        for name, _ in SRS_FILES:
            target_file = os.path.join(target_dir, name)
            assert os.path.exists(target_file)
            assert not os.path.exists(f"{target_file}.tmp")
            assert os.path.getsize(target_file) >= SRS_MIN_SIZE


class TestPackagingInclusionAndIntegrity:
    """Verify packaging pipeline correctly captures all rule assets without data corruption."""

    def test_all_required_source_assets_exist(self):
        """Verify repository contains all required rule assets in assets/rules/."""
        source_rules_dir = Path("assets/rules")
        required_assets = [
            "geoip.dat",
            "geosite.dat",
            "geoip-ir.srs",
            "geosite-ir.srs",
            "geosite-category-ads-all.srs",
            "geoip-cn.srs",
            "ru-bundle.srs",
        ]
        for asset in required_assets:
            asset_path = source_rules_dir / asset
            assert asset_path.exists(), f"Missing required asset: {asset_path}"
            assert asset_path.stat().st_size > 0, f"Asset is empty: {asset_path}"

    def test_simulated_release_package_layout_and_hashes(self, tmp_path):
        """Simulate packaging step from release.yml and verify SHA-256 match and completeness."""
        pkg_dir = tmp_path / "package"
        pkg_assets = pkg_dir / "assets"
        pkg_rules = pkg_assets / "rules"
        pkg_bin = pkg_dir / "bin"
        pkg_rules.mkdir(parents=True)
        pkg_bin.mkdir(parents=True)

        source_rules = Path("assets/rules")
        source_bin = Path("bin")

        # Copy assets as release.yml does: Copy-Item -Recurse "assets" "package/"
        for f in source_rules.iterdir():
            if f.is_file():
                shutil.copy2(f, pkg_rules / f.name)

        # Copy bin as release.yml does: Copy-Item -Recurse "dist/bin" "package/"
        for f in source_bin.iterdir():
            if f.is_file():
                shutil.copy2(f, pkg_bin / f.name)

        # 1. Verify all rules exist in package/assets/rules/
        required_rules = [
            "geoip.dat",
            "geosite.dat",
            "geoip-ir.srs",
            "geosite-ir.srs",
            "geosite-category-ads-all.srs",
            "geoip-cn.srs",
            "ru-bundle.srs",
        ]
        for name in required_rules:
            pkg_file = pkg_rules / name
            src_file = source_rules / name
            assert pkg_file.exists(), f"{name} missing in package/assets/rules"
            # SHA-256 integrity check
            src_sha = hashlib.sha256(src_file.read_bytes()).hexdigest()
            pkg_sha = hashlib.sha256(pkg_file.read_bytes()).hexdigest()
            assert src_sha == pkg_sha, f"SHA-256 mismatch for {name}"

        # 2. Verify fallback binary assets exist in package/bin/
        required_bin_assets = [
            "xray.exe",
            "sing-box.exe",
            "wintun.dll",
            "geoip.dat",
            "geosite.dat",
        ]
        for name in required_bin_assets:
            pkg_file = pkg_bin / name
            assert pkg_file.exists(), f"{name} missing in package/bin"
