"""Проверка прав: администраторы группы и кэш этих проверок."""

from __future__ import annotations

import logging
import time

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatMember

from .compat import as_str

logger = logging.getLogger(__name__)

#: Статусы участника, при которых он считается администратором группы.
ADMIN_STATUSES: frozenset[str] = frozenset(
    {
        as_str(ChatMemberStatus.CREATOR),
        as_str(ChatMemberStatus.ADMINISTRATOR),
    }
)


async def get_member(bot: Bot, chat_id: int, user_id: int) -> ChatMember | None:
    """Возвращает участника чата или ``None``, если запрос не удался."""
    try:
        return await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError as exc:
        logger.warning("Не удалось получить участника %s в чате %s: %s", user_id, chat_id, exc)
        return None


async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Является ли пользователь администратором (или создателем) группы.

    При ошибке запроса возвращает ``False``: если права проверить не удалось,
    безопаснее не трогать сообщение, чем удалить сообщение администратора.
    """
    member = await get_member(bot, chat_id, user_id)
    if member is None:
        return False
    return as_str(getattr(member, "status", None)) in ADMIN_STATUSES


async def can_delete_messages(bot: Bot, chat_id: int) -> bool:
    """Может ли бот удалять сообщения в чате.

    Используется для понятной диагностики: без права «Удалять сообщения»
    фильтры работать не будут (сообщение останется, а в лог попадёт ошибка).
    """
    member = await get_member(bot, chat_id, bot.id)
    if member is None:
        return False
    status = as_str(getattr(member, "status", None))
    if status == as_str(ChatMemberStatus.CREATOR):
        # Создатель чата может всё.
        return True
    return status == as_str(ChatMemberStatus.ADMINISTRATOR) and bool(getattr(member, "can_delete_messages", False))


class AdminCache:
    """Кэш результатов «пользователь — администратор?».

    ``getChatMember`` — платный вызов с точки зрения лимитов Telegram (≈30 rps),
    а статус администратора меняется редко. Кэш с TTL убирает запрос на каждое
    сообщение в активной группе.
    """

    def __init__(self, bot: Bot, ttl: float = 300.0, max_size: int = 4096) -> None:
        self._bot = bot
        self._ttl = max(0.0, ttl)
        self._max_size = max(1, max_size)
        self._cache: dict[tuple[int, int], tuple[float, bool]] = {}

    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        """Проверка с кэшированием (при ``ttl == 0`` кэш выключен)."""
        if self._ttl == 0:
            return await is_admin(self._bot, chat_id, user_id)

        key = (chat_id, user_id)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        value = await is_admin(self._bot, chat_id, user_id)
        self._store(key, value, now)
        return value

    def _store(self, key: tuple[int, int], value: bool, now: float) -> None:
        if len(self._cache) >= self._max_size:
            self._prune(now)
        self._cache[key] = (now + self._ttl, value)

    def _prune(self, now: float) -> None:
        """Удаляет протухшие записи, а если их нет — половину самых старых."""
        expired = [key for key, (expires_at, _) in self._cache.items() if expires_at <= now]
        for key in expired:
            del self._cache[key]
        if len(self._cache) >= self._max_size:
            oldest = sorted(self._cache.items(), key=lambda item: item[1][0])
            for key, _ in oldest[: len(oldest) // 2 + 1]:
                del self._cache[key]

    def invalidate(self, chat_id: int, user_id: int | None = None) -> None:
        """Сбрасывает кэш по пользователю или по всему чату."""
        if user_id is None:
            for key in [key for key in self._cache if key[0] == chat_id]:
                del self._cache[key]
        else:
            self._cache.pop((chat_id, user_id), None)

    def clear(self) -> None:
        """Полный сброс кэша."""
        self._cache.clear()
