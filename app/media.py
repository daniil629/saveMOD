from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from aiogram import Bot
from aiogram.types import FSInputFile, Message

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MediaDescriptor:
    file_object: Any
    content_type: str
    extension: str


@dataclass(slots=True)
class MediaResult:
    content_type: str
    media_path: str | None = None
    error: str | None = None


def _safe_extension(file_name: str | None, default: str) -> str:
    if not file_name:
        return default
    suffix = Path(file_name).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return suffix
    return default


def describe_media(message: Message) -> MediaDescriptor | None:
    if message.photo:
        return MediaDescriptor(message.photo[-1], "photo", ".jpg")
    if message.video:
        extension = _safe_extension(getattr(message.video, "file_name", None), ".mp4")
        return MediaDescriptor(message.video, "video", extension)
    if message.animation:
        extension = _safe_extension(getattr(message.animation, "file_name", None), ".mp4")
        return MediaDescriptor(message.animation, "animation", extension)
    if message.voice:
        return MediaDescriptor(message.voice, "voice", ".ogg")
    if message.video_note:
        return MediaDescriptor(message.video_note, "video_note", ".mp4")
    if message.audio:
        extension = _safe_extension(getattr(message.audio, "file_name", None), ".mp3")
        return MediaDescriptor(message.audio, "audio", extension)
    if message.sticker:
        if message.sticker.is_animated:
            extension = ".tgs"
        elif message.sticker.is_video:
            extension = ".webm"
        else:
            extension = ".webp"
        return MediaDescriptor(message.sticker, "sticker", extension)
    if message.document:
        extension = _safe_extension(message.document.file_name, ".bin")
        return MediaDescriptor(message.document, "document", extension)
    return None


class MediaManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.media_dir.resolve()

    async def cache(self, bot: Bot, message: Message, connection_id: str) -> MediaResult:
        descriptor = describe_media(message)
        if descriptor is None:
            return MediaResult(content_type="text")
        if not self.settings.save_media:
            return MediaResult(descriptor.content_type, error="disabled")

        file_size = getattr(descriptor.file_object, "file_size", None)
        if file_size and file_size > self.settings.max_media_size_bytes:
            return MediaResult(descriptor.content_type, error="too_large")

        connection_hash = hashlib.sha256(connection_id.encode("utf-8")).hexdigest()[:20]
        directory = self.root / connection_hash / str(message.chat.id)
        filename = f"{message.message_id}{descriptor.extension}"
        destination = directory / filename
        temporary = directory / f".{filename}.part"

        if destination.exists() and destination.stat().st_size > 0:
            return MediaResult(descriptor.content_type, str(destination))

        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            await bot.download(descriptor.file_object, destination=temporary)
            actual_size = temporary.stat().st_size
            if actual_size == 0:
                raise OSError("Telegram returned an empty file")
            if actual_size > self.settings.max_media_size_bytes:
                temporary.unlink(missing_ok=True)
                return MediaResult(descriptor.content_type, error="too_large")
            temporary.replace(destination)
            try:
                destination.chmod(0o600)
            except OSError:
                pass
            return MediaResult(descriptor.content_type, str(destination))
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            logger.warning(
                "Media download failed: type=%s chat=%s message=%s error=%s",
                descriptor.content_type,
                message.chat.id,
                message.message_id,
                type(exc).__name__,
            )
            return MediaResult(descriptor.content_type, error=type(exc).__name__)

    def delete_paths(self, paths: Iterable[str]) -> int:
        deleted = 0
        for raw_path in set(paths):
            if not raw_path:
                continue
            try:
                path = Path(raw_path).resolve()
                if path != self.root and self.root not in path.parents:
                    logger.warning("Refusing to delete a path outside the media directory")
                    continue
                if path.is_file():
                    path.unlink()
                    deleted += 1
            except OSError as exc:
                logger.warning("Could not delete cached media: %s", type(exc).__name__)
        self._remove_empty_directories()
        return deleted

    def _remove_empty_directories(self) -> None:
        if not self.root.exists():
            return
        for directory, dirnames, filenames in os.walk(self.root, topdown=False):
            if dirnames or filenames:
                continue
            path = Path(directory)
            if path == self.root:
                continue
            try:
                path.rmdir()
            except OSError:
                pass

    async def send_cached(
        self,
        bot: Bot,
        chat_id: int,
        media_path: str,
        content_type: str,
        caption: str | None = None,
    ) -> bool:
        path = Path(media_path)
        if not path.is_file():
            return False

        input_file = FSInputFile(path, filename=path.name)
        try:
            if content_type == "photo":
                await bot.send_photo(chat_id, input_file, caption=caption)
            elif content_type == "video":
                await bot.send_video(chat_id, input_file, caption=caption)
            elif content_type == "animation":
                await bot.send_animation(chat_id, input_file, caption=caption)
            elif content_type == "voice":
                await bot.send_voice(chat_id, input_file, caption=caption)
            elif content_type == "video_note":
                await bot.send_video_note(chat_id, input_file)
            elif content_type == "audio":
                await bot.send_audio(chat_id, input_file, caption=caption)
            elif content_type == "sticker":
                await bot.send_sticker(chat_id, input_file)
            else:
                await bot.send_document(chat_id, input_file, caption=caption)
            return True
        except Exception as first_error:
            logger.warning("Native media send failed, trying document: %s", type(first_error).__name__)
            try:
                fallback_file = FSInputFile(path, filename=path.name)
                await bot.send_document(chat_id, fallback_file, caption=caption)
                return True
            except Exception as second_error:
                logger.error("Could not send cached media: %s", type(second_error).__name__)
                return False
