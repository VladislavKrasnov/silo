from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from app.i18n import translate
from app.telegram import views
from app.telegram.callbacks import DashboardPage, EventsPage, FleetCommand, ProjectCommand, ProjectListPage
from app.telegram.context import PanelContext
from app.telegram.formatting import mono, render_action_result, render_logs
from app.telegram.keyboards import build_fleet_confirmation_keyboard

router = Router(name="dashboard")

PROGRESS_KEYS: dict[str, str] = {
    "start": "projects.progress_start",
    "stop": "projects.progress_stop",
    "restart": "projects.progress_restart",
    "rebuild": "projects.progress_rebuild",
}


@router.message(Command("start"))
async def start_command(message: Message, command: CommandObject, context: PanelContext, lang: str) -> None:
    slug = (command.args or "").strip()
    if not slug:
        text, markup = views.main_menu_payload(context, lang)
        await message.answer(text, reply_markup=markup)
        return
    await _run_named_project_action(message, context, lang, "start", slug)


@router.message(Command("stop"))
async def stop_command(message: Message, command: CommandObject, context: PanelContext, lang: str) -> None:
    slug = (command.args or "").strip()
    if not slug:
        text, markup = views.project_action_payload(context, "stop", 0, lang)
        await message.answer(text, reply_markup=markup)
        return
    await _run_named_project_action(message, context, lang, "stop", slug)


@router.message(Command("restart"))
async def restart_command(message: Message, command: CommandObject, context: PanelContext, lang: str) -> None:
    slug = (command.args or "").strip()
    if not slug:
        text, markup = views.project_action_payload(context, "restart", 0, lang)
        await message.answer(text, reply_markup=markup)
        return
    await _run_named_project_action(message, context, lang, "restart", slug)


async def _run_named_project_action(
    message: Message, context: PanelContext, lang: str, action: str, slug: str
) -> None:
    supervisor = context.fleet.get(slug)
    if supervisor is None:
        await message.answer(translate("projects.not_found", lang, slug=mono(slug)))
        return

    if action == "start" and supervisor.is_active:
        await message.answer(translate("projects.already_running", lang, slug=mono(slug)))
        return
    if action == "stop" and not supervisor.is_active:
        await message.answer(translate("projects.already_stopped", lang, slug=mono(slug)))
        return

    await _apply_action(context, slug, action)
    await message.answer(render_action_result(views.action_verb(action, lang), slug))


@router.callback_query(FleetCommand.filter(F.action == "menu"))
async def show_main_menu(callback: CallbackQuery, context: PanelContext, lang: str) -> None:
    await views.replace_message(callback, views.main_menu_payload(context, lang))
    await callback.answer()


@router.callback_query(FleetCommand.filter(F.action == "restart"))
async def restart_fleet(callback: CallbackQuery, context: PanelContext, lang: str) -> None:
    await views.replace_message(callback, views.project_action_payload(context, "restart", 0, lang))
    await callback.answer()


@router.callback_query(FleetCommand.filter(F.action == "stop"))
async def stop_fleet(callback: CallbackQuery, context: PanelContext, lang: str) -> None:
    await views.replace_message(callback, views.project_action_payload(context, "stop", 0, lang))
    await callback.answer()


@router.callback_query(FleetCommand.filter(F.action == "stop-all-confirm"))
async def confirm_stop_all(callback: CallbackQuery, lang: str) -> None:
    await views.replace_message(
        callback,
        (
            f"{translate('projects.stop_all_confirm_title', lang)}\n\n"
            f"{translate('projects.stop_all_confirm_body', lang)}",
            build_fleet_confirmation_keyboard("stop", lang),
        ),
    )
    await callback.answer()


@router.callback_query(FleetCommand.filter(F.action == "restart-all-confirm"))
async def confirm_restart_all(callback: CallbackQuery, lang: str) -> None:
    await views.replace_message(
        callback,
        (
            f"{translate('projects.restart_all_confirm_title', lang)}\n\n"
            f"{translate('projects.restart_all_confirm_body', lang)}",
            build_fleet_confirmation_keyboard("restart", lang),
        ),
    )
    await callback.answer()


@router.callback_query(FleetCommand.filter(F.action == "stop-all-yes"))
async def run_stop_all(callback: CallbackQuery, context: PanelContext, lang: str) -> None:
    await callback.answer()
    await views.show_transition(callback, translate("projects.progress_stop_all", lang))
    await context.fleet.stop_all()
    await views.replace_message(callback, views.project_action_payload(context, "stop", 0, lang))


@router.callback_query(FleetCommand.filter(F.action == "restart-all-yes"))
async def run_restart_all(callback: CallbackQuery, context: PanelContext, lang: str) -> None:
    await callback.answer()
    await views.show_transition(callback, translate("projects.progress_restart_all", lang))
    await context.fleet.restart_all()
    await views.replace_message(callback, views.project_action_payload(context, "restart", 0, lang))


