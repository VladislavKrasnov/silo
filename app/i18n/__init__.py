from __future__ import annotations

from app.i18n.store import LocaleStore
from app.i18n.translator import DEFAULT_LOCALE, SUPPORTED_LOCALES, detect_locale, translate

__all__ = ["LocaleStore", "DEFAULT_LOCALE", "SUPPORTED_LOCALES", "detect_locale", "translate"]
