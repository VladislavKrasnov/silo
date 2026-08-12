from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class DashboardPage(CallbackData, prefix="dash"):
    page: int


class ProjectListPage(CallbackData, prefix="plist"):
    action: str
    page: int


class ProjectCommand(CallbackData, prefix="proj"):
    action: str
    index: int


class ProjectMenu(CallbackData, prefix="pmenu"):
    index: int


class ProjectCatalogPage(CallbackData, prefix="pcat"):
    page: int


class IngestCommand(CallbackData, prefix="ingest"):
    action: str


class AccountChoice(CallbackData, prefix="acc"):
    account_id: int


class AccountCommand(CallbackData, prefix="acmd"):
    action: str
    account_id: int


class SecretsMenu(CallbackData, prefix="sec"):
    action: str
    index: int


class SettingsSection(CallbackData, prefix="set"):
    section: str
    page: int


class AlertToggle(CallbackData, prefix="atog"):
    index: int
    page: int


class PreferenceCommand(CallbackData, prefix="pref"):
    action: str
    key: str


class EventsPage(CallbackData, prefix="ev"):
    page: int


class ConfirmCommand(CallbackData, prefix="cfm"):
    action: str
    index: int


class FleetCommand(CallbackData, prefix="fleet"):
    action: str


class LocaleChoice(CallbackData, prefix="lang"):
    locale: str
