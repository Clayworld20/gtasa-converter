"""Панель администратора: /settings, /help и инлайн-кнопки."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.filters.chat_member_updated import JOIN_TRANSITION, ChatMemberUpdatedFilter
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InaccessibleMessage,
    InlineKeyboardMarkup,
    Message,
)

from .. import permissions
from ..callbacks import SettingsCallback
from ..config import Config
from ..keyboards import build_settings_keyboard, flag_title
from ..models import TOGGLE_FIELDS, ChatSettings
from ..services import ModerationService, SettingsService, is_group_chat
from ..texts import help_text, settings_text

logger = logging.getLogger(__name__)

#: Текст, который видят не-администраторы.
DENIED_TEXT = "⛔ Команда доступна только администраторам группы."
#: Ответ на команды в личных сообщениях.
PRIVATE_TEXT = (
    "🛡 Этот бот управляет модерацией группы.\n\n"
    "Добавьте его в группу, выдайте права администратора с правом "
    "«Удалять сообщения» и отправьте там команду /settings."
)


# --------------------------------------------------------------------- #
# Команды
# --------------------------------------------------------------------- #
async def cmd_start(message: Message, config: Config) -> None:
    """Приветствие: в личке — инструкция, в группе — краткая справка."""
    if not is_group_chat(message.chat.type):
        await message.answer(PRIVATE_TEXT)
        return
    await message.answer(f"🛡 Бот-модератор на связи.\n\n{help_text(config)}", disable_notification=True)


async def cmd_help(message: Message, config: Config, settings_service: SettingsService) -> None:
    """Справка по командам и текущий статус фильтров."""
    if not is_group_chat(message.chat.type):
        await message.answer(PRIVATE_TEXT)
        return
    settings = await settings_service.get(message.chat.id)
    await message.answer(
        f"{help_text(config)}\n\n🛡 Текущий статус: включено фильтров "
        f"<b>{settings.enabled_count} из {len(TOGGLE_FIELDS)}</b> — подробности в /settings.",
        disable_notification=True,
    )


async def cmd_settings(
    message: Message,
    bot: Bot,
    config: Config,
    settings_service: SettingsService,
    moderation_service: ModerationService,
) -> None:
    """Панель настроек модерации (только для администраторов группы)."""
    if not is_group_chat(message.chat.type):
        await message.answer(PRIVATE_TEXT)
        return

    if message.from_user is None or not await permissions.is_admin(bot, message.chat.id, message.from_user.id):
        # Автоудаляемое уведомление: не засоряем чат.
        await moderation_service.reply_ephemeral(message, DENIED_TEXT)
        return

    settings = await settings_service.get(message.chat.id)
    await message.answer(
        settings_text(settings, config),
        reply_markup=_keyboard(settings, config),
        disable_notification=True,
    )


# --------------------------------------------------------------------- #
# Инлайн-кнопки
# --------------------------------------------------------------------- #
async def on_toggle(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    bot: Bot,
    config: Config,
    settings_service: SettingsService,
) -> None:
    """Переключает фильтр и перерисовывает панель."""
    if not await _authorize(callback, bot):
        return

    if callback_data.flag not in TOGGLE_FIELDS:
        await callback.answer("Неизвестный фильтр", show_alert=True)
        return

    chat_id = callback.message.chat.id  # type: ignore[union-attr]
    settings = await settings_service.toggle(chat_id, callback_data.flag, user_id=callback.from_user.id)
    state = "включено ✅" if settings.flag(callback_data.flag) else "выключено ❌"
    title = flag_title(
        callback_data.flag,
        target_username=config.target_username,
        banned_hashtag=config.banned_hashtag,
    )
    await callback.answer(f"{title}: {state}")
    await _render(callback, bot, settings, config)


async def on_refresh(
    callback: CallbackQuery,
    bot: Bot,
    config: Config,
    settings_service: SettingsService,
) -> None:
    """Обновляет панель (например, если настройки поменял другой админ)."""
    if not await _authorize(callback, bot):
        return
    chat_id = callback.message.chat.id  # type: ignore[union-attr]
    settings = await settings_service.get(chat_id)
    await callback.answer("Обновлено")
    await _render(callback, bot, settings, config)


async def on_reset(
    callback: CallbackQuery,
    bot: Bot,
    config: Config,
    settings_service: SettingsService,
) -> None:
    """Сбрасывает фильтры к значениям по умолчанию."""
    if not await _authorize(callback, bot):
        return
    chat_id = callback.message.chat.id  # type: ignore[union-attr]
    settings = await settings_service.reset(chat_id, user_id=callback.from_user.id)
    await callback.answer("Настройки сброшены к значениям по умолчанию ♻️")
    await _render(callback, bot, settings, config)


# --------------------------------------------------------------------- #
# Служебные хэндлеры
# --------------------------------------------------------------------- #
async def on_bot_added_to_chat(event: ChatMemberUpdated, bot: Bot, config: Config) -> None:
    """Подсказывает первую команду, когда бота добавили в группу."""
    if not is_group_chat(event.chat.type):
        return
    try:
        await bot.send_message(
            event.chat.id,
            "🛡 <b>Спасибо за добавление!</b>\n\n"
            f"{help_text(config)}\n\n"
            "⚠️ Не забудьте выдать боту права администратора с правом «Удалять сообщения», "
            "иначе фильтры не смогут удалять сообщения.",
        )
    except TelegramAPIError as exc:
        logger.warning("Не удалось поприветствовать чат %s: %s", event.chat.id, exc)


# --------------------------------------------------------------------- #
# Вспомогательное
# --------------------------------------------------------------------- #
def _keyboard(settings: ChatSettings, config: Config) -> InlineKeyboardMarkup:
    return build_settings_keyboard(
        settings,
        target_username=config.target_username,
        banned_hashtag=config.banned_hashtag,
    )


async def _authorize(callback: CallbackQuery, bot: Bot) -> bool:
    """Пускает к настройкам только администраторов группы."""
    message = callback.message
    if message is None:
        await callback.answer("Сообщение недоступно", show_alert=True)
        return False
    if not is_group_chat(message.chat.type):
        await callback.answer("Панель работает только в группах", show_alert=True)
        return False
    if not await permissions.is_admin(bot, message.chat.id, callback.from_user.id):
        await callback.answer(DENIED_TEXT, show_alert=True)
        return False
    return True


async def _render(callback: CallbackQuery, bot: Bot, settings: ChatSettings, config: Config) -> None:
    """Перерисовывает панель настроек в том же сообщении."""
    message = callback.message
    if message is None:
        return
    text = settings_text(settings, config)
    markup = _keyboard(settings, config)
    try:
        if isinstance(message, InaccessibleMessage):
            # Сообщение слишком старое для редактирования — публикуем новую панель.
            await bot.send_message(message.chat.id, text, reply_markup=markup, disable_notification=True)
            return
        await message.edit_text(text, reply_markup=markup)
    except TelegramAPIError as exc:
        logger.warning("Не удалось обновить панель настроек в чате %s: %s", message.chat.id, exc)


# --------------------------------------------------------------------- #
# Роутер
# --------------------------------------------------------------------- #
def build_admin_router() -> Router:
    """Создаёт роутер с командами и обработчиками кнопок (свежий на приложение)."""
    router = Router(name="admin")

    router.message.register(cmd_start, Command("start"))
    router.message.register(cmd_help, Command("help"))
    router.message.register(cmd_settings, Command("settings", "rule"))

    router.callback_query.register(on_toggle, SettingsCallback.filter(F.action == "toggle"), F.message)
    router.callback_query.register(on_refresh, SettingsCallback.filter(F.action == "refresh"), F.message)
    router.callback_query.register(on_reset, SettingsCallback.filter(F.action == "reset"), F.message)

    router.my_chat_member.register(on_bot_added_to_chat, ChatMemberUpdatedFilter(JOIN_TRANSITION))
    return router
