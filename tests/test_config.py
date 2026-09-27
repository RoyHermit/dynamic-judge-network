"""Tests for typed Settings loading. Uses MOCK_API_KEY placeholders only —
never a real secret (project CLAUDE.md security rules)."""

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_load_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "MOCK_API_KEY")
    settings = Settings.load()
    assert settings.typesafe_api_key == "MOCK_API_KEY"


def test_settings_load_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings.load()


def test_settings_load_raises_when_api_key_empty(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    with pytest.raises(ValidationError):
        Settings.load()
