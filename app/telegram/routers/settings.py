from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.alerts.kinds import ALERT_DEFINITIONS, AlertSeverity
from app.alerts.settings import PREFERENCE_BOUNDS
from app.i18n import translate
from app.ingest.github_oauth import (
    TOKEN_CREATION_URL,
    DeviceAuthorization,
    GitHubIdentity,
    GitHubOAuthError,
    fetch_identity,
    poll_for_access_token,
    request_device_authorization,
)
from app.telegram import views
from app.telegram.callbacks import (
    AccountCommand,
    AlertToggle,
    LocaleChoice,
    PreferenceCommand,
    SettingsSection,
)
from app.telegram.context import PanelContext
from app.telegram.formatting import bold, mono
from app.telegram.states import AccountFlow, PreferenceFlow

router = Router(name="settings")

SEVERITY_CYCLE: tuple[str, ...] = (AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.CRITICAL)
PREFERENCE_PROMPT_KEYS: dict[str, str] = {
    "cpu_threshold_percent": "thresholds.prompt_cpu",
    "memory_threshold_percent": "thresholds.prompt_memory",
    "disk_threshold_percent": "thresholds.prompt_disk",
    "quiet_hours_window": "thresholds.prompt_window",
}


@router.message(Command("settings"))
async def show_settings(message: Message, lang: str) -> None:
    text, markup = views.settings_root_payload(lang)
    await message.answer(text, reply_markup=markup)


@router.callback_query(SettingsSection.filter(F.section == "root"))
async def open_settings_root(callback: CallbackQuery, lang: str) -> None:
    await views.replace_message(callback, views.settings_root_payload(lang))
    await callback.answer()


@router.callback_query(SettingsSection.filter(F.section == "language"))
async def open_language_picker(callback: CallbackQuery, lang: str) -> None:
    await views.replace_message(callback, views.language_picker_payload(lang))
    await callback.answer()


@router.callback_query(LocaleChoice.filter())
async def choose_language(
    callback: CallbackQuery, callback_data: LocaleChoice, context: PanelContext
) -> None:
    await context.locales.set(callback.from_user.id, callback_data.locale)
    await callback.answer(translate("language.changed", callback_data.locale))
    await views.replace_message(callback, views.main_menu_payload(context, callback_data.locale))


@router.callback_query(SettingsSection.filter(F.section == "alerts"))
async def open_alert_rules(
    callback: CallbackQuery, callback_data: SettingsSection, context: PanelContext, lang: str
) -> None:
    await views.replace_message(callback, views.alert_rules_payload(context, callback_data.page, lang))
    await callback.answer()


@router.callback_query(AlertToggle.filter())
async def toggle_alert_rule(
    callback: CallbackQuery, callback_data: AlertToggle, context: PanelContext, lang: str
) -> None:
    if not 0 <= callback_data.index < len(ALERT_DEFINITIONS):
        await callback.answer()
        return

    kind = str(ALERT_DEFINITIONS[callback_data.index].kind)
    enabled = not context.alert_settings.rule_for(kind).enabled
    await context.alert_settings.set_enabled(kind, enabled)

    await callback.answer(translate("alerts.enabled" if enabled else "alerts.disabled", lang, kind=kind))
    await views.replace_message(callback, views.alert_rules_payload(context, callback_data.page, lang))


@router.callback_query(SettingsSection.filter(F.section == "thresholds"))
async def open_thresholds(callback: CallbackQuery, context: PanelContext, lang: str) -> None:
    await views.replace_message(callback, views.thresholds_payload(context, lang))
    await callback.answer()


@router.callback_query(PreferenceCommand.filter(F.action == "toggle"))
async def toggle_quiet_hours(callback: CallbackQuery, context: PanelContext, lang: str) -> None:
    enabled = not context.alert_settings.preferences.quiet_hours_enabled
    await context.alert_settings.set_preference("quiet_hours_enabled", "1" if enabled else "0")
    await callback.answer(
        translate("thresholds.quiet_enabled" if enabled else "thresholds.quiet_disabled", lang)
    )
    await views.replace_message(callback, views.thresholds_payload(context, lang))


@router.callback_query(PreferenceCommand.filter(F.action == "cycle"))
async def cycle_minimum_severity(callback: CallbackQuery, context: PanelContext, lang: str) -> None:
    current = context.alert_settings.preferences.minimum_severity
    position = SEVERITY_CYCLE.index(current) if current in SEVERITY_CYCLE else 0
    next_severity = SEVERITY_CYCLE[(position + 1) % len(SEVERITY_CYCLE)]
    await context.alert_settings.set_preference("minimum_severity", next_severity)
    await callback.answer(translate("thresholds.severity_now", lang, severity=next_severity))
    await views.replace_message(callback, views.thresholds_payload(context, lang))


@router.callback_query(PreferenceCommand.filter(F.action == "edit"))
async def prompt_preference_value(
    callback: CallbackQuery, callback_data: PreferenceCommand, state: FSMContext, lang: str
) -> None:
    prompt_key = PREFERENCE_PROMPT_KEYS.get(callback_data.key)
    if prompt_key is None:
        await callback.answer()
        return

    await state.set_state(PreferenceFlow.awaiting_value)
    await state.update_data(key=callback_data.key)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"{translate(prompt_key, lang)}\n\n{translate('common.cancel_hint', lang)}"
        )


