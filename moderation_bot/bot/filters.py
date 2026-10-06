"""Фильтрация сообщений: правила модерации и проверка типов контента."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from enum import Enum

from aiogram.types import Message

from .models import ChatSettings


class ContentKind(str, Enum):
    """Тип контента сообщения (то, что видит Telegram Bot API)."""

    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    ANIMATION = "animation"
    DOCUMENT = "document"
    STICKER = "sticker"
    AUDIO = "audio"
    VOICE = "voice"
    VIDEO_NOTE = "video_note"
    POLL = "poll"
    OTHER = "other"

    @property
    def is_visual_media(self) -> bool:
        """Картинки и видео (то, что обычно и называют «медиа»)."""
        return self in {ContentKind.PHOTO, ContentKind.VIDEO, ContentKind.ANIMATION, ContentKind.VIDEO_NOTE}

    @property
    def is_media(self) -> bool:
        """Любые медиавложения (шире, чем картинки и видео)."""
        return self is not ContentKind.TEXT and self is not ContentKind.POLL and self is not ContentKind.OTHER


#: Порядок важен: проверяем от «визуального» к «прочему».
_CONTENT_CHECKS: tuple[tuple[ContentKind, str], ...] = (
    (ContentKind.PHOTO, "photo"),
    (ContentKind.VIDEO, "video"),
    (ContentKind.ANIMATION, "animation"),
    (ContentKind.VIDEO_NOTE, "video_note"),
    (ContentKind.DOCUMENT, "document"),
    (ContentKind.STICKER, "sticker"),
    (ContentKind.AUDIO, "audio"),
    (ContentKind.VOICE, "voice"),
    (ContentKind.POLL, "poll"),
)


def content_kind(message: Message) -> ContentKind:
    """Определяет тип контента сообщения."""
    for kind, field in _CONTENT_CHECKS:
        if getattr(message, field, None) is not None:
            return kind
    if message.text is not None:
        return ContentKind.TEXT
    return ContentKind.OTHER


class Reason(str, Enum):
    """Причина удаления сообщения."""

    TARGET_USER = "target_user"
    HASHTAG = "hashtag"
    MEDIA_FROM_TARGET = "media_from_target"
    MEDIA_NON_ADMIN = "media_non_admin"


#: Человекочитаемые причины (для уведомлений в чате и логов).
REASON_LABELS: dict[Reason, str] = {
    Reason.TARGET_USER: "сообщение от заблокированного пользователя",
    Reason.HASHTAG: "сообщение содержит запрещённый хэштег",
    Reason.MEDIA_FROM_TARGET: "медиа от заблокированного пользователя",
    Reason.MEDIA_NON_ADMIN: "медиа от не-администратора",
}


def reason_label(reason: Reason | None) -> str:
    """Человекочитаемая причина удаления (безопасно для HTML)."""
    if reason is None:
        return "неизвестная причина"
    return html.escape(REASON_LABELS.get(reason, reason.value))


class Action(str, Enum):
    """Что бот делает с сообщением."""

    ALLOW = "allow"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class ModerationDecision:
    """Результат проверки сообщения."""

    action: Action
    reason: Reason | None = None
    kind: ContentKind = ContentKind.OTHER
    source: str = "rules"

    @property
    def should_delete(self) -> bool:
        return self.action is Action.DELETE

    @classmethod
    def allow(cls, kind: ContentKind, source: str = "rules") -> ModerationDecision:
        return cls(action=Action.ALLOW, kind=kind, source=source)

    @classmethod
    def delete(cls, reason: Reason, kind: ContentKind, source: str = "rules") -> ModerationDecision:
        return cls(action=Action.DELETE, reason=reason, kind=kind, source=source)


# --------------------------------------------------------------------- #
# Правила
# --------------------------------------------------------------------- #
def normalize_username(value: str | None) -> str:
    """`@ZazTagBot` -> `zaztagbot`."""
    if not value:
        return ""
    return value.strip().lstrip("@").lower()


def normalize_text(value: str | None) -> str:
    """Нормализует текст для поиска хэштега.

    Убирает пробелы и приводит к нижнему регистру, чтобы ловить варианты
    `#реклама`, `# реклама`, `#Реклама  ` и т.п.
    """
    if not value:
        return ""
    return re.sub(r"\s+", "", value).lower()


def message_matches_hashtag(message: Message, needle: str) -> bool:
    """Есть ли в сообщении запрещённый хэштег.

    Ищем в тексте, в подписи к медиа и в тексте опроса — то есть во всех местах,
    куда Telegram позволяет положить текст. «Подчёркивание» варианта `# реклама`
    реализовано нормализацией (удаление пробелов) — см. :func:`normalize_text`.
    """
    haystack_parts: list[str | None] = [message.text, message.caption]
    poll = getattr(message, "poll", None)
    if poll is not None:
        haystack_parts.extend([poll.question, poll.explanation])
        option_texts = [option.text for option in poll.options]
        haystack_parts.append(" ".join(option_texts))
    return any(needle and needle in normalize_text(part) for part in haystack_parts)


def is_target_user(message: Message, target_username: str) -> bool:
    """Автор сообщения — тот самый бот/аккаунт (сравнение по @username)."""
    if not target_username:
        return False
    return normalize_username(message.from_user.username if message.from_user else None) == target_username


# --------------------------------------------------------------------- #
# Оркестратор
# --------------------------------------------------------------------- #
class MessageModerator:
    """Применяет включённые фильтры чата к сообщению.

    Чистая логика без вызовов API: все внешние данные (настройки, статус
    администратора) передаются в :meth:`evaluate`. Это делает правила
    легко тестируемыми.
    """

    def __init__(self, target_username: str, banned_hashtag: str) -> None:
        self.target_username = normalize_username(target_username)
        self.hashtag_needle = normalize_text(banned_hashtag)

    def evaluate(
        self,
        message: Message,
        settings: ChatSettings,
        *,
        is_sender_admin: bool = False,
        sender_username: str | None = None,
    ) -> ModerationDecision:
        """Возвращает решение по сообщению.

        Порядок проверок (первое сработавшее правило выигрывает):

        1. `block_target_user` — автор сообщения это :attr:`target_username`;
        2. `block_hashtag` — в тексте/подписи есть «#реклама»;
        3. `block_media_from_target` — медиа от target-бота;
        4. `block_media_non_admin` — медиа не от администратора группы.

        Администраторы группы — исключение для правил 3 и 4 (правила против
        не-админов): их собственные медиа не удаляются.
        """
        kind = content_kind(message)

        sender_is_target = (
            normalize_username(sender_username) == self.target_username
            if sender_username is not None
            else is_target_user(message, self.target_username)
        )

        if settings.block_target_user and sender_is_target:
            return ModerationDecision.delete(Reason.TARGET_USER, kind)

        if settings.block_hashtag and message_matches_hashtag(message, self.hashtag_needle):
            return ModerationDecision.delete(Reason.HASHTAG, kind)

        # Дальше — правила про медиа: администраторов не трогаем.
        if is_sender_admin:
            return ModerationDecision.allow(kind)

        if settings.block_media_from_target and sender_is_target and kind.is_media:
            return ModerationDecision.delete(Reason.MEDIA_FROM_TARGET, kind)

        if settings.block_media_non_admin and kind.is_visual_media:
            return ModerationDecision.delete(Reason.MEDIA_NON_ADMIN, kind)

        return ModerationDecision.allow(kind)


# --------------------------------------------------------------------- #
# Хелперы для интерфейса
# --------------------------------------------------------------------- #
CONTENT_KIND_LABELS: dict[ContentKind, str] = {
    ContentKind.TEXT: "текст",
    ContentKind.PHOTO: "фото",
    ContentKind.VIDEO: "видео",
    ContentKind.ANIMATION: "GIF",
    ContentKind.DOCUMENT: "документ",
    ContentKind.STICKER: "стикер",
    ContentKind.AUDIO: "аудио",
    ContentKind.VOICE: "голосовое",
    ContentKind.VIDEO_NOTE: "кружок",
    ContentKind.POLL: "опрос",
    ContentKind.OTHER: "прочее",
}


def content_label(kind: ContentKind) -> str:
    """Название типа контента для логов."""
    return CONTENT_KIND_LABELS.get(kind, kind.value)
