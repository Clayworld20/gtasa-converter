"""Callback-фабрики панели настроек (вместо ручного парсинга callback_data)."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="modsettings"):
    """Действия панели `/settings`.

    Префикс без разделителя ``:`` — этого требует ``CallbackData`` из aiogram 3.
    """

    action: str  # "toggle" | "refresh" | "reset"
    flag: str = ""  # имя фильтра из bot.models.TOGGLE_FIELDS
