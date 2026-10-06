"""Тестовые двойники: бот, который ничего не отправляет в Telegram.

Реализован через ``__call__`` — так сообщения aiogram «работают» с ним как с
настоящим ``Bot`` (shortcuts вроде ``message.delete()`` вызывают ``bot(method)``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiogram.enums import ChatType
from aiogram.types import Chat, ChatMemberMember, ChatMemberOwner, Message, User

BOT_ID = 777000


class FakeSession:
    """Заглушка HTTP-сессии: приложению достаточно метода ``close()``."""

    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeBot:
    """Минимальная замена ``aiogram.Bot``: записывает вызовы, ничего не шлёт."""

    def __init__(self, *, bot_id: int = BOT_ID, admin_ids: set[int] | None = None) -> None:
        self.id = bot_id
        self.session = FakeSession()
        self.admin_ids = set(admin_ids or set())
        self.deleted: list[tuple[int, int]] = []
        self.sent: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.forwarded: list[dict[str, Any]] = []
        self.answered: list[dict[str, Any]] = []
        self.member_requests: list[tuple[int, int]] = []
        self._next_message_id = 900

    # -- «Bot API» ------------------------------------------------------ #
    async def __call__(self, method: Any, request_timeout: int | None = None) -> Any:
        """Диспетчер вызовов: aiogram зовёт ``bot(method)`` в shortcut-методах."""
        name = type(method).__name__
        if name == "DeleteMessage":
            return await self.delete_message(method.chat_id, method.message_id)
        if name == "SendMessage":
            payload = method.model_dump(exclude_none=True)
            payload.pop("chat_id", None)
            payload.pop("text", None)
            # Клавиатуру сохраняем объектом, а не сериализованным словарём.
            payload["reply_markup"] = method.reply_markup
            return await self.send_message(method.chat_id, method.text, **payload)
        if name == "ForwardMessage":
            return await self.forward_message(method.chat_id, method.from_chat_id, method.message_id)
        if name == "GetChatMember":
            return await self.get_chat_member(method.chat_id, method.user_id)
        if name == "EditMessageText":
            return await self.edit_message_text(
                chat_id=method.chat_id,
                message_id=method.message_id,
                text=method.text,
                reply_markup=method.reply_markup,
            )
        if name == "AnswerCallbackQuery":
            return await self.answer_callback_query(
                callback_query_id=method.callback_query_id,
                text=method.text,
                show_alert=bool(method.show_alert),
            )
        raise AssertionError(f"FakeBot не умеет обрабатывать {name}")

    async def delete_message(self, chat_id: int, message_id: int, **_: Any) -> bool:
        self.deleted.append((chat_id, message_id))
        return True

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Message:
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})
        return self.make_message(chat_id=chat_id, text=text)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Any = None,
        **kwargs: Any,
    ) -> Message:
        self.edited.append(
            {"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup, **kwargs}
        )
        return self.make_message(chat_id=chat_id, text=text, message_id=message_id)

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False, **_: Any
    ) -> bool:
        self.answered.append({"id": callback_query_id, "text": text, "show_alert": show_alert})
        return True

    async def forward_message(self, chat_id: int, from_chat_id: int, message_id: int, **_: Any) -> Message:
        self.forwarded.append({"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id})
        return self.make_message(chat_id=chat_id, text="forwarded")

    async def get_chat_member(self, chat_id: int, user_id: int, **_: Any):
        self.member_requests.append((chat_id, user_id))
        if user_id in self.admin_ids or user_id == self.id:
            return ChatMemberOwner(
                user=User(id=user_id, is_bot=user_id == self.id, first_name="Admin"),
                is_anonymous=False,
            )
        return ChatMemberMember(user=User(id=user_id, is_bot=user_id == self.id, first_name="Member"))

    # -- Помощники ------------------------------------------------------ #
    def make_message(
        self,
        *,
        chat_id: int = -1001234567890,
        text: str = "служебное сообщение",
        message_id: int | None = None,
        chat_type: str = ChatType.SUPERGROUP.value,
    ) -> Message:
        if message_id is None:
            self._next_message_id += 1
            message_id = self._next_message_id
        message = Message(
            message_id=message_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=chat_id, type=chat_type, title="Тестовая группа"),
            text=text,
        )
        return message.as_(self)

    @property
    def deleted_ids(self) -> list[int]:
        return [message_id for _, message_id in self.deleted]

    @property
    def sent_texts(self) -> list[str]:
        return [item["text"] for item in self.sent]

    @property
    def edited_texts(self) -> list[str]:
        return [item["text"] for item in self.edited]

    def sent_messages_with_markup(self) -> list[dict[str, Any]]:
        """Сообщения, у которых есть инлайн-клавиатура (то есть панели)."""
        return [item for item in self.sent if item.get("reply_markup") is not None]

    def panels(self) -> list[Any]:
        """Клавиатуры отправленных панелей (в порядке отправки)."""
        return [item["reply_markup"] for item in self.sent_messages_with_markup()]
