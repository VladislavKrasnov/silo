from __future__ import annotations

import re
from collections.abc import Iterable

REDACTION_PLACEHOLDER: str = "[redacted]"
_MINIMUM_REDACTABLE_LENGTH: int = 6


class SecretRedactor:
    __slots__ = ("_pattern",)

    def __init__(self, secret_values: Iterable[str] = ()):
        self._pattern: re.Pattern[str] | None = None
        self.replace_values(secret_values)

    def replace_values(self, secret_values: Iterable[str]) -> None:
        candidates = sorted(
            {value for value in secret_values if len(value) >= _MINIMUM_REDACTABLE_LENGTH},
            key=len,
            reverse=True,
        )
        self._pattern = re.compile("|".join(re.escape(value) for value in candidates)) if candidates else None

    def apply(self, text: str) -> str:
        if self._pattern is None:
            return text
        return self._pattern.sub(REDACTION_PLACEHOLDER, text)
