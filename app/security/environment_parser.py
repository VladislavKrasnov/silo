from __future__ import annotations

from dataclasses import dataclass, field

from app.constants import ENVIRONMENT_KEY_PATTERN

MAX_ENVIRONMENT_ENTRIES: int = 256
MAX_ENVIRONMENT_VALUE_LENGTH: int = 8192
_QUOTE_CHARACTERS: frozenset[str] = frozenset({'"', "'"})
_CONTROL_CHARACTERS: frozenset[str] = frozenset(chr(code) for code in range(32) if code != 9)


@dataclass(frozen=True, slots=True)
class ParsedEnvironment:
    entries: dict[str, str] = field(default_factory=dict)
    rejected_lines: tuple[str, ...] = ()


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in _QUOTE_CHARACTERS:
        return value[1:-1]
    return value


def parse_environment_assignments(raw_text: str) -> ParsedEnvironment:
    entries: dict[str, str] = {}
    rejected: list[str] = []

    for raw_line in raw_text.splitlines():
        line = raw_line.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()

        key, separator, raw_value = line.partition("=")
        key = key.strip()
        value = _strip_matching_quotes(raw_value.strip())

        if not separator or not ENVIRONMENT_KEY_PATTERN.match(key):
            rejected.append(raw_line[:64])
            continue
        if len(value) > MAX_ENVIRONMENT_VALUE_LENGTH or _CONTROL_CHARACTERS.intersection(value):
            rejected.append(f"{key}=...")
            continue
        if len(entries) >= MAX_ENVIRONMENT_ENTRIES and key not in entries:
            rejected.append(f"{key}=...")
            continue

        entries[key] = value

    return ParsedEnvironment(entries=entries, rejected_lines=tuple(rejected))
