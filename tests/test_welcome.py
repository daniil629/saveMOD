from __future__ import annotations

import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.commands import (
    HELP_TEXT,
    SUPPORT_USERNAME,
    WELCOME_PHOTO,
    start,
    welcome_caption,
    welcome_keyboard,
)


def test_welcome_keyboard_has_only_help_and_support():
    keyboard = welcome_keyboard()
    assert len(keyboard.inline_keyboard) == 2
    assert len(keyboard.inline_keyboard[0]) == 1
    assert len(keyboard.inline_keyboard[1]) == 1

    help_button = keyboard.inline_keyboard[0][0]
    support_button = keyboard.inline_keyboard[1][0]
    assert help_button.text == "📖 Как пользоваться?"
    assert help_button.callback_data == "welcome_help"
    assert support_button.text == "💬 Поддержка"
    assert support_button.url == f"https://t.me/{SUPPORT_USERNAME}"


def test_welcome_caption_is_safe_and_fits_telegram_limit():
    caption = welcome_caption('<b>"Bot"</b>')
    assert "&lt;b&gt;" in caption
    assert "<script>" not in caption
    assert len(caption) <= 1024
    assert "Наш функционал" in caption


def test_welcome_banner_is_packaged_png():
    assert WELCOME_PHOTO.is_file()
    data = WELCOME_PHOTO.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (1200, 600)
    assert "@ovexiu" in HELP_TEXT


async def test_start_sends_photo_welcome():
    message = SimpleNamespace(answer_photo=AsyncMock(), answer=AsyncMock())
    bot = SimpleNamespace(
        get_me=AsyncMock(return_value=SimpleNamespace(first_name="SaveeBooot"))
    )
    await start(message, bot)
    message.answer_photo.assert_awaited_once()
    message.answer.assert_not_awaited()
    kwargs = message.answer_photo.await_args.kwargs
    assert "SaveeBooot" in kwargs["caption"]
    assert kwargs["reply_markup"].inline_keyboard[1][0].url == "https://t.me/ovexiu"
