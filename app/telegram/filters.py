from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from app.alerts.dispatcher import AlertDispatcher
from app.alerts.kinds import AlertKind


class IsAdmin(BaseFilter):
    def __init__(self, admin_ids: frozenset[int], alerts: AlertDispatcher):
        self.admin_ids = admin_ids
        self.alerts = alerts

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if user is not None and user.id in self.admin_ids:
            return True
        if user is not None:
            self.alerts.publish(
                AlertKind.SECURITY_UNAUTHORIZED_ACCESS,
                f"user id {user.id} attempted to use the control panel",
            )
        return False
