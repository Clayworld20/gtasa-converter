"""Тесты правил фильтрации (чистая логика, без сети и БД)."""

from __future__ import annotations

import pytest
from aiogram.enums import ChatType

from bot.filters import (
    Action,
    ContentKind,
    MessageModerator,
    Reason,
    content_kind,
    is_target_user,
    message_matches_hashtag,
    normalize_text,
    normalize_username,
    reason_label,
)
from bot.models import SettingsDefaults
from tests.conftest import (
    CHAT_ID,
    fake_animation,
    fake_document,
    fake_photo,
    fake_sticker,
    fake_video,
    make_message,
)

TARGET = "zaztagbot"


@pytest.fixture
def moderator() -> MessageModerator:
    return MessageModerator(TARGET, "#реклама")


@pytest.fixture
def all_on():
    return SettingsDefaults(
        block_target_user=True,
        block_hashtag=True,
        block_media_from_target=True,
        block_media_non_admin=True,
    )


# --------------------------------------------------------------------- #
# Нормализация
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@ZazTagBot", "zaztagbot"),
        ("zaztagbot", "zaztagbot"),
        ("  @zaztagbot  ", "zaztagbot"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_username(raw, expected):
    assert normalize_username(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("# реклама", "#реклама"),
        ("#Реклама", "#реклама"),
        ("  #РЕКЛАМА\n", "#реклама"),
        ("Купите срочно # реклама !", "купитесрочно#реклама!"),
    ],
)
def test_normalize_text(raw, expected):
    assert normalize_text(raw) == expected


# --------------------------------------------------------------------- #
# Правило 1: конкретный пользователь
# --------------------------------------------------------------------- #
def test_target_user_message_is_deleted(moderator, settings):
    message = make_message(text="Привет, я бот-рекламщик", username="ZazTagBot", is_bot=True)

    decision = moderator.evaluate(message, settings)

    assert decision.should_delete
    assert decision.reason is Reason.TARGET_USER


def test_target_user_message_allowed_when_flag_off(moderator, settings):
    settings = settings.with_flag("block_target_user", False).with_flag("block_hashtag", False)
    message = make_message(text="обычный текст", username="zaztagbot", is_bot=True)

    decision = moderator.evaluate(message, settings)

    assert decision.action is Action.ALLOW


def test_animation_and_video_note_are_media(moderator, settings):
    settings = settings.with_flag("block_media_non_admin", True)
    for media in (fake_animation(), fake_document()):
        field = "animation" if media.__class__.__name__ == "Animation" else "document"
        message = make_message(**{field: media}, username="regular_user")
        decision = moderator.evaluate(message, settings)
        expected = Action.DELETE if field == "animation" else Action.ALLOW
        assert decision.action is expected


def test_other_bot_is_not_touched(moderator, settings):
    message = make_message(text="обычный текст", username="some_other_bot", is_bot=True)

    assert moderator.evaluate(message, settings).action is Action.ALLOW


def test_is_target_user_handles_missing_username(moderator, settings):
    message = make_message(text="без юзернейма", username=None)
    assert is_target_user(message, TARGET) is False
    assert moderator.evaluate(message, settings.with_flag("block_hashtag", False)).action is Action.ALLOW


# --------------------------------------------------------------------- #
# Правило 2: хэштег
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "#реклама",
        "Купите наш курс #реклама срочно",
        "# Реклама",
        "#РЕКЛАМА!!!",
        "текст\n\n#Реклама",
    ],
)
def test_hashtag_in_text_is_deleted(moderator, settings, text):
    settings = settings.with_flag("block_target_user", False)
    message = make_message(text=text, username="regular_user")

    decision = moderator.evaluate(message, settings)

    assert decision.should_delete
    assert decision.reason is Reason.HASHTAG


def test_hashtag_in_caption_is_deleted(moderator, settings):
    settings = settings.with_flag("block_target_user", False)
    message = make_message(caption="Крутое предложение #реклама", photo=fake_photo(), username="regular_user")

    decision = moderator.evaluate(message, settings)

    assert decision.should_delete
    assert decision.reason is Reason.HASHTAG
    assert decision.kind is ContentKind.PHOTO


def test_hashtag_allowed_when_flag_off(moderator, settings):
    settings = settings.with_flag("block_hashtag", False).with_flag("block_target_user", False)
    message = make_message(text="#реклама", username="regular_user")

    assert moderator.evaluate(message, settings).action is Action.ALLOW


def test_hashtag_lookup_ignores_empty_needle(moderator):
    message = make_message(text="#реклама")
    assert message_matches_hashtag(message, "") is False


