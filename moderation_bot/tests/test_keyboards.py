"""Тесты панели: callback_data, клавиатуры и текст панели."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from bot.callbacks import SettingsCallback
from bot.keyboards import build_settings_keyboard
from bot.models import TOGGLE_FIELDS
from bot.texts import help_text, settings_text


def test_callback_round_trip():
    packed = SettingsCallback(action="toggle", flag="block_hashtag").pack()
    parsed = SettingsCallback.unpack(packed)

    assert parsed.action == "toggle"
    assert parsed.flag == "block_hashtag"


def test_callback_without_flag():
    parsed = SettingsCallback.unpack(SettingsCallback(action="refresh").pack())

    assert parsed.action == "refresh"
    assert parsed.flag == ""


def test_keyboard_has_button_for_every_filter(settings, config):
    keyboard = build_settings_keyboard(settings, target_username="zaztagbot", banned_hashtag="#реклама")

    assert isinstance(keyboard, InlineKeyboardMarkup)
    rows = keyboard.inline_keyboard
    assert len(rows) == len(TOGGLE_FIELDS) + 1  # фильтры + ряд служебных кнопок

    packed_flags = [SettingsCallback.unpack(button.callback_data).flag for row in rows[:-1] for button in row]
    assert packed_flags == list(TOGGLE_FIELDS)
    assert [button.callback_data for button in rows[-1]] == [
        SettingsCallback(action="refresh").pack(),
        SettingsCallback(action="reset").pack(),
    ]


def test_keyboard_marks_enabled_filters(settings, config):
    settings = settings.with_flag("block_hashtag", False)
    keyboard = build_settings_keyboard(settings, target_username="zaztagbot", banned_hashtag="#реклама")

    texts = {SettingsCallback.unpack(row[0].callback_data).flag: row[0].text for row in keyboard.inline_keyboard[:-1]}

    assert texts["block_target_user"].startswith("✅")
    assert texts["block_hashtag"].startswith("❌")
    assert "zaztagbot" in texts["block_target_user"]
    assert "#реклама" in texts["block_hashtag"]


def test_keyboard_uses_configured_values(settings, config):
    keyboard = build_settings_keyboard(settings, target_username="adbot", banned_hashtag="#спам")
    texts = [row[0].text for row in keyboard.inline_keyboard[:-1]]

    assert any("adbot" in text for text in texts)
    assert any("#спам" in text for text in texts)


def test_settings_text_shows_state(settings, config):
    text = settings_text(settings, config)

    assert "Модерация группы" in text
    assert str(settings.chat_id) in text
    assert "3 из 4" in text  # по умолчанию включены 3 фильтра из 4
    assert "<b>" in text


def test_settings_text_reflects_configured_target(settings, config):
    text = settings_text(settings, config)

    assert config.target_username in text
    assert config.banned_hashtag in text


def test_help_text_mentions_commands(config):
    text = help_text(config)

    assert "/settings" in text
    assert "/help" in text
    assert config.target_username in text
