from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiosqlite

from .utils import to_iso, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS connections (
    id              TEXT PRIMARY KEY,
    owner_id        INTEGER NOT NULL,
    owner_chat_id   INTEGER NOT NULL,
    owner_name      TEXT NOT NULL,
    owner_username  TEXT,
    is_enabled      INTEGER NOT NULL DEFAULT 1,
    can_reply       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_connections_owner
    ON connections(owner_id);

CREATE TABLE IF NOT EXISTS messages (
    connection_id   TEXT NOT NULL,
    chat_id         INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    sender_id       INTEGER,
    sender_name     TEXT,
    sender_username TEXT,
    chat_title      TEXT,
    text            TEXT NOT NULL DEFAULT '',
    reply_context   TEXT,
    content_type    TEXT NOT NULL DEFAULT 'text',
    media_path      TEXT,
    is_outgoing     INTEGER NOT NULL DEFAULT 0,
    is_disappearing INTEGER NOT NULL DEFAULT 0,
    sent_at         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT,
    PRIMARY KEY (connection_id, chat_id, message_id),
    FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_deleted_at ON messages(deleted_at);

CREATE TABLE IF NOT EXISTS edits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id   TEXT NOT NULL,
    chat_id         INTEGER NOT NULL,
    message_id      INTEGER NOT NULL,
    old_text        TEXT NOT NULL DEFAULT '',
    new_text        TEXT NOT NULL DEFAULT '',
    edited_at       TEXT NOT NULL,
    FOREIGN KEY (connection_id, chat_id, message_id)
        REFERENCES messages(connection_id, chat_id, message_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_edits_message
    ON edits(connection_id, chat_id, message_id);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("База данных не подключена")
        return self._connection

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._connection = await aiosqlite.connect(self.path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA journal_mode = WAL")
        await self._connection.execute("PRAGMA synchronous = NORMAL")
        await self._connection.executescript(SCHEMA)
        await self._run_migrations()
        await self._connection.commit()

    async def _run_migrations(self) -> None:
        cursor = await self.connection.execute("PRAGMA table_info(messages)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "reply_context" not in columns:
            await self.connection.execute(
                "ALTER TABLE messages ADD COLUMN reply_context TEXT"
            )

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    @staticmethod
    def _dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    async def upsert_connection(
        self,
        *,
        connection_id: str,
        owner_id: int,
        owner_chat_id: int,
        owner_name: str,
        owner_username: str | None,
        is_enabled: bool,
        can_reply: bool,
        connected_at: Any = None,
    ) -> None:
        now = to_iso(utc_now())
        created_at = to_iso(connected_at) if connected_at is not None else now
        async with self._lock:
            # Telegram currently permits one connected business bot per account.
            # A new active id supersedes older ids; a delayed disable update for
            # an old id must not accidentally disable the current connection.
            if is_enabled:
                await self.connection.execute(
                    "UPDATE connections SET is_enabled = 0, updated_at = ? "
                    "WHERE owner_id = ? AND id <> ?",
                    (now, owner_id, connection_id),
                )
            await self.connection.execute(
                """
                INSERT INTO connections (
                    id, owner_id, owner_chat_id, owner_name, owner_username,
                    is_enabled, can_reply, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    owner_chat_id = excluded.owner_chat_id,
                    owner_name = excluded.owner_name,
                    owner_username = excluded.owner_username,
                    is_enabled = excluded.is_enabled,
                    can_reply = excluded.can_reply,
                    updated_at = excluded.updated_at
                """,
                (
                    connection_id,
                    owner_id,
                    owner_chat_id,
                    owner_name,
                    owner_username,
                    int(is_enabled),
                    int(can_reply),
                    created_at,
                    now,
                ),
            )
            await self.connection.commit()

    async def get_connection(self, connection_id: str) -> dict[str, Any] | None:
        async with self._lock:
            cursor = await self.connection.execute(
                "SELECT * FROM connections WHERE id = ?", (connection_id,)
            )
            return self._dict(await cursor.fetchone())

    async def get_owner_connections(self, owner_id: int) -> list[dict[str, Any]]:
        async with self._lock:
            cursor = await self.connection.execute(
                "SELECT * FROM connections WHERE owner_id = ? ORDER BY updated_at DESC",
                (owner_id,),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def save_message(self, record: dict[str, Any]) -> bool:
        now = to_iso(utc_now())
        created_at = record.get("created_at") or now
        async with self._lock:
            cursor = await self.connection.execute(
                """
                INSERT OR IGNORE INTO messages (
                    connection_id, chat_id, message_id, sender_id, sender_name,
                    sender_username, chat_title, text, reply_context, content_type,
                    media_path, is_outgoing, is_disappearing, sent_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["connection_id"],
                    record["chat_id"],
                    record["message_id"],
                    record.get("sender_id"),
                    record.get("sender_name"),
                    record.get("sender_username"),
                    record.get("chat_title"),
                    record.get("text") or "",
                    record.get("reply_context"),
                    record.get("content_type") or "text",
                    record.get("media_path"),
                    int(bool(record.get("is_outgoing"))),
                    int(bool(record.get("is_disappearing"))),
                    record.get("sent_at") or created_at,
                    created_at,
                    now,
                ),
            )
            await self.connection.commit()
            return cursor.rowcount > 0

    async def get_message(
        self, connection_id: str, chat_id: int, message_id: int
    ) -> dict[str, Any] | None:
        async with self._lock:
            cursor = await self.connection.execute(
                "SELECT * FROM messages WHERE connection_id = ? AND chat_id = ? AND message_id = ?",
                (connection_id, chat_id, message_id),
            )
            return self._dict(await cursor.fetchone())

    async def record_edit(
        self,
        *,
        connection_id: str,
        chat_id: int,
        message_id: int,
        new_text: str,
        edited_at: str,
    ) -> dict[str, Any] | None:
        async with self._lock:
            cursor = await self.connection.execute(
                "SELECT * FROM messages WHERE connection_id = ? AND chat_id = ? AND message_id = ?",
                (connection_id, chat_id, message_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            record = dict(row)
            old_text = record.get("text") or ""
            await self.connection.execute(
                """
                INSERT INTO edits (
                    connection_id, chat_id, message_id, old_text, new_text, edited_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (connection_id, chat_id, message_id, old_text, new_text, edited_at),
            )
            await self.connection.execute(
                "UPDATE messages SET text = ?, updated_at = ? "
                "WHERE connection_id = ? AND chat_id = ? AND message_id = ?",
                (new_text, edited_at, connection_id, chat_id, message_id),
            )
            await self.connection.commit()
            record["old_text"] = old_text
            record["new_text"] = new_text
            return record

    async def mark_deleted(
        self, connection_id: str, chat_id: int, message_id: int, deleted_at: str
    ) -> bool:
        async with self._lock:
            cursor = await self.connection.execute(
                "UPDATE messages SET deleted_at = ? "
                "WHERE connection_id = ? AND chat_id = ? AND message_id = ? AND deleted_at IS NULL",
                (deleted_at, connection_id, chat_id, message_id),
            )
            await self.connection.commit()
            return cursor.rowcount > 0

    async def get_owner_stats(self, owner_id: int) -> dict[str, int]:
        queries = {
            "active_connections": (
                "SELECT COUNT(*) FROM connections WHERE owner_id = ? AND is_enabled = 1",
                (owner_id,),
            ),
            "messages": (
                "SELECT COUNT(*) FROM messages m JOIN connections c ON c.id = m.connection_id "
                "WHERE c.owner_id = ?",
                (owner_id,),
            ),
            "deleted": (
                "SELECT COUNT(*) FROM messages m JOIN connections c ON c.id = m.connection_id "
                "WHERE c.owner_id = ? AND m.deleted_at IS NOT NULL",
                (owner_id,),
            ),
            "edits": (
                "SELECT COUNT(*) FROM edits e JOIN connections c ON c.id = e.connection_id "
                "WHERE c.owner_id = ?",
                (owner_id,),
            ),
            "media": (
                "SELECT COUNT(*) FROM messages m JOIN connections c ON c.id = m.connection_id "
                "WHERE c.owner_id = ? AND m.media_path IS NOT NULL",
                (owner_id,),
            ),
        }
        result: dict[str, int] = {}
        async with self._lock:
            for key, (query, params) in queries.items():
                cursor = await self.connection.execute(query, params)
                row = await cursor.fetchone()
                result[key] = int(row[0]) if row else 0
        return result

    async def cleanup_expired(self, cutoff_iso: str) -> tuple[list[str], int]:
        async with self._lock:
            cursor = await self.connection.execute(
                "SELECT media_path FROM messages WHERE created_at < ? AND media_path IS NOT NULL",
                (cutoff_iso,),
            )
            paths = [row[0] for row in await cursor.fetchall() if row[0]]
            cursor = await self.connection.execute(
                "DELETE FROM messages WHERE created_at < ?", (cutoff_iso,)
            )
            count = max(0, cursor.rowcount)
            await self.connection.commit()
            return paths, count

    async def delete_owner_data(self, owner_id: int) -> tuple[list[str], dict[str, int]]:
        async with self._lock:
            cursor = await self.connection.execute(
                "SELECT m.media_path FROM messages m JOIN connections c ON c.id = m.connection_id "
                "WHERE c.owner_id = ? AND m.media_path IS NOT NULL",
                (owner_id,),
            )
            paths = [row[0] for row in await cursor.fetchall() if row[0]]
            stats: dict[str, int] = {}
            for key, table in (("messages", "messages"), ("edits", "edits")):
                alias = "m" if table == "messages" else "e"
                cursor = await self.connection.execute(
                    f"SELECT COUNT(*) FROM {table} {alias} "
                    f"JOIN connections c ON c.id = {alias}.connection_id WHERE c.owner_id = ?",
                    (owner_id,),
                )
                row = await cursor.fetchone()
                stats[key] = int(row[0]) if row else 0
            cursor = await self.connection.execute(
                "DELETE FROM connections WHERE owner_id = ?", (owner_id,)
            )
            stats["connections"] = max(0, cursor.rowcount)
            await self.connection.commit()
            return paths, stats
