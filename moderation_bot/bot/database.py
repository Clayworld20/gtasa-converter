"""Асинхронный слой доступа к SQLite (aiosqlite).

Хранит настройки модерации по каждой группе (per-chat):

* ``block_target_user``      — удалять сообщения от :attr:`Config.target_username`;
* ``block_hashtag``          — удалять сообщения с запрещённым хэштегом;
* ``block_media_from_target``— удалять медиа (фото/видео/...) от target-бота;
* ``block_media_non_admin``  — удалять медиа от всех, кроме администраторов группы.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import aiosqlite

from .models import TOGGLE_FIELDS, ChatSettings, SettingsDefaults

logger = logging.getLogger(__name__)

# Имена колонок не приходят извне — они берутся из TOGGLE_FIELDS,
# поэтому подстановка в SQL безопасна (значения всегда через параметры ?).
_FLAG_COLUMNS = ", ".join(TOGGLE_FIELDS)
_FLAG_COLUMNS_DDL = ",\n    ".join(f"{name} INTEGER NOT NULL DEFAULT 0" for name in TOGGLE_FIELDS)
_PLACEHOLDERS = ", ".join("?" for _ in TOGGLE_FIELDS)
_FLAG_UPSERT = ", ".join(f"{name} = excluded.{name}" for name in TOGGLE_FIELDS)


class SettingsRepository:
    """Хранилище настроек. Один экземпляр на процесс бота."""

    def __init__(self, db_path: str | Path, defaults: SettingsDefaults | None = None) -> None:
        self.db_path = Path(db_path)
        self.defaults = defaults or SettingsDefaults()
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------ #
    # Жизненный цикл
    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        """Открывает соединение, включает WAL и создаёт схему."""
        if self._conn is not None:
            return
        if self.db_path.parent != Path(""):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        # WAL + busy_timeout: несколько подключений (бот и CLI) не блокируют друг друга.
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        self._conn = conn
        await self._create_schema()
        logger.info("База данных готова: %s", self.db_path)

    async def _create_schema(self) -> None:
        await self._require_conn().executescript(
            f"""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                {_FLAG_COLUMNS_DDL},
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_by INTEGER
            );
            """
        )
        await self._require_conn().commit()

    async def close(self) -> None:
        """Закрывает соединение (безопасно вызывать повторно)."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("Соединение с базой данных закрыто")

    async def __aenter__(self) -> SettingsRepository:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------ #
    # Публичный API
    # ------------------------------------------------------------------ #
    async def get(self, chat_id: int) -> ChatSettings:
        """Настройки чата или значения по умолчанию, если строки ещё нет."""
        conn = self._require_conn()
        async with conn.execute(
            f"SELECT chat_id, {_FLAG_COLUMNS} FROM chat_settings WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return ChatSettings.from_defaults(chat_id, self.defaults)
        return ChatSettings.from_row(row)

    async def set_flag(self, chat_id: int, flag: str, value: bool, updated_by: int | None = None) -> ChatSettings:
        """Ставит флаг и возвращает актуальные настройки чата.

        Строка создаётся лениво (upsert), при этом остальные флаги берут значения
        по умолчанию — так первое нажатие кнопки в новой группе не «теряет» настройки.
        """
        if flag not in TOGGLE_FIELDS:
            raise ValueError(f"Неизвестный фильтр: {flag!r}")

        row_values = list(self.defaults.as_tuple())
        row_values[TOGGLE_FIELDS.index(flag)] = int(bool(value))

        sql = f"""
            INSERT INTO chat_settings (chat_id, {_FLAG_COLUMNS}, updated_by)
            VALUES (?, {_PLACEHOLDERS}, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                {flag} = excluded.{flag},
                updated_at = datetime('now'),
                updated_by = excluded.updated_by
        """
        conn = self._require_conn()
        await conn.execute(sql, (chat_id, *row_values, updated_by))
        await conn.commit()
        return await self.get(chat_id)

    async def toggle(self, chat_id: int, flag: str, updated_by: int | None = None) -> ChatSettings:
        """Инвертирует флаг и возвращает актуальные настройки."""
        current = await self.get(chat_id)
        return await self.set_flag(chat_id, flag, not current.flag(flag), updated_by=updated_by)

    async def reset(self, chat_id: int, updated_by: int | None = None) -> ChatSettings:
        """Сбрасывает настройки чата к значениям по умолчанию."""
        conn = self._require_conn()
        await conn.execute("DELETE FROM chat_settings WHERE chat_id = ?", (chat_id,))
        await conn.commit()
        settings = await self.set_flag(chat_id, TOGGLE_FIELDS[0], self.defaults.block_target_user, updated_by)
        # set_flag создал строку из дефолтов; остальные флаги уже дефолтные.
        logger.info("Настройки чата %s сброшены к значениям по умолчанию", chat_id)
        return settings

    async def seed(self, chat_id: int, settings: ChatSettings, updated_by: int | None = None) -> ChatSettings:
        """Принудительно записывает полный набор флагов (используется CLI и тестами)."""
        conn = self._require_conn()
        await conn.execute(
            f"INSERT INTO chat_settings (chat_id, {_FLAG_COLUMNS}, updated_by) "
            f"VALUES (?, {_PLACEHOLDERS}, ?) "
            f"ON CONFLICT(chat_id) DO UPDATE SET {_FLAG_UPSERT}, updated_at = datetime('now'), "
            f"updated_by = excluded.updated_by",
            (chat_id, *(int(settings.flag(name)) for name in TOGGLE_FIELDS), updated_by),
        )
        await conn.commit()
        return await self.get(chat_id)

    async def all_chats(self) -> Iterable[ChatSettings]:
        """Все чаты, для которых есть сохранённые настройки."""
        conn = self._require_conn()
        async with conn.execute(f"SELECT chat_id, {_FLAG_COLUMNS} FROM chat_settings ORDER BY chat_id") as cursor:
            rows = await cursor.fetchall()
        return [ChatSettings.from_row(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Внутреннее
    # ------------------------------------------------------------------ #
    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("База данных не инициализирована: вызовите await repository.connect()")
        return self._conn
