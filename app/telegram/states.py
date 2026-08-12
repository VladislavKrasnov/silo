from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class IngestFlow(StatesGroup):
    awaiting_repository_url = State()
    awaiting_account_choice = State()
    awaiting_archive = State()


class SecretsFlow(StatesGroup):
    awaiting_assignments = State()


class AccountFlow(StatesGroup):
    awaiting_token = State()


class PreferenceFlow(StatesGroup):
    awaiting_value = State()
