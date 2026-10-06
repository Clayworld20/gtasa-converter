"""Тесты сервиса модерации: реальные сообщения aiogram + поддельный Bot."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from bot import services as services_module
from bot.database import SettingsRepository
from bot.services import ModerationService, is_group_chat
from tests.conftest import CHAT_ID, fake_photo, make_message
from tests.fakes import BOT_ID, FakeBot


def _message(fake_bot: FakeBot, **kwargs):
    """Сообщение, «привязанное» к поддельному боту: message.delete() работает."""
    return make_message(bot=fake_bot, **kwargs)


async def test_target_user_message_is_deleted(moderation_service: ModerationService, fake_bot: FakeBot):
    message = _message(fake_bot, text="купите курс", username="ZazTagBot", is_bot=True, message_id=11)

    decision = await moderation_service.handle_message(message)

    assert decision is not None
    assert decision.should_delete
    assert fake_bot.deleted_ids == [11]


async def test_hashtag_message_is_deleted(moderation_service: ModerationService, fake_bot: FakeBot):
    message = _message(fake_bot, text="Срочно! #реклама курса", username="spammer", message_id=12)

    decision = await moderation_service.handle_message(message)

    assert decision is not None
    assert decision.should_delete
    assert (CHAT_ID, 12) in fake_bot.deleted


async def test_regular_text_is_kept(moderation_service: ModerationService, fake_bot: FakeBot):
    message = _message(fake_bot, text="Привет всем!", username="friend", message_id=13)

    decision = await moderation_service.handle_message(message)

    assert decision is not None
    assert not decision.should_delete
    assert fake_bot.deleted == []


async def test_photo_from_non_admin_deleted_when_rule_enabled(
    moderation_service: ModerationService, repository: SettingsRepository, fake_bot: FakeBot
):
    await repository.set_flag(CHAT_ID, "block_media_non_admin", True)
    message = _message(fake_bot, photo=fake_photo(), username="user", message_id=14)

    decision = await moderation_service.handle_message(message)

    assert decision is not None
    assert decision.should_delete
    assert fake_bot.deleted_ids == [14]


async def test_photo_from_admin_kept(
    moderation_service: ModerationService, repository: SettingsRepository, fake_bot: FakeBot
):
    await repository.set_flag(CHAT_ID, "block_media_non_admin", True)
    message = _message(fake_bot, photo=fake_photo(), username="admin", user_id=555, message_id=15)

    decision = await moderation_service.handle_message(message)

    assert decision is not None
    assert not decision.should_delete
    assert fake_bot.deleted == []


async def test_photo_from_target_deleted(
    moderation_service: ModerationService, repository: SettingsRepository, fake_bot: FakeBot
):
    await repository.set_flag(CHAT_ID, "block_target_user", False)
    await repository.set_flag(CHAT_ID, "block_hashtag", False)
    message = _message(fake_bot, photo=fake_photo(), username="zaztagbot", is_bot=True, message_id=16)

    decision = await moderation_service.handle_message(message)

    assert decision is not None
    assert decision.should_delete
    # Статус администратора для target-бота не запрашивается — экономим вызовы API.
    assert (CHAT_ID, BOT_ID) not in fake_bot.member_requests
    assert fake_bot.deleted_ids == [16]


async def test_admin_status_checked_only_when_media_rules_enabled(
    moderation_service: ModerationService, repository: SettingsRepository, fake_bot: FakeBot
):
    await repository.set_flag(CHAT_ID, "block_media_non_admin", False)
    message = _message(fake_bot, text="обычный текст", username="user", message_id=17)

    await moderation_service.handle_message(message)

    assert fake_bot.member_requests == []


async def test_private_chat_is_ignored(moderation_service: ModerationService, fake_bot: FakeBot):
    message = _message(fake_bot, text="#реклама", chat_type="private", chat_id=42, message_id=18)

    assert await moderation_service.handle_message(message) is None
    assert fake_bot.deleted == []


async def test_own_messages_are_ignored(moderation_service: ModerationService, fake_bot: FakeBot):
    message = _message(fake_bot, text="#реклама", user_id=BOT_ID, message_id=19)

    assert await moderation_service.handle_message(message) is None
    assert fake_bot.deleted == []


async def test_anonymous_messages_are_ignored(moderation_service: ModerationService, fake_bot: FakeBot):
    message = _message(fake_bot, text="#реклама", from_user=False, message_id=20)

    assert await moderation_service.handle_message(message) is None


async def test_all_filters_off_means_no_deletion(
    moderation_service: ModerationService, repository: SettingsRepository, fake_bot: FakeBot
):
    from bot.models import TOGGLE_FIELDS

    for flag in TOGGLE_FIELDS:
        await repository.set_flag(CHAT_ID, flag, False)
    message = _message(fake_bot, text="#реклама", photo=fake_photo(), username="zaztagbot", is_bot=True, message_id=21)

    decision = await moderation_service.handle_message(message)

    assert decision is not None
    assert not decision.should_delete
    assert fake_bot.deleted == []


async def test_notice_is_sent_and_cleaned_up(
    fake_bot: FakeBot, repository: SettingsRepository, moderator, config, monkeypatch
):
    """С включёнными уведомлениями бот отвечает и убирает своё сообщение."""
    monkeypatch.setattr(services_module, "NOTICE_TTL_SECONDS", 0.05)
    config = replace(config, notify_on_delete=True)
    service = ModerationService(bot=fake_bot, repository=repository, moderator=moderator, config=config)
    message = _message(fake_bot, text="#реклама", username="spammer", message_id=22)

    await service.handle_message(message)
    await asyncio.sleep(0.25)

    assert fake_bot.deleted_ids[0] == 22  # удалено исходное сообщение
    assert len(fake_bot.deleted_ids) == 2  # следом убрано уведомление
    assert any("Удалено" in text for text in fake_bot.sent_texts)
    await service.shutdown()


async def test_deleted_message_is_mirrored_to_log_chat(
    fake_bot: FakeBot, repository: SettingsRepository, moderator, config
):
    config = replace(config, forward_deleted_to_log=True, log_chat_id=-100777)
    service = ModerationService(bot=fake_bot, repository=repository, moderator=moderator, config=config)
    message = _message(fake_bot, text="#реклама", username="spammer", message_id=23)

    await service.handle_message(message)

    assert fake_bot.forwarded == [{"chat_id": -100777, "from_chat_id": CHAT_ID, "message_id": 23}]
    assert fake_bot.deleted_ids == [23]
    await service.shutdown()


async def test_delete_failure_is_logged_not_raised(moderation_service: ModerationService, fake_bot: FakeBot, caplog):
    """Если бот не администратор, ошибка Telegram не ломает обработку апдейта."""

    async def failing_delete(chat_id: int, message_id: int, **kwargs):
        from aiogram.exceptions import TelegramBadRequest
        from aiogram.methods import DeleteMessage

        raise TelegramBadRequest(
            method=DeleteMessage(chat_id=chat_id, message_id=message_id),
            message="message can't be deleted",
        )

    fake_bot.delete_message = failing_delete  # type: ignore[assignment]
    message = _message(fake_bot, text="#реклама", username="spammer", message_id=24)

    with caplog.at_level("WARNING"):
        decision = await moderation_service.handle_message(message)

    assert decision is not None
    assert decision.should_delete
    assert any("Не удалось удалить сообщение" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    ("chat_type", "expected"),
    [("group", True), ("supergroup", True), ("private", False), ("channel", False)],
)
def test_is_group_chat(chat_type, expected):
    assert is_group_chat(chat_type) is expected


async def test_shutdown_cancels_pending_notices(
    fake_bot: FakeBot, repository: SettingsRepository, moderator, config, monkeypatch
):
    monkeypatch.setattr(services_module, "NOTICE_TTL_SECONDS", 30.0)
    config = replace(config, notify_on_delete=True)
    service = ModerationService(bot=fake_bot, repository=repository, moderator=moderator, config=config)
    message = _message(fake_bot, text="#реклама", username="spammer", message_id=25)

    await service.handle_message(message)
    await service.shutdown()

    assert fake_bot.deleted_ids == [25]  # уведомление удалить не успели — задача отменена
