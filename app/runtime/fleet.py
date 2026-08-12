from __future__ import annotations

import asyncio
import logging

from app.alerts.dispatcher import AlertDispatcher
from app.database.repositories import ProjectRecord, ProjectRepository
from app.projects.layout import ProjectsLayout
from app.runtime.builder import ProjectBuilder
from app.runtime.supervisor import ProjectSupervisor
from app.sandbox.launcher import SandboxLauncher
from app.security.redaction import SecretRedactor
from app.security.vault import SecretsVault

logger = logging.getLogger(__name__)


class FleetManager:
    def __init__(
        self,
        layout: ProjectsLayout,
        project_repository: ProjectRepository,
        launcher: SandboxLauncher,
        builder: ProjectBuilder,
        vault: SecretsVault,
        alerts: AlertDispatcher,
        redactor: SecretRedactor,
        shutdown_event: asyncio.Event,
    ):
        self._layout = layout
        self._project_repository = project_repository
        self._launcher = launcher
        self._builder = builder
        self._vault = vault
        self._alerts = alerts
        self._redactor = redactor
        self._shutdown_event = shutdown_event
        self.supervisors: dict[str, ProjectSupervisor] = {}
        self.records: dict[str, ProjectRecord] = {}

    async def synchronize(self) -> None:
        records = await self._project_repository.list_all()
        self.records = {record.slug: record for record in records}
        registered_slugs = set(self.records)

        for orphaned_slug in set(self.supervisors) - registered_slugs:
            supervisor = self.supervisors.pop(orphaned_slug)
            await supervisor.stop(announce=False)

        for record in records:
            if record.slug in self.supervisors:
                continue
            if not self._layout.exists(record.slug):
                logger.warning("project %s is registered but its directory is missing", record.slug)
                continue
            self.supervisors[record.slug] = ProjectSupervisor(
                project_id=record.id,
                paths=self._layout.paths_for(record.slug),
                shutdown_event=self._shutdown_event,
                launcher=self._launcher,
                builder=self._builder,
                vault=self._vault,
                alerts=self._alerts,
                redactor=self._redactor,
            )

    @property
    def sorted_slugs(self) -> list[str]:
        return sorted(self.supervisors)

    def resolve_slug_by_index(self, index: int) -> str | None:
        slugs = self.sorted_slugs
        return slugs[index] if 0 <= index < len(slugs) else None

    def index_of(self, slug: str) -> int | None:
        try:
            return self.sorted_slugs.index(slug)
        except ValueError:
            return None

    def get(self, slug: str) -> ProjectSupervisor | None:
        return self.supervisors.get(slug)

    def running_slugs(self) -> list[str]:
        return [slug for slug in self.sorted_slugs if self.supervisors[slug].is_active]

    def stopped_slugs(self) -> list[str]:
        return [slug for slug in self.sorted_slugs if not self.supervisors[slug].is_active]

    async def start_autostart_projects(self) -> None:
        await asyncio.gather(
            *(
                supervisor.start()
                for slug, supervisor in self.supervisors.items()
                if self.records[slug].autostart
            )
        )

    async def stop_all(self) -> None:
        await asyncio.gather(
            *(supervisor.stop(announce=False) for supervisor in self.supervisors.values()),
            return_exceptions=True,
        )

    async def start_all(self) -> None:
        await asyncio.gather(
            *(supervisor.start() for supervisor in self.supervisors.values() if not supervisor.is_active),
            return_exceptions=True,
        )

    async def restart_all(self) -> None:
        await asyncio.gather(
            *(
                supervisor.restart() if supervisor.is_active else supervisor.start()
                for supervisor in self.supervisors.values()
            ),
            return_exceptions=True,
        )

    async def detach(self, slug: str) -> None:
        supervisor = self.supervisors.pop(slug, None)
        self.records.pop(slug, None)
        if supervisor is not None:
            await supervisor.stop(announce=False)

    def sample_resource_usage(self) -> None:
        for supervisor in self.supervisors.values():
            supervisor.sample_resource_usage()
