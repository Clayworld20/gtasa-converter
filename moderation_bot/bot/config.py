"""Конфигурация бота: чтение переменных окружения.

Все «магические» значения приложения (токен, ID чата, имя бота-рекламщика,
хэштег-маркер рекламы) живут здесь и настраиваются через `.env`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

#: Корень проекта (каталог, где лежат bot/, data/ и .env.example).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
#: Файл базы данных по умолчанию.
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "moderation.sqlite3"


class ConfigError(RuntimeError):
    """Некорректная конфигурация: понятное сообщение вместо трейсбека."""


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on", "да"}


def _env_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw.strip())
    except ValueError as exc:  # pragma: no cover - защита от опечаток в .env
        raise ConfigError(f"Переменная {name} должна быть целым числом, получено {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError as exc:  # pragma: no cover - защита от опечаток в .env
        raise ConfigError(f"Переменная {name} должна быть числом, получено {raw!r}") from exc


#: Маркеры «заглушки» в токене — по ним понимаем, что .env ещё не заполнен.
_PLACEHOLDER_MARKERS = ("replace", "paste", "your_token", "your-token", "ваш", "вставьте", "xxxx", "123456:abc")


def _looks_like_placeholder(token: str) -> bool:
    """Похож ли токен на незаполненный шаблон из `.env.example`."""
    lowered = token.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _normalize_target(raw: str | None) -> str:
    """Приводит @Username к нижнему регистру и убирает символ @."""
    if not raw:
        return ""
    return raw.strip().lstrip("@").lower()


@dataclass(frozen=True, slots=True)
class Config:
    """Иммутабельная конфигурация приложения."""

    bot_token: str
    #: @username «нежелательного» бота (по умолчанию zaztagbot).
    target_username: str
    #: Хэштег-маркер рекламы (по умолчанию #реклама).
    banned_hashtag: str
    #: Явный ID группы. Если None — бот работает во всех группах, куда его добавили:
    #: настройки хранятся per-chat, у каждой группы своя панель.
    allowed_chat_id: int | None
    db_path: Path
    #: Сколько секунд кэшировать результат проверки «является ли админом» (0 — не кэшировать).
    admin_cache_ttl: float
    #: Отвечать ли в чат на срабатывание фильтра (само сообщение удаляется всегда).
    notify_on_delete: bool
    #: Логировать ли удалённые сообщения в консоль.
    verbose_log: bool
    #: Отправлять ли исходное удалённое сообщение в лог-канал (если задан).
    forward_deleted_to_log: bool
    #: Канал/чат для копий удалённых сообщений (None — выключено).
    log_chat_id: int | None

    @property
    def hashtag_needle(self) -> str:
        """Хэштег в нормализованном виде (нижний регистр, без пробелов)."""
        return self.banned_hashtag.strip().lower().replace(" ", "")


def load_config(env_file: str | os.PathLike[str] | None = ".env") -> Config:
    """Загружает `.env` и собирает :class:`Config`.

    Raises:
        ConfigError: если не задан `BOT_TOKEN` (или он не похож на токен BotFather).
    """
    if env_file is not None:
        # override=False: переменные окружения процесса имеют приоритет над файлом.
        load_dotenv(env_file, override=False)

    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token or _looks_like_placeholder(token):
        raise ConfigError("BOT_TOKEN не задан. Скопируйте .env.example в .env и вставьте токен от @BotFather.")
    if ":" not in token or not token.split(":", 1)[0].isdigit():
        raise ConfigError(
            "BOT_TOKEN выглядит некорректно (ожидается формат '123456789:AA...'). Проверьте значение в .env."
        )

    db_path_raw = os.getenv("DB_PATH", "").strip()
    db_path = Path(db_path_raw).expanduser() if db_path_raw else DEFAULT_DB_PATH
    if not db_path.is_absolute():
        db_path = (PROJECT_ROOT / db_path).resolve()

    return Config(
        bot_token=token,
        target_username=_normalize_target(os.getenv("TARGET_USERNAME", "zaztagbot")) or "zaztagbot",
        banned_hashtag=(os.getenv("BANNED_HASHTAG") or "#реклама").strip() or "#реклама",
        allowed_chat_id=_env_int("ALLOWED_CHAT_ID"),
        db_path=db_path,
        admin_cache_ttl=_env_float("ADMIN_CACHE_TTL", 300.0),
        notify_on_delete=_env_bool("NOTIFY_ON_DELETE", default=True),
        verbose_log=_env_bool("VERBOSE_LOG", default=True),
        forward_deleted_to_log=_env_bool("FORWARD_DELETED_TO_LOG", default=False),
        log_chat_id=_env_int("LOG_CHAT_ID"),
    )
