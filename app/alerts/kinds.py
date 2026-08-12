from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertKind(StrEnum):
    PROJECT_STARTED = "project.started"
    PROJECT_STOPPED = "project.stopped"
    PROJECT_CRASHED = "project.crashed"
    PROJECT_RESTART_LOOP = "project.restart_loop"
    PROJECT_BUILD_FAILED = "project.build_failed"
    PROJECT_REMOVED = "project.removed"
    PROJECT_MISCONFIGURED = "project.misconfigured"
    PROJECT_SECRETS_MISSING = "project.secrets_missing"
    HOST_RESOURCE_PRESSURE = "host.resource_pressure"
    ORCHESTRATOR_DEGRADED_ISOLATION = "orchestrator.degraded_isolation"
    SECURITY_UNAUTHORIZED_ACCESS = "security.unauthorized_access"
    SECURITY_SECRETS_CHANGED = "security.secrets_changed"
    SECURITY_INGEST_REJECTED = "security.ingest_rejected"


@dataclass(frozen=True, slots=True)
class AlertDefinition:
    kind: AlertKind
    title: str
    severity: AlertSeverity
    default_enabled: bool
    default_throttle_seconds: int
    user_configurable: bool = False


ALERT_DEFINITIONS: Final[tuple[AlertDefinition, ...]] = (
    AlertDefinition(AlertKind.PROJECT_STARTED, "Project started", AlertSeverity.INFO, False, 30),
    AlertDefinition(AlertKind.PROJECT_STOPPED, "Project stopped", AlertSeverity.INFO, False, 30),
    AlertDefinition(
        AlertKind.PROJECT_CRASHED, "Project crashed", AlertSeverity.CRITICAL, True, 60, user_configurable=True
    ),
    AlertDefinition(
        AlertKind.PROJECT_RESTART_LOOP,
        "Restart loop detected",
        AlertSeverity.CRITICAL,
        True,
        300,
        user_configurable=True,
    ),
    AlertDefinition(
        AlertKind.PROJECT_BUILD_FAILED,
        "Build failed",
        AlertSeverity.CRITICAL,
        True,
        60,
        user_configurable=True,
    ),
    AlertDefinition(AlertKind.PROJECT_REMOVED, "Project removed", AlertSeverity.WARNING, False, 0),
    AlertDefinition(AlertKind.PROJECT_MISCONFIGURED, "Manifest invalid", AlertSeverity.WARNING, False, 300),
    AlertDefinition(
        AlertKind.PROJECT_SECRETS_MISSING,
        "Required secrets missing",
        AlertSeverity.WARNING,
        False,
        600,
        user_configurable=True,
    ),
    AlertDefinition(
        AlertKind.HOST_RESOURCE_PRESSURE,
        "Host resource pressure",
        AlertSeverity.WARNING,
        False,
        600,
        user_configurable=True,
    ),
    AlertDefinition(
        AlertKind.ORCHESTRATOR_DEGRADED_ISOLATION,
        "Isolation degraded",
        AlertSeverity.CRITICAL,
        True,
        3600,
        user_configurable=True,
    ),
    AlertDefinition(
        AlertKind.SECURITY_UNAUTHORIZED_ACCESS,
        "Unauthorized access attempt",
        AlertSeverity.WARNING,
        True,
        300,
    ),
    AlertDefinition(AlertKind.SECURITY_SECRETS_CHANGED, "Secrets changed", AlertSeverity.INFO, False, 0),
    AlertDefinition(AlertKind.SECURITY_INGEST_REJECTED, "Ingest rejected", AlertSeverity.WARNING, False, 60),
)

USER_CONFIGURABLE_ALERT_KINDS: Final[tuple[AlertKind, ...]] = tuple(
    definition.kind for definition in ALERT_DEFINITIONS if definition.user_configurable
)

ALERT_DEFINITIONS_BY_KIND: Final[dict[str, AlertDefinition]] = {
    definition.kind: definition for definition in ALERT_DEFINITIONS
}
