from __future__ import annotations

from datetime import datetime, timezone

import pytest_asyncio
from aiogram.types import BusinessMessagesDeleted, Chat, Message, User

from app.config import Settings
from app.db import Database
from app.handlers.business import (
    business_message_edited,
    business_message_received,
    business_messages_deleted,
)
from app.media import MediaManager


class FakeBot:
    def __init__(self):
        self.sent_messages = []
        self.events = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent_messages.append((chat_id, text))
        self.events.append(("message", text))

    async def send_photo(self, chat_id, photo, **kwargs):
        self.events.append(("photo", photo))


@pytest_asyncio.fixture
async def environment(tmp_path):
    settings = Settings(bot_token="123:TEST", data_dir=tmp_path / "data")
    settings.prepare_directories()
    db = Database(settings.db_path)
    await db.connect()
    await db.upsert_connection(
        connection_id="connection-1",
        owner_id=100,
        owner_chat_id=100,
        owner_name="Owner",
        owner_username="owner",
        is_enabled=True,
        can_reply=False,
    )
    media = MediaManager(settings)
    bot = FakeBot()
    yield settings, db, media, bot
    await db.close()


def make_business_message(
    text: str,
    edited: bool = False,
    message_id: int = 1,
    reply_to_message: Message | None = None,
) -> Message:
    now = datetime.now(timezone.utc)
    values = {
        "message_id": message_id,
        "date": now,
        "chat": Chat(id=200, type="private", first_name="Sender"),
        "from_user": User(id=200, is_bot=False, first_name="Sender", username="sender"),
        "business_connection_id": "connection-1",
        "text": text,
    }
    if edited:
        values["edit_date"] = int(now.timestamp())
    if reply_to_message is not None:
        values["reply_to_message"] = reply_to_message
    return Message(**values)


async def test_receive_edit_delete_flow(environment):
    settings, db, media, bot = environment
    context = make_business_message("reply context", message_id=99)
    original = make_business_message("original", reply_to_message=context)
    await business_message_received(
        original, bot, db, media, settings, bot_username="SaveeBooot_bot"
    )

    saved = await db.get_message("connection-1", 200, 1)
    assert saved is not None
    assert saved["text"] == "original"
    assert saved["reply_context"] == "reply context"
    assert saved["is_outgoing"] == 0

    edited = make_business_message("changed", edited=True)
    await business_message_edited(
        edited, bot, db, media, settings, bot_username="SaveeBooot_bot"
    )
    assert len(bot.sent_messages) == 1
    assert "отредактировал сообщение" in bot.sent_messages[0][1]
    assert "<b>Было:</b>" in bot.sent_messages[0][1]
    assert "<b>Стало:</b>" in bot.sent_messages[0][1]
    assert "original" in bot.sent_messages[0][1]
    assert "changed" in bot.sent_messages[0][1]
    assert "@SaveeBooot_bot" in bot.sent_messages[0][1]

    event = BusinessMessagesDeleted(
        business_connection_id="connection-1",
        chat=Chat(id=200, type="private", first_name="Sender"),
        message_ids=[1],
    )
    await business_messages_deleted(
        event, bot, db, media, settings, bot_username="SaveeBooot_bot"
    )
    assert len(bot.sent_messages) == 2
    assert "удалил сообщение" in bot.sent_messages[1][1]
    assert "changed" in bot.sent_messages[1][1]
    assert "В ответ на:" in bot.sent_messages[1][1]
    assert "reply context" in bot.sent_messages[1][1]
    assert "@SaveeBooot_bot" in bot.sent_messages[1][1]

    stats = await db.get_owner_stats(100)
    assert stats["messages"] == 1
    assert stats["edits"] == 1
    assert stats["deleted"] == 1


async def test_outgoing_message_is_not_archived(environment):
    settings, db, media, bot = environment
    outgoing = Message(
        message_id=2,
        date=datetime.now(timezone.utc),
        chat=Chat(id=200, type="private", first_name="Sender"),
        from_user=User(id=100, is_bot=False, first_name="Owner"),
        business_connection_id="connection-1",
        text="my own message",
    )
    await business_message_received(outgoing, bot, db, media, settings)
    assert await db.get_message("connection-1", 200, 2) is None
    assert bot.sent_messages == []


async def test_deleted_media_is_sent_before_report(environment, tmp_path):
    settings, db, media, bot = environment
    photo = tmp_path / "cached-photo.jpg"
    photo.write_bytes(b"fake-image")
    await db.save_message(
        {
            "connection_id": "connection-1",
            "chat_id": 200,
            "message_id": 7,
            "sender_id": 200,
            "sender_name": "Sender",
            "sender_username": "sender",
            "text": "",
            "content_type": "photo",
            "media_path": str(photo),
        }
    )
    event = BusinessMessagesDeleted(
        business_connection_id="connection-1",
        chat=Chat(id=200, type="private", first_name="Sender"),
        message_ids=[7],
    )
    await business_messages_deleted(
        event, bot, db, media, settings, bot_username="SaveeBooot_bot"
    )
    assert [event[0] for event in bot.events] == ["photo", "message"]
    assert "[фото]" in bot.events[1][1]
    assert "@SaveeBooot_bot" in bot.events[1][1]
