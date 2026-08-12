from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.alerts.kinds import ALERT_DEFINITIONS_BY_KIND
from app.alerts.settings import AlertRule
from app.database.repositories import GitHubAccountRecord
from app.i18n import translate
from app.pagination import Page
from app.telegram.callbacks import (
    AccountChoice,
    AccountCommand,
    AlertToggle,
    BackupCommand,
    ConfirmCommand,
    DashboardPage,
    EventsPage,
    FleetCommand,
    IngestCommand,
    LocaleChoice,
    PreferenceCommand,
    ProjectCatalogPage,
    ProjectCommand,
    ProjectListPage,
    ProjectMenu,
    SecretsMenu,
    SettingsSection,
)


def _navigation_row(page: Page, lang: str, build_callback) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if page.has_previous:
        row.append(
            InlineKeyboardButton(
                text=translate("common.prev", lang), callback_data=build_callback(page.page_index - 1)
            )
        )
    if page.has_next:
        row.append(
            InlineKeyboardButton(
                text=translate("common.next", lang), callback_data=build_callback(page.page_index + 1)
            )
        )
    return row


def build_language_picker_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("language.button_en", "en"), callback_data=LocaleChoice(locale="en").pack()
                ),
                InlineKeyboardButton(
                    text=translate("language.button_ru", "ru"), callback_data=LocaleChoice(locale="ru").pack()
                ),
            ]
        ]
    )


def build_main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("menu.start_restart", lang),
                    callback_data=FleetCommand(action="restart").pack(),
                ),
                InlineKeyboardButton(
                    text=translate("menu.stop", lang), callback_data=FleetCommand(action="stop").pack()
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("menu.projects", lang), callback_data=ProjectCatalogPage(page=0).pack()
                ),
                InlineKeyboardButton(
                    text=translate("menu.settings", lang),
                    callback_data=SettingsSection(section="root", page=0).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("menu.status", lang), callback_data=DashboardPage(page=0).pack()
                )
            ],
        ]
    )


def build_dashboard_keyboard(page: Page, lang: str) -> InlineKeyboardMarkup:
    navigation_row: list[InlineKeyboardButton] = []
    if page.has_previous:
        navigation_row.append(
            InlineKeyboardButton(
                text=translate("common.prev", lang),
                callback_data=DashboardPage(page=page.page_index - 1).pack(),
            )
        )
    navigation_row.append(
        InlineKeyboardButton(
            text=translate("common.refresh", lang), callback_data=DashboardPage(page=page.page_index).pack()
        )
    )
    if page.has_next:
        navigation_row.append(
            InlineKeyboardButton(
                text=translate("common.next", lang),
                callback_data=DashboardPage(page=page.page_index + 1).pack(),
            )
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            navigation_row,
            [
                InlineKeyboardButton(
                    text=translate("common.back", lang), callback_data=FleetCommand(action="menu").pack()
                )
            ],
        ]
    )


def _project_button_label(slug: str, status_by_slug: dict[str, bool] | None, lang: str) -> str:
    if status_by_slug is None:
        return slug
    status_word = translate(
        "projects.status_running" if status_by_slug[slug] else "projects.status_stopped", lang
    )
    return f"{status_word} — {slug}"


_BULK_ACTION_KEYS: dict[str, str] = {
    "stop": "projects.stop_all_button",
    "restart": "projects.restart_all_button",
}


