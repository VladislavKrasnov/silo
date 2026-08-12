from __future__ import annotations

from app.database.repositories import UserPreferenceRepository
from app.i18n.translator import SUPPORTED_LOCALES

LOCALE_PREFERENCE_KEY: str = "locale"


class LocaleStore:
    def __init__(self, repository: UserPreferenceRepository):
        self._repository = repository
        self._cache: dict[int, str] = {}

    async def get(self, user_id: int) -> str | None:
        if user_id in self._cache:
            return self._cache[user_id]
        stored = await self._repository.get(user_id, LOCALE_PREFERENCE_KEY)
        if stored not in SUPPORTED_LOCALES:
            return None
        self._cache[user_id] = stored
        return stored

    async def set(self, user_id: int, locale: str) -> None:
        if locale not in SUPPORTED_LOCALES:
            raise ValueError(f"unsupported locale: {locale}")
        await self._repository.set(user_id, LOCALE_PREFERENCE_KEY, locale)
        self._cache[user_id] = locale
