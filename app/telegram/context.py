from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.alerts.dispatcher import AlertDispatcher
from app.alerts.settings import AlertSettingsStore
from app.database.repositories import (
    EventRepository,
    GitHubAccountRepository,
    ProjectRepository,
)
from app.i18n import LocaleStore
from app.ingest.pipeline import ProjectIngestionPipeline
from app.reporting import ResourceSampler
from app.runtime.fleet import FleetManager
from app.security.vault import SecretsVault


@dataclass(frozen=True, slots=True)
class PanelContext:
    fleet: FleetManager
    sampler: ResourceSampler
    pipeline: ProjectIngestionPipeline
    vault: SecretsVault
    project_repository: ProjectRepository
    account_repository: GitHubAccountRepository
    event_repository: EventRepository
    alert_settings: AlertSettingsStore
    alerts: AlertDispatcher
    locales: LocaleStore
    admin_ids: frozenset[int]
    github_oauth_client_id: str | None
    database_path: Path
