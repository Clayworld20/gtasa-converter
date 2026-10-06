"""Тексты интерфейса: панель `/settings` и справка."""

from __future__ import annotations

from .config import Config
from .filters import normalize_username
from .keyboards import FLAG_HINTS, flag_title
from .models import TOGGLE_FIELDS, ChatSettings


def _target(config: Config) -> str:
    """@username без символа @ — так короче подписи кнопок."""
    return normalize_username(config.target_username)


def _title(flag: str, config: Config) -> str:
    return flag_title(flag, target_username=_target(config), banned_hashtag=config.banned_hashtag)


def _context(config: Config) -> dict[str, str]:
    """Значения для подстановки в подсказки (см. `keyboards.FLAG_HINTS`)."""
    return {"target": _target(config), "hashtag": config.banned_hashtag}


def settings_text(settings: ChatSettings, config: Config) -> str:
    """HTML-текст панели настроек.

    Разметка минимальна (`<b>`, `<i>`, `<code>`) — ничто не интерполируется
    из пользовательских данных, поэтому HTML безопасен.
    """
    context = _context(config)
    lines = [
        "🛡 <b>Модерация группы</b>",
        f"Чат: <code>{settings.chat_id}</code>",
        f"Включено фильтров: <b>{settings.enabled_count} из {len(TOGGLE_FIELDS)}</b>",
        "",
        "<b>Переключатели</b> — нажмите кнопку, чтобы включить или выключить:",
    ]
    for flag in TOGGLE_FIELDS:
        mark = "✅ вкл" if settings.flag(flag) else "❌ выкл"
        lines.append(f"{mark} — {_title(flag, config)}")
    lines += ["", "<b>Что делает каждый фильтр</b>"]
    lines += [hint.format(**context) for hint in FLAG_HINTS]
    lines.append("")
    lines.append(
        "<i>Сообщение удаляется сразу после отправки. Медиа-правила не применяются к администраторам группы.</i>"
    )
    return "\n".join(lines)


def help_text(config: Config) -> str:
    """HTML-справка по командам бота."""
    context = _context(config)
    target_line = (
        f"• Бот удаляет сообщения от <code>@{context['target']}</code> (по @username отправителя) и/или медиа от него."
    )
    hashtag_line = (
        f"• Бот удаляет сообщения с хэштегом <code>{context['hashtag']}</code> (ищет в тексте и в подписи к медиа)."
    )
    return "\n".join(
        [
            "🛡 <b>Бот-модератор</b>",
            "",
            "<b>Команды</b> (для администраторов группы):",
            "• /settings — панель с инлайн-кнопками всех фильтров",
            "• /rule — то же самое (короткий вызов)",
            "• /help — эта справка",
            "",
            "<b>Как работает модерация</b>",
            target_line,
            hashtag_line,
            "• Правило «медиа от не-админов» удаляет картинки и видео всех участников, кроме админов.",
            "",
            "<b>Что нужно один раз настроить в группе</b>",
            "• Выдать боту права администратора с правом «Удалять сообщения».",
            "• Отключить приватность (в @BotFather: /setprivacy → Disable), иначе бот не увидит сообщения без команд.",
        ]
    )
