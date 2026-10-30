from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any

from aiogram.types import Message, User

CONTENT_TYPE_NAMES = {
    "text": "Текст",
    "photo": "Фото",
    "video": "Видео",
    "animation": "GIF/анимация",
    "voice": "Голосовое сообщение",
    "video_note": "Видеосообщение",
    "audio": "Аудио",
    "document": "Документ",
    "sticker": "Стикер",
    "contact": "Контакт",
    "location": "Геопозиция",
    "venue": "Место",
    "poll": "Опрос",
    "dice": "Дайс",
    "story": "История",
}

MEDIA_PLACEHOLDERS = {
    "photo": "[фото]",
    "video": "[видео]",
    "video_note": "[видео]",
    "animation": "[гиф]",
    "voice": "[голосовое]",
    "audio": "[аудио]",
    "document": "[документ]",
    "sticker": "[стикер]",
    "contact": "[контакт]",
    "location": "[геопозиция]",
    "venue": "[место]",
    "poll": "[опрос]",
    "dice": "[дайс]",
    "story": "[история]",
}

DISAPPEARING_LABELS = {
    "photo": "самоуничтожающееся 📸 фото",
    "video": "самоуничтожающееся 🎥 видео",
    "video_note": "самоуничтожающееся 🎥 видеосообщение",
    "voice": "самоуничтожающееся 🎤 голосовое сообщение",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return utc_now()


def to_iso(value: Any) -> str:
    return to_utc_datetime(value).isoformat(timespec="seconds")


def format_datetime(value: Any) -> str:
    if not value:
        return "неизвестно"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return escape(value)
    dt = to_utc_datetime(value)
    return dt.strftime("%d.%m.%Y %H:%M:%S UTC")


def full_name(user: User | None) -> str:
    if not user:
        return "Неизвестный отправитель"
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or "Без имени"


def chat_name(message: Message) -> str:
    chat = message.chat
    return chat.full_name or chat.title or f"Чат {chat.id}"


def message_content_type(message: Message) -> str:
    value = getattr(message, "content_type", "text")
    value = getattr(value, "value", value)
    return str(value) if value else "text"


def content_type_name(content_type: str | None) -> str:
    return CONTENT_TYPE_NAMES.get(content_type or "", "Сообщение")


def media_placeholder(content_type: str | None) -> str:
    return MEDIA_PLACEHOLDERS.get(content_type or "", "[сообщение]")


def extract_text(message: Message) -> str:
    if message.text is not None:
        return message.text
    if message.caption is not None:
        return message.caption
    if message.contact:
        contact = message.contact
        name = " ".join(part for part in (contact.first_name, contact.last_name) if part)
        return f"Контакт: {name}\nТелефон: {contact.phone_number}"
    if message.venue:
        venue = message.venue
        return f"Место: {venue.title}\nАдрес: {venue.address}"
    if message.location:
        location = message.location
        return f"Геопозиция: {location.latitude}, {location.longitude}"
    if message.poll:
        options = "\n".join(f"• {option.text}" for option in message.poll.options)
        return f"Опрос: {message.poll.question}\n{options}"
    if message.dice:
        return f"{message.dice.emoji} Значение: {message.dice.value}"
    if message.sticker and message.sticker.emoji:
        return f"Стикер: {message.sticker.emoji}"
    return ""


def extract_reply_context(message: Message) -> str | None:
    replied = message.reply_to_message
    if replied is None:
        return None
    text = extract_text(replied).strip()
    if text:
        return text[:500]
    return media_placeholder(message_content_type(replied))


def is_probably_disappearing(message: Message) -> bool:
    """Bot API has no reliable TTL flag; this is only a conservative hint."""
    return bool(getattr(message, "has_protected_content", False)) and message_content_type(message) in {
        "photo",
        "video",
        "video_note",
        "voice",
    }


def has_media(message: Message) -> bool:
    return message_content_type(message) in {
        "photo",
        "video",
        "animation",
        "voice",
        "video_note",
        "audio",
        "document",
        "sticker",
    }


def has_media_type(content_type: str | None) -> bool:
    return content_type in {
        "photo",
        "video",
        "animation",
        "voice",
        "video_note",
        "audio",
        "document",
        "sticker",
    }


def format_actor(name: str | None, username: str | None, user_id: int | None) -> str:
    safe_name = escape(name or "Неизвестный отправитель")
    safe_username = escape(username.lstrip("@")) if username else None
    if safe_username and user_id is not None:
        return (
            f'{safe_name} (<a href="https://t.me/{safe_username}">@{safe_username}</a>: '
            f"<code>{user_id}</code>)"
        )
    if safe_username:
        return f'{safe_name} (<a href="https://t.me/{safe_username}">@{safe_username}</a>)'
    if user_id is not None:
        return f"{safe_name} (<code>{user_id}</code>)"
    return safe_name


def format_user(name: str | None, username: str | None, user_id: int | None) -> str:
    """Backward-compatible alias used by older custom handlers."""
    return format_actor(name, username, user_id)


def bot_link(username: str | None) -> str:
    if not username:
        return ""
    safe_username = escape(username.lstrip("@"))
    return f'<a href="https://t.me/{safe_username}">@{safe_username}</a>'


def with_bot_footer(text: str, bot_username: str | None) -> str:
    footer = bot_link(bot_username)
    return f"{text}\n\n{footer}" if footer else text


def clipped_html(value: str | None, limit: int, empty: str = "[текста нет]") -> str:
    text = value or ""
    if not text:
        return escape(empty)
    if len(text) > limit:
        text = text[: max(1, limit - 1)].rstrip() + "…"
    return escape(text)


def deleted_report(
    record: dict[str, Any],
    deleted_at: str | None = None,
    bot_username: str | None = None,
) -> str:
    """Build the compact deletion card; deleted_at remains for API compatibility."""
    del deleted_at  # The compact design intentionally does not display timestamps.
    content_type = record.get("content_type") or "text"
    raw_text = record.get("text") or ""
    if raw_text:
        text = clipped_html(raw_text, 3000)
    elif content_type != "text":
        text = escape(media_placeholder(content_type))
    else:
        text = "[текста нет]"

    quote = f"<blockquote>{text}"
    reply_context = record.get("reply_context")
    if reply_context:
        quote += f"\n↩ <b>В ответ на:</b> {clipped_html(reply_context, 500)}"
    quote += "</blockquote>"

    if not record.get("media_path") and has_media_type(content_type):
        quote += "\n\n⚠️ <i>Вложение недоступно или превышает лимит.</i>"

    actor = format_actor(
        record.get("sender_name"),
        record.get("sender_username"),
        record.get("sender_id"),
    )
    report = f"🗑 {actor}\nудалил сообщение:\n\n{quote}"
    return with_bot_footer(report, bot_username)


def edited_report(
    record: dict[str, Any],
    old_text: str,
    new_text: str,
    edited_at: str | None = None,
    bot_username: str | None = None,
) -> str:
    """Build the compact edit card; edited_at remains for API compatibility."""
    del edited_at
    actor = format_actor(
        record.get("sender_name"),
        record.get("sender_username"),
        record.get("sender_id"),
    )
    report = (
        f"✏️ {actor}\n"
        "отредактировал сообщение:\n\n"
        f"<b>Было:</b>\n<blockquote>{clipped_html(old_text, 1400)}</blockquote>\n\n"
        f"<b>Стало:</b>\n<blockquote>{clipped_html(new_text, 1400)}</blockquote>"
    )
    return with_bot_footer(report, bot_username)


def saved_media_report(
    record: dict[str, Any],
    content_type: str,
    text: str | None,
    bot_username: str | None = None,
    disappearing: bool = True,
) -> str:
    actor = format_actor(
        record.get("sender_name"),
        record.get("sender_username"),
        record.get("sender_id"),
    )
    if disappearing:
        label = DISAPPEARING_LABELS.get(content_type, "самоуничтожающееся медиа")
        heading = f"{actor} отправил(а)\n{label}"
    else:
        heading = f"📎 {actor}\nмедиа сохранено"

    report = (
        f"{heading}\n\n"
        f"<b>Текст:</b>\n<blockquote>{clipped_html(text, 2000)}</blockquote>\n\n"
        "🖼 <b>Сохранено с помощью</b>"
    )
    footer = bot_link(bot_username)
    if footer:
        report += f"\n{footer}."
    return report
