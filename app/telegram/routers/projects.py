from __future__ import annotations

import contextlib
from io import BytesIO
from pathlib import PurePosixPath

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.constants import ARCHIVE_MAX_COMPRESSED_BYTES
from app.i18n import translate
from app.ingest.github import GitHubCloneError, parse_repository_url, validate_git_reference
from app.ingest.pipeline import IngestError
from app.projects.layout import ProjectSlugError, normalize_slug
from app.system_stats import format_byte_count
from app.telegram import views
from app.telegram.callbacks import (
    AccountChoice,
    ConfirmCommand,
    IngestCommand,
    ProjectCatalogPage,
    ProjectCommand,
    ProjectMenu,
)
from app.telegram.context import PanelContext
from app.telegram.formatting import bold, mono
from app.telegram.keyboards import build_account_choice_keyboard, build_confirmation_keyboard
from app.telegram.states import IngestFlow

router = Router(name="projects")


async def _discard_message(message: Message) -> None:
    with contextlib.suppress(TelegramBadRequest):
        await message.delete()


@router.message(Command("projects"))
async def show_catalog(message: Message, context: PanelContext, lang: str) -> None:
    text, markup = views.project_catalog_payload(context, 0, lang)
    await message.answer(text, reply_markup=markup)


@router.callback_query(ProjectCatalogPage.filter())
async def turn_catalog_page(
    callback: CallbackQuery, callback_data: ProjectCatalogPage, context: PanelContext, lang: str
) -> None:
    await views.replace_message(callback, views.project_catalog_payload(context, callback_data.page, lang))
    await callback.answer()


@router.callback_query(ProjectMenu.filter())
async def open_project_menu(
    callback: CallbackQuery, callback_data: ProjectMenu, context: PanelContext, lang: str
) -> None:
    payload = await views.project_menu_payload(context, callback_data.index, lang)
    if payload is None:
        await callback.answer(translate("projects.no_longer_exists", lang), show_alert=True)
        return
    await views.replace_message(callback, payload)
    await callback.answer()