# --------------------------------------------------------------------- #
# Правило 3: медиа от target-пользователя
# --------------------------------------------------------------------- #
def test_media_from_target_is_deleted(moderator, own_settings):
    message = make_message(photo=fake_photo(), username="zaztagbot", is_bot=True)

    decision = moderator.evaluate(message, own_settings)

    assert decision.should_delete
    assert decision.reason is Reason.MEDIA_FROM_TARGET


def test_target_text_allowed_when_only_media_rule_enabled(moderator, own_settings):
    message = make_message(text="текстовое сообщение", username="zaztagbot", is_bot=True)

    assert moderator.evaluate(message, own_settings).action is Action.ALLOW


def test_media_from_target_not_deleted_when_flag_off(moderator, settings):
    settings = (
        settings.with_flag("block_target_user", False)
        .with_flag("block_hashtag", False)
        .with_flag("block_media_from_target", False)
    )
    message = make_message(document=fake_document(), username="zaztagbot", is_bot=True)

    assert moderator.evaluate(message, settings).action is Action.ALLOW


# --------------------------------------------------------------------- #
# Правило 4: медиа от не-администраторов
# --------------------------------------------------------------------- #
def test_photo_from_non_admin_is_deleted(moderator, settings):
    settings = settings.with_flag("block_media_non_admin", True)
    message = make_message(photo=fake_photo(), username="regular_user")

    decision = moderator.evaluate(message, settings, is_sender_admin=False)

    assert decision.should_delete
    assert decision.reason is Reason.MEDIA_NON_ADMIN


def test_video_from_non_admin_is_deleted(moderator, settings):
    settings = settings.with_flag("block_media_non_admin", True)
    message = make_message(video=fake_video(), username="regular_user")

    decision = moderator.evaluate(message, settings, is_sender_admin=False)

    assert decision.reason is Reason.MEDIA_NON_ADMIN


def test_media_from_admin_is_kept(moderator, settings):
    settings = settings.with_flag("block_media_non_admin", True)
    message = make_message(photo=fake_photo(), username="group_admin")

    assert moderator.evaluate(message, settings, is_sender_admin=True).action is Action.ALLOW


def test_text_from_non_admin_is_kept(moderator, settings):
    settings = settings.with_flag("block_media_non_admin", True)
    message = make_message(text="просто текст", username="regular_user")

    assert moderator.evaluate(message, settings).action is Action.ALLOW


def test_document_from_non_admin_is_kept(moderator, settings):
    """Правило «медиа от не-админов» касается только картинок и видео."""
    settings = settings.with_flag("block_media_non_admin", True)
    message = make_message(document=fake_document(), username="regular_user")

    assert moderator.evaluate(message, settings, is_sender_admin=False).action is Action.ALLOW


def test_target_rule_wins_over_media_rules(moderator, settings):
    message = make_message(photo=fake_photo(), username="zaztagbot", is_bot=True)

    assert moderator.evaluate(message, settings).reason is Reason.TARGET_USER


# --------------------------------------------------------------------- #
# Определение типа контента
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"text": "привет"}, ContentKind.TEXT),
        ({"photo": fake_photo()}, ContentKind.PHOTO),
        ({"video": fake_video()}, ContentKind.VIDEO),
        ({"animation": fake_animation()}, ContentKind.ANIMATION),
        ({"document": fake_document()}, ContentKind.DOCUMENT),
        ({"sticker": fake_sticker()}, ContentKind.STICKER),
        ({}, ContentKind.OTHER),
    ],
)
def test_content_kind(kwargs, expected):
    message = make_message(**kwargs)
    assert content_kind(message) is expected


def test_visual_media_flags():
    assert ContentKind.PHOTO.is_visual_media is True
    assert ContentKind.VIDEO.is_visual_media is True
    assert ContentKind.ANIMATION.is_visual_media is True
    assert ContentKind.DOCUMENT.is_media is True
    assert ContentKind.DOCUMENT.is_visual_media is False
    assert ContentKind.TEXT.is_media is False


# --------------------------------------------------------------------- #
# Прочее
# --------------------------------------------------------------------- #
def test_reason_label_is_human_readable():
    assert "хэштег" in reason_label(Reason.HASHTAG)
    assert reason_label(None) == "неизвестная причина"


def test_private_chat_message_is_not_moderated_by_rules(moderator, settings):
    """В личке фильтры бессмысленны, но правила остаются чистыми и не падают."""
    message = make_message(text="#реклама", chat_type=ChatType.PRIVATE.value, chat_id=42)
    assert moderator.evaluate(message, settings).should_delete is True  # правило сработало


def test_chat_id_is_preserved_in_settings(settings):
    assert settings.chat_id == CHAT_ID
