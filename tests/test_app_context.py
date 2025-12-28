"""Unit tests for AppContext."""
import json
import os
from unittest.mock import patch

import pytest

from src.core.app_context import AppContext


class TestAppContext:
    """Test suite for AppContext."""

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

        # Patch constants where they are imported
        with patch("src.core.app_context.RECENT_FILES_PATH", recent_files_path), patch(
            "src.repositories.recent_files_repository.RECENT_FILES_PATH", recent_files_path
        ), patch("src.repositories.recent_files_repository.LAST_FILE_PATH", last_file_path):
            manager = AppContext.create()
            # The __init__ will set _config_dir based on patched RECENT_FILES_PATH
            return manager

    def test_ensure_config_dir(self, temp_config_dir):
        """Test configuration directory is created."""
        with patch(
            "src.core.app_context.RECENT_FILES_PATH",
            str(temp_config_dir / "recent_files.json"),
        ):
            AppContext.create()
            assert os.path.exists(str(temp_config_dir))

    def test_recent_files_operations(self, ctx):
        """Test adding, getting, and removing recent files."""
        test_file = "test_config_1.json"

        # Add file
        ctx.recent_files.add(test_file)
        recent = ctx.recent_files.get_all()
        assert test_file in recent

        # Add again (should move to top/not duplicate)
        ctx.recent_files.add(test_file)
        assert len(ctx.recent_files.get_all()) == 1

        # Remove file
        ctx.recent_files.remove(test_file)
        assert test_file not in ctx.recent_files.get_all()

    def test_last_selected_file(self, ctx):
        """Test setting and getting last selected file."""
        test_file = "last_used.json"
        ctx.recent_files.set_last_selected(test_file)
        assert ctx.recent_files.get_last_selected() == test_file

    def test_profile_crud(self, ctx):
        """Test Create, Read, Update, Delete for profiles."""
        name = "Test Profile"
        config = {"v": "2", "ps": "test", "add": "127.0.0.1"}

        # Save profile
        profile_id = ctx.profiles.save(name, config)
        assert profile_id is not None

        # Load profiles
        profiles = ctx.profiles.load_all()
        assert any(p["id"] == profile_id for p in profiles)
        assert any(p["name"] == name for p in profiles)

        # Update profile
        new_name = "Updated Name"
        ctx.profiles.update(profile_id, {"name": new_name})
        updated = ctx.get_profile_by_id(profile_id)
        assert updated["name"] == new_name

        # Delete profile
        ctx.profiles.delete(profile_id)
        assert ctx.get_profile_by_id(profile_id) is None

    def test_subscription_crud(self, ctx):
        """Test CRUD for subscriptions."""
        name = "My Sub"
        url = "https://example.com/sub"

        # Save
        sub_id = ctx.subscriptions.save(name, url)
        assert sub_id is not None

        # Load
        subs = ctx.subscriptions.load_all()
        assert any(s["id"] == sub_id for s in subs)

        # Update data
        sub = ctx.subscriptions.load_all()[0]
        sub["last_updated"] = "2023-01-01"
        ctx.subscriptions.update(sub)

        updated_sub = ctx.subscriptions.load_all()[0]
        assert updated_sub["last_updated"] == "2023-01-01"

        # Delete
        ctx.subscriptions.delete(sub_id)
        assert len(ctx.subscriptions.load_all()) == 0

    def test_dns_config(self, ctx):
        """Test loading and saving DNS configuration."""
        dns_list = [{"address": "8.8.8.8", "protocol": "udp"}]
        ctx.dns.save(dns_list)

        loaded = ctx.dns.load()
        assert loaded == dns_list

    def test_routing_rules_persistence(self, ctx):
        """Test persistent storage of routing rules."""
        rules = {"direct": ["google.com"], "proxy": [], "block": []}
        ctx.routing.save_rules(rules)
        loaded = ctx.routing.load_rules()
        assert loaded["direct"] == ["google.com"]

    def test_routing_toggles(self, ctx):
        """Test setting and getting routing toggles."""
        ctx.routing.save_toggle("block_ads", True)
        toggles = ctx.routing.load_toggles()
        assert toggles["block_ads"] is True

    def test_settings_getters_setters(self, ctx):
        """Test all simple setting getter/setter pairs for coverage."""
        # Proxy Port
        ctx.settings.set_proxy_port(9999)
        assert ctx.settings.get_proxy_port() == 9999
        ctx.settings.set_proxy_port(500)  # Below MIN_PORT
        assert ctx.settings.get_proxy_port() == 9999

        # Routing Country
        ctx.settings.set_routing_country("ir")
        assert ctx.settings.get_routing_country() == "ir"
        ctx.settings.set_routing_country("invalid")  # Should be ignored or default
        assert ctx.settings.get_routing_country() == "ir"

        # Custom DNS
        ctx.settings.set_custom_dns("1.1.1.1")
        assert ctx.settings.get_custom_dns() == "1.1.1.1"

        # Connection Mode
        ctx.settings.set_connection_mode("proxy")
        assert ctx.settings.get_connection_mode() == "proxy"
        ctx.settings.set_connection_mode("invalid")
        assert ctx.settings.get_connection_mode() == "proxy"

        # Theme Mode
        ctx.settings.set_theme_mode("light")
        assert ctx.settings.get_theme_mode() == "light"

        # Sort Mode
        ctx.settings.set_sort_mode("ping_asc")
        assert ctx.settings.get_sort_mode() == "ping_asc"

        # Language
        ctx.settings.set_language("fa")
        assert ctx.settings.get_language() == "fa"

        # Remember Close
        ctx.settings.set_remember_close_choice(True)
        assert ctx.settings.get_remember_close_choice() is True

    def test_load_config_real_file(self, ctx, temp_config_dir):
        """Test load_config with a real file."""
        config_path = temp_config_dir / "real_config.json"
        test_data = {"outbounds": [{"protocol": "vless"}]}
        with open(config_path, "w") as f:
            json.dump(test_data, f)

        config, remove = ctx.load_config(str(config_path))
        assert config["outbounds"][0]["protocol"] == "vless"
        assert remove is False

        # Test bad JSON file
        bad_path = temp_config_dir / "bad.json"
        with open(bad_path, "w") as f:
            f.write("!!")
        config, remove = ctx.load_config(str(bad_path))
        assert config is None
        assert remove is True

    def test_get_profile_by_id_subscription(self, ctx):
        """Test getting a profile from a subscription."""
        sub_id = ctx.subscriptions.save("Sub", "url")
        sub_profile = {
            "id": "p1",
            "name": "S1",
            "config": {},
            "subscription_id": sub_id,
        }
        # Injects subscription data manually for testing retrieval
        subs = ctx.subscriptions.load_all()
        subs[0]["profiles"] = [sub_profile]
        ctx.subscriptions.update(subs[0])

        profile = ctx.get_profile_by_id("p1")
        assert profile is not None
        assert profile["name"] == "S1"
        assert profile["subscription_id"] == sub_id

    def test_last_selected_profile_id(self, ctx):
        """Test setting and getting last selected profile ID."""
        ctx.settings.set_last_selected_profile_id("test-id")
        assert ctx.settings.get_last_selected_profile_id() == "test-id"
        ctx.settings.set_last_selected_profile_id("")  # Should ignore
        assert ctx.settings.get_last_selected_profile_id() == "test-id"

    def test_dns_config_defaults(self, temp_config_dir):
        """Test that default DNS config is returned if file missing."""
        new_dir = temp_config_dir / "dns_test"
        new_dir.mkdir()
        recent_path = os.path.join(str(new_dir), "r.json")
        with patch("src.core.app_context.RECENT_FILES_PATH", recent_path):
            mgr = AppContext.create()
            dns = mgr.dns.load()
            assert len(dns) == 2
            assert dns[0]["address"] == "1.1.1.1"

    def test_routing_toggles_full(self, ctx):
        """Test all default routing toggles are present."""
        toggles = ctx.routing.load_toggles()
        assert "block_udp_443" in toggles
        assert "block_ads" in toggles
        assert "direct_private_ips" in toggles
        assert "direct_local_domains" in toggles

        ctx.routing.save_toggle("direct_private_ips", False)
        assert ctx.routing.load_toggles()["direct_private_ips"] is False

    def test_get_profile_precedence(self, ctx):
        """Test that local profiles take precedence or are searched first."""
        pid = "duplicate-id"
        ctx.profiles.save("Local", {"v": "local"})  # No profile_id arg in impl

        # Manually inject into subscription
        ctx.subscriptions.save("Sub", "url")
        subs = ctx.subscriptions.load_all()
        subs[0]["profiles"] = [{"id": pid, "name": "Sub", "config": {"v": "sub"}}]
        ctx.subscriptions.update(subs[0])

        # We need to find the ID of the local profile we just saved
        local_profiles = ctx.profiles.load_all()
        local_pid = local_profiles[0]["id"]

        # Injects subscription data with SAME ID for testing priority
        subs[0]["profiles"] = [{"id": local_pid, "name": "Sub", "config": {"v": "sub"}}]
        ctx.subscriptions.update(subs[0])

        profile = ctx.get_profile_by_id(local_pid)
        assert profile is not None
        # Should find local first
        assert profile["name"] == "Local"
