from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} должен быть целым числом") from exc
    if value < minimum:
        raise RuntimeError(f"{name} должен быть не меньше {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    data_dir: Path
    save_media: bool = True
    max_media_size_mb: int = 20
    retention_days: int = 7
    cleanup_interval_hours: int = 12
    log_deletions: bool = True
    log_edits: bool = True
    save_media_on_reply: bool = True
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "messages.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def max_media_size_bytes(self) -> int:
        return self.max_media_size_mb * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token or ":" not in token or token.endswith("REPLACE_ME"):
            raise RuntimeError(
                "Укажите BOT_TOKEN в файле .env. Получите токен у @BotFather; "
                "не публикуйте его и не отправляйте другим людям."
            )

        data_dir = Path(os.getenv("DATA_DIR", "./data")).expanduser().resolve()
        return cls(
            bot_token=token,
            data_dir=data_dir,
            save_media=_as_bool(os.getenv("SAVE_MEDIA"), True),
            max_media_size_mb=_as_int("MAX_MEDIA_SIZE_MB", 20, minimum=1),
            retention_days=_as_int("RETENTION_DAYS", 7, minimum=0),
            cleanup_interval_hours=_as_int("CLEANUP_INTERVAL_HOURS", 12, minimum=1),
            log_deletions=_as_bool(os.getenv("LOG_DELETIONS"), True),
            log_edits=_as_bool(os.getenv("LOG_EDITS"), True),
            save_media_on_reply=_as_bool(os.getenv("SAVE_MEDIA_ON_REPLY"), True),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        )

    def prepare_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.media_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
