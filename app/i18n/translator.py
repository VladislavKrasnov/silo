from __future__ import annotations

from typing import Final

from app.i18n.catalog import STRINGS

SUPPORTED_LOCALES: Final[tuple[str, ...]] = ("en", "ru")
DEFAULT_LOCALE: Final[str] = "en"


def detect_locale(telegram_language_code: str | None) -> str | None:
    if not telegram_language_code:
        return None
    return "ru" if telegram_language_code.strip().lower().startswith("ru") else DEFAULT_LOCALE


def translate(key: str, locale: str, **params: object) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    template = entry.get(locale) or entry.get(DEFAULT_LOCALE) or key
    return template.format(**params) if params else template
