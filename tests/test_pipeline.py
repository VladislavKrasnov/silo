from __future__ import annotations

import asyncio

import pytest

from app.alerts.dispatcher import NullAlertDispatcher
from app.database.engine import Database
from app.database.repositories import GitHubAccountRepository, ProjectRepository, SecretRepository
from app.ingest.github import GitHubCloner
from app.ingest.pipeline import IngestError, ProjectIngestionPipeline
from app.projects.layout import ProjectsLayout
from app.runtime.builder import ProjectBuilder
from app.runtime.fleet import FleetManager
from app.runtime.supervisor import ProjectState
from app.sandbox.launcher import SandboxLauncher
from app.security.vault import SecretsVault

RESIDENT_BOT_SOURCE = b"""
import os, signal, sys, time
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
print("token=" + os.environ.get("BOT_TOKEN", "unset"), flush=True)
time.sleep(300)
"""

MANIFEST_SOURCE = b"""
[run]
command = ["python", "-u", "main.py"]

[environment]
required = ["BOT_TOKEN"]
"""

GRACEFUL_BOT_SOURCE = b"""
import signal, sys, time

def leave(*_):
    print("graceful-exit", flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, leave)
print("ready", flush=True)
time.sleep(300)
"""

GRACEFUL_MANIFEST_SOURCE = b"""
[run]
command = ["python", "-u", "main.py"]
stop_timeout_seconds = 10
"""

SLOW_BUILD_MANIFEST_SOURCE = b"""
[build]
steps = [["python", "-c", "import time; time.sleep(600)"]]
timeout_seconds = 600

[run]
command = ["python", "-u", "main.py"]
"""


@pytest.fixture
def pipeline(database: Database, projects_layout: ProjectsLayout, cipher, redactor):
    return ProjectIngestionPipeline(
        layout=projects_layout,
        project_repository=ProjectRepository(database),
        account_repository=GitHubAccountRepository(database),
        cipher=cipher,
        cloner=GitHubCloner(redactor),
        alerts=NullAlertDispatcher(),
    )


