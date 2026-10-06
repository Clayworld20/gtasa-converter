"""Общие фикстуры тестов: конфиг, репозиторий, сервис и сообщения."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from aiogram.enums import ChatType
from aiogram.types import (
    Animation,
    Chat,
    Document,
    Message,
    PhotoSize,
    Sticker,
    User,
    Video,
    VideoNote,
)

from bot.config import Config
from bot.database import SettingsRepository
from bot.filters import MessageModerator
from bot.models import ChatSettings, SettingsDefaults
from bot.services import ModerationService, SettingsService
from tests.fakes import BOT_ID, FakeBot

CHAT_ID = -1001234567890
TARGET_USERNAME = "zaztagbot"
BANNED_HASHTAG = "#реклама"


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """Конфиг с выключенными уведомлениями, чтобы тесты не зависели от TTL."""
    return Config(
        bot_token="123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
        target_username=TARGET_USERNAME,
        banned_hashtag=BANNED_HASHTAG,
        allowed_chat_id=None,
        db_path=tmp_path / "test.sqlite3",
        admin_cache_ttl=0.0,
        notify_on_delete=False,
        verbose_log=False,
        forward_deleted_to_log=False,
        log_chat_id=None,
    )


@pytest.fixture
async def repository(config: Config) -> SettingsRepository:
    async with SettingsRepository(config.db_path) as repo:
        yield repo


@pytest.fixture
async def settings_service(repository: SettingsRepository) -> SettingsService:
    return SettingsService(repository)


@pytest.fixture
def moderator() -> MessageModerator:
    return MessageModerator(TARGET_USERNAME, BANNED_HASHTAG)


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot(admin_ids={555})


@pytest.fixture
async def moderation_service(
    fake_bot: FakeBot,
    repository: SettingsRepository,
    moderator: MessageModerator,
    config: Config,
) -> ModerationService:
    service = ModerationService(
        bot=fake_bot,
        repository=repository,
        moderator=moderator,
        config=config,
    )
    yield service
    await service.shutdown()


# --------------------------------------------------------------------- #
# Фабрики сообщений
# --------------------------------------------------------------------- #
def make_user(
    user_id: int = 42,
    username: str | None = "user",
    first_name: str = "Тест",
    is_bot: bool = False,
) -> User:
    return User(id=user_id, is_bot=is_bot, first_name=first_name, username=username)


def make_chat(chat_id: int = CHAT_ID, chat_type: str = ChatType.SUPERGROUP.value) -> Chat:
    return Chat(id=chat_id, type=chat_type, title="Тестовая группа")


def make_message(
    *,
    text: str | None = None,
    caption: str | None = None,
    username: str | None = "user",
    user_id: int = 42,
    is_bot: bool = False,
    message_id: int = 100,
    chat_id: int = CHAT_ID,
    chat_type: str = ChatType.SUPERGROUP.value,
    photo: Any = None,
    video: Any = None,
    animation: Any = None,
    document: Any = None,
    sticker: Any = None,
    bot: Any = None,
    from_user: bool = True,
) -> Message:
    """Собирает настоящий ``aiogram.types.Message`` (без обращений к сети)."""
    message = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=make_chat(chat_id=chat_id, chat_type=chat_type),
        from_user=make_user(user_id=user_id, username=username, is_bot=is_bot) if from_user else None,
        text=text,
        caption=caption,
        photo=photo,
        video=video,
        animation=animation,
        document=document,
        sticker=sticker,
    )
    return message.as_(bot) if bot is not None else message


def fake_photo() -> list[PhotoSize]:
    """Список размеров фото — так Telegram присылает ``message.photo``."""
    return [PhotoSize(file_id="photo-file-id", file_unique_id="photo-uid", width=1280, height=720)]


def fake_video() -> Video:
    return Video(file_id="video-id", file_unique_id="video-uid", width=1280, height=720, duration=12)


def fake_animation() -> Animation:
    return Animation(file_id="anim-id", file_unique_id="anim-uid", width=320, height=240, duration=3)


def fake_document() -> Document:
    return Document(file_id="doc-id", file_unique_id="doc-uid", file_name="file.pdf")


def fake_sticker() -> Sticker:
    return Sticker(
        file_id="sticker-id",
        file_unique_id="sticker-uid",
        type="regular",
        width=512,
        height=512,
        is_animated=False,
        is_video=False,
    )


def fake_video_note() -> VideoNote:
    return VideoNote(file_id="note-id", file_unique_id="note-uid", length=240, duration=5)


@pytest.fixture
def settings() -> ChatSettings:
    """Настройки со значениями по умолчанию."""
    return ChatSettings.from_defaults(CHAT_ID, SettingsDefaults())


@pytest.fixture
def own_settings(settings: ChatSettings) -> ChatSettings:
    """Настройки, где включены только правила про модерацию медиа."""
    return settings.with_flag("block_target_user", False).with_flag("block_hashtag", False)


__all__ = [
    "BANNED_HASHTAG",
    "BOT_ID",
    "CHAT_ID",
    "TARGET_USERNAME",
    "fake_animation",
    "fake_document",
    "fake_photo",
    "fake_sticker",
    "fake_video",
    "fake_video_note",
    "make_chat",
    "make_message",
    "make_user",
]
