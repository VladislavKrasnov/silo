from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace

from app.alerts.kinds import ALERT_DEFINITIONS, AlertSeverity
from app.database.repositories import AlertPreferenceRepository, AlertRuleRepository

SEVERITY_RANK: dict[str, int] = {AlertSeverity.INFO: 0, AlertSeverity.WARNING: 1, AlertSeverity.CRITICAL: 2}
THROTTLE_CEILING_SECONDS: int = 86400
DEFAULTS_MIGRATION_MARKER: str = "_alert_defaults_migrated_v2"


@dataclass(frozen=True, slots=True)
class AlertPreferences:
    cpu_threshold_percent: int = 90
    memory_threshold_percent: int = 85
    disk_threshold_percent: int = 90
    quiet_hours_enabled: bool = False
    quiet_hours_start: int = 23
    quiet_hours_end: int = 7
    minimum_severity: str = AlertSeverity.INFO


PREFERENCE_BOUNDS: dict[str, tuple[int, int]] = {
    "cpu_threshold_percent": (1, 100),
    "memory_threshold_percent": (1, 100),
    "disk_threshold_percent": (1, 100),
    "quiet_hours_start": (0, 23),
    "quiet_hours_end": (0, 23),
}


@dataclass(frozen=True, slots=True)
class AlertRule:
    enabled: bool
    throttle_seconds: int


class AlertSettingsStore:
    def __init__(
        self, rule_repository: AlertRuleRepository, preference_repository: AlertPreferenceRepository
    ):
        self._rule_repository = rule_repository
        self._preference_repository = preference_repository
        self._rules: dict[str, AlertRule] = {}
        self._preferences = AlertPreferences()

    @property
    def preferences(self) -> AlertPreferences:
        return self._preferences

    async def load(self) -> None:
        defaults = {
            definition.kind: (definition.default_enabled, definition.default_throttle_seconds)
            for definition in ALERT_DEFINITIONS
        }
        stored_preferences = await self._preference_repository.load_all()
        if DEFAULTS_MIGRATION_MARKER not in stored_preferences:
            await self._rule_repository.reset_to_defaults(defaults)
            await self._preference_repository.set(DEFAULTS_MIGRATION_MARKER, "1")
        else:
            await self._rule_repository.seed_missing(defaults)
        self._rules = {
            record.kind: AlertRule(enabled=record.enabled, throttle_seconds=record.throttle_seconds)
            for record in await self._rule_repository.list_all()
        }
        self._preferences = self._materialize_preferences(await self._preference_repository.load_all())

    @staticmethod
    def _materialize_preferences(stored: dict[str, str]) -> AlertPreferences:
        defaults = AlertPreferences()
        overrides: dict[str, object] = {}
        for key, raw_value in stored.items():
            if key in PREFERENCE_BOUNDS:
                lower_bound, upper_bound = PREFERENCE_BOUNDS[key]
                try:
                    overrides[key] = max(lower_bound, min(int(raw_value), upper_bound))
                except ValueError:
                    continue
            elif key == "quiet_hours_enabled":
                overrides[key] = raw_value == "1"
            elif key == "minimum_severity" and raw_value in SEVERITY_RANK:
                overrides[key] = raw_value
        return replace(defaults, **overrides)

    def rule_for(self, kind: str) -> AlertRule:
        return self._rules.get(kind, AlertRule(enabled=True, throttle_seconds=0))

    def all_rules(self) -> dict[str, AlertRule]:
        return dict(self._rules)

    async def set_enabled(self, kind: str, enabled: bool) -> None:
        await self._rule_repository.set_enabled(kind, enabled)
        current = self.rule_for(kind)
        self._rules[kind] = AlertRule(enabled=enabled, throttle_seconds=current.throttle_seconds)

    async def set_throttle(self, kind: str, throttle_seconds: int) -> None:
        clamped = max(0, min(throttle_seconds, THROTTLE_CEILING_SECONDS))
        await self._rule_repository.set_throttle(kind, clamped)
        current = self.rule_for(kind)
        self._rules[kind] = AlertRule(enabled=current.enabled, throttle_seconds=clamped)

    async def set_preference(self, key: str, value: str) -> None:
        await self._preference_repository.set(key, value)
        self._preferences = self._materialize_preferences(await self._preference_repository.load_all())

    def suppresses(self, severity: str) -> bool:
        if SEVERITY_RANK.get(severity, 0) < SEVERITY_RANK.get(self._preferences.minimum_severity, 0):
            return True
        return self._within_quiet_hours() and severity != AlertSeverity.CRITICAL

    def _within_quiet_hours(self) -> bool:
        if not self._preferences.quiet_hours_enabled:
            return False
        current_hour = dt.datetime.now(dt.UTC).hour
        start, end = self._preferences.quiet_hours_start, self._preferences.quiet_hours_end
        if start == end:
            return False
        if start < end:
            return start <= current_hour < end
        return current_hour >= start or current_hour < end
