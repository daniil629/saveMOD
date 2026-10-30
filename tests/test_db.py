from __future__ import annotations

from datetime import timedelta

import aiosqlite
import pytest_asyncio

from app.db import SCHEMA, Database
from app.utils import to_iso, utc_now


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


def make_record(**overrides):
    now = to_iso(utc_now())
    record = {
        "connection_id": "connection-1",
        "chat_id": 200,
        "message_id": 1,
        "sender_id": 200,
        "sender_name": "Test User",
        "sender_username": "test_user",
        "chat_title": "Test User",
        "text": "old text",
        "content_type": "photo",
        "media_path": "/media/example.jpg",
        "is_outgoing": False,
        "is_disappearing": False,
        "sent_at": now,
        "created_at": now,
    }
    record.update(overrides)
    return record


async def add_connection(db: Database, connection_id: str = "connection-1"):
    await db.upsert_connection(
        connection_id=connection_id,
        owner_id=100,
        owner_chat_id=100,
        owner_name="Owner",
        owner_username="owner",
        is_enabled=True,
        can_reply=False,
    )


async def test_message_lifecycle_and_owner_stats(db: Database):
    await add_connection(db)
    assert await db.save_message(make_record()) is True
    # Duplicate Telegram updates must not create duplicate messages.
    assert await db.save_message(make_record()) is False

    loaded = await db.get_message("connection-1", 200, 1)
    assert loaded is not None
    assert loaded["text"] == "old text"

    edited_at = to_iso(utc_now())
    edited = await db.record_edit(
        connection_id="connection-1",
        chat_id=200,
        message_id=1,
        new_text="new text",
        edited_at=edited_at,
    )
    assert edited is not None
    assert edited["old_text"] == "old text"
    assert (await db.get_message("connection-1", 200, 1))["text"] == "new text"

    assert await db.mark_deleted("connection-1", 200, 1, edited_at) is True
    assert await db.mark_deleted("connection-1", 200, 1, edited_at) is False

    stats = await db.get_owner_stats(100)
    assert stats == {
        "active_connections": 1,
        "messages": 1,
        "deleted": 1,
        "edits": 1,
        "media": 1,
    }


async def test_retention_cleanup_and_owner_purge(db: Database):
    await add_connection(db)
    old_date = to_iso(utc_now() - timedelta(days=30))
    await db.save_message(
        make_record(message_id=1, created_at=old_date, sent_at=old_date, media_path="/media/old.jpg")
    )
    await db.save_message(make_record(message_id=2, media_path="/media/new.jpg"))

    paths, deleted = await db.cleanup_expired(to_iso(utc_now() - timedelta(days=7)))
    assert deleted == 1
    assert paths == ["/media/old.jpg"]
    assert await db.get_message("connection-1", 200, 1) is None
    assert await db.get_message("connection-1", 200, 2) is not None

    await db.record_edit(
        connection_id="connection-1",
        chat_id=200,
        message_id=2,
        new_text="changed",
        edited_at=to_iso(utc_now()),
    )
    paths, stats = await db.delete_owner_data(100)
    assert paths == ["/media/new.jpg"]
    assert stats["messages"] == 1
    assert stats["edits"] == 1
    assert stats["connections"] == 1
    assert await db.get_owner_connections(100) == []
    assert (await db.get_owner_stats(100))["messages"] == 0


async def test_replaced_connection_is_marked_inactive(db: Database):
    await add_connection(db, "old")
    await add_connection(db, "new")
    assert (await db.get_connection("old"))["is_enabled"] == 0
    assert (await db.get_connection("new"))["is_enabled"] == 1
    assert (await db.get_owner_stats(100))["active_connections"] == 1

    # A delayed disable update for the superseded id must not disable "new".
    await db.upsert_connection(
        connection_id="old",
        owner_id=100,
        owner_chat_id=100,
        owner_name="Owner",
        owner_username="owner",
        is_enabled=False,
        can_reply=False,
    )
    assert (await db.get_connection("new"))["is_enabled"] == 1


async def test_existing_database_gets_reply_context_migration(tmp_path):
    path = tmp_path / "old-schema.db"
    old_schema = SCHEMA.replace("    reply_context   TEXT,\n", "")
    async with aiosqlite.connect(path) as connection:
        await connection.executescript(old_schema)
        await connection.commit()

    db = Database(path)
    await db.connect()
    try:
        cursor = await db.connection.execute("PRAGMA table_info(messages)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "reply_context" in columns
    finally:
        await db.close()
