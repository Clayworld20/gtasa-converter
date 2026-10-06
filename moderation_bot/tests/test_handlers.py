"""Интеграционные тесты: реальный Dispatcher, роутеры и хэндлеры + поддельный Bot.

Проверяют именно склейку: доступ к `/settings`, инлайн-кнопки, удаление
сообщений через настоящий `aiogram.Message` и обработку апдейтов с наручниками.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from aiogram.types import CallbackQuery, Update, User

from bot.app import AppContext, build_app
from bot.callbacks import SettingsCallback
from bot.models import TOGGLE_FIELDS
from tests.conftest import CHAT_ID, fake_photo, make_message
from tests.fakes import BOT_ID, FakeBot

ADMIN_ID = 555
USER_ID = 42


@pytest.fixture
async def app(config, fake_bot: FakeBot):
    """Полностью собранное приложение, но с поддельным ботом."""
    application = await build_app(config, bot=fake_bot)  # type: ignore[arg-type]
    yield application
    await application.shutdown()


def _update(update_id: int, **payload) -> Update:
    return Update(update_id=update_id, **payload)


def _callback(callback_data: str, *, message, user_id: int = ADMIN_ID, update_id: int = 100) -> Update:
    """Апдейт-нажатие на инлайн-кнопку панели."""
    callback = CallbackQuery(
        id=f"cb-{update_id}",
        from_user=User(id=user_id, is_bot=False, first_name="Тест"),
        chat_instance="chat-instance",
        message=message,
        data=callback_data,
    )
    return _update(update_id, callback_query=callback)


async def test_settings_panel_is_sent_to_admin(app: AppContext, fake_bot: FakeBot):
    message = make_message(text="/settings", user_id=ADMIN_ID, username="admin")

    await app.dispatcher.feed_update(fake_bot, _update(1, message=message))

    panels = fake_bot.panels()
    assert len(panels) == 1
    assert len(panels[0].inline_keyboard) == len(TOGGLE_FIELDS) + 1


async def test_settings_is_denied_for_non_admin(app: AppContext, fake_bot: FakeBot):
    message = make_message(text="/settings", user_id=USER_ID, username="user")

    await app.dispatcher.feed_update(fake_bot, _update(2, message=message))

    assert fake_bot.panels() == []
    assert any("⛔" in text for text in fake_bot.sent_texts)


async def test_help_command_works(app: AppContext, fake_bot: FakeBot):
    message = make_message(text="/help", user_id=USER_ID, username="user")

    await app.dispatcher.feed_update(fake_bot, _update(3, message=message))

    assert any("/settings" in text for text in fake_bot.sent_texts)


async def test_settings_in_private_chat_explains_usage(app: AppContext, fake_bot: FakeBot):
    message = make_message(text="/settings", chat_type="private", chat_id=USER_ID, user_id=USER_ID)

    await app.dispatcher.feed_update(fake_bot, _update(4, message=message))

    assert fake_bot.panels() == []
    assert any("Добавьте его в группу" in text for text in fake_bot.sent_texts)


async def test_toggle_button_updates_settings_and_panel(app: AppContext, fake_bot: FakeBot):
    panel = make_message(text="панель", user_id=BOT_ID, is_bot=True, message_id=555)
    callback_update = _callback(SettingsCallback(action="toggle", flag="block_hashtag").pack(), message=panel)

    await app.dispatcher.feed_update(fake_bot, callback_update)

    settings = await app.settings_service.get(CHAT_ID)
    assert settings.block_hashtag is False
    assert fake_bot.answered[-1]["text"] is not None
    assert "выключено" in fake_bot.answered[-1]["text"]
    assert fake_bot.edited
    assert "Модерация группы" in fake_bot.edited[-1]["text"]


async def test_toggle_button_is_denied_for_non_admin(app: AppContext, fake_bot: FakeBot):
    panel = make_message(text="панель", user_id=BOT_ID, is_bot=True, message_id=556)
    callback_update = _callback(
        SettingsCallback(action="toggle", flag="block_hashtag").pack(), message=panel, user_id=USER_ID
    )
    before = await app.settings_service.get(CHAT_ID)

    await app.dispatcher.feed_update(fake_bot, callback_update)

    after = await app.settings_service.get(CHAT_ID)
    assert after == before
    assert fake_bot.answered[-1]["show_alert"] is True
    assert fake_bot.edited == []


async def test_refresh_button_rerenders_panel(app: AppContext, fake_bot: FakeBot):
    panel = make_message(text="панель", user_id=BOT_ID, is_bot=True, message_id=557)
    callback_update = _callback(SettingsCallback(action="refresh").pack(), message=panel)

    await app.dispatcher.feed_update(fake_bot, callback_update)

    assert fake_bot.edited
    assert "Модерация группы" in fake_bot.edited[-1]["text"]


async def test_reset_button_restores_defaults(app: AppContext, fake_bot: FakeBot):
    await app.settings_service.toggle(CHAT_ID, "block_hashtag", user_id=ADMIN_ID)
    panel = make_message(text="панель", user_id=BOT_ID, is_bot=True, message_id=558)
    callback_update = _callback(SettingsCallback(action="reset").pack(), message=panel)

    await app.dispatcher.feed_update(fake_bot, callback_update)

    settings = await app.settings_service.get(CHAT_ID)
    assert settings.block_hashtag is True
    assert "по умолчанию" in fake_bot.answered[-1]["text"]


async def test_hashtag_message_is_deleted_end_to_end(app: AppContext, fake_bot: FakeBot):
    message = make_message(text="Покупайте! #реклама", user_id=USER_ID, username="spammer", message_id=600)

    await app.dispatcher.feed_update(fake_bot, _update(5, message=message))

    assert fake_bot.deleted_ids == [600]


async def test_target_bot_message_is_deleted_end_to_end(app: AppContext, fake_bot: FakeBot):
    message = make_message(text="Реклама канала", username="ZazTagBot", is_bot=True, user_id=999, message_id=601)

    await app.dispatcher.feed_update(fake_bot, _update(6, message=message))

    assert fake_bot.deleted_ids == [601]


async def test_photo_is_deleted_end_to_end_when_rule_enabled(app: AppContext, fake_bot: FakeBot):
    await app.settings_service.toggle(CHAT_ID, "block_media_non_admin", user_id=ADMIN_ID)
    message = make_message(photo=fake_photo(), username="user", user_id=USER_ID, message_id=602)

    await app.dispatcher.feed_update(fake_bot, _update(7, message=message))

    assert fake_bot.deleted_ids == [602]


async def test_regular_message_is_kept_end_to_end(app: AppContext, fake_bot: FakeBot):
    message = make_message(text="Привет, как дела?", user_id=USER_ID, username="friend", message_id=603)

    await app.dispatcher.feed_update(fake_bot, _update(8, message=message))

    assert fake_bot.deleted_ids == []


async def test_settings_command_is_not_treated_as_rule_violation(app: AppContext, fake_bot: FakeBot):
    """Команду администратора модерация не трогает."""
    message = make_message(text="/settings", user_id=ADMIN_ID, username="admin", message_id=604)

    await app.dispatcher.feed_update(fake_bot, _update(9, message=message))

    assert fake_bot.deleted_ids == []
    assert fake_bot.panels()  # панель отправлена


async def test_whitelist_blocks_other_chats(config, fake_bot: FakeBot):
    """С ALLOWED_CHAT_ID бот игнорирует остальные группы."""
    restricted = replace(config, allowed_chat_id=CHAT_ID)
    application = await build_app(restricted, bot=fake_bot)  # type: ignore[arg-type]
    try:
        foreign = make_message(text="#реклама", chat_id=-1009999, user_id=USER_ID, message_id=605)
        await application.dispatcher.feed_update(fake_bot, _update(10, message=foreign))
        own = make_message(text="#реклама", chat_id=CHAT_ID, user_id=USER_ID, message_id=606)
        await application.dispatcher.feed_update(fake_bot, _update(11, message=own))
    finally:
        await application.shutdown()

    assert fake_bot.deleted_ids == [606]


async def test_private_message_is_never_deleted(app: AppContext, fake_bot: FakeBot):
    message = make_message(text="#реклама", chat_type="private", chat_id=USER_ID, user_id=USER_ID, message_id=607)

    await app.dispatcher.feed_update(fake_bot, _update(12, message=message))

    assert fake_bot.deleted_ids == []
