"""Сборка приложения: конфиг → Bot → Dispatcher → запуск.

Модуль — единственное место, где объекты связываются друг с другом
(composition root). Хэндлеры получают зависимости через ``workflow_data``
диспетчера, поэтому их легко тестировать по отдельности.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError

from .config import Config, load_config
from .database import SettingsRepository
from .filters import MessageModerator
from .handlers import build_router
from .logging_setup import setup_logging
from .middlewares import ChatWhitelistMiddleware
from .permissions import AdminCache
from .services import ModerationService, SettingsService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppContext:
    """Собранное приложение и его зависимости."""

    config: Config
    bot: Bot
    dispatcher: Dispatcher
    repository: SettingsRepository
    moderator: MessageModerator
    settings_service: SettingsService
    moderation_service: ModerationService

    async def shutdown(self) -> None:
        """Аккуратно освобождает ресурсы."""
        await self.moderation_service.shutdown()
        await self.repository.close()
        await self.bot.session.close()


async def build_app(config: Config | None = None, bot: Bot | None = None) -> AppContext:
    """Собирает диспетчер, базу данных и сервисы.

    Args:
        config: готовая конфигурация (по умолчанию читается из окружения).
        bot: готовый экземпляр бота. Параметр существует для тестов: позволяет
            подставить двойника, не меняя остальную сборку.
    """
    config = config or load_config()

    bot = bot or Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    repository = SettingsRepository(config.db_path)
    await repository.connect()

    moderator = MessageModerator(config.target_username, config.banned_hashtag)
    admin_cache = AdminCache(bot, ttl=config.admin_cache_ttl)
    moderation_service = ModerationService(
        bot=bot,
        repository=repository,
        moderator=moderator,
        config=config,
        admin_cache=admin_cache,
    )
    settings_service = SettingsService(repository)

    dispatcher = Dispatcher(
        config=config,
        repository=repository,
        moderator=moderator,
        settings_service=settings_service,
        moderation_service=moderation_service,
    )
    # Единая точка ограничения «бот только для одного чата».
    dispatcher.message.outer_middleware(ChatWhitelistMiddleware(config.allowed_chat_id))
    dispatcher.callback_query.outer_middleware(ChatWhitelistMiddleware(config.allowed_chat_id))
    dispatcher.include_router(build_router())

    return AppContext(
        config=config,
        bot=bot,
        dispatcher=dispatcher,
        repository=repository,
        moderator=moderator,
        settings_service=settings_service,
        moderation_service=moderation_service,
    )


async def run_polling(config: Config | None = None) -> None:
    """Запускает long-polling до остановки (Ctrl+C / SIGTERM)."""
    config = config or (load_config())
    setup_logging(verbose=config.verbose_log)

    app = await build_app(config)
    try:
        me = await app.bot.get_me()
        logger.info("Бот запущен: @%s (id=%s)", me.username, me.id)
        logger.info(
            "Фильтры: польз.=@%s | хэштег=%s | чат=%s",
            config.target_username,
            config.banned_hashtag,
            config.allowed_chat_id if config.allowed_chat_id is not None else "все группы",
        )
        await app.dispatcher.start_polling(app.bot)
    except TelegramUnauthorizedError:
        logger.error("Telegram отклонил токен: проверьте BOT_TOKEN в .env")
        raise
    except TelegramAPIError as exc:
        logger.error("Ошибка Telegram API: %s", exc)
        raise
    finally:
        await app.shutdown()
        logger.info("Бот остановлен")


def run(config: Config | None = None) -> None:
    """Синхронная обёртка для запуска из скрипта/консоли."""
    try:
        asyncio.run(run_polling(config))
    except KeyboardInterrupt:  # pragma: no cover - ручная остановка
        logger.info("Остановлено пользователем")
