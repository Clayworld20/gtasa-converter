"""Настройка логирования: аккуратный вывод в консоль (и в файл при желании)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

#: Шумные логгеры сторонних библиотек.
NOISY_LOGGERS = ("aiogram.event", "aiogram.dispatcher", "asyncio")


def setup_logging(verbose: bool = True, log_file: str | Path | None = None) -> None:
    """Инициализирует корневой логгер.

    Args:
        verbose: включить уровень DEBUG для логов самого бота.
        log_file: путь к файлу логов (None — только консоль).
    """
    root = logging.getLogger()
    if root.handlers:  # повторный вызов не должен дублировать хэндлеры
        for handler in list(root.handlers):
            root.removeHandler(handler)

    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(console)

    if log_file is not None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        file_handler.setLevel(logging.INFO)
        root.addHandler(file_handler)

    # Логи самого бота — DEBUG, aiogram — INFO, чтобы не тонуть в апдейтах.
    logging.getLogger("bot").setLevel(logging.DEBUG if verbose else logging.INFO)
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO if not verbose else logging.DEBUG)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