async def _wait_until(predicate, timeout: float = 60.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition was not met before timeout")


class TestArchiveIngestion:
    async def test_installs_a_project_into_its_own_directory(
        self, pipeline: ProjectIngestionPipeline, projects_layout: ProjectsLayout, zip_builder
    ) -> None:
        payload = zip_builder({"main.py": RESIDENT_BOT_SOURCE, "fleet.toml": MANIFEST_SOURCE})
        outcome = await pipeline.ingest_archive(payload, "weather-bot")

        paths = projects_layout.paths_for(outcome.slug)
        assert outcome.slug == "weather-bot"
        assert (paths.workspace / "main.py").is_file()
        assert paths.virtualenv.is_dir() and paths.logs.is_dir()
        assert projects_layout.discovered_slugs() == ["weather-bot"]

    async def test_generates_a_manifest_when_the_archive_omits_one(
        self, pipeline: ProjectIngestionPipeline, projects_layout: ProjectsLayout, zip_builder
    ) -> None:
        outcome = await pipeline.ingest_archive(zip_builder({"main.py": b"print(1)"}), "alpha")

        assert outcome.manifest_generated is True
        assert projects_layout.paths_for("alpha").manifest.is_file()

    async def test_strips_credential_files_from_the_workspace(
        self, pipeline: ProjectIngestionPipeline, projects_layout: ProjectsLayout, zip_builder
    ) -> None:
        payload = zip_builder(
            {"main.py": b"print(1)", ".env": b"BOT_TOKEN=leaked", ".npmrc": b"//registry:_authToken=x"}
        )
        outcome = await pipeline.ingest_archive(payload, "alpha")

        workspace = projects_layout.paths_for("alpha").workspace
        assert not (workspace / ".env").exists()
        assert not (workspace / ".npmrc").exists()
        assert outcome.report.removed_sensitive_paths == 2

    async def test_rejects_a_duplicate_slug(self, pipeline: ProjectIngestionPipeline, zip_builder) -> None:
        payload = zip_builder({"main.py": b"print(1)"})
        await pipeline.ingest_archive(payload, "alpha")

        with pytest.raises(IngestError, match="already exists"):
            await pipeline.ingest_archive(payload, "alpha")

    async def test_leaves_no_residue_when_ingestion_fails(
        self, pipeline: ProjectIngestionPipeline, projects_layout: ProjectsLayout, zip_builder
    ) -> None:
        with pytest.raises(IngestError):
            await pipeline.ingest_archive(zip_builder({"../escape.py": b"x"}), "alpha")

        assert list(projects_layout.projects_root_dir.iterdir()) == []

    async def test_removal_deletes_the_directory_and_the_record(
        self,
        pipeline: ProjectIngestionPipeline,
        projects_layout: ProjectsLayout,
        database: Database,
        zip_builder,
    ) -> None:
        await pipeline.ingest_archive(zip_builder({"main.py": b"print(1)"}), "alpha")
        assert await pipeline.remove("alpha") is True

        assert projects_layout.discovered_slugs() == []
        assert await ProjectRepository(database).get_by_slug("alpha") is None


class TestSupervisedLifecycle:
    async def _build_fleet(
        self, database: Database, projects_layout: ProjectsLayout, cipher, redactor, shutdown_event
    ) -> tuple[FleetManager, SecretsVault]:
        launcher = SandboxLauncher("native", "python:3.12-slim")
        await launcher.select_backend()
        vault = SecretsVault(SecretRepository(database), GitHubAccountRepository(database), cipher, redactor)
        fleet = FleetManager(
            layout=projects_layout,
            project_repository=ProjectRepository(database),
            launcher=launcher,
            builder=ProjectBuilder(launcher, redactor),
            vault=vault,
            alerts=NullAlertDispatcher(),
            redactor=redactor,
            shutdown_event=shutdown_event,
        )
        await fleet.synchronize()
        return fleet, vault

    @pytest.mark.slow
    async def test_builds_starts_and_stops_a_project(
        self,
        pipeline: ProjectIngestionPipeline,
        database: Database,
        projects_layout: ProjectsLayout,
        cipher,
        redactor,
        zip_builder,
    ) -> None:
        await pipeline.ingest_archive(
            zip_builder({"main.py": RESIDENT_BOT_SOURCE, "fleet.toml": MANIFEST_SOURCE}), "alpha"
        )

        shutdown_event = asyncio.Event()
        fleet, vault = await self._build_fleet(database, projects_layout, cipher, redactor, shutdown_event)
        supervisor = fleet.get("alpha")
        assert supervisor is not None

        await vault.store(supervisor.project_id, {"BOT_TOKEN": "injected-token"}, replace_existing=True)
        await supervisor.start()

        try:
            await _wait_until(lambda: supervisor.state is ProjectState.RUNNING)
            assert supervisor.pid is not None
            assert projects_layout.paths_for("alpha").virtualenv.joinpath("bin", "python").exists()
            await _wait_until(lambda: any("token=" in line for line in supervisor.recent_output))
        finally:
            await supervisor.stop(announce=False)

        assert supervisor.state is ProjectState.STOPPED
        assert supervisor.pid is None

    @pytest.mark.slow
    async def test_injects_secrets_without_writing_them_to_the_workspace(
        self,
        pipeline: ProjectIngestionPipeline,
        database: Database,
        projects_layout: ProjectsLayout,
        cipher,
        redactor,
        zip_builder,
    ) -> None:
        await pipeline.ingest_archive(
            zip_builder({"main.py": RESIDENT_BOT_SOURCE, "fleet.toml": MANIFEST_SOURCE}), "alpha"
        )

        shutdown_event = asyncio.Event()
        fleet, vault = await self._build_fleet(database, projects_layout, cipher, redactor, shutdown_event)
        supervisor = fleet.get("alpha")
        assert supervisor is not None

        await vault.store(supervisor.project_id, {"BOT_TOKEN": "injected-token"}, replace_existing=True)
        await supervisor.start()

        try:
            await _wait_until(lambda: any("token=" in line for line in supervisor.recent_output))
        finally:
            await supervisor.stop(announce=False)

        workspace = projects_layout.paths_for("alpha").workspace
        assert not (workspace / ".env").exists()
        assert not any("injected-token" in path.read_text() for path in workspace.rglob("*.py"))
        assert any("token=[redacted]" in line for line in supervisor.recent_output)

    @pytest.mark.slow
    async def test_stop_lets_the_project_run_its_shutdown_handler(
        self,
        pipeline: ProjectIngestionPipeline,
        database: Database,
        projects_layout: ProjectsLayout,
        cipher,
        redactor,
        zip_builder,
    ) -> None:
        await pipeline.ingest_archive(
            zip_builder({"main.py": GRACEFUL_BOT_SOURCE, "fleet.toml": GRACEFUL_MANIFEST_SOURCE}), "alpha"
        )

        shutdown_event = asyncio.Event()
        fleet, _vault = await self._build_fleet(database, projects_layout, cipher, redactor, shutdown_event)
        supervisor = fleet.get("alpha")
        assert supervisor is not None

        await supervisor.start()
        await _wait_until(lambda: any("ready" in line for line in supervisor.recent_output))
        await supervisor.stop(announce=False)

        assert supervisor.state is ProjectState.STOPPED
        assert any("graceful-exit" in line for line in supervisor.recent_output)

    @pytest.mark.slow
    async def test_stop_during_a_build_does_not_wait_for_the_build_timeout(
        self,
        pipeline: ProjectIngestionPipeline,
        database: Database,
        projects_layout: ProjectsLayout,
        cipher,
        redactor,
        zip_builder,
    ) -> None:
        await pipeline.ingest_archive(
            zip_builder({"main.py": b"print(1)", "fleet.toml": SLOW_BUILD_MANIFEST_SOURCE}), "alpha"
        )

        shutdown_event = asyncio.Event()
        fleet, _vault = await self._build_fleet(database, projects_layout, cipher, redactor, shutdown_event)
        supervisor = fleet.get("alpha")
        assert supervisor is not None

        await supervisor.start()
        await _wait_until(lambda: supervisor.state is ProjectState.BUILDING, timeout=30.0)

        loop = asyncio.get_running_loop()
        started_at = loop.time()
        await asyncio.wait_for(supervisor.stop(announce=False), timeout=30.0)

        assert loop.time() - started_at < 25.0
        assert supervisor.is_active is False

    async def test_reports_a_misconfigured_manifest(
        self,
        pipeline: ProjectIngestionPipeline,
        database: Database,
        projects_layout: ProjectsLayout,
        cipher,
        redactor,
        zip_builder,
    ) -> None:
        await pipeline.ingest_archive(zip_builder({"main.py": b"print(1)"}), "alpha")
        projects_layout.paths_for("alpha").manifest.write_text("[run]\ncommand = []\n")

        shutdown_event = asyncio.Event()
        fleet, _vault = await self._build_fleet(database, projects_layout, cipher, redactor, shutdown_event)
        supervisor = fleet.get("alpha")
        assert supervisor is not None

        await supervisor.start()
        await _wait_until(lambda: supervisor.state is ProjectState.MISCONFIGURED, timeout=10.0)
        assert supervisor.is_active is False


class TestFleetBulkOperations:
    async def _build_fleet(
        self, database: Database, projects_layout: ProjectsLayout, cipher, redactor, shutdown_event
    ) -> FleetManager:
        launcher = SandboxLauncher("native", "python:3.12-slim")
        await launcher.select_backend()
        vault = SecretsVault(SecretRepository(database), GitHubAccountRepository(database), cipher, redactor)
        fleet = FleetManager(
            layout=projects_layout,
            project_repository=ProjectRepository(database),
            launcher=launcher,
            builder=ProjectBuilder(launcher, redactor),
            vault=vault,
            alerts=NullAlertDispatcher(),
            redactor=redactor,
            shutdown_event=shutdown_event,
        )
        await fleet.synchronize()
        return fleet

    @pytest.mark.slow
    async def test_start_all_starts_every_stopped_project(
        self,
        pipeline: ProjectIngestionPipeline,
        database: Database,
        projects_layout: ProjectsLayout,
        cipher,
        redactor,
        zip_builder,
    ) -> None:
        await pipeline.ingest_archive(zip_builder({"main.py": RESIDENT_BOT_SOURCE}), "alpha")
        await pipeline.ingest_archive(zip_builder({"main.py": RESIDENT_BOT_SOURCE}), "beta")

        shutdown_event = asyncio.Event()
        fleet = await self._build_fleet(database, projects_layout, cipher, redactor, shutdown_event)

        try:
            await fleet.start_all()
            await _wait_until(lambda: set(fleet.running_slugs()) == {"alpha", "beta"})
        finally:
            await fleet.stop_all()

    @pytest.mark.slow
    async def test_restart_all_starts_stopped_and_restarts_running(
        self,
        pipeline: ProjectIngestionPipeline,
        database: Database,
        projects_layout: ProjectsLayout,
        cipher,
        redactor,
        zip_builder,
    ) -> None:
        await pipeline.ingest_archive(zip_builder({"main.py": RESIDENT_BOT_SOURCE}), "alpha")
        await pipeline.ingest_archive(zip_builder({"main.py": RESIDENT_BOT_SOURCE}), "beta")

        shutdown_event = asyncio.Event()
        fleet = await self._build_fleet(database, projects_layout, cipher, redactor, shutdown_event)

        try:
            await fleet.get("alpha").start()
            await _wait_until(lambda: fleet.get("alpha").is_active)
            running_pid_before = fleet.get("alpha").pid

            await fleet.restart_all()
            await _wait_until(lambda: set(fleet.running_slugs()) == {"alpha", "beta"})
            await _wait_until(lambda: fleet.get("alpha").pid != running_pid_before)
        finally:
            await fleet.stop_all()

    @pytest.mark.slow
    async def test_stop_all_stops_every_running_project(
        self,
        pipeline: ProjectIngestionPipeline,
        database: Database,
        projects_layout: ProjectsLayout,
        cipher,
        redactor,
        zip_builder,
    ) -> None:
        await pipeline.ingest_archive(zip_builder({"main.py": RESIDENT_BOT_SOURCE}), "alpha")

        shutdown_event = asyncio.Event()
        fleet = await self._build_fleet(database, projects_layout, cipher, redactor, shutdown_event)
        await fleet.start_all()
        await _wait_until(lambda: fleet.get("alpha").is_active)

        await fleet.stop_all()

        assert fleet.running_slugs() == []
