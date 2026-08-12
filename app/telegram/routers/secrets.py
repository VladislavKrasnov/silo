from __future__ import annotations

import contextlib
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.alerts.kinds import AlertKind
from app.i18n import translate
from app.security.environment_parser import parse_environment_assignments
from app.telegram import views
from app.telegram.callbacks import SecretsMenu
from app.telegram.context import PanelContext
from app.telegram.formatting import bold, mono
from app.telegram.states import SecretsFlow

router = Router(name="secrets")

MAX_ENVIRONMENT_DOCUMENT_BYTES: int = 256 * 1024


async def _discard_message(message: Message) -> None:
    with contextlib.suppress(TelegramBadRequest):
        await message.delete()


@router.message(Command("env"))
async def show_env_catalog(message: Message, context: PanelContext, lang: str) -> None:
    text, markup = views.project_catalog_payload(context, 0, lang)
    await message.answer(f"{text}\n\n{translate('secrets.catalog_hint', lang)}", reply_markup=markup)


@router.callback_query(SecretsMenu.filter(F.action == "open"))
async def open_secrets(
    callback: CallbackQuery, callback_data: SecretsMenu, context: PanelContext, lang: str
) -> None:
    payload = await views.secrets_payload(context, callback_data.index, lang)
    if payload is None:
        await callback.answer(translate("projects.no_longer_exists", lang), show_alert=True)
        return
    await views.replace_message(callback, payload)
    await callback.answer()


@router.callback_query(SecretsMenu.filter(F.action.in_({"load", "replace"})))
async def prompt_assignments(
    callback: CallbackQuery, callback_data: SecretsMenu, state: FSMContext, context: PanelContext, lang: str
) -> None:
    slug = context.fleet.resolve_slug_by_index(callback_data.index)
    record = context.fleet.records.get(slug) if slug else None
    if record is None:
        await callback.answer(translate("projects.no_longer_exists", lang), show_alert=True)
        return

    await state.set_state(SecretsFlow.awaiting_assignments)
    await state.update_data(
        project_id=record.id, index=callback_data.index, replace=callback_data.action == "replace"
    )
    await callback.answer()

    if callback.message is not None:
        mode = translate(
            "secrets.mode_replace" if callback_data.action == "replace" else "secrets.mode_merge", lang
        )
        await callback.message.answer(
            f"{bold(translate('secrets.load_title', lang, slug=mono(record.slug)))}\n\n"
            f"{translate('secrets.load_prompt', lang, mode=mode)}\n\n"
            f"{translate('common.cancel_hint', lang)}"
        )


@router.message(SecretsFlow.awaiting_assignments)
async def receive_assignments(
    message: Message, state: FSMContext, context: PanelContext, bot: Bot, lang: str
) -> None:
    flow_data = await state.get_data()
    raw_text = message.text or message.caption or ""

    if message.document is not None:
        if (message.document.file_size or 0) > MAX_ENVIRONMENT_DOCUMENT_BYTES:
            await message.answer(translate("secrets.too_large", lang))
            return
        buffer = BytesIO()
        await bot.download(message.document, destination=buffer)
        raw_text = buffer.getvalue().decode("utf-8", errors="replace")
        buffer.close()

    await state.clear()
    await _discard_message(message)

    parsed = parse_environment_assignments(raw_text)
    if not parsed.entries:
        await message.answer(translate("secrets.none_found", lang))
        return

    project_id = int(flow_data["project_id"])
    stored_count = await context.vault.store(project_id, parsed.entries, bool(flow_data["replace"]))
    context.alerts.publish(
        AlertKind.SECURITY_SECRETS_CHANGED,
        f"{stored_count} variable(s) loaded",
        context.fleet.resolve_slug_by_index(int(flow_data["index"])),
    )

    summary = [
        translate(
            "secrets.stored_summary",
            lang,
            count=mono(stored_count),
            names=", ".join(mono(name) for name in parsed.entries),
        )
    ]
    if parsed.rejected_lines:
        summary.append(translate("secrets.ignored_lines", lang, count=mono(len(parsed.rejected_lines))))
    summary.append(translate("secrets.restart_hint", lang))
    await message.answer("\n".join(summary))


@router.callback_query(SecretsMenu.filter(F.action == "purge"))
async def purge_secrets(
    callback: CallbackQuery, callback_data: SecretsMenu, context: PanelContext, lang: str
) -> None:
    slug = context.fleet.resolve_slug_by_index(callback_data.index)
    record = context.fleet.records.get(slug) if slug else None
    if record is None:
        await callback.answer(translate("projects.no_longer_exists", lang), show_alert=True)
        return

    purged = await context.vault.purge(record.id)
    context.alerts.publish(AlertKind.SECURITY_SECRETS_CHANGED, f"{purged} variable(s) deleted", record.slug)
    await callback.answer(translate("secrets.deleted_count", lang, count=purged))

    payload = await views.secrets_payload(context, callback_data.index, lang)
    if payload is not None:
        await views.replace_message(callback, payload)