@router.callback_query(IngestCommand.filter(F.action == "github"))
async def prompt_repository_url(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(IngestFlow.awaiting_repository_url)
    await callback.answer()
    if callback.message is not None:
        example = mono("https://github.com/owner/repository main")
        await callback.message.answer(
            f"{bold(translate('ingest.github_title', lang))}\n\n"
            f"{translate('ingest.github_prompt', lang, example=example)}\n\n"
            f"{translate('common.cancel_hint', lang)}"
        )


@router.message(IngestFlow.awaiting_repository_url)
async def receive_repository_url(
    message: Message, state: FSMContext, context: PanelContext, lang: str
) -> None:
    raw_input = (message.text or "").strip().split()
    if not raw_input:
        await message.answer(translate("ingest.send_repo_url", lang))
        return

    try:
        coordinates = parse_repository_url(raw_input[0])
        git_reference = validate_git_reference(raw_input[1]) if len(raw_input) > 1 else None
        slug = normalize_slug(coordinates.repository)
    except (GitHubCloneError, ProjectSlugError) as error:
        await message.answer(translate("ingest.rejected", lang, error=mono(error)))
        return

    await state.update_data(repository_url=coordinates.normalized_url, git_reference=git_reference, slug=slug)
    await state.set_state(IngestFlow.awaiting_account_choice)

    accounts = await context.account_repository.list_all()
    await message.answer(
        translate("ingest.will_install_as", lang, repo=mono(coordinates.normalized_url), slug=mono(slug)),
        reply_markup=build_account_choice_keyboard(accounts, lang),
    )


@router.callback_query(AccountChoice.filter(), IngestFlow.awaiting_account_choice)
async def clone_repository(
    callback: CallbackQuery, callback_data: AccountChoice, state: FSMContext, context: PanelContext, lang: str
) -> None:
    flow_data = await state.get_data()
    await state.clear()
    await callback.answer(translate("ingest.cloning", lang))

    if callback.message is None:
        return

    try:
        coordinates = parse_repository_url(flow_data["repository_url"])
        outcome = await context.pipeline.ingest_github(
            coordinates=coordinates,
            requested_slug=flow_data["slug"],
            git_reference=flow_data.get("git_reference"),
            account_id=callback_data.account_id or None,
        )
    except (IngestError, GitHubCloneError, KeyError) as error:
        await callback.message.answer(translate("projects.install_failed", lang, error=mono(error)))
        return

    await context.fleet.synchronize()
    await callback.message.answer(_render_install_summary(outcome, lang))


@router.callback_query(IngestCommand.filter(F.action == "archive"))
async def prompt_archive_upload(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(IngestFlow.awaiting_archive)
    await callback.answer()
    if callback.message is not None:
        limit = mono(format_byte_count(ARCHIVE_MAX_COMPRESSED_BYTES))
        await callback.message.answer(
            f"{bold(translate('ingest.zip_title', lang))}\n\n"
            f"{translate('ingest.zip_prompt', lang, limit=limit)}\n\n"
            f"{translate('common.cancel_hint', lang)}"
        )


@router.message(IngestFlow.awaiting_archive, F.document)
async def receive_archive(
    message: Message, state: FSMContext, context: PanelContext, bot: Bot, lang: str
) -> None:
    document = message.document
    assert document is not None

    file_name = PurePosixPath(document.file_name or "project.zip").name
    if not file_name.lower().endswith(".zip"):
        await message.answer(translate("ingest.zip_only", lang))
        return
    if (document.file_size or 0) > ARCHIVE_MAX_COMPRESSED_BYTES:
        limit = mono(format_byte_count(ARCHIVE_MAX_COMPRESSED_BYTES))
        await message.answer(translate("ingest.zip_too_large", lang, limit=limit))
        return

    try:
        slug = normalize_slug(PurePosixPath(file_name).stem)
    except ProjectSlugError as error:
        await message.answer(translate("ingest.rejected", lang, error=mono(error)))
        return

    buffer = BytesIO()
    await bot.download(document, destination=buffer)
    payload = buffer.getvalue()
    buffer.close()

    await state.clear()
    await _discard_message(message)

    try:
        outcome = await context.pipeline.ingest_archive(payload, slug)
    except IngestError as error:
        await message.answer(translate("projects.install_failed", lang, error=mono(error)))
        return
    finally:
        del payload

    await context.fleet.synchronize()
    await message.answer(_render_install_summary(outcome, lang))


@router.callback_query(ProjectCommand.filter(F.action == "refresh"))
async def refresh_project(
    callback: CallbackQuery, callback_data: ProjectCommand, context: PanelContext, lang: str
) -> None:
    slug = context.fleet.resolve_slug_by_index(callback_data.index)
    supervisor = context.fleet.get(slug) if slug else None
    if supervisor is None or slug is None:
        await callback.answer(translate("projects.no_longer_exists", lang), show_alert=True)
        return

    await callback.answer(translate("projects.pulling", lang))
    await supervisor.stop(announce=False)

    try:
        await context.pipeline.refresh_from_github(slug)
    except (IngestError, GitHubCloneError) as error:
        if callback.message is not None:
            await callback.message.answer(translate("projects.pull_failed", lang, error=mono(error)))
        return

    await supervisor.rebuild()
    payload = await views.project_menu_payload(context, callback_data.index, lang)
    if payload is not None:
        await views.replace_message(callback, payload)


@router.callback_query(ConfirmCommand.filter(F.action == "delete"))
async def confirm_deletion(
    callback: CallbackQuery, callback_data: ConfirmCommand, context: PanelContext, lang: str
) -> None:
    slug = context.fleet.resolve_slug_by_index(callback_data.index)
    if slug is None:
        await callback.answer(translate("projects.no_longer_exists", lang), show_alert=True)
        return
    await views.replace_message(
        callback,
        (
            f"{translate('projects.delete_confirm_title', lang, slug=mono(slug))}\n\n"
            f"{translate('projects.delete_confirm_body', lang)}",
            build_confirmation_keyboard("delete", callback_data.index, lang),
        ),
    )
    await callback.answer()


@router.callback_query(ConfirmCommand.filter(F.action == "delete-yes"))
async def delete_project(
    callback: CallbackQuery, callback_data: ConfirmCommand, context: PanelContext, lang: str
) -> None:
    slug = context.fleet.resolve_slug_by_index(callback_data.index)
    if slug is None:
        await callback.answer(translate("projects.no_longer_exists", lang), show_alert=True)
        return

    await callback.answer(translate("projects.deleting", lang))
    await context.fleet.detach(slug)
    await context.pipeline.remove(slug)
    await context.fleet.synchronize()
    await context.vault.refresh_redaction()
    await views.replace_message(callback, views.project_catalog_payload(context, 0, lang))


@router.message(Command("cancel"))
async def cancel_flow(message: Message, state: FSMContext, lang: str) -> None:
    if await state.get_state() is None:
        await message.answer(translate("flow.nothing_to_cancel", lang))
        return
    await state.clear()
    await message.answer(translate("flow.cancelled", lang))


def _render_install_summary(outcome, lang: str) -> str:
    lines = [
        translate("projects.installed", lang, slug=mono(outcome.slug)),
        translate("projects.files", lang, count=mono(outcome.report.file_count)),
    ]
    if outcome.report.removed_links or outcome.report.removed_sensitive_paths:
        lines.append(
            translate(
                "projects.stripped",
                lang,
                links=mono(outcome.report.removed_links),
                sensitive=mono(outcome.report.removed_sensitive_paths),
            )
        )
    if outcome.manifest_generated:
        lines.append(translate("projects.manifest_generated", lang))
    lines.append(translate("projects.next_steps", lang))
    return "\n".join(lines)
