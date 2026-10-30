from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, LinkPreviewOptions

from .config import Settings
from .db import Database
from .handlers import business_router, commands_router
from .media import MediaManager
from .utils import to_iso, utc_now

logger = logging.getLogger(__name__)


async def cleanup_loop(db: Database, media: MediaManager, settings: Settings) -> None:
    while True:
        try:
            cutoff = to_iso(utc_now() - timedelta(days=settings.retention_days))
            paths, records = await db.cleanup_expired(cutoff)
            files = media.delete_paths(paths)
            if records or files:
                logger.info("Retention cleanup: %s records, %s files", records, files)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Retention cleanup failed")
        await asyncio.sleep(settings.cleanup_interval_hours * 3600)


async def main() -> None:
    try:
        settings = Settings.from_env()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    settings.prepare_directories()

    db = Database(settings.db_path)
    await db.connect()
    media = MediaManager(settings)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview=LinkPreviewOptions(is_disabled=True),
        ),
    )
    dp = Dispatcher()
    dp.include_router(commands_router)
    dp.include_router(business_router)
    cleanup_task: asyncio.Task[None] | None = None

    try:
        me = await bot.get_me()
        logger.info("Started as @%s (id=%s)", me.username, me.id)
        if not getattr(me, "can_connect_to_business", False):
            logger.warning(
                "Business/Secretary Mode appears disabled. Enable it in @BotFather, "
                "otherwise Telegram will not allow account connections."
            )
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Подключение и возможности"),
                BotCommand(command="status", description="Статус и статистика архива"),
                BotCommand(command="privacy", description="Приватность и хранение"),
                BotCommand(command="delete_my_data", description="Удалить мою историю"),
                BotCommand(command="help", description="Помощь"),
            ]
        )
        if settings.retention_days > 0:
            cleanup_task = asyncio.create_task(
                cleanup_loop(db, media, settings),
                name="retention-cleanup",
            )
        await dp.start_polling(
            bot,
            db=db,
            media=media,
            settings=settings,
            bot_username=me.username or "",
            close_bot_session=False,
        )
    finally:
        if cleanup_task is not None:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
