"""Сервисный слой: бизнес-логика модерации и работы с настройками.

Хэндлеры остаются «тонкими», а вся логика живёт здесь и покрыта тестами.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from . import permissions
from .compat import as_str
from .config import Config
from .database import SettingsRepository
from .filters import (
    MessageModerator,
    ModerationDecision,
    content_kind,
    content_label,
    normalize_username,
    reason_label,
)
from .models import ChatSettings

logger = logging.getLogger(__name__)

#: Сколько секунд висит служебное уведомление бота в чате.
NOTICE_TTL_SECONDS = 6.0

#: Чаты, в которых работает модерация и панель.
GROUP_TYPES: frozenset[str] = frozenset({as_str(ChatType.GROUP), as_str(ChatType.SUPERGROUP)})


def is_group_chat(chat_type: object) -> bool:
    """True для обычной группы и супергруппы (строка или enum — не важно)."""
    return as_str(chat_type) in GROUP_TYPES


class SettingsService:
    """Чтение и изменение настроек модерации чата."""

    def __init__(self, repository: SettingsRepository) -> None:
        self._repository = repository

    async def get(self, chat_id: int) -> ChatSettings:
        """Текущие настройки чата."""
        return await self._repository.get(chat_id)

    async def toggle(self, chat_id: int, flag: str, user_id: int | None = None) -> ChatSettings:
        """Инвертирует фильтр и возвращает новые настройки."""
        settings = await self._repository.toggle(chat_id, flag, updated_by=user_id)
        logger.info(
            "Чат %s: фильтр %s -> %s (изменил %s)",
            chat_id,
            flag,
            "вкл" if settings.flag(flag) else "выкл",
            user_id,
        )
        return settings

    async def reset(self, chat_id: int, user_id: int | None = None) -> ChatSettings:
        """Сбрасывает настройки чата к значениям по умолчанию."""
        settings = await self._repository.reset(chat_id, updated_by=user_id)
        logger.info("Чат %s: настройки сброшены (изменил %s)", chat_id, user_id)
        return settings


class ModerationService:
    """Проверяет сообщения и удаляет те, что попали под фильтры."""

    def __init__(
        self,
        bot: Bot,
        repository: SettingsRepository,
        moderator: MessageModerator,
        config: Config,
        admin_cache: permissions.AdminCache | None = None,
    ) -> None:
        self._bot = bot
        self._repository = repository
        self._moderator = moderator
        self._config = config
        self._admin_cache = admin_cache or permissions.AdminCache(bot, ttl=0.0)
        self._background_tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------ #
    # Основной сценарий
    # ------------------------------------------------------------------ #
    async def handle_message(self, message: Message) -> ModerationDecision | None:
        """Проверяет сообщение; при срабатывании фильтра удаляет его.

        Returns:
            Решение по сообщению или ``None``, если сообщение вне зоны модерации.
        """
        if not self._should_moderate(message):
            return None

        sender = message.from_user
        if sender is None:  # перестраховка: см. _should_moderate
            return None

        settings = await self._repository.get(message.chat.id)
        if not settings.any_enabled:
            return ModerationDecision.allow(content_kind(message))

        sender_is_target = normalize_username(sender.username) == self._moderator.target_username
        # Статус администратора влияет только на правило «медиа от не-админов»:
        # остальные правила не делают исключений, а для target-пользователя
        # запрос статуса всё равно не нужен.
        is_sender_admin = False
        if settings.block_media_non_admin and not sender_is_target:
            is_sender_admin = await self._admin_cache.is_admin(message.chat.id, sender.id)

        decision = self._moderator.evaluate(
            message,
            settings,
            is_sender_admin=is_sender_admin,
            sender_username=sender.username,
        )
        if decision.should_delete:
            await self._apply(message, decision)
        return decision

    def _should_moderate(self, message: Message) -> bool:
        """Нужно ли вообще смотреть на это сообщение.

        Пропускаем всё, что не группа, сообщения без автора (анонимный админ
        или запись от имени канала — автора не определить) и свои сообщения
        (панель настроек, служебные уведомления).
        """
        if not is_group_chat(message.chat.type) or message.from_user is None:
            return False
        return message.from_user.id != self._bot.id

    async def _apply(self, message: Message, decision: ModerationDecision) -> None:
        """Копирует сообщение в лог-чат (если нужно) и удаляет его."""
        await self._mirror_to_log_chat(message, decision)

        try:
            await message.delete()
        except TelegramAPIError as exc:
            logger.warning(
                "Не удалось удалить сообщение %s в чате %s: %s. "
                "Проверьте, что бот — администратор с правом «Удалять сообщения».",
                message.message_id,
                message.chat.id,
                exc,
            )
            return

        self._log_deleted(message, decision)
        if self._config.notify_on_delete:
            await self.reply_ephemeral(
                message,
                f"🗑 Удалено: <i>{reason_label(decision.reason)}</i> ({content_label(decision.kind)})",
            )

    def _log_deleted(self, message: Message, decision: ModerationDecision) -> None:
        if not self._config.verbose_log:
            return
        sender = message.from_user
        logger.info(
            "Удалено сообщение %s | чат=%s | автор=%s (@%s, id=%s) | тип=%s | причина=%s",
            message.message_id,
            message.chat.id,
            " ".join(filter(None, [sender.full_name if sender else None])),
            sender.username if sender else None,
            sender.id if sender else None,
            content_label(decision.kind),
            decision.reason.value if decision.reason else "unknown",
        )

    async def _mirror_to_log_chat(self, message: Message, decision: ModerationDecision) -> None:
        """Отправляет копию удаляемого сообщения в лог-чат.

        Копия делается **до** удаления: Telegram не позволяет переслать
        уже удалённое сообщение.
        """
        if not (self._config.forward_deleted_to_log and self._config.log_chat_id):
            return
        if self._config.log_chat_id == message.chat.id:
            return
        try:
            await self._bot.forward_message(
                chat_id=self._config.log_chat_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            await self._bot.send_message(
                chat_id=self._config.log_chat_id,
                text=(
                    f"🚫 Модерация: <i>{reason_label(decision.reason)}</i>"
                    f" | чат <code>{message.chat.id}</code>"
                    f" | автор <code>{message.from_user.id if message.from_user else '—'}</code>"
                ),
                disable_notification=True,
            )
        except TelegramAPIError as exc:
            logger.warning("Не удалось отправить копию сообщения в лог-чат %s: %s", self._config.log_chat_id, exc)

    # ------------------------------------------------------------------ #
    # Служебные уведомления с авто-удалением
    # ------------------------------------------------------------------ #
    async def reply_ephemeral(self, message: Message, text: str, ttl: float | None = None) -> Message | None:
        """Отправляет сообщение, которое бот уберёт через ``ttl`` секунд."""
        ttl = NOTICE_TTL_SECONDS if ttl is None else ttl
        try:
            notice = await message.answer(text, disable_notification=True)
        except TelegramAPIError as exc:
            logger.debug("Не удалось отправить уведомление в чат %s: %s", message.chat.id, exc)
            return None
        self.schedule_deletion(notice, ttl=ttl)
        return notice

    def schedule_deletion(self, message: Message, ttl: float | None = None) -> None:
        """Планирует удаление служебного сообщения (не блокирует обработку апдейта)."""
        task = asyncio.create_task(self._delete_later(message, NOTICE_TTL_SECONDS if ttl is None else ttl))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _delete_later(self, message: Message, delay: float) -> None:
        await asyncio.sleep(delay)  # отмена задачи (при остановке бота) прерывает ожидание
        try:
            await message.delete()
        except TelegramAPIError as exc:
            logger.debug("Не удалось убрать служебное сообщение %s: %s", message.message_id, exc)

    async def shutdown(self) -> None:
        """Отменяет отложенные задачи (вызывается при остановке бота)."""
        pending = [task for task in self._background_tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._background_tasks.clear()
