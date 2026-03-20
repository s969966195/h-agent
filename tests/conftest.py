"""
Pytest configuration and shared fixtures.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Set test environment variables
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_API_BASE", "http://localhost:8000")
os.environ.setdefault("MODEL_ID", "test-model")


@pytest.fixture
def tmp_path(tmp_path_factory):
    """Provide a temporary directory for tests."""
    return tmp_path_factory.mktemp("h_agent_test")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure each test has a clean environment."""
    # Don't modify os.environ directly, just ensure test vars are set
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_BASE", "http://localhost:8000")
    monkeypatch.setenv("MODEL_ID", "test-model")
