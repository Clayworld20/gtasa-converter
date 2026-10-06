"""Хэндлер модерации: проверяет каждое сообщение в группе."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import Message

from ..services import ModerationService, is_group_chat

logger = logging.getLogger(__name__)


async def moderate_message(message: Message, moderation_service: ModerationService) -> None:
    """Точка входа фильтрации.

    Хэндлер зарегистрирован без фильтров — значит, получает все сообщения,
    которые не перехватили хэндлеры выше (например, команды администратора).
    Сама логика живёт в :meth:`ModerationService.handle_message`.
    """
    if not is_group_chat(message.chat.type):
        return
    decision = await moderation_service.handle_message(message)
    if decision is not None and decision.should_delete:
        logger.debug(
            "Сообщение %s в чате %s удалено (%s)",
            message.message_id,
            message.chat.id,
            decision.reason,
        )


def build_moderation_router() -> Router:
    """Создаёт роутер модерации (свежий экземпляр на каждое приложение)."""
    router = Router(name="moderation")
    router.message.register(moderate_message)
    return router