def build_project_action_keyboard(
    action: str,
    page: Page[str],
    slug_to_index: dict[str, int],
    lang: str,
    status_by_slug: dict[str, bool] | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    bulk_action_key = _BULK_ACTION_KEYS.get(action)
    if bulk_action_key is not None and page.items:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate(bulk_action_key, lang),
                    callback_data=FleetCommand(action=f"{action}-all-confirm").pack(),
                )
            ]
        )
    rows += [
        [
            InlineKeyboardButton(
                text=_project_button_label(slug, status_by_slug, lang),
                callback_data=ProjectCommand(action=action, index=slug_to_index[slug]).pack(),
            )
        ]
        for slug in page.items
    ]
    navigation_row = _navigation_row(
        page, lang, lambda index: ProjectListPage(action=action, page=index).pack()
    )
    navigation_row.append(
        InlineKeyboardButton(
            text=translate("common.back", lang), callback_data=FleetCommand(action="menu").pack()
        )
    )
    rows.append(navigation_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_project_catalog_keyboard(
    page: Page[str], slug_to_index: dict[str, int], lang: str
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=slug, callback_data=ProjectMenu(index=slug_to_index[slug]).pack())]
        for slug in page.items
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=translate("projects.add_github", lang),
                callback_data=IngestCommand(action="github").pack(),
            ),
            InlineKeyboardButton(
                text=translate("projects.upload_zip", lang),
                callback_data=IngestCommand(action="archive").pack(),
            ),
        ]
    )
    navigation_row = _navigation_row(page, lang, lambda index: ProjectCatalogPage(page=index).pack())
    navigation_row.append(
        InlineKeyboardButton(
            text=translate("common.back", lang), callback_data=FleetCommand(action="menu").pack()
        )
    )
    rows.append(navigation_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_project_menu_keyboard(
    index: int, is_active: bool, is_github: bool, lang: str
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    translate("projects.button_stop", lang)
                    if is_active
                    else translate("projects.button_start", lang)
                ),
                callback_data=ProjectCommand(action="stop" if is_active else "start", index=index).pack(),
            ),
            InlineKeyboardButton(
                text=translate("projects.button_restart", lang),
                callback_data=ProjectCommand(action="restart", index=index).pack(),
            ),
            InlineKeyboardButton(
                text=translate("projects.button_rebuild", lang),
                callback_data=ProjectCommand(action="rebuild", index=index).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate("projects.button_variables", lang),
                callback_data=SecretsMenu(action="open", index=index).pack(),
            ),
            InlineKeyboardButton(
                text=translate("projects.button_logs", lang),
                callback_data=ProjectCommand(action="logs", index=index).pack(),
            ),
            InlineKeyboardButton(
                text=translate("projects.button_autostart", lang),
                callback_data=ProjectCommand(action="autostart", index=index).pack(),
            ),
        ],
    ]
    if is_github:
        rows.append(
            [
                InlineKeyboardButton(
                    text=translate("projects.button_pull", lang),
                    callback_data=ProjectCommand(action="refresh", index=index).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate("projects.button_delete", lang),
                callback_data=ConfirmCommand(action="delete", index=index).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=translate("common.back", lang), callback_data=ProjectCatalogPage(page=0).pack()
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_post_install_keyboard(index: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("projects.open_project", lang),
                    callback_data=ProjectMenu(index=index).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("common.back", lang), callback_data=ProjectCatalogPage(page=0).pack()
                )
            ],
        ]
    )


def build_back_to_project_keyboard(index: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("common.back", lang), callback_data=ProjectMenu(index=index).pack()
                )
            ]
        ]
    )


def build_confirmation_keyboard(action: str, index: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("projects.confirm", lang),
                    callback_data=ConfirmCommand(action=f"{action}-yes", index=index).pack(),
                ),
                InlineKeyboardButton(
                    text=translate("projects.cancel_button", lang),
                    callback_data=ProjectMenu(index=index).pack(),
                ),
            ]
        ]
    )


def build_fleet_confirmation_keyboard(action: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("projects.confirm", lang),
                    callback_data=FleetCommand(action=f"{action}-all-yes").pack(),
                ),
                InlineKeyboardButton(
                    text=translate("projects.cancel_button", lang),
                    callback_data=FleetCommand(action=action).pack(),
                ),
            ]
        ]
    )


def build_account_choice_keyboard(accounts: list[GitHubAccountRecord], lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=account.label, callback_data=AccountChoice(account_id=account.id).pack())]
        for account in accounts
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=translate("ingest.public_no_account", lang),
                callback_data=AccountChoice(account_id=0).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_secrets_keyboard(index: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("secrets.button_load", lang),
                    callback_data=SecretsMenu(action="load", index=index).pack(),
                ),
                InlineKeyboardButton(
                    text=translate("secrets.button_replace", lang),
                    callback_data=SecretsMenu(action="replace", index=index).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("secrets.button_purge", lang),
                    callback_data=SecretsMenu(action="purge", index=index).pack(),
                ),
                InlineKeyboardButton(
                    text=translate("common.back", lang), callback_data=ProjectMenu(index=index).pack()
                ),
            ],
        ]
    )


