from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message

from ..config import Settings
from ..db import Database
from ..media import MediaManager
from ..utils import (
    chat_name,
    deleted_report,
    edited_report,
    extract_reply_context,
    extract_text,
    full_name,
    has_media,
    is_probably_disappearing,
    message_content_type,
    saved_media_report,
    to_iso,
    utc_now,
)

logger = logging.getLogger(__name__)
router = Router(name="business")
SAVE_COMMANDS = {"save", "/save", "!save", "сохрани", "сохранить"}


async def store_connection(db: Database, connection: BusinessConnection) -> dict[str, Any]:
    rights = getattr(connection, "rights", None)
    can_reply = bool(
        getattr(rights, "can_reply", False) or getattr(connection, "can_reply", False)
    )
    await db.upsert_connection(
        connection_id=connection.id,
        owner_id=connection.user.id,
        owner_chat_id=connection.user_chat_id,
        owner_name=full_name(connection.user),
        owner_username=connection.user.username,
        is_enabled=connection.is_enabled,
        can_reply=can_reply,
        connected_at=connection.date,
    )
    stored = await db.get_connection(connection.id)
    if stored is None:
        raise RuntimeError("Не удалось сохранить Business-подключение")
    return stored


async def ensure_connection(
    bot: Bot, db: Database, connection_id: str | None
) -> dict[str, Any] | None:
    if not connection_id:
        return None
    stored = await db.get_connection(connection_id)
    if stored is not None:
        return stored
    try:
        fresh = await bot.get_business_connection(business_connection_id=connection_id)
    except Exception as exc:
        logger.warning("Unknown business connection %s: %s", connection_id, type(exc).__name__)
        return None
    return await store_connection(db, fresh)


@router.business_connection()
async def business_connection_changed(
    connection: BusinessConnection,
    bot: Bot,
    db: Database,
) -> None:
    await store_connection(db, connection)
    if connection.is_enabled:
        text = (
            "✅ <b>Архивирование подключено</b>\n\n"
            "Новые входящие сообщения из разрешённых вами личных чатов будут сохраняться. "
            "Уведомления об удалениях и правках придут сюда.\n\n"
            "Проверить статус: /status. Условия хранения: /privacy."
        )
    else:
        text = (
            "⏸ <b>Подключение отключено</b>\n\n"
            "Новые сообщения больше не поступают в архив. Ранее сохранённую историю "
            "можно удалить командой /delete_my_data."
        )
    try:
        await bot.send_message(connection.user_chat_id, text)
    except Exception as exc:
        logger.warning("Could not send connection notification: %s", type(exc).__name__)


async def cache_incoming_message(
    bot: Bot,
    db: Database,
    media: MediaManager,
    connection: dict[str, Any],
    message: Message,
) -> dict[str, Any]:
    connection_id = message.business_connection_id or connection["id"]
    media_result = await media.cache(bot, message, connection_id)
    sender = message.from_user
    record = {
        "connection_id": connection_id,
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "sender_id": sender.id if sender else None,
        "sender_name": full_name(sender),
        "sender_username": sender.username if sender else None,
        "chat_title": chat_name(message),
        "text": extract_text(message),
        "reply_context": extract_reply_context(message),
        "content_type": message_content_type(message),
        "media_path": media_result.media_path,
        "is_outgoing": False,
        "is_disappearing": is_probably_disappearing(message),
        "sent_at": to_iso(message.date),
    }
    await db.save_message(record)
    stored = await db.get_message(connection_id, message.chat.id, message.message_id)
    return stored or record


@router.business_message()
async def business_message_received(
    message: Message,
    bot: Bot,
    db: Database,
    media: MediaManager,
    settings: Settings,
    bot_username: str = "",
) -> None:
    connection = await ensure_connection(bot, db, message.business_connection_id)
    if not connection or not connection["is_enabled"]:
        return

    sender_id = message.from_user.id if message.from_user else None
    is_outgoing = sender_id == connection["owner_id"]
    if is_outgoing:
        await maybe_save_replied_media(
            bot, db, media, settings, connection, message, bot_username
        )
        return

    await cache_incoming_message(bot, db, media, connection, message)


