"""
Tests for h_agent.plugins module.
"""
import os
import pytest

os.environ["OPENAI_API_KEY"] = "test"
os.environ["OPENAI_API_BASE"] = "http://localhost:8000"
os.environ["MODEL_ID"] = "test-model"

from h_agent.plugins import (
    Plugin,
    load_plugin,
    load_all_plugins,
    get_plugin,
    list_plugins,
    enable_plugin,
    disable_plugin,
    get_enabled_tools,
    get_enabled_handlers,
    _discover_plugins,
)


class TestPluginSystem:
    """Plugin system tests."""

    def test_plugin_dataclass(self):
        plugin = Plugin(
            name="test-plugin",
            version="0.1.0",
            description="A test plugin",
            author="tester",
        )
        assert plugin.name == "test-plugin"
        assert plugin.version == "0.1.0"
        assert plugin.enabled is True
        assert plugin.to_dict()["name"] == "test-plugin"

    def test_discover_plugins(self):
        plugins = _discover_plugins()
        assert isinstance(plugins, list)

    def test_load_all_plugins(self):
        plugins = load_all_plugins()
        assert isinstance(plugins, dict)

    def test_get_plugin_not_found(self):
        result = get_plugin("nonexistent-plugin-xyz")
        assert result is None

    def test_list_plugins(self):
        plugins = list_plugins()
        assert isinstance(plugins, list)

    def test_enable_disable_plugin(self):
        # Load all first
        load_all_plugins()
        # Try to enable/disable a non-existent plugin (should return False)
        result = enable_plugin("nonexistent-plugin-xyz")
        assert result is False

    def test_get_enabled_tools(self):
        tools = get_enabled_tools()
        assert isinstance(tools, list)

    def test_get_enabled_handlers(self):
        handlers = get_enabled_handlers()
        assert isinstance(handlers, dict)
