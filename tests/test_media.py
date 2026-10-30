from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from aiogram.types import Chat, Message, PhotoSize, User

from app.config import Settings
from app.media import MediaManager, describe_media


class FakeBot:
    async def download(self, file_object, destination):
        Path(destination).write_bytes(b"fake-image-data")


def make_photo_message() -> Message:
    return Message(
        message_id=7,
        date=datetime.now(timezone.utc),
        chat=Chat(id=50, type="private"),
        from_user=User(id=50, is_bot=False, first_name="Sender"),
        photo=[
            PhotoSize(
                file_id="photo-id",
                file_unique_id="photo-unique-id",
                width=640,
                height=480,
                file_size=15,
            )
        ],
    )


async def test_media_cache_and_safe_delete(tmp_path):
    settings = Settings(bot_token="123:TEST", data_dir=tmp_path / "data")
    settings.prepare_directories()
    manager = MediaManager(settings)
    message = make_photo_message()

    descriptor = describe_media(message)
    assert descriptor is not None
    assert descriptor.content_type == "photo"
    assert descriptor.extension == ".jpg"

    result = await manager.cache(FakeBot(), message, "secret-connection-id")
    assert result.error is None
    assert result.media_path is not None
    cached_path = Path(result.media_path)
    assert cached_path.read_bytes() == b"fake-image-data"
    assert "secret-connection-id" not in str(cached_path)

    outside = tmp_path / "outside.txt"
    outside.write_text("must stay")
    deleted = manager.delete_paths([str(cached_path), str(outside)])
    assert deleted == 1
    assert not cached_path.exists()
    assert outside.read_text() == "must stay"
