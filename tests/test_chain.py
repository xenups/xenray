"""Unit tests for Chain functionality."""
from unittest.mock import patch


import pytest

from src.core.app_context import AppContext


class TestChainValidation:
    """Test suite for chain validation logic."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        """Fixture to provide a temporary configuration directory."""
        config_dir = tmp_path / "xenray"
        config_dir.mkdir()
        return config_dir

    @pytest.fixture
    def ctx(self, temp_config_dir):
        """Fixture to provide a AppContext with mocked paths."""
        recent_files_path = str(temp_config_dir / "recent_files.json")
        last_file_path = str(temp_config_dir / "last_entry.txt")

        with patch("src.core.app_context.RECENT_FILES_PATH", recent_files_path), patch(
            "src.repositories.recent_files_repository.LAST_FILE_PATH", last_file_path
        ):
            manager = AppContext.create()
            return manager

    def _create_profile(self, ctx, name: str, protocol: str = "vless"):
        """Helper to create a test profile with a given protocol."""
        config = {
            "outbounds": [
                {
                    "tag": f"{name}-tag",
                    "protocol": protocol,
                    "settings": {"vnext": [{"address": "test.com", "port": 443}]},
                    "streamSettings": {"network": "tcp"},
                }
            ]
        }
        return ctx.profiles.save(name, config)

    def test_chain_validation_min_items(self, ctx):
        """Chain with < 2 items should fail validation."""
        p1 = self._create_profile(ctx, "Server1")

        # Empty list
        is_valid, error = ctx.validate_chain([])
        assert is_valid is False
        assert "Invalid chain items" in error or "at least 2" in error

        # Single item
        is_valid, error = ctx.validate_chain([p1])
        assert is_valid is False
        assert "at least 2" in error

    def test_chain_validation_circular(self, ctx):
        """Chain with duplicate items should fail validation."""
        p1 = self._create_profile(ctx, "Server1")

        is_valid, error = ctx.validate_chain([p1, p1])
        assert is_valid is False
        assert "Duplicate" in error

    def test_chain_validation_invalid_protocol(self, ctx):
        """Chain containing freedom/blackhole should fail."""
        p1 = self._create_profile(ctx, "Server1", "vless")
        p2 = self._create_profile(ctx, "FreedomServer", "freedom")

        is_valid, error = ctx.validate_chain([p1, p2])
        assert is_valid is False
        # freedom is not in CHAINABLE_PROTOCOLS, so it fails with "No valid proxy outbound"
        assert "freedom" in error.lower() or "cannot be used" in error or "No valid proxy" in error

    def test_chain_validation_no_nesting(self, ctx):
        """Chain referencing another chain should fail validation."""
        p1 = self._create_profile(ctx, "Server1")
        p2 = self._create_profile(ctx, "Server2")

        # Create a chain first
        chain_id = ctx.save_chain("TestChain", [p1, p2])
        assert chain_id is not None

        # Try to create another chain that references the first chain
        p3 = self._create_profile(ctx, "Server3")
        is_valid, error = ctx.validate_chain([chain_id, p3])
        assert is_valid is False
        assert "contain other chains" in error

    def test_chain_validation_last_item_no_dialer_proxy(self, ctx):
        """Last chain outbound must not have existing dialerProxy."""
        p1 = self._create_profile(ctx, "Server1")

        # Create a profile with existing dialerProxy
        config_with_dialer = {
            "outbounds": [
                {
                    "tag": "dialer-test-tag",
                    "protocol": "vless",
                    "settings": {"vnext": [{"address": "test.com", "port": 443}]},
                    "streamSettings": {
                        "network": "tcp",
                        "sockopt": {"dialerProxy": "some-other-outbound"},
                    },
                }
            ]
        }
        p2 = ctx.profiles.save("DialerServer", config_with_dialer)

        # If this is the last item, it should fail
        is_valid, error = ctx.validate_chain([p1, p2])
        assert is_valid is False
        assert "dialerProxy" in error

    def test_chain_validation_missing_profile(self, ctx):
        """Chain with non-existent profile ID should fail."""
        p1 = self._create_profile(ctx, "Server1")

        is_valid, error = ctx.validate_chain([p1, "non-existent-id"])
        assert is_valid is False
        assert "not found" in error or "Server not found" in error

    def test_chain_validation_success(self, ctx):
        """Valid chain should pass validation."""
        p1 = self._create_profile(ctx, "Server1", "vless")
        p2 = self._create_profile(ctx, "Server2", "vmess")

        is_valid, error = ctx.validate_chain([p1, p2])
        assert is_valid is True
        assert error == ""


class TestChainCRUD:
    """Test suite for chain CRUD operations."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        """Fixture to provide a temporary configuration directory."""
        config_dir = tmp_path / "xenray"
        config_dir.mkdir()
        return config_dir

    @pytest.fixture
    def ctx(self, temp_config_dir):
        """Fixture to provide a AppContext with mocked paths."""
        recent_files_path = str(temp_config_dir / "recent_files.json")
        last_file_path = str(temp_config_dir / "last_entry.txt")

        with patch("src.core.app_context.RECENT_FILES_PATH", recent_files_path), patch(
            "src.repositories.recent_files_repository.LAST_FILE_PATH", last_file_path
        ):
            manager = AppContext.create()
            return manager

    def _create_profile(self, ctx, name: str, protocol: str = "vless"):
        """Helper to create a test profile."""
        config = {
            "outbounds": [
                {
                    "tag": f"{name}-tag",
                    "protocol": protocol,
                    "settings": {"vnext": [{"address": "test.com", "port": 443}]},
                    "streamSettings": {"network": "tcp"},
                }
            ]
        }
        return ctx.profiles.save(name, config)

    def test_chain_save_and_load(self, ctx):
        """Test saving and loading chains."""
        p1 = self._create_profile(ctx, "Server1")
        p2 = self._create_profile(ctx, "Server2")

        chain_id = ctx.save_chain("My Chain", [p1, p2])
        assert chain_id is not None

        chains = ctx.load_chains()
        assert len(chains) == 1
        assert chains[0]["name"] == "My Chain"
        assert chains[0]["items"] == [p1, p2]
        assert chains[0]["valid"] is True

    def test_chain_get_by_id(self, ctx):
        """Test getting a chain by ID."""
        p1 = self._create_profile(ctx, "Server1")
        p2 = self._create_profile(ctx, "Server2")

        chain_id = ctx.save_chain("My Chain", [p1, p2])
        chain = ctx.get_chain_by_id(chain_id)

        assert chain is not None
        assert chain["name"] == "My Chain"

        # Non-existent chain
        assert ctx.get_chain_by_id("non-existent") is None

    def test_chain_update(self, ctx):
        """Test updating a chain."""
        p1 = self._create_profile(ctx, "Server1")
        p2 = self._create_profile(ctx, "Server2")
        p3 = self._create_profile(ctx, "Server3")

        chain_id = ctx.save_chain("My Chain", [p1, p2])

        # Update name only
        success = ctx.update_chain(chain_id, {"name": "Updated Chain"})
        assert success is True

        chain = ctx.get_chain_by_id(chain_id)
        assert chain["name"] == "Updated Chain"

        # Update items
        success = ctx.update_chain(chain_id, {"items": [p1, p3]})
        assert success is True

        chain = ctx.get_chain_by_id(chain_id)
        assert chain["items"] == [p1, p3]

    def test_chain_delete(self, ctx):
        """Test deleting a chain."""
        p1 = self._create_profile(ctx, "Server1")
        p2 = self._create_profile(ctx, "Server2")

        chain_id = ctx.save_chain("My Chain", [p1, p2])
        assert len(ctx.load_chains()) == 1

        ctx.chains.delete(chain_id)
        assert len(ctx.load_chains()) == 0

    def test_chain_is_chain(self, ctx):
        """Test is_chain helper."""
        p1 = self._create_profile(ctx, "Server1")
        p2 = self._create_profile(ctx, "Server2")

        # Profile ID should not be a chain
        assert ctx.chains.is_chain(p1) is False

        # Chain ID should be a chain
        chain_id = ctx.save_chain("My Chain", [p1, p2])
        assert ctx.chains.is_chain(chain_id) is True

    def test_chain_marks_invalid_on_missing_profile(self, ctx, temp_config_dir):
        """Chain should be marked invalid when referenced profile is deleted."""
        p1 = self._create_profile(ctx, "Server1")
        p2 = self._create_profile(ctx, "Server2")

        ctx.save_chain("My Chain", [p1, p2])  # chain_id unused, saved for side effect

        # Verify chain is valid initially
        chains = ctx.load_chains()
        assert chains[0]["valid"] is True

        # Delete one of the profiles
        ctx.profiles.delete(p2)

        # Reload chains - should now be invalid
        chains = ctx.load_chains()
        assert chains[0]["valid"] is False
        assert p2 in chains[0]["missing_profiles"]


class TestChainConfigGeneration:
    """Test suite for chain config generation in XrayConfigProcessor."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        """Fixture to provide a temporary configuration directory."""
        config_dir = tmp_path / "xenray"
        config_dir.mkdir()
        return config_dir

    @pytest.fixture
    def ctx(self, temp_config_dir):
        """Fixture to provide a AppContext with mocked paths."""
        recent_files_path = str(temp_config_dir / "recent_files.json")
        last_file_path = str(temp_config_dir / "last_entry.txt")

        with patch("src.core.app_context.RECENT_FILES_PATH", recent_files_path), patch(
            "src.repositories.recent_files_repository.LAST_FILE_PATH", last_file_path
        ):
            manager = AppContext.create()
            return manager

    @pytest.fixture
    def xray_processor(self, ctx):
        """Fixture to provide an XrayConfigProcessor."""
        from src.services.xray_config_processor import XrayConfigProcessor

        return XrayConfigProcessor(ctx)

    def _create_profile(self, ctx, name: str, tag: str = None, protocol: str = "vless"):
        """Helper to create a test profile."""
        config = {
            "outbounds": [
                {
                    "tag": tag or f"{name}-tag",
                    "protocol": protocol,
                    "settings": {"vnext": [{"address": f"{name}.com", "port": 443}]},
                    "streamSettings": {"network": "tcp"},
                }
            ]
        }
        return ctx.profiles.save(name, config)

    def test_chain_config_generation(self, ctx, xray_processor):
        """Generated outbounds should have correct dialerProxy injection."""
        p1 = self._create_profile(ctx, "Server1", "server1-tag")
        p2 = self._create_profile(ctx, "Server2", "server2-tag")
        p3 = self._create_profile(ctx, "Server3", "server3-tag")

        chain = {
            "id": "test-chain",
            "name": "Test Chain",
            "items": [p1, p2, p3],
        }

        success, config, error = xray_processor.build_chain_config(chain)
        assert success is True, f"Failed: {error}"

        outbounds = config["outbounds"]
        assert len(outbounds) == 3

        # NEW LOGIC: Entry -> Exit
        # Item 0 (Entry) should NOT have dialerProxy (connects directly)
        assert "dialerProxy" not in outbounds[0].get("streamSettings", {}).get("sockopt", {})

        # Item 1 should have dialerProxy pointing to Item 0
        assert "dialerProxy" in outbounds[1].get("streamSettings", {}).get("sockopt", {})
        assert outbounds[1]["streamSettings"]["sockopt"]["dialerProxy"] == outbounds[0]["tag"]

        # Item 2 (Exit) should have dialerProxy pointing to Item 1
        assert "dialerProxy" in outbounds[2].get("streamSettings", {}).get("sockopt", {})
        assert outbounds[2]["streamSettings"]["sockopt"]["dialerProxy"] == outbounds[1]["tag"]

    def test_chain_full_config_build(self, ctx, xray_processor):
        """Test build_chain_config produces a complete Xray config."""
        p1 = self._create_profile(ctx, "Server1")
        p2 = self._create_profile(ctx, "Server2")

        chain = {
            "id": "test-chain",
            "name": "Test Chain",
            "items": [p1, p2],
        }

        success, config, error = xray_processor.build_chain_config(chain)
        assert success is True, f"Failed: {error}"

        # Full config should have all sections
        assert "outbounds" in config
        assert "routing" in config
        assert "log" in config

        # Should have chain outbounds
        assert len(config["outbounds"]) == 2

        # Verify routing structure exists (even if empty)
        assert isinstance(config["routing"], dict)
