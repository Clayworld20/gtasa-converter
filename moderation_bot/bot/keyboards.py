"""Инлайн-клавиатуры панели администратора."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .callbacks import SettingsCallback
from .models import TOGGLE_FIELDS, ChatSettings

#: Подписи фильтров для кнопок.
FLAG_TITLES: dict[str, str] = {
    "block_target_user": "Сообщения от @{target}",
    "block_hashtag": "Хэштег {hashtag}",
    "block_media_from_target": "Медиа от @{target}",
    "block_media_non_admin": "Медиа от не-админов",
}

#: Короткое пояснение под панелью.
FLAG_HINTS: tuple[str, ...] = (
    "• «Сообщения от @{target}» — удалять любое сообщение этого пользователя.",
    "• «Хэштег {hashtag}» — удалять сообщения с этим хэштегом (текст и подписи).",
    "• «Медиа от @{target}» — удалять фото/видео/GIF/кружки этого пользователя.",
    "• «Медиа от не-админов» — удалять фото и видео всех, кроме администраторов.",
)


def flag_title(flag: str, *, target_username: str, banned_hashtag: str) -> str:
    """Подпись кнопки для конкретного фильтра."""
    try:
        return FLAG_TITLES[flag].format(target=target_username, hashtag=banned_hashtag)
    except KeyError as exc:  # pragma: no cover - защита от рассинхронизации
        raise ValueError(f"Нет подписи для фильтра {flag!r}") from exc


def build_settings_keyboard(
    settings: ChatSettings,
    *,
    target_username: str = "zaztagbot",
    banned_hashtag: str = "#реклама",
) -> InlineKeyboardMarkup:
    """Клавиатура панели: по кнопке на каждый фильтр (✅ включён / ❌ выключен)."""
    rows: list[list[InlineKeyboardButton]] = []
    for flag in TOGGLE_FIELDS:
        enabled = settings.flag(flag)
        title = flag_title(flag, target_username=target_username, banned_hashtag=banned_hashtag)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'✅' if enabled else '❌'} {title}",
                    callback_data=SettingsCallback(action="toggle", flag=flag).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=SettingsCallback(action="refresh").pack(),
            ),
            InlineKeyboardButton(
                text="♻️ Сбросить",
                callback_data=SettingsCallback(action="reset").pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_toggles_keyboard(
    settings: ChatSettings,
    *,
    target_username: str = "zaztagbot",
    banned_hashtag: str = "#реклама",
) -> InlineKeyboardMarkup:
    """Компактная клавиатура «только переключатели» для inline-режима."""
    rows = []
    for flag in TOGGLE_FIELDS:
        title = flag_title(flag, target_username=target_username, banned_hashtag=banned_hashtag)
        mark = "✅" if settings.flag(flag) else "❌"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {title}",
                    callback_data=SettingsCallback(action="toggle", flag=flag).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
