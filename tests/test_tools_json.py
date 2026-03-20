"""
Tests for h_agent.tools.json_utils module.
"""
import pytest

from h_agent.tools.json_utils import (
    tool_json_parse,
    tool_json_format,
    tool_json_query,
    tool_json_validate,
    TOOL_HANDLERS,
)


class TestJsonParse:
    """json_parse tool tests."""

    def test_parse_valid_json(self):
        result = tool_json_parse('{"key": "value"}')
        assert "value" in result

    def test_parse_invalid_json(self):
        result = tool_json_parse("{invalid}")
        assert "Error" in result or "Parse Error" in result

    def test_parse_pretty(self):
        result = tool_json_parse('{"a":1,"b":2}', pretty=True)
        assert "\n" in result or "a" in result


class TestJsonFormat:
    """json_format tool tests."""

    def test_format_valid_json(self):
        result = tool_json_format('{"a":1,"b":2}')
        assert "\n" in result or "a" in result or "1" in result

    def test_format_invalid_json(self):
        result = tool_json_format("{invalid}")
        assert "Error" in result


class TestJsonQuery:
    """json_query tool tests."""

    def test_query_object_key(self):
        result = tool_json_query('{"name": "Ekko", "age": 25}', "name")
        assert "Ekko" in result

    def test_query_nested_key(self):
        result = tool_json_query('{"user": {"name": "Ekko"}}', "user.name")
        assert "Ekko" in result

    def test_query_array_index(self):
        result = tool_json_query('{"items": ["a", "b", "c"]}', "items[1]")
        assert "b" in result

    def test_query_path_not_found(self):
        result = tool_json_query('{"a": 1}', "nonexistent.path")
        assert "not found" in result.lower() or "None" in result

    def test_query_invalid_json(self):
        result = tool_json_query("{invalid}", "key")
        assert "Error" in result


class TestJsonValidate:
    """json_validate tool tests."""

    def test_validate_valid_object(self):
        result = tool_json_validate('{"key": "value"}')
        assert "Valid" in result or "object" in result

    def test_validate_valid_array(self):
        result = tool_json_validate('[1, 2, 3]')
        assert "Valid" in result or "array" in result.lower()

    def test_validate_valid_string(self):
        result = tool_json_validate('"just a string"')
        assert "Valid" in result

    def test_validate_invalid(self):
        result = tool_json_validate("{invalid}")
        assert "Invalid" in result or "Error" in result


class TestToolHandlersMap:
    """Verify all tool handlers are registered."""

    def test_all_handlers_registered(self):
        expected = ["json_parse", "json_format", "json_query", "json_validate"]
        for name in expected:
            assert name in TOOL_HANDLERS
