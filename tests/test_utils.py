from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import Chat, Message, PhotoSize, User

from app.utils import (
    deleted_report,
    extract_text,
    is_probably_disappearing,
    message_content_type,
    saved_media_report,
)


def make_message(**kwargs) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=50, type="private", first_name="Chat"),
        from_user=User(id=50, is_bot=False, first_name="Sender"),
        **kwargs,
    )


def test_text_and_content_type():
    message = make_message(text="Hello")
    assert extract_text(message) == "Hello"
    assert message_content_type(message) == "text"


def test_photo_and_protected_hint():
    photo = PhotoSize(
        file_id="file-id",
        file_unique_id="unique-id",
        width=100,
        height=100,
        file_size=123,
    )
    message = make_message(photo=[photo], caption="caption", has_protected_content=True)
    assert extract_text(message) == "caption"
    assert message_content_type(message) == "photo"
    assert is_probably_disappearing(message) is True


def test_reports_escape_user_content():
    record = {
        "sender_name": "<script>alert(1)</script>",
        "sender_username": None,
        "sender_id": 50,
        "chat_title": "<b>chat</b>",
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "content_type": "text",
        "text": "<img src=x>",
        "media_path": None,
    }
    report = deleted_report(record, bot_username="SaveeBooot_bot")
    assert "<script>" not in report
    assert "&lt;script&gt;" in report
    assert "&lt;img src=x&gt;" in report
    assert "удалил сообщение" in report
    assert "@SaveeBooot_bot" in report
    assert "Чат:" not in report


def test_saved_media_report_matches_compact_design():
    report = saved_media_report(
        {
            "sender_name": "RUBUP",
            "sender_username": "to5ru",
            "sender_id": 8474474613,
        },
        "photo",
        "",
        "SaveeBooot_bot",
        disappearing=True,
    )
    assert "RUBUP" in report
    assert "@to5ru" in report
    assert "самоуничтожающееся 📸 фото" in report
    assert "<b>Текст:</b>" in report
    assert "[текста нет]" in report
    assert "Сохранено с помощью" in report
    assert ">@SaveeBooot_bot</a>." in report
