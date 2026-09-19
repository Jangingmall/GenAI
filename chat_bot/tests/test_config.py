"""Configuration tests for Kubernetes Secret file support."""

import pytest

from app import config


def test_db_password_file_takes_precedence(monkeypatch, tmp_path):
    secret = tmp_path / "password"
    secret.write_text("from-file\n", encoding="utf-8")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(secret))
    monkeypatch.setenv("DB_PASSWORD", "from-env")

    assert config._read_db_password() == "from-file"


def test_db_password_file_missing_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PASSWORD_FILE", str(tmp_path / "missing"))

    with pytest.raises(RuntimeError, match="DB_PASSWORD_FILE"):
        config._read_db_password()


def test_db_password_env_is_fallback(monkeypatch):
    monkeypatch.delenv("DB_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("DB_PASSWORD", "from-env")

    assert config._read_db_password() == "from-env"
