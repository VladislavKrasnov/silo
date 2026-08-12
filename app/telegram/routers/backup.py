from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import os
import tempfile
from pathlib import Path

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile

from app.backup import build_backup_archive
from app.config import PROJECT_ROOT_DIR
from app.constants import TELEGRAM_DOCUMENT_UPLOAD_LIMIT_BYTES
from app.i18n import translate
from app.system_stats import format_byte_count
from app.telegram import views
from app.telegram.callbacks import BackupCommand
from app.telegram.context import PanelContext
from app.telegram.formatting import mono

logger = logging.getLogger(__name__)

router = Router(name="backup")


@router.callback_query(BackupCommand.filter())
async def create_backup(callback: CallbackQuery, context: PanelContext, bot: Bot, lang: str) -> None:
    if callback.message is None:
        return
    await callback.answer()
    await views.show_transition(callback, translate("backup.progress", lang))

    chat_id = callback.message.chat.id
    descriptor, raw_path = tempfile.mkstemp(prefix="silo-backup-", suffix=".zip")
    os.close(descriptor)
    archive_path = Path(raw_path)

    try:
        archive = await asyncio.to_thread(
            build_backup_archive, PROJECT_ROOT_DIR, context.database_path, archive_path
        )
        archive_bytes = archive.path.stat().st_size

        if archive_bytes > TELEGRAM_DOCUMENT_UPLOAD_LIMIT_BYTES:
            await views.replace_message(
                callback,
                (
                    translate(
                        "backup.too_large",
                        lang,
                        size=mono(format_byte_count(archive_bytes)),
                        limit=mono(format_byte_count(TELEGRAM_DOCUMENT_UPLOAD_LIMIT_BYTES)),
                    ),
                    views.settings_root_payload(lang)[1],
                ),
            )
            return

        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        caption = translate(
            "backup.caption", lang, count=archive.file_count, size=format_byte_count(archive_bytes)
        )
        await bot.send_document(
            chat_id, FSInputFile(archive_path, filename=f"silo-backup-{timestamp}.zip"), caption=caption
        )
    except Exception as error:
        logger.exception("failed to build backup archive")
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(translate("backup.failed", lang, error=str(error)))
        return
    finally:
        archive_path.unlink(missing_ok=True)

    await views.replace_message(callback, views.settings_root_payload(lang))
