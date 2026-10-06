"""Тесты CLI (`manage.py`): настройка без Telegram и демонстрация правил."""

from __future__ import annotations

import asyncio

import pytest

import manage
from bot import config as bot_config
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


# --------------------------------------------------------------------- #
# selftest
# --------------------------------------------------------------------- #
async def test_selftest_offline_without_token(monkeypatch, tmp_path, capsys):
    """Без токена selftest не падает, а перечисляет, что осталось сделать."""
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "selftest.sqlite3"))

    code = await manage._cmd_selftest(offline=True)

    out = capsys.readouterr().out
    assert code == 1
    assert "Python" in out
    assert "aiogram" in out
    assert "BOT_TOKEN" in out
    assert "База данных доступна" in out
    assert "Что осталось сделать" in out


async def test_selftest_offline_with_token_is_ok(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "selftest.sqlite3"))
    monkeypatch.setenv("VERBOSE_LOG", "false")

    code = await manage._cmd_selftest(offline=True)

    out = capsys.readouterr().out
    assert code == 0
    assert "BOT_TOKEN задан" in out
    assert "@zaztagbot" in out
    assert "#реклама" in out
    assert "Всё готово" in out
    assert "Проверка связи с Telegram пропущена" in out


async def test_selftest_creates_database_file(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "nested" / "selftest.sqlite3"
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setenv("DB_PATH", str(db_path))

    await manage._cmd_selftest(offline=True)
    capsys.readouterr()

    assert db_path.exists()


async def test_selftest_warns_about_bad_username(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "selftest.sqlite3"))
    monkeypatch.setenv("TARGET_USERNAME", "zaz tag bot!")

    code = await manage._cmd_selftest(offline=True)

    out = capsys.readouterr().out
    assert code == 1
    assert "не похож на @username" in out


async def test_selftest_accepts_valid_username(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "selftest.sqlite3"))
    monkeypatch.setenv("TARGET_USERNAME", "@ZazTagBot")

    code = await manage._cmd_selftest(offline=True)

    out = capsys.readouterr().out
    assert code == 0
    assert "@zaztagbot" in out


def test_main_selftest_offline(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "selftest.sqlite3"))

    assert manage.main(["selftest", "--offline"]) == 0
    assert "Всё готово" in capsys.readouterr().out


def test_main_selftest_without_token_returns_one(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "selftest.sqlite3"))
    # Чтобы не подхватить реальный .env проекта, уводим PROJECT_ROOT в пустой каталог.
    monkeypatch.setattr(manage, "PROJECT_ROOT", tmp_path)

    assert manage.main(["selftest", "--offline"]) == 1
    assert "Что осталось сделать" in capsys.readouterr().out


# --------------------------------------------------------------------- #
# Путь к .env и базе не зависит от текущего каталога
# --------------------------------------------------------------------- #
def test_load_config_reads_env_next_to_project(monkeypatch, tmp_path):
    """load_config() без аргументов находит `.env` рядом с проектом, а не в текущем каталоге."""
    env_file = tmp_path / ".env"
    env_file.write_text("BOT_TOKEN=" + TOKEN + "\nTARGET_USERNAME=SomeBot\n", encoding="utf-8")
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("TARGET_USERNAME", raising=False)
    # Подменяем «каталог проекта» целиком, чтобы тест не зависел от реального .env.
    monkeypatch.setattr(bot_config, "PROJECT_ROOT", tmp_path)

    config = load_config()

    assert config.bot_token == TOKEN
    assert config.target_username == "somebot"


def test_resolve_db_path_is_absolute():
    from bot.config import PROJECT_ROOT, resolve_db_path

    assert resolve_db_path("data/x.sqlite3") == (PROJECT_ROOT / "data" / "x.sqlite3").resolve()


def test_env_values_win_over_env_file(monkeypatch, tmp_path):
    """Переменные окружения процесса приоритетнее файла .env."""
    env_file = tmp_path / ".env"
    env_file.write_text("BOT_TOKEN=123456789:FromFileTokenAAAAAAAAAAAAAAAAAAAA\n", encoding="utf-8")
    monkeypatch.setenv("BOT_TOKEN", TOKEN)

    assert load_config(env_file=env_file).bot_token == TOKEN
