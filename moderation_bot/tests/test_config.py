"""Тесты конфигурации: чтение .env, нормализация значений, понятные ошибки."""

from __future__ import annotations

import pytest

from bot.config import DEFAULT_DB_PATH, Config, ConfigError, load_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Изолируем тесты от переменных окружения окружения."""
    for name in (
        "BOT_TOKEN",
        "TARGET_USERNAME",
        "BANNED_HASHTAG",
        "ALLOWED_CHAT_ID",
        "DB_PATH",
        "ADMIN_CACHE_TTL",
        "NOTIFY_ON_DELETE",
        "VERBOSE_LOG",
        "FORWARD_DELETED_TO_LOG",
        "LOG_CHAT_ID",
    ):
        monkeypatch.delenv(name, raising=False)


def test_missing_token_raises(monkeypatch):
    with pytest.raises(ConfigError, match="BOT_TOKEN"):
        load_config(env_file=None)


def test_placeholder_token_raises(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456789:REPLACE_WITH_YOUR_TOKEN")

    with pytest.raises(ConfigError, match="BOT_TOKEN"):
        load_config(env_file=None)


def test_token_without_colon_raises(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "нет-двоеточия")

    with pytest.raises(ConfigError, match="выглядит некорректно"):
        load_config(env_file=None)


def test_defaults(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")

    config = load_config(env_file=None)

    assert isinstance(config, Config)
    assert config.target_username == "zaztagbot"
    assert config.banned_hashtag == "#реклама"
    assert config.hashtag_needle == "#реклама"
    assert config.allowed_chat_id is None
    assert config.db_path == DEFAULT_DB_PATH
    assert config.admin_cache_ttl == 300.0
    assert config.notify_on_delete is True


def test_custom_values(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
    monkeypatch.setenv("TARGET_USERNAME", "@SomeAdBot")
    monkeypatch.setenv("BANNED_HASHTAG", "# РЕКЛАМА")
    monkeypatch.setenv("ALLOWED_CHAT_ID", "-1001234567890")
    monkeypatch.setenv("ADMIN_CACHE_TTL", "0")
    monkeypatch.setenv("NOTIFY_ON_DELETE", "false")
    monkeypatch.setenv("LOG_CHAT_ID", "-100777")

    config = load_config(env_file=None)

    assert config.target_username == "someadbot"  # @ убран, регистр приведён
    assert config.hashtag_needle == "#реклама"  # пробелы убраны
    assert config.allowed_chat_id == -1001234567890
    assert config.admin_cache_ttl == 0.0
    assert config.notify_on_delete is False
    assert config.log_chat_id == -100777


def test_invalid_int_raises(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
    monkeypatch.setenv("ALLOWED_CHAT_ID", "не число")

    with pytest.raises(ConfigError, match="целым числом"):
        load_config(env_file=None)


def test_db_path_relative_to_project_root(monkeypatch, tmp_path, config):
    monkeypatch.setenv("BOT_TOKEN", "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
    monkeypatch.setenv("DB_PATH", "data/custom.sqlite3")

    loaded = load_config(env_file=None)

    assert loaded.db_path.is_absolute()
    assert loaded.db_path.name == "custom.sqlite3"
