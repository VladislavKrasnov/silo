from __future__ import annotations

import asyncio
import hashlib
import logging
import signal
import time
from collections import deque
from enum import StrEnum

import psutil

from app.alerts.dispatcher import AlertDispatcher
from app.alerts.kinds import AlertKind
from app.constants import (
    CHILD_LOG_LINE_MAX_BYTES,
    CHILD_LOG_RETAINED_LINES,
    CRASH_BACKOFF_SECONDS,
    CRASH_COUNTER_RESET_THRESHOLD_SECONDS,
)
from app.projects.layout import ProjectPaths
from app.projects.manifest import ManifestError, ProjectManifest, RestartPolicy, load_manifest
from app.runtime.builder import ProjectBuilder
from app.sandbox.launcher import SandboxLauncher, terminate_process_tree
from app.sandbox.spec import SandboxSpec
from app.security.redaction import SecretRedactor
from app.security.vault import SecretsVault

logger = logging.getLogger(__name__)

BUILD_STAMP_FILENAME: str = ".build-stamp"


class ProjectState(StrEnum):
    STOPPED = "stopped"
    BUILDING = "building"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    CRASHED = "crashed"
    BUILD_FAILED = "build failed"
    MISCONFIGURED = "misconfigured"


ACTIVE_STATES: frozenset[ProjectState] = frozenset(
    {ProjectState.BUILDING, ProjectState.STARTING, ProjectState.RUNNING}
)


