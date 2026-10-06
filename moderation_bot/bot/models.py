"""Модели данных: настройки чата и значения по умолчанию.

Модуль не зависит ни от aiogram, ни от базы данных — это «чистые» структуры,
которые удобно переиспользовать в тестах.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Поля-флаги модерации. Порядок используется в панели настроек и в SQL.
TOGGLE_FIELDS: tuple[str, ...] = (
    "block_target_user",
    "block_hashtag",
    "block_media_from_target",
    "block_media_non_admin",
)


@dataclass(frozen=True, slots=True)
class SettingsDefaults:
    """Какие фильтры включены для чата, который бот видит впервые."""

    block_target_user: bool = True
    block_hashtag: bool = True
    block_media_from_target: bool = True
    block_media_non_admin: bool = False

    def as_tuple(self) -> tuple[int, ...]:
        """Значения флагов в порядке :data:`TOGGLE_FIELDS` (для INSERT)."""
        return tuple(int(getattr(self, name)) for name in TOGGLE_FIELDS)


@dataclass(frozen=True, slots=True)
class ChatSettings:
    """Настройки модерации конкретной группы."""

    chat_id: int
    block_target_user: bool
    block_hashtag: bool
    block_media_from_target: bool
    block_media_non_admin: bool

    @classmethod
    def from_row(cls, row) -> ChatSettings:
        """Собирает настройки из строки SQLite (aiosqlite.Row или dict)."""
        return cls(
            chat_id=int(row["chat_id"]),
            block_target_user=bool(row["block_target_user"]),
            block_hashtag=bool(row["block_hashtag"]),
            block_media_from_target=bool(row["block_media_from_target"]),
            block_media_non_admin=bool(row["block_media_non_admin"]),
        )

    @classmethod
    def from_defaults(cls, chat_id: int, defaults: SettingsDefaults) -> ChatSettings:
        """Настройки по умолчанию (когда строки в БД ещё нет)."""
        return cls(chat_id=chat_id, **{name: bool(getattr(defaults, name)) for name in TOGGLE_FIELDS})

    def flag(self, name: str) -> bool:
        """Значение флага по имени с проверкой допустимости имени."""
        if name not in TOGGLE_FIELDS:
            raise ValueError(f"Неизвестный фильтр: {name!r}")
        return bool(getattr(self, name))

    def with_flag(self, name: str, value: bool) -> ChatSettings:
        """Копия настроек с изменённым флагом."""
        if name not in TOGGLE_FIELDS:
            raise ValueError(f"Неизвестный фильтр: {name!r}")
        return replace(self, **{name: bool(value)})

    @property
    def any_enabled(self) -> bool:
        """True, если включён хотя бы один фильтр."""
        return any(getattr(self, name) for name in TOGGLE_FIELDS)

    @property
    def enabled_count(self) -> int:
        """Сколько фильтров включено (для текста панели)."""
        return sum(1 for name in TOGGLE_FIELDS if getattr(self, name))
