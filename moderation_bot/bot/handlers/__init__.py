"""Сборка роутеров: сначала команды админов, затем — модерация сообщений."""

from __future__ import annotations

from aiogram import Router

from . import admin, moderation


def build_router() -> Router:
    """Корневой роутер бота.

    Роутеры создаются заново при каждом вызове: один экземпляр aiogram-Router
    можно включить только в одно дерево, а приложений в тестах бывает больше
    одного.

    Порядок важен: ``admin`` идёт первым, поэтому команда ``/settings``
    обрабатывается и не «доезжает» до catch-all хэндлера модерации.
    """
    router = Router(name="root")
    router.include_router(admin.build_admin_router())
    router.include_router(moderation.build_moderation_router())
    return router


__all__ = ["admin", "build_router", "moderation"]