class ProjectSupervisor:
    def __init__(
        self,
        project_id: int,
        paths: ProjectPaths,
        shutdown_event: asyncio.Event,
        launcher: SandboxLauncher,
        builder: ProjectBuilder,
        vault: SecretsVault,
        alerts: AlertDispatcher,
        redactor: SecretRedactor,
    ):
        self.project_id = project_id
        self.paths = paths
        self.slug = paths.slug
        self.shutdown_event = shutdown_event

        self._launcher = launcher
        self._builder = builder
        self._vault = vault
        self._alerts = alerts
        self._redactor = redactor

        self.state: ProjectState = ProjectState.STOPPED
        self.pid: int | None = None
        self.start_time: float = time.time()
        self.cpu_percent: float = 0.0
        self.restart_count: int = 0
        self.last_failure_detail: str = ""
        self.manifest: ProjectManifest | None = None

        self.recent_output: deque[str] = deque(maxlen=CHILD_LOG_RETAINED_LINES)
        self._process: asyncio.subprocess.Process | None = None
        self._resource_probe: psutil.Process | None = None
        self._supervisor_task: asyncio.Task[None] | None = None
        self._stop_requested = asyncio.Event()
        self._lifecycle_lock = asyncio.Lock()
        self._rebuild_requested = False

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    def sample_resource_usage(self) -> None:
        if not self.pid or not psutil.pid_exists(self.pid):
            self._resource_probe = None
            self.cpu_percent = 0.0
            return
        try:
            if self._resource_probe is None or self._resource_probe.pid != self.pid:
                self._resource_probe = psutil.Process(self.pid)
                self._resource_probe.cpu_percent(interval=None)
                self.cpu_percent = 0.0
            else:
                self.cpu_percent = self._resource_probe.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self._resource_probe = None
            self.cpu_percent = 0.0

    def memory_bytes(self) -> int:
        if self.pid is None or not psutil.pid_exists(self.pid):
            return 0
        try:
            probe = self._resource_probe or psutil.Process(self.pid)
            return probe.memory_info().rss + sum(
                child.memory_info().rss for child in probe.children(recursive=True)
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._supervisor_task is not None and not self._supervisor_task.done():
                return
            self._stop_requested.clear()
            self.state = ProjectState.STARTING
            self._supervisor_task = asyncio.create_task(
                self._run_supervised_lifecycle(), name=f"supervisor:{self.slug}"
            )

    async def stop(self, announce: bool = True) -> None:
        async with self._lifecycle_lock:
            task = self._supervisor_task
            if task is None or task.done():
                self.state = ProjectState.STOPPED
                self.pid = None
                return
            self.state = ProjectState.STOPPING
            self._stop_requested.set()
        await task
        if announce:
            self._alerts.publish(AlertKind.PROJECT_STOPPED, "stopped on request", self.slug)

    async def restart(self) -> None:
        await self.stop(announce=False)
        await self.start()

    async def rebuild(self) -> None:
        await self.stop(announce=False)
        self._invalidate_build_stamp()
        self._rebuild_requested = True
        await self.start()

    def _build_signature(self, manifest: ProjectManifest) -> str:
        payload = repr((manifest.runtime_kind, manifest.build_steps)).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _build_stamp_path(self):
        return self.paths.root / BUILD_STAMP_FILENAME

    def _invalidate_build_stamp(self) -> None:
        self._build_stamp_path().unlink(missing_ok=True)

    def _build_is_current(self, manifest: ProjectManifest) -> bool:
        stamp_path = self._build_stamp_path()
        try:
            return stamp_path.read_text(encoding="utf-8").strip() == self._build_signature(manifest)
        except OSError:
            return False

    def _record_build_stamp(self, manifest: ProjectManifest) -> None:
        self._build_stamp_path().write_text(self._build_signature(manifest), encoding="utf-8")

    def _load_manifest(self) -> ProjectManifest | None:
        try:
            manifest = load_manifest(self.paths.manifest, self.slug)
        except ManifestError as error:
            self.state = ProjectState.MISCONFIGURED
            self.last_failure_detail = str(error)
            self._alerts.publish(AlertKind.PROJECT_MISCONFIGURED, str(error), self.slug)
            return None
        self.manifest = manifest
        return manifest

    async def _collect_environment(self, manifest: ProjectManifest) -> dict[str, str]:
        environment = await self._vault.materialize(self.project_id)
        missing = [name for name in manifest.required_environment if name not in environment]
        if missing:
            self._alerts.publish(
                AlertKind.PROJECT_SECRETS_MISSING,
                f"required variables are not loaded: {', '.join(missing)}",
                self.slug,
            )
        return environment

    async def _stream_child_output(self, stream: asyncio.StreamReader) -> None:
        while True:
            try:
                line = await stream.readline()
            except ValueError:
                continue
            if not line:
                break
            decoded = self._redactor.apply(
                line[:CHILD_LOG_LINE_MAX_BYTES].decode("utf-8", errors="replace").rstrip()
            )
            self.recent_output.append(decoded)
            logger.info("[%s] %s", self.slug, decoded)

    async def _interruptible_delay(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop_requested.wait(), timeout=seconds)
        except TimeoutError:
            pass

    def _should_keep_running(self) -> bool:
        return not self._stop_requested.is_set() and not self.shutdown_event.is_set()

    def _backoff_for(self, crash_count: int) -> int:
        return CRASH_BACKOFF_SECONDS[min(crash_count, len(CRASH_BACKOFF_SECONDS) - 1)]

    async def _run_supervised_lifecycle(self) -> None:
        crash_count = 0

        while self._should_keep_running():
            manifest = self._load_manifest()
            if manifest is None:
                return

            environment = await self._collect_environment(manifest)

            if self._rebuild_requested or not self._build_is_current(manifest):
                self.state = ProjectState.BUILDING
                outcome = await self._builder.build(self.paths, manifest, environment, self._stop_requested)
                self._rebuild_requested = False

                if not outcome.succeeded:
                    self.state = ProjectState.BUILD_FAILED
                    detail = outcome.output_tail[-700:].strip() or "(no output captured)"
                    self.last_failure_detail = f"{outcome.failing_step}: {detail}"
                    self._alerts.publish(
                        AlertKind.PROJECT_BUILD_FAILED,
                        f"step {outcome.failing_step!r} failed\n{detail}",
                        self.slug,
                    )
                    return

                self._record_build_stamp(manifest)

            if not self._should_keep_running():
                break

            spec = SandboxSpec(
                paths=self.paths,
                command=manifest.run_command,
                working_directory=manifest.working_directory,
                environment=environment,
                limits=manifest.resources,
                network_enabled=manifest.network_enabled,
                virtualenv_writable=False,
            )

            try:
                process = await self._launcher.spawn(spec)
            except OSError as error:
                self.state = ProjectState.CRASHED
                self.last_failure_detail = str(error)
                self._alerts.publish(AlertKind.PROJECT_CRASHED, f"failed to spawn: {error}", self.slug)
                await self._interruptible_delay(self._backoff_for(crash_count))
                crash_count += 1
                continue

            self._process = process
            self.pid = process.pid
            self.start_time = time.time()
            self.state = ProjectState.RUNNING
            self._alerts.publish(AlertKind.PROJECT_STARTED, f"running with pid {process.pid}", self.slug)

            output_task = asyncio.create_task(self._stream_child_output(process.stdout))
            return_code = await self._await_process_exit(process, manifest)
            await asyncio.gather(output_task, return_exceptions=True)

            self.pid = None
            self._process = None
            uptime_seconds = time.time() - self.start_time

            if self._stop_requested.is_set() or self.shutdown_event.is_set():
                self.state = ProjectState.STOPPED
                return

            if uptime_seconds > CRASH_COUNTER_RESET_THRESHOLD_SECONDS:
                crash_count = 0

            if return_code == 0 and manifest.restart_policy is not RestartPolicy.ALWAYS:
                self.state = ProjectState.STOPPED
                self._alerts.publish(AlertKind.PROJECT_STOPPED, "exited cleanly", self.slug)
                return

            if manifest.restart_policy is RestartPolicy.NEVER:
                self.state = ProjectState.CRASHED
                self._alerts.publish(AlertKind.PROJECT_CRASHED, f"exited with code {return_code}", self.slug)
                return

            self.state = ProjectState.CRASHED
            self.restart_count += 1
            self.last_failure_detail = f"exit code {return_code}"
            backoff_seconds = self._backoff_for(crash_count)
            self._alerts.publish(
                AlertKind.PROJECT_CRASHED,
                f"exited with code {return_code}, restarting in {backoff_seconds}s",
                self.slug,
            )
            crash_count += 1
            if crash_count == len(CRASH_BACKOFF_SECONDS):
                self._alerts.publish(
                    AlertKind.PROJECT_RESTART_LOOP,
                    f"crashed {crash_count} times in a row, backing off to {backoff_seconds}s",
                    self.slug,
                )
            await self._interruptible_delay(backoff_seconds)

        self.state = ProjectState.STOPPED
        self.pid = None

    async def _await_process_exit(
        self, process: asyncio.subprocess.Process, manifest: ProjectManifest
    ) -> int | None:
        exit_task = asyncio.create_task(process.wait())
        stop_task = asyncio.create_task(self._stop_requested.wait())
        shutdown_task = asyncio.create_task(self.shutdown_event.wait())

        _done, pending = await asyncio.wait(
            (exit_task, stop_task, shutdown_task), return_when=asyncio.FIRST_COMPLETED
        )
        for pending_task in pending:
            pending_task.cancel()

        if not exit_task.done():
            await terminate_process_tree(
                process,
                grace_seconds=manifest.stop_timeout_seconds,
                stop_signal=getattr(signal, manifest.stop_signal),
            )
        return process.returncode
