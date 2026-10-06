"""Мидлвари: ограничение работы бота одним чатом."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class ChatWhitelistMiddleware(BaseMiddleware):
    """Пропускает апдейты только из разрешённого чата (если он задан).

    Если ``ALLOWED_CHAT_ID`` не указан, бот работает во всех группах, куда его
    добавили: у каждой группы свои настройки (per-chat), конфликтов нет.
    """

    def __init__(self, allowed_chat_id: int | None) -> None:
        self.allowed_chat_id = allowed_chat_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if self.allowed_chat_id is None:
            return await handler(event, data)

        chat = data.get("event_chat") or getattr(event, "chat", None)
        if chat is not None and getattr(chat, "id", None) != self.allowed_chat_id:
            logger.debug("Апдейт из чата %s проигнорирован (ALLOWED_CHAT_ID=%s)", chat.id, self.allowed_chat_id)
            return None

        return await handler(event, data)
