from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app.alerts.dispatcher import AlertDispatcher, NullAlertDispatcher
from app.alerts.kinds import AlertKind
from app.alerts.settings import AlertSettingsStore
from app.config import AppConfig
from app.database.engine import Database
from app.database.repositories import (
    AlertPreferenceRepository,
    AlertRuleRepository,
    EventRepository,
    GitHubAccountRepository,
    ProjectRepository,
    SecretRepository,
    UserPreferenceRepository,
)
from app.i18n import LocaleStore
from app.ingest.github import GitHubCloner
from app.ingest.pipeline import ProjectIngestionPipeline
from app.projects.layout import ProjectsLayout
from app.reporting import ResourceSampler
from app.runtime.builder import ProjectBuilder
from app.runtime.fleet import FleetManager
from app.sandbox.launcher import SandboxLauncher
from app.security.crypto import SecretCipher, load_or_create_master_key
from app.security.redaction import SecretRedactor
from app.security.vault import SecretsVault
from app.telegram.context import PanelContext
from app.telegram.panel import ControlPanelBot

logger = logging.getLogger(__name__)


class ApplicationController:
    def __init__(self, config: AppConfig):
        self.config = config
        self.shutdown_event = asyncio.Event()

        config.ensure_directories()
        self.layout = ProjectsLayout(config.projects_root_dir)
        self.layout.prepare_root()

        self.database = Database(config.database_path)
        self.redactor = SecretRedactor()
        self.cipher = SecretCipher(load_or_create_master_key(config.master_key_path))
        self.launcher = SandboxLauncher(config.isolation_backend, config.container_image)
        self.alerts: AlertDispatcher = NullAlertDispatcher()
        self.control_panel: ControlPanelBot | None = None

    def _request_shutdown(self) -> None:
        logger.info("shutdown signal received, stopping every project")
        self.shutdown_event.set()

    def _install_signal_handlers(self) -> None:
        if sys.platform == "win32":
            return
        loop = asyncio.get_running_loop()
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signal_number, self._request_shutdown)

    async def _assemble(self) -> tuple[PanelContext, ResourceSampler, FleetManager]:
        await self.database.connect()

        project_repository = ProjectRepository(self.database)
        secret_repository = SecretRepository(self.database)
        account_repository = GitHubAccountRepository(self.database)
        event_repository = EventRepository(self.database)
        locales = LocaleStore(UserPreferenceRepository(self.database))

        alert_settings = AlertSettingsStore(
            AlertRuleRepository(self.database), AlertPreferenceRepository(self.database)
        )
        await alert_settings.load()

        self.alerts = AlertDispatcher(alert_settings, event_repository, self.redactor, self.shutdown_event)

        vault = SecretsVault(secret_repository, account_repository, self.cipher, self.redactor)
        await vault.refresh_redaction()

        backend = await self.launcher.select_backend()
        builder = ProjectBuilder(self.launcher, self.redactor)

        fleet = FleetManager(
            layout=self.layout,
            project_repository=project_repository,
            launcher=self.launcher,
            builder=builder,
            vault=vault,
            alerts=self.alerts,
            redactor=self.redactor,
            shutdown_event=self.shutdown_event,
        )
        await fleet.synchronize()

        pipeline = ProjectIngestionPipeline(
            layout=self.layout,
            project_repository=project_repository,
            account_repository=account_repository,
            cipher=self.cipher,
            cloner=GitHubCloner(self.redactor),
            alerts=self.alerts,
        )
        await pipeline.purge_staging_residue()

        sampler = ResourceSampler(
            fleet, self.config.projects_root_dir, self.alerts, alert_settings, self.shutdown_event
        )
        sampler.isolation_backend = backend.name

        context = PanelContext(
            fleet=fleet,
            sampler=sampler,
            pipeline=pipeline,
            vault=vault,
            project_repository=project_repository,
            account_repository=account_repository,
            event_repository=event_repository,
            alert_settings=alert_settings,
            alerts=self.alerts,
            locales=locales,
            admin_ids=self.config.admin_ids,
            github_oauth_client_id=self.config.github_oauth_client_id,
            database_path=self.config.database_path,
        )
        return context, sampler, fleet

    def _build_control_panel(self, context: PanelContext) -> ControlPanelBot | None:
        if not self.config.master_bot_token:
            logger.warning("MASTER_BOT_TOKEN is not set, control panel disabled")
            return None
        if not self.config.admin_ids:
            logger.warning("ADMIN_IDS is empty, nobody will be able to operate the control panel")

        panel = ControlPanelBot(self.config.master_bot_token, context, self.shutdown_event)
        self.alerts.bind_transport(panel.deliver_alert)
        return panel

    async def run(self) -> None:
        self._install_signal_handlers()
        context, sampler, fleet = await self._assemble()

        self.control_panel = self._build_control_panel(context)

        tasks = [
            asyncio.create_task(self.alerts.run(), name="alert-dispatcher"),
            asyncio.create_task(sampler.run(), name="resource-sampler"),
        ]
        if self.control_panel is not None:
            tasks.append(asyncio.create_task(self.control_panel.run(), name="control-panel"))

        if not self.launcher.backend.provides_filesystem_isolation:
            self.alerts.publish(
                AlertKind.ORCHESTRATOR_DEGRADED_ISOLATION,
                "no sandbox backend is available, projects share the host filesystem namespace",
            )

        if self.config.autostart_projects:
            await fleet.start_autostart_projects()

        try:
            await self.shutdown_event.wait()
        finally:
            await fleet.stop_all()
            await self.alerts.drain()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self.control_panel is not None:
                await self.control_panel.close()
            await self.database.close()


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    controller = ApplicationController(AppConfig.from_environment())

    try:
        asyncio.run(controller.run())
    except KeyboardInterrupt:
        pass