@router.message(Command("status", "stats"))
async def show_dashboard(message: Message, context: PanelContext, lang: str) -> None:
    text, markup = views.dashboard_payload(context, 0, lang)
    await message.answer(text, reply_markup=markup)


@router.message(Command("events"))
async def show_events(message: Message, context: PanelContext, lang: str) -> None:
    text, markup = await views.events_payload(context, 0, lang)
    await message.answer(text, reply_markup=markup)


@router.message(Command("logs"))
async def show_logs(message: Message, command: CommandObject, context: PanelContext, lang: str) -> None:
    slug = (command.args or "").strip()
    supervisor = context.fleet.get(slug)
    if supervisor is None:
        await message.answer(translate("projects.not_found", lang, slug=mono(slug)))
        return
    await message.answer(render_logs(slug, list(supervisor.recent_output), lang))


@router.callback_query(DashboardPage.filter())
async def turn_dashboard_page(
    callback: CallbackQuery, callback_data: DashboardPage, context: PanelContext, lang: str
) -> None:
    await views.replace_message(callback, views.dashboard_payload(context, callback_data.page, lang))
    await callback.answer()


@router.callback_query(EventsPage.filter())
async def turn_events_page(
    callback: CallbackQuery, callback_data: EventsPage, context: PanelContext, lang: str
) -> None:
    await views.replace_message(callback, await views.events_payload(context, callback_data.page, lang))
    await callback.answer()


@router.callback_query(ProjectListPage.filter())
async def show_project_action_list(
    callback: CallbackQuery, callback_data: ProjectListPage, context: PanelContext, lang: str
) -> None:
    if callback_data.action not in views.ACTION_TITLES:
        await callback.answer()
        return
    await views.replace_message(
        callback, views.project_action_payload(context, callback_data.action, callback_data.page, lang)
    )
    await callback.answer()


@router.callback_query(ProjectCommand.filter(F.action == "logs"))
async def show_project_logs(
    callback: CallbackQuery, callback_data: ProjectCommand, context: PanelContext, lang: str
) -> None:
    slug = context.fleet.resolve_slug_by_index(callback_data.index)
    supervisor = context.fleet.get(slug) if slug else None
    if supervisor is None or callback.message is None:
        await callback.answer(translate("projects.no_longer_exists", lang), show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(render_logs(supervisor.slug, list(supervisor.recent_output), lang))


@router.callback_query(ProjectCommand.filter(F.action.in_({"start", "stop", "restart", "rebuild"})))
async def run_project_command(
    callback: CallbackQuery, callback_data: ProjectCommand, context: PanelContext, lang: str
) -> None:
    slug = context.fleet.resolve_slug_by_index(callback_data.index)
    supervisor = context.fleet.get(slug) if slug else None
    if supervisor is None or slug is None:
        await callback.answer(translate("projects.no_longer_exists", lang), show_alert=True)
        return

    action = callback_data.action
    if action == "start" and supervisor.is_active:
        await callback.answer(translate("projects.already_running_alert", lang), show_alert=True)
        return
    if action == "stop" and not supervisor.is_active:
        await callback.answer(translate("projects.already_stopped_alert", lang), show_alert=True)
        return

    await callback.answer()
    await views.show_transition(callback, translate(PROGRESS_KEYS[action], lang, slug=mono(slug)))
    await _apply_action(context, slug, action)

    menu_payload = await views.project_menu_payload(context, callback_data.index, lang)
    await views.replace_message(
        callback, menu_payload or views.project_action_payload(context, "restart", 0, lang)
    )


@router.callback_query(ProjectCommand.filter(F.action == "autostart"))
async def toggle_autostart(
    callback: CallbackQuery, callback_data: ProjectCommand, context: PanelContext, lang: str
) -> None:
    slug = context.fleet.resolve_slug_by_index(callback_data.index)
    record = context.fleet.records.get(slug) if slug else None
    if record is None or slug is None:
        await callback.answer(translate("projects.no_longer_exists", lang), show_alert=True)
        return

    await context.project_repository.set_autostart(slug, not record.autostart)
    await context.fleet.synchronize()
    await callback.answer(
        translate("projects.autostart_disabled", lang)
        if record.autostart
        else translate("projects.autostart_enabled", lang)
    )

    menu_payload = await views.project_menu_payload(context, callback_data.index, lang)
    if menu_payload is not None:
        await views.replace_message(callback, menu_payload)


async def _apply_action(context: PanelContext, slug: str, action: str) -> None:
    supervisor = context.fleet.get(slug)
    if supervisor is None:
        return
    if action == "start":
        await supervisor.start()
    elif action == "stop":
        await supervisor.stop()
    elif action == "rebuild":
        await supervisor.rebuild()
    else:
        await supervisor.restart()
