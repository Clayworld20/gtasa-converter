"""Совместимость с разными версиями aiogram 3.x.

В разных релизах aiogram одно и то же поле приходит то строкой, то членом
перечисления (перечисление ``ChatMemberStatus`` в 3.31 — уже ``Enum``, а не
``str``). Приведение к строке в одном месте избавляет остальной код от
проверок вида «str это или enum».
"""

from __future__ import annotations

from enum import Enum
from typing import Any


def as_str(value: Any, default: str = "") -> str:
    """Возвращает строковое представление значения (enum → его value)."""
    if value is None:
        return default
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)
