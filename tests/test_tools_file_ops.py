"""
Tests for h_agent.tools.file_ops module.
"""
import os
import tempfile
import pytest

from h_agent.tools.file_ops import (
    tool_file_read,
    tool_file_write,
    tool_file_edit,
    tool_file_glob,
    tool_file_exists,
    tool_file_info,
    TOOL_HANDLERS,
)


class TestToolFileRead:
    """file_read tool tests."""

    def test_read_existing_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        result = tool_file_read(str(test_file))
        assert "Hello, World!" in result

    def test_read_nonexistent_file(self, tmp_path):
        result = tool_file_read(str(tmp_path / "nonexistent.txt"))
        assert "Error" in result or "not found" in result.lower()

    def test_read_with_offset(self, tmp_path):
        test_file = tmp_path / "multiline.txt"
        test_file.write_text("line1\nline2\nline3\n")
        result = tool_file_read(str(test_file), offset=2)
        assert "line2" in result

    def test_read_with_limit(self, tmp_path):
        test_file = tmp_path / "multiline.txt"
        test_file.write_text("line1\nline2\nline3\n")
        result = tool_file_read(str(test_file), limit=2)
        # Should contain context header or first 2 lines
        assert "line1" in result

    def test_read_directory_error(self, tmp_path):
        result = tool_file_read(str(tmp_path))
        assert "Error" in result or "directory" in result.lower()


class TestToolFileWrite:
    """file_write tool tests."""

    def test_write_new_file(self, tmp_path):
        test_file = tmp_path / "written.txt"
        result = tool_file_write(str(test_file), "New content here")
        assert "Wrote" in result or "success" in result.lower()
        assert test_file.read_text() == "New content here"

    def test_write_creates_parent_dirs(self, tmp_path):
        test_file = tmp_path / "subdir" / "nested" / "file.txt"
        result = tool_file_write(str(test_file), "Deep content")
        assert "Wrote" in result or "success" in result.lower()
        assert test_file.exists()

    def test_append_mode(self, tmp_path):
        test_file = tmp_path / "append.txt"
        test_file.write_text("Original")
        tool_file_write(str(test_file), " Appended", append=True)
        assert test_file.read_text() == "Original Appended"


class TestToolFileEdit:
    """file_edit tool tests."""

    def test_edit_exact_match(self, tmp_path):
        test_file = tmp_path / "editable.txt"
        test_file.write_text("Hello, World!")
        result = tool_file_edit(str(test_file), "World", "Ekko")
        assert "success" in result.lower() or "edited" in result.lower()
        assert test_file.read_text() == "Hello, Ekko!"

    def test_edit_text_not_found(self, tmp_path):
        test_file = tmp_path / "editable.txt"
        test_file.write_text("Hello")
        result = tool_file_edit(str(test_file), "NonExistent", "Replaced")
        assert "Error" in result or "not found" in result.lower()

    def test_edit_multiple_occurrences_error(self, tmp_path):
        test_file = tmp_path / "editable.txt"
        test_file.write_text("foo bar foo")
        result = tool_file_edit(str(test_file), "foo", "baz")
        assert "multiple" in result.lower() or "Error" in result

    def test_edit_nonexistent_file(self, tmp_path):
        result = tool_file_edit(str(tmp_path / "nonexistent.txt"), "a", "b")
        assert "Error" in result or "not found" in result.lower()


class TestToolFileGlob:
    """file_glob tool tests."""

    def test_glob_finds_files(self, tmp_path):
        (tmp_path / "a.py").touch()
        (tmp_path / "b.py").touch()
        result = tool_file_glob("*.py", str(tmp_path), recursive=False)
        assert "a.py" in result
        assert "b.py" in result

    def test_glob_no_matches(self, tmp_path):
        result = tool_file_glob("*.xyz", str(tmp_path))
        assert "No files found" in result

    def test_glob_recursive(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "deep.py").touch()
        result = tool_file_glob("*.py", str(tmp_path), recursive=True)
        assert "deep.py" in result


class TestToolFileExists:
    """file_exists tool tests."""

    def test_exists_file(self, tmp_path):
        test_file = tmp_path / "exists.txt"
        test_file.touch()
        result = tool_file_exists(str(test_file))
        assert "True" in result

    def test_exists_directory(self, tmp_path):
        result = tool_file_exists(str(tmp_path))
        assert "True" in result

    def test_not_exists(self, tmp_path):
        result = tool_file_exists(str(tmp_path / "nonexistent"))
        assert "False" in result


class TestToolFileInfo:
    """file_info tool tests."""

    def test_file_info_basic(self, tmp_path):
        test_file = tmp_path / "info.txt"
        test_file.write_text("Hello!")
        result = tool_file_info(str(test_file))
        assert "info.txt" in result
        assert "bytes" in result

    def test_file_info_with_checksum(self, tmp_path):
        test_file = tmp_path / "info.txt"
        test_file.write_text("Hello!")
        result = tool_file_info(str(test_file), checksum=True)
        assert "md5" in result.lower()

    def test_file_info_nonexistent(self, tmp_path):
        result = tool_file_info(str(tmp_path / "nonexistent"))
        assert "Error" in result or "not found" in result.lower()
