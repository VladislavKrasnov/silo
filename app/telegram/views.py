from __future__ import annotations

import contextlib

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from app.alerts.kinds import ALERT_DEFINITIONS, USER_CONFIGURABLE_ALERT_KINDS
from app.constants import (
    ALERT_RULE_PAGE_SIZE,
    DASHBOARD_PROCESS_PAGE_SIZE,
    EVENT_HISTORY_PAGE_SIZE,
    PROJECT_LIST_PAGE_SIZE,
)
from app.i18n import translate
from app.pagination import Page, paginate
from app.reporting import build_project_snapshot
from app.telegram import formatting, keyboards
from app.telegram.context import PanelContext

Payload = tuple[str, InlineKeyboardMarkup]

ACTION_VERB_KEYS: dict[str, str] = {
    "start": "projects.verb_started",
    "stop": "projects.verb_stopped",
    "restart": "projects.verb_restarted",
    "rebuild": "projects.verb_rebuilding",
}
ACTION_TITLE_KEYS: dict[str, str] = {
    "start": "projects.action_start_title",
    "stop": "projects.action_stop_title",
    "restart": "projects.action_restart_title",
}
ACTION_EMPTY_KEYS: dict[str, str] = {
    "start": "projects.all_running",
    "stop": "projects.none_running",
    "restart": "projects.empty",
}
ACTION_TITLES: dict[str, str] = ACTION_TITLE_KEYS


def action_verb(action: str, lang: str) -> str:
    return translate(ACTION_VERB_KEYS[action], lang)


def main_menu_payload(context: PanelContext, lang: str) -> Payload:
    system_snapshot = context.sampler.build_system_snapshot()
    total_projects = len(context.fleet.sorted_slugs)
    running = len(context.fleet.running_slugs())

    lines = [formatting.bold(translate("menu.title", lang)), ""]
    lines += formatting.render_status_lines(system_snapshot, lang)
    lines.append("")
    if total_projects == 0:
        lines.append(translate("menu.no_projects", lang))
    else:
        lines.append(translate("menu.projects_running", lang, running=running, total=total_projects))

    return "\n".join(lines), keyboards.build_main_menu_keyboard(lang)


def dashboard_payload(context: PanelContext, page_index: int, lang: str) -> Payload:
    slugs = context.fleet.sorted_slugs
    snapshots = [build_project_snapshot(context.fleet.supervisors[slug]) for slug in slugs]
    page = paginate(snapshots, page_index, DASHBOARD_PROCESS_PAGE_SIZE)
    system_snapshot = context.sampler.build_system_snapshot()
    return (
        formatting.render_dashboard(system_snapshot, page, len(slugs), lang),
        keyboards.build_dashboard_keyboard(page, lang),
    )


def project_action_payload(context: PanelContext, action: str, page_index: int, lang: str) -> Payload:
    if action == "start":
        candidates = context.fleet.stopped_slugs()
    elif action == "restart":
        candidates = context.fleet.sorted_slugs
    else:
        candidates = context.fleet.running_slugs()
    page = paginate(candidates, page_index, PROJECT_LIST_PAGE_SIZE)
    slug_to_index = {
        slug: index for index, slug in enumerate(context.fleet.sorted_slugs) if slug in page.items
    }
    status_by_slug = (
        {slug: context.fleet.supervisors[slug].is_active for slug in page.items}
        if action == "restart"
        else None
    )
    return (
        formatting.render_project_list(
            translate(ACTION_TITLE_KEYS[action], lang), page, translate(ACTION_EMPTY_KEYS[action], lang), lang
        ),
        keyboards.build_project_action_keyboard(action, page, slug_to_index, lang, status_by_slug),
    )


def project_catalog_payload(context: PanelContext, page_index: int, lang: str) -> Payload:
    slugs = context.fleet.sorted_slugs
    page = paginate(slugs, page_index, PROJECT_LIST_PAGE_SIZE)
    slug_to_index = {slug: index for index, slug in enumerate(slugs) if slug in page.items}
    return (
        formatting.render_project_list(
            translate("projects.title", lang), page, translate("projects.empty", lang), lang
        ),
        keyboards.build_project_catalog_keyboard(page, slug_to_index, lang),
    )


async def project_menu_payload(context: PanelContext, index: int, lang: str) -> Payload | None:
    slug = context.fleet.resolve_slug_by_index(index)
    supervisor = context.fleet.get(slug) if slug else None
    record = context.fleet.records.get(slug) if slug else None
    if supervisor is None or record is None:
        return None

    secret_names = await context.vault.names(record.id)
    text = formatting.render_project_detail(
        record, build_project_snapshot(supervisor), secret_names, supervisor.last_failure_detail, lang
    )
    markup = keyboards.build_project_menu_keyboard(
        index, supervisor.is_active, record.source_kind == "github", lang
    )
    return text, markup


async def secrets_payload(context: PanelContext, index: int, lang: str) -> Payload | None:
    slug = context.fleet.resolve_slug_by_index(index)
    record = context.fleet.records.get(slug) if slug else None
    if record is None:
        return None
    names = await context.vault.names(record.id)
    return (
        formatting.render_secrets_overview(record.slug, names, lang),
        keyboards.build_secrets_keyboard(index, lang),
    )


def settings_root_payload(lang: str) -> Payload:
    text = f"{formatting.bold(translate('settings.title', lang))}\n\n{translate('settings.intro', lang)}"
    return text, keyboards.build_settings_root_keyboard(lang)


def language_picker_payload(lang: str) -> Payload:
    return translate("language.pick_title", lang), keyboards.build_language_picker_keyboard()


def alert_rules_payload(context: PanelContext, page_index: int, lang: str) -> Payload:
    all_kinds = [str(definition.kind) for definition in ALERT_DEFINITIONS]
    kind_index = {kind: index for index, kind in enumerate(all_kinds)}
    configurable_kinds = [str(kind) for kind in USER_CONFIGURABLE_ALERT_KINDS]
    page = paginate(configurable_kinds, page_index, ALERT_RULE_PAGE_SIZE)
    rules = context.alert_settings.all_rules()
    return (
        formatting.render_alert_rules(page, rules, lang),
        keyboards.build_alert_rules_keyboard(page, rules, kind_index, lang),
    )


def thresholds_payload(context: PanelContext, lang: str) -> Payload:
    preferences = context.alert_settings.preferences
    return (
        formatting.render_preferences(preferences, lang),
        keyboards.build_thresholds_keyboard(preferences.quiet_hours_enabled, lang),
    )


async def accounts_payload(context: PanelContext, lang: str) -> Payload:
    accounts = await context.account_repository.list_all()
    return formatting.render_accounts(accounts, lang), keyboards.build_accounts_keyboard(accounts, lang)


async def events_payload(context: PanelContext, page_index: int, lang: str) -> Payload:
    total_events = await context.event_repository.count()
    total_pages = max(1, -(-total_events // EVENT_HISTORY_PAGE_SIZE))
    clamped_index = max(0, min(page_index, total_pages - 1))
    records = await context.event_repository.recent(
        EVENT_HISTORY_PAGE_SIZE, clamped_index * EVENT_HISTORY_PAGE_SIZE
    )
    page = Page(items=tuple(records), page_index=clamped_index, total_pages=total_pages)
    return formatting.render_events(page, lang), keyboards.build_events_keyboard(page, lang)


async def replace_message(callback: CallbackQuery, payload: Payload) -> None:
    if callback.message is None:
        return
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(payload[0], reply_markup=payload[1])