def build_settings_root_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("settings.alert_rules", lang),
                    callback_data=SettingsSection(section="alerts", page=0).pack(),
                ),
                InlineKeyboardButton(
                    text=translate("settings.thresholds", lang),
                    callback_data=SettingsSection(section="thresholds", page=0).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("settings.accounts", lang),
                    callback_data=SettingsSection(section="accounts", page=0).pack(),
                ),
                InlineKeyboardButton(
                    text=translate("settings.events", lang), callback_data=EventsPage(page=0).pack()
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("language.settings_row", lang),
                    callback_data=SettingsSection(section="language", page=0).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("settings.backup", lang), callback_data=BackupCommand().pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("common.back", lang), callback_data=FleetCommand(action="menu").pack()
                )
            ],
        ]
    )


def build_alert_rules_keyboard(
    page: Page[str], rules: dict[str, AlertRule], kind_index: dict[str, int], lang: str
) -> InlineKeyboardMarkup:
    def _row_text(kind: str) -> str:
        state_word = translate("alerts.on", lang) if rules[kind].enabled else translate("alerts.off", lang)
        return f"{state_word} — {ALERT_DEFINITIONS_BY_KIND[kind].title}"

    rows = [
        [
            InlineKeyboardButton(
                text=_row_text(kind),
                callback_data=AlertToggle(index=kind_index[kind], page=page.page_index).pack(),
            )
        ]
        for kind in page.items
        if kind in rules
    ]
    navigation_row = _navigation_row(
        page, lang, lambda index: SettingsSection(section="alerts", page=index).pack()
    )
    navigation_row.append(
        InlineKeyboardButton(
            text=translate("common.back", lang), callback_data=SettingsSection(section="root", page=0).pack()
        )
    )
    rows.append(navigation_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_thresholds_keyboard(quiet_hours_enabled: bool, lang: str) -> InlineKeyboardMarkup:
    quiet_label = (
        translate("thresholds.quiet_hours_on", lang)
        if quiet_hours_enabled
        else translate("thresholds.quiet_hours_off", lang)
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("thresholds.button_cpu", lang),
                    callback_data=PreferenceCommand(action="edit", key="cpu_threshold_percent").pack(),
                ),
                InlineKeyboardButton(
                    text=translate("thresholds.button_memory", lang),
                    callback_data=PreferenceCommand(action="edit", key="memory_threshold_percent").pack(),
                ),
                InlineKeyboardButton(
                    text=translate("thresholds.button_disk", lang),
                    callback_data=PreferenceCommand(action="edit", key="disk_threshold_percent").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("thresholds.button_cycle_severity", lang),
                    callback_data=PreferenceCommand(action="cycle", key="minimum_severity").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=quiet_label,
                    callback_data=PreferenceCommand(action="toggle", key="quiet_hours_enabled").pack(),
                ),
                InlineKeyboardButton(
                    text=translate("thresholds.button_window", lang),
                    callback_data=PreferenceCommand(action="edit", key="quiet_hours_window").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("common.back", lang),
                    callback_data=SettingsSection(section="root", page=0).pack(),
                )
            ],
        ]
    )


def build_accounts_keyboard(accounts: list[GitHubAccountRecord], lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=translate("accounts.button_delete", lang, label=account.label),
                callback_data=AccountCommand(action="delete", account_id=account.id).pack(),
            )
        ]
        for account in accounts
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=translate("accounts.button_add", lang),
                callback_data=AccountCommand(action="add", account_id=0).pack(),
            ),
            InlineKeyboardButton(
                text=translate("common.back", lang),
                callback_data=SettingsSection(section="root", page=0).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_events_keyboard(page: Page, lang: str) -> InlineKeyboardMarkup:
    navigation_row = _navigation_row(page, lang, lambda index: EventsPage(page=index).pack())
    navigation_row.append(
        InlineKeyboardButton(
            text=translate("common.back", lang), callback_data=FleetCommand(action="menu").pack()
        )
    )
    return InlineKeyboardMarkup(inline_keyboard=[navigation_row])
