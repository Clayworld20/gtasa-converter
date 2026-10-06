"""Точка входа: ``python -m bot``."""

from __future__ import annotations

import sys

from .app import run
from .config import ConfigError


def main() -> int:
    """Запускает бота и возвращает код выхода."""
    try:
        run()
    except ConfigError as exc:
        print(f"❌ Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("\n👋 Остановлено пользователем", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