async def maybe_save_replied_media(
    bot: Bot,
    db: Database,
    media: MediaManager,
    settings: Settings,
    connection: dict[str, Any],
    message: Message,
    bot_username: str = "",
) -> None:
    replied = message.reply_to_message
    if not settings.save_media_on_reply or replied is None:
        return
    if replied.from_user and replied.from_user.id == connection["owner_id"]:
        return

    connection_id = message.business_connection_id or connection["id"]
    cached = await db.get_message(connection_id, message.chat.id, replied.message_id)
    reply_text = (message.text or message.caption or "").strip().lower()
    explicit = reply_text in SAVE_COMMANDS
    cached_path = cached.get("media_path") if cached else None
    disappearing_hint = is_probably_disappearing(replied) or bool(
        cached and cached.get("is_disappearing")
    )
    uncached_media = has_media(replied) and not cached_path

    # A normal cached photo does not need a copy on every reply. An explicit save
    # command, a protected/ephemeral candidate, or previously uncached media does.
    if not (explicit or disappearing_hint or uncached_media):
        return

    content_type = (
        cached.get("content_type") if cached else message_content_type(replied)
    ) or "document"
    if not has_media(replied) and not cached_path:
        if explicit:
            await bot.send_message(
                connection["owner_chat_id"],
                "В сообщении, на которое вы ответили, нет поддерживаемого медиафайла.",
            )
        return

    media_path = cached_path
    if not media_path:
        result = await media.cache(bot, replied, connection_id)
        media_path = result.media_path
        content_type = result.content_type

    sender = replied.from_user
    sender_name = (
        cached.get("sender_name")
        if cached
        else full_name(sender)
    )
    sender_username = (
        cached.get("sender_username")
        if cached
        else (sender.username if sender else None)
    )
    sender_id = cached.get("sender_id") if cached else (sender.id if sender else None)
    caption = (cached.get("text") if cached else "") or extract_text(replied)

    if not media_path:
        if explicit or disappearing_hint:
            await bot.send_message(
                connection["owner_chat_id"],
                "⚠️ Telegram не предоставил файл для сохранения, либо он превышает "
                "настроенный лимит. Для медиа с таймером попробуйте ответить до открытия.",
            )
        return

    # Media goes first, so the compact report appears directly underneath it.
    sent = await media.send_cached(
        bot,
        connection["owner_chat_id"],
        media_path,
        content_type,
    )
    if not sent:
        await bot.send_message(
            connection["owner_chat_id"],
            "⚠️ Файл найден в архиве, но отправить его не удалось.",
        )
        return

    report = saved_media_report(
        {
            "sender_name": sender_name,
            "sender_username": sender_username,
            "sender_id": sender_id,
        },
        content_type,
        caption,
        bot_username,
        disappearing=disappearing_hint,
    )
    await bot.send_message(connection["owner_chat_id"], report)


@router.edited_business_message()
async def business_message_edited(
    message: Message,
    bot: Bot,
    db: Database,
    media: MediaManager,
    settings: Settings,
    bot_username: str = "",
) -> None:
    connection = await ensure_connection(bot, db, message.business_connection_id)
    if not connection or not connection["is_enabled"]:
        return

    connection_id = message.business_connection_id or connection["id"]
    saved = await db.get_message(connection_id, message.chat.id, message.message_id)
    sender_id = message.from_user.id if message.from_user else None
    if sender_id == connection["owner_id"] or (saved and saved.get("is_outgoing")):
        return
    if saved is None:
        # The bot may have been connected after the original message arrived.
        # Cache the current version so a later deletion can still be reported.
        await cache_incoming_message(bot, db, media, connection, message)
        return

    old_text = saved.get("text") or ""
    new_text = extract_text(message)
    if old_text == new_text:
        return

    edited_at = to_iso(message.edit_date or utc_now())
    record = await db.record_edit(
        connection_id=connection_id,
        chat_id=message.chat.id,
        message_id=message.message_id,
        new_text=new_text,
        edited_at=edited_at,
    )
    if not settings.log_edits or record is None:
        return

    await bot.send_message(
        connection["owner_chat_id"],
        edited_report(record, old_text, new_text, edited_at, bot_username),
    )


@router.deleted_business_messages()
async def business_messages_deleted(
    event: BusinessMessagesDeleted,
    bot: Bot,
    db: Database,
    media: MediaManager,
    settings: Settings,
    bot_username: str = "",
) -> None:
    connection = await ensure_connection(bot, db, event.business_connection_id)
    if not connection:
        return

    deleted_at = to_iso(utc_now())
    for message_id in event.message_ids:
        record = await db.get_message(
            event.business_connection_id,
            event.chat.id,
            message_id,
        )
        if record is None:
            # Nothing can be recovered if the message predates the connection/cache.
            continue
        first_notification = await db.mark_deleted(
            event.business_connection_id,
            event.chat.id,
            message_id,
            deleted_at,
        )
        if not first_notification or record.get("is_outgoing") or not settings.log_deletions:
            continue

        try:
            media_path = record.get("media_path")
            media_sent = True
            if media_path:
                # Match the reference design: media above, deletion card below.
                media_sent = await media.send_cached(
                    bot,
                    connection["owner_chat_id"],
                    media_path,
                    record.get("content_type") or "document",
                )
            await bot.send_message(
                connection["owner_chat_id"],
                deleted_report(record, deleted_at, bot_username),
            )
            if media_path and not media_sent:
                await bot.send_message(
                    connection["owner_chat_id"],
                    "⚠️ Текст восстановлен, но вложение отправить не удалось.",
                )
        except Exception as exc:
            # One blocked/failed notification must not suppress the other ids
            # from the same BusinessMessagesDeleted update.
            logger.warning("Could not report deleted message: %s", type(exc).__name__)
