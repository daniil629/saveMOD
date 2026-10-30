from __future__ import annotations

from html import escape
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import Settings
from ..db import Database
from ..media import MediaManager

router = Router(name="commands")

PRIVACY_TEXT = (
    "🔐 <b>Приватность</b>\n\n"
    "Бот сохраняет только сообщения из личных чатов, которые вы сами разрешили при "
    "подключении через «Автоматизацию чатов». Уведомления приходят только вам.\n\n"
    "База и медиа хранятся на сервере владельца бота. Срок хранения задаётся настройкой "
    "RETENTION_DAYS. Команда /delete_my_data удаляет вашу историю и файлы.\n\n"
    "Бот не восстанавливает старые удалённые сообщения, не работает в секретных чатах "
    "и не обходит ограничения Telegram. Используйте архивирование законно и, когда это "
    "требуется, предупреждайте собеседников об обработке переписки."
)


SUPPORT_USERNAME = "ovexiu"
WELCOME_PHOTO = Path(__file__).resolve().parents[1] / "assets" / "welcome.png"

HELP_TEXT = (
    "📖 <b>Как пользоваться</b>\n\n"
    "<b>1. Подключите бота</b>\n"
    "Откройте <b>Настройки Telegram → Автоматизация чатов</b> "
    "(в старых версиях: Telegram для бизнеса → Чат-боты), добавьте этого бота "
    "и выберите личные чаты, которые разрешаете архивировать.\n\n"
    "<b>2. Удалённые и отредактированные сообщения</b>\n"
    "После подключения бот автоматически сохраняет новые входящие сообщения. "
    "Если собеседник удалит или изменит сообщение, карточка с сохранённой копией "
    "придёт в этот чат.\n\n"
    "<b>3. Одноразовые фото, видео и кружки</b>\n"
    "Не открывайте медиа и ответьте на него в исходном диалоге словом "
    "<code>save</code> или <code>/save</code>. Если Telegram ещё предоставляет файл, "
    "бот пришлёт сохранённую копию сюда.\n\n"
    "<b>4. Управление</b>\n"
    "/status — подключение и статистика архива\n"
    "/privacy — условия хранения данных\n"
    "/delete_my_data — удалить вашу историю и файлы\n\n"
    "⚠️ Старые удалённые сообщения и секретные чаты недоступны. Чтобы полностью "
    "прекратить архивирование, отключите бота в «Автоматизации чатов».\n\n"
    '💬 Поддержка: <a href="https://t.me/ovexiu">@ovexiu</a>'
)


def welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Как пользоваться?",
                    callback_data="welcome_help",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Поддержка",
                    url=f"https://t.me/{SUPPORT_USERNAME}",
                )
            ],
        ]
    )


def welcome_caption(bot_name: str) -> str:
    return (
        f"🤖 <b>{escape(bot_name)}</b> — бот, который сохраняет важные сообщения и медиа.\n\n"
        "<b>Наш функционал 👇</b>\n"
        "<blockquote>• Одноразовые фото, видео, кружки и голосовые — если Telegram отдаёт файл.\n"
        "• Медиа с таймером по ответу до открытия.\n"
        "• Удалённые сообщения.\n"
        "• Отредактированные сообщения: старая и новая версии.</blockquote>\n\n"
        "Откройте инструкцию, чтобы подключить бота и проверить возможности 👇"
    )


@router.message(CommandStart(), F.chat.type == "private")
async def start(message: Message, bot: Bot) -> None:
    me = await bot.get_me()
    caption = welcome_caption(me.first_name or "Message Keeper")
    keyboard = welcome_keyboard()
    if WELCOME_PHOTO.is_file():
        await message.answer_photo(
            photo=FSInputFile(WELCOME_PHOTO, filename="welcome.png"),
            caption=caption,
            reply_markup=keyboard,
        )
    else:
        await message.answer(caption, reply_markup=keyboard)


@router.message(Command("help"), F.chat.type == "private")
async def help_command(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.callback_query(F.data == "welcome_help")
async def welcome_help_callback(callback: CallbackQuery) -> None:
    await callback.answer("Инструкция открыта")
    if callback.message:
        await callback.message.answer(HELP_TEXT)


@router.message(Command("privacy"), F.chat.type == "private")
async def privacy(message: Message, settings: Settings) -> None:
    retention = (
        "автоочистка отключена"
        if settings.retention_days == 0
        else f"автоочистка через {settings.retention_days} дн."
    )
    await message.answer(PRIVACY_TEXT + f"\n\nТекущая настройка сервера: {retention}")


@router.message(Command("status"), F.chat.type == "private")
async def status(message: Message, db: Database, settings: Settings) -> None:
    if not message.from_user:
        return
    stats = await db.get_owner_stats(message.from_user.id)
    connections = await db.get_owner_connections(message.from_user.id)
    active = next((item for item in connections if item["is_enabled"]), None)
    if active:
        connection_text = "🟢 Подключение активно"
    elif connections:
        connection_text = "🔴 Подключение отключено в Telegram"
    else:
        connection_text = "⚪ Бот ещё не подключён через «Автоматизацию чатов»"
    retention = "выключена" if settings.retention_days == 0 else f"{settings.retention_days} дн."
    await message.answer(
        "📊 <b>Ваш архив</b>\n\n"
        f"{connection_text}\n"
        f"💾 Сообщений: <b>{stats['messages']}</b>\n"
        f"🗑 Удалений зафиксировано: <b>{stats['deleted']}</b>\n"
        f"✏️ Правок зафиксировано: <b>{stats['edits']}</b>\n"
        f"📎 Медиафайлов: <b>{stats['media']}</b>\n"
        f"🧹 Автоочистка: <b>{retention}</b>"
    )


@router.message(Command("delete_my_data"), F.chat.type == "private")
async def delete_my_data(message: Message) -> None:
    if not message.from_user:
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить всё",
                    callback_data=f"purge_yes:{message.from_user.id}",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"purge_no:{message.from_user.id}",
                ),
            ]
        ]
    )
    await message.answer(
        "⚠️ Удалить из базы <b>всю вашу историю, медиа и сведения о подключениях</b>? "
        "Действие необратимо. Само подключение в Telegram при этом нужно отключать отдельно.",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.regexp(r"^purge_(yes|no):\d+$"))
async def purge_callback(
    callback: CallbackQuery,
    db: Database,
    media: MediaManager,
) -> None:
    if not callback.data or not callback.from_user:
        return
    action, raw_owner_id = callback.data.split(":", maxsplit=1)
    owner_id = int(raw_owner_id)
    if callback.from_user.id != owner_id:
        await callback.answer("Эта кнопка предназначена другому пользователю.", show_alert=True)
        return

    if action == "purge_no":
        await callback.answer("Отменено")
        if callback.message:
            await callback.message.edit_text("Удаление отменено. Данные не изменены.")
        return

    paths, stats = await db.delete_owner_data(owner_id)
    deleted_files = media.delete_paths(paths)
    await callback.answer("Данные удалены")
    if callback.message:
        await callback.message.edit_text(
            "✅ История удалена.\n\n"
            f"Сообщений: {stats['messages']}, правок: {stats['edits']}, "
            f"файлов с диска: {deleted_files}.\n\n"
            "Чтобы бот не начал новый архив, отключите его в «Автоматизации чатов»."
        )
