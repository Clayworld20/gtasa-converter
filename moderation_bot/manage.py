#!/usr/bin/env python3
"""CLI для настройки модерации без Telegram.

Примеры:

    python manage.py list
    python manage.py show --chat -1001234567890
    python manage.py set --chat -1001234567890 --flag block_hashtag --value off
    python manage.py doctor --chat -1001234567890
    python manage.py demo
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aiogram.types import Message

from bot.config import Config, ConfigError, load_config
from bot.database import SettingsRepository
from bot.filters import MessageModerator, content_label, reason_label
from bot.keyboards import flag_title
from bot.models import TOGGLE_FIELDS, ChatSettings, SettingsDefaults
from bot.permissions import can_delete_messages

MARKS = {True: "✅ вкл", False: "❌ выкл"}
ON_VALUES = {"on", "1", "true", "yes", "вкл", "да"}
OFF_VALUES = {"off", "0", "false", "no", "выкл", "нет"}


def _format(settings: ChatSettings, config: Config) -> str:
    lines = [f"Чат {settings.chat_id} — включено {settings.enabled_count} из {len(TOGGLE_FIELDS)}:"]
    for flag in TOGGLE_FIELDS:
        title = flag_title(flag, target_username=config.target_username, banned_hashtag=config.banned_hashtag)
        lines.append(f"  {MARKS[settings.flag(flag)]}  {flag} — {title}")
    return "\n".join(lines)


async def _with_repository(config: Config, coro_factory):
    repository = SettingsRepository(config.db_path)
    await repository.connect()
    try:
        return await coro_factory(repository)
    finally:
        await repository.close()


async def _cmd_show(config: Config, chat_id: int) -> int:
    settings = await _with_repository(config, lambda repo: repo.get(chat_id))
    print(_format(settings, config))
    return 0


async def _cmd_list(config: Config) -> int:
    chats = await _with_repository(config, lambda repo: repo.all_chats())
    if not chats:
        print("В базе пока нет настроек — панель /settings ещё не открывали ни в одной группе.")
        return 0
    for settings in chats:
        print(_format(settings, config))
    return 0


async def _cmd_set(config: Config, chat_id: int, flag: str, value: bool) -> int:
    settings = await _with_repository(config, lambda repo: repo.set_flag(chat_id, flag, value))
    print(f"Обновлено: {flag} -> {'вкл' if value else 'выкл'}")
    print(_format(settings, config))
    return 0


async def _cmd_doctor(config: Config, chat_id: int) -> int:
    """Проверяет токен, доступ к чату и право бота удалять сообщения."""
    from aiogram import Bot
    from aiogram.exceptions import TelegramAPIError

    ok = True
    bot = Bot(token=config.bot_token)
    try:
        me = await bot.get_me()
        print(f"✅ Токен валиден: @{me.username} (id={me.id})")

        chat = await bot.get_chat(chat_id)
        print(f"✅ Чат доступен: {chat.title!r} (type={chat.type}, id={chat.id})")

        if await can_delete_messages(bot, chat_id):
            print("✅ У бота есть право удалять сообщения")
        else:
            ok = False
            print("❌ Бот не может удалять сообщения: выдайте права администратора с «Удалять сообщения»")

        member = await bot.get_chat_member(chat_id, bot.id)
        print(f"ℹ️ Статус бота в чате: {member.status}")
    except TelegramAPIError as exc:
        ok = False
        print(f"❌ Ошибка Telegram API: {exc}")
    finally:
        await bot.session.close()
    return 0 if ok else 1


def _sample_messages() -> list[Message]:
    """Сообщения-примеры для демонстрации правил (без сети)."""
    from datetime import datetime, timezone

    from aiogram.enums import ChatType
    from aiogram.types import Chat, Message, PhotoSize, User

    chat = Chat(id=-1001234567890, type=ChatType.SUPERGROUP.value, title="Демо-группа")
    photo = [PhotoSize(file_id="f", file_unique_id="u", width=1280, height=720)]

    def message(
        *,
        text: str = "",
        caption: str = "",
        username: str = "user",
        is_bot: bool = False,
        with_photo: bool = False,
    ) -> Message:
        return Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=chat,
            from_user=User(id=1, is_bot=is_bot, first_name="Демо", username=username),
            text=text or None,
            caption=caption or None,
            photo=photo if with_photo else None,
        )

    return [
        message(text="Привет! Как дела?", username="friend"),
        message(text="Срочная продажа курса #реклама", username="spammer"),
        message(text="# Реклама канала", username="spammer"),
        message(text="Подпишись на канал", username="zaztagbot", is_bot=True),
        message(username="zaztagbot", is_bot=True, with_photo=True),
        message(username="spammer", with_photo=True),
        message(caption="Свежий мем #реклама", username="friend", with_photo=True),
    ]


async def _cmd_demo(config: Config, chat_id: int | None) -> int:
    """Показывает, что бот сделает с типовыми сообщениями при текущих настройках."""
    if chat_id is None:
        settings = ChatSettings.from_defaults(0, SettingsDefaults())
        source = "значения по умолчанию"
    else:
        settings = await _with_repository(config, lambda repo: repo.get(chat_id))
        source = f"настройки чата {chat_id}"

    moderator = MessageModerator(config.target_username, config.banned_hashtag)
    print(f"Демонстрация правил ({source}): цель=@{config.target_username}, хэштег={config.banned_hashtag}\n")

    for message in _sample_messages():
        decision = moderator.evaluate(message, settings, sender_username=message.from_user.username)
        author = f"@{message.from_user.username}" + (" (бот)" if message.from_user.is_bot else "")
        preview = (message.text or message.caption or "").strip() or f"[{content_label(decision.kind)}]"
        verdict = f"🗑 УДАЛИТЬ — {reason_label(decision.reason)}" if decision.should_delete else "✅ оставить"
        print(f"{verdict:<62} | {author:<22} | {preview[:40]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Настройки модерации без Telegram")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="показать настройки всех чатов")

    show = sub.add_parser("show", help="показать настройки одного чата")
    show.add_argument("--chat", type=int, required=True, help="ID группы, например -1001234567890")

    set_cmd = sub.add_parser("set", help="включить/выключить фильтр")
    set_cmd.add_argument("--chat", type=int, required=True)
    set_cmd.add_argument("--flag", choices=TOGGLE_FIELDS, required=True)
    set_cmd.add_argument("--value", required=True, help="on/off (или вкл/выкл)")

    doctor = sub.add_parser("doctor", help="проверить токен и права бота в чате")
    doctor.add_argument("--chat", type=int, required=True)

    demo = sub.add_parser("demo", help="показать, какие сообщения будут удалены (без Telegram)")
    demo.add_argument("--chat", type=int, default=None, help="взять настройки этого чата из базы")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    if args.command == "list":
        return asyncio.run(_cmd_list(config))
    if args.command == "show":
        return asyncio.run(_cmd_show(config, args.chat))
    if args.command == "doctor":
        return asyncio.run(_cmd_doctor(config, args.chat))
    if args.command == "demo":
        return asyncio.run(_cmd_demo(config, args.chat))

    value_raw = args.value.strip().lower()
    if value_raw in ON_VALUES:
        value = True
    elif value_raw in OFF_VALUES:
        value = False
    else:
        print(f"❌ Не понимаю значение {args.value!r}: используйте on/off", file=sys.stderr)
        return 2
    return asyncio.run(_cmd_set(config, args.chat, args.flag, value))


if __name__ == "__main__":
    raise SystemExit(main())
