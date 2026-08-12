from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.alerts.kinds import ALERT_DEFINITIONS_BY_KIND, AlertKind, AlertSeverity
from app.alerts.settings import AlertSettingsStore
from app.constants import ALERT_QUEUE_CAPACITY
from app.database.repositories import EventRepository
from app.security.redaction import SecretRedactor

logger = logging.getLogger(__name__)

AlertTransport = Callable[["Alert"], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Alert:
    kind: str
    severity: str
    title: str
    message: str
    project_slug: str | None
    created_at: float


class AlertDispatcher:
    def __init__(
        self,
        settings: AlertSettingsStore,
        event_repository: EventRepository,
        redactor: SecretRedactor,
        shutdown_event: asyncio.Event,
    ):
        self._settings = settings
        self._event_repository = event_repository
        self._redactor = redactor
        self._shutdown_event = shutdown_event
        self._queue: asyncio.Queue[Alert] = asyncio.Queue(maxsize=ALERT_QUEUE_CAPACITY)
        self._last_delivery: dict[tuple[str, str | None], float] = {}
        self._transport: AlertTransport | None = None

    def bind_transport(self, transport: AlertTransport) -> None:
        self._transport = transport

    def publish(self, kind: AlertKind, message: str, project_slug: str | None = None) -> None:
        definition = ALERT_DEFINITIONS_BY_KIND.get(kind)
        if definition is None:
            return
        alert = Alert(
            kind=str(kind),
            severity=str(definition.severity),
            title=definition.title,
            message=self._redactor.apply(message)[:1024],
            project_slug=project_slug,
            created_at=time.time(),
        )
        try:
            self._queue.put_nowait(alert)
        except asyncio.QueueFull:
            logger.warning("alert queue saturated, dropping %s", kind)

    def _passes_throttle(self, alert: Alert) -> bool:
        throttle_seconds = self._settings.rule_for(alert.kind).throttle_seconds
        if throttle_seconds <= 0:
            return True
        throttle_key = (alert.kind, alert.project_slug)
        previous_delivery = self._last_delivery.get(throttle_key, 0.0)
        if alert.created_at - previous_delivery < throttle_seconds:
            return False
        self._last_delivery[throttle_key] = alert.created_at
        return True

    async def _process(self, alert: Alert) -> None:
        await self._event_repository.record(alert.kind, alert.severity, alert.project_slug, alert.message)

        if not self._settings.rule_for(alert.kind).enabled:
            return
        if self._settings.suppresses(alert.severity) or not self._passes_throttle(alert):
            return
        if self._transport is None:
            return

        try:
            await self._transport(alert)
        except Exception:
            logger.exception("alert transport failed for %s", alert.kind)

    async def run(self) -> None:
        shutdown_task = asyncio.create_task(self._shutdown_event.wait())
        try:
            while True:
                queue_task = asyncio.create_task(self._queue.get())
                done, _pending = await asyncio.wait(
                    (queue_task, shutdown_task), return_when=asyncio.FIRST_COMPLETED
                )
                if queue_task in done:
                    await self._process(queue_task.result())
                    continue
                queue_task.cancel()
                await self.drain()
                return
        finally:
            shutdown_task.cancel()

    async def drain(self) -> None:
        while not self._queue.empty():
            await self._process(self._queue.get_nowait())


class NullAlertDispatcher(AlertDispatcher):
    def __init__(self) -> None:
        self._queue = asyncio.Queue()

    def publish(self, kind: AlertKind, message: str, project_slug: str | None = None) -> None:
        logger.info("alert %s [%s] %s", kind, project_slug or "-", message)

    def bind_transport(self, transport: AlertTransport) -> None:
        return None

    async def run(self) -> None:
        return None

    async def drain(self) -> None:
        return None


SEVERITY_LABELS: dict[str, str] = {
    AlertSeverity.INFO: "INFO",
    AlertSeverity.WARNING: "WARNING",
    AlertSeverity.CRITICAL: "CRITICAL",
}