@router.message(PreferenceFlow.awaiting_value)
async def receive_preference_value(
    message: Message, state: FSMContext, context: PanelContext, lang: str
) -> None:
    flow_data = await state.get_data()
    key = str(flow_data.get("key", ""))
    tokens = (message.text or "").split()

    if key == "quiet_hours_window":
        if len(tokens) != 2 or not all(token.isdigit() for token in tokens):
            await message.answer(translate("thresholds.send_two_hours", lang))
            return
        start, end = (max(0, min(int(token), 23)) for token in tokens)
        await context.alert_settings.set_preference("quiet_hours_start", str(start))
        await context.alert_settings.set_preference("quiet_hours_end", str(end))
    elif key in PREFERENCE_BOUNDS:
        if len(tokens) != 1 or not tokens[0].isdigit():
            await message.answer(translate("thresholds.send_one_number", lang))
            return
        lower_bound, upper_bound = PREFERENCE_BOUNDS[key]
        await context.alert_settings.set_preference(
            key, str(max(lower_bound, min(int(tokens[0]), upper_bound)))
        )
    else:
        await state.clear()
        return

    await state.clear()
    text, markup = views.thresholds_payload(context, lang)
    await message.answer(text, reply_markup=markup)


@router.callback_query(SettingsSection.filter(F.section == "accounts"))
async def open_accounts(callback: CallbackQuery, context: PanelContext, lang: str) -> None:
    await views.replace_message(callback, await views.accounts_payload(context, lang))
    await callback.answer()


def _device_flow_keyboard(authorization: DeviceAuthorization, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("accounts.device_flow_open", lang), url=authorization.verification_uri
                )
            ]
        ]
    )


def _token_fallback_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=translate("accounts.fallback_button", lang), url=TOKEN_CREATION_URL)]
        ]
    )


async def _reserve_account_label(context: PanelContext, preferred_label: str) -> str:
    existing = {account.label for account in await context.account_repository.list_all()}
    truncated = preferred_label[:32]
    if truncated not in existing:
        return truncated
    suffix = 2
    while f"{truncated[:29]}-{suffix}" in existing:
        suffix += 1
    return f"{truncated[:29]}-{suffix}"


async def _store_identity(context: PanelContext, identity: GitHubIdentity) -> str:
    label = await _reserve_account_label(context, identity.username)
    await context.vault.store_github_token(label, identity.username, identity.token)
    return label


async def _prompt_token_fallback(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(AccountFlow.awaiting_token)
    await message.answer(
        f"{bold(translate('accounts.fallback_title', lang))}\n\n"
        f"{translate('accounts.fallback_body', lang)}\n\n"
        f"{translate('common.cancel_hint', lang)}",
        reply_markup=_token_fallback_keyboard(lang),
    )


async def _run_device_flow(
    bot: Bot, chat_id: int, context: PanelContext, authorization: DeviceAuthorization, lang: str
) -> None:
    try:
        token = await poll_for_access_token(context.github_oauth_client_id or "", authorization)
        identity = await fetch_identity(token)
    except GitHubOAuthError as error:
        key = "accounts.device_flow_expired" if str(error) == "expired" else "accounts.device_flow_denied"
        with contextlib.suppress(Exception):
            await bot.send_message(chat_id, translate(key, lang))
        return

    await _store_identity(context, identity)
    with contextlib.suppress(Exception):
        await bot.send_message(
            chat_id, translate("accounts.device_flow_success", lang, username=mono(identity.username))
        )


@router.callback_query(AccountCommand.filter(F.action == "add"))
async def start_account_link(
    callback: CallbackQuery, context: PanelContext, state: FSMContext, bot: Bot, lang: str
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    if context.github_oauth_client_id:
        try:
            authorization = await request_device_authorization(context.github_oauth_client_id)
        except GitHubOAuthError:
            await _prompt_token_fallback(callback.message, state, lang)
            return

        await callback.message.answer(
            f"{bold(translate('accounts.device_flow_title', lang))}\n\n"
            f"{translate('accounts.device_flow_body', lang, code=mono(authorization.user_code))}",
            reply_markup=_device_flow_keyboard(authorization, lang),
        )
        asyncio.create_task(
            _run_device_flow(bot, callback.message.chat.id, context, authorization, lang),
            name="github-device-flow",
        )
        return

    await _prompt_token_fallback(callback.message, state, lang)


@router.message(AccountFlow.awaiting_token)
async def receive_token(message: Message, state: FSMContext, context: PanelContext, lang: str) -> None:
    token = (message.text or "").strip()
    with contextlib.suppress(TelegramBadRequest):
        await message.delete()

    if not token:
        await message.answer(translate("accounts.invalid_token", lang))
        return

    try:
        identity = await fetch_identity(token)
    except GitHubOAuthError:
        await message.answer(translate("accounts.invalid_token", lang))
        return

    await state.clear()
    await _store_identity(context, identity)
    text, markup = await views.accounts_payload(context, lang)
    await message.answer(translate("accounts.device_flow_success", lang, username=mono(identity.username)))
    await message.answer(text, reply_markup=markup)


@router.callback_query(AccountCommand.filter(F.action == "delete"))
async def delete_account(
    callback: CallbackQuery, callback_data: AccountCommand, context: PanelContext, lang: str
) -> None:
    await context.vault.delete_github_account(callback_data.account_id)
    await callback.answer(translate("accounts.deleted", lang))
    await views.replace_message(callback, await views.accounts_payload(context, lang))
