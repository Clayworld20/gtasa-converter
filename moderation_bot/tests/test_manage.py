"""Тесты CLI (`manage.py`): настройка без Telegram и демонстрация правил."""

from __future__ import annotations

import asyncio

import pytest

import manage
from bot.config import Config, load_config
from tests.conftest import CHAT_ID

TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"


async def test_demo_shows_decisions(config: Config, capsys):
    code = await manage._cmd_demo(config, None)

    out = capsys.readouterr().out
    assert code == 0
    assert "Демонстрация правил" in out
    assert "УДАЛИТЬ" in out
    assert "оставить" in out


async def test_demo_uses_chat_settings(config: Config, capsys):
    await manage._cmd_set(config, CHAT_ID, "block_target_user", False)

    await manage._cmd_demo(config, CHAT_ID)

    out = capsys.readouterr().out
    assert f"настройки чата {CHAT_ID}" in out


async def test_set_and_show(config: Config, capsys):
    await manage._cmd_set(config, CHAT_ID, "block_hashtag", False)
    await manage._cmd_show(config, CHAT_ID)

    out = capsys.readouterr().out
    assert "Обновлено: block_hashtag -> выкл" in out
    assert "❌ выкл  block_hashtag" in out


async def test_show_on_empty_database(config: Config, capsys):
    await manage._cmd_show(config, CHAT_ID)

    assert "включено 3 из 4" in capsys.readouterr().out


async def test_list_without_settings(config: Config, capsys):
    await manage._cmd_list(config)

    assert "В базе пока нет настроек" in capsys.readouterr().out


async def test_list_after_change(config: Config, capsys):
    await manage._cmd_set(config, CHAT_ID, "block_hashtag", True)

    await manage._cmd_list(config)

    assert str(CHAT_ID) in capsys.readouterr().out


def test_main_demo(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "cli.sqlite3"))

    assert manage.main(["demo"]) == 0
    assert "Демонстрация правил" in capsys.readouterr().out


def test_main_rejects_invalid_value(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "cli.sqlite3"))

    assert manage.main(["set", "--chat", str(CHAT_ID), "--flag", "block_hashtag", "--value", "может"]) == 2
    assert "используйте on/off" in capsys.readouterr().err


def test_main_reports_config_error(monkeypatch, capsys):
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    assert manage.main(["list"]) == 2
    assert "BOT_TOKEN" in capsys.readouterr().err


@pytest.mark.parametrize(("value", "expected"), [("вкл", True), ("off", False), ("да", True), ("нет", False)])
def test_main_parses_flag_values(monkeypatch, tmp_path, value: str, expected: bool):
    """`main()` понимает и английские, и русские значения on/off."""
    db_path = tmp_path / "cli.sqlite3"
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("VERBOSE_LOG", "false")

    code = manage.main(["set", "--chat", str(CHAT_ID), "--flag", "block_media_non_admin", "--value", value])
    assert code == 0

    async def read_flag() -> bool:
        config = load_config(env_file=None)
        return (await manage._with_repository(config, lambda repo: repo.get(CHAT_ID))).block_media_non_admin

    assert asyncio.run(read_flag()) is expected
