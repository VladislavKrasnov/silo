from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.projects.layout import ProjectPaths
from app.projects.manifest import ProjectManifest, RuntimeKind
from app.sandbox.launcher import SandboxLauncher
from app.sandbox.spec import SandboxSpec
from app.security.redaction import SecretRedactor

logger = logging.getLogger(__name__)

BUILD_LOG_FILENAME: str = "build.log"


@dataclass(frozen=True, slots=True)
class BuildOutcome:
    succeeded: bool
    failing_step: str | None
    output_tail: str


class ProjectBuilder:
    def __init__(self, launcher: SandboxLauncher, redactor: SecretRedactor):
        self._launcher = launcher
        self._redactor = redactor

    def _append_build_log(self, paths: ProjectPaths, heading: str, body: str) -> None:
        log_path = paths.logs / BUILD_LOG_FILENAME
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {heading} ===\n{body}\n")

    async def _provision_virtualenv(
        self, paths: ProjectPaths, manifest: ProjectManifest, cancellation_event: asyncio.Event | None
    ) -> BuildOutcome | None:
        if manifest.runtime_kind is not RuntimeKind.PYTHON:
            return None
        if (paths.virtualenv / "bin" / "python").exists() or (
            paths.virtualenv / "Scripts" / "python.exe"
        ).exists():
            return None

        result = await self._launcher.run_to_completion(
            self._launcher.virtualenv_creation_spec(paths),
            timeout_seconds=300,
            redactor=self._redactor,
            cancellation_event=cancellation_event,
        )
        self._append_build_log(paths, "virtualenv", result.output)
        if result.succeeded:
            return None
        return BuildOutcome(
            succeeded=False, failing_step="create virtualenv", output_tail=result.output[-1024:]
        )

    async def build(
        self,
        paths: ProjectPaths,
        manifest: ProjectManifest,
        environment: dict[str, str],
        cancellation_event: asyncio.Event | None = None,
    ) -> BuildOutcome:
        provisioning_failure = await self._provision_virtualenv(paths, manifest, cancellation_event)
        if provisioning_failure is not None:
            return provisioning_failure

        for step in manifest.build_steps:
            spec = SandboxSpec(
                paths=paths,
                command=step,
                working_directory=manifest.working_directory,
                environment=environment,
                limits=None,
                network_enabled=True,
                virtualenv_writable=True,
            )
            result = await self._launcher.run_to_completion(
                spec,
                timeout_seconds=manifest.build_timeout_seconds,
                redactor=self._redactor,
                cancellation_event=cancellation_event,
            )
            rendered_step = " ".join(step)
            self._append_build_log(paths, rendered_step, result.output)

            if not result.succeeded:
                reason = "timed out" if result.timed_out else f"exited with code {result.exit_code}"
                logger.warning("build step %r for %s %s", rendered_step, paths.slug, reason)
                return BuildOutcome(
                    succeeded=False, failing_step=rendered_step, output_tail=result.output[-1024:]
                )

        return BuildOutcome(succeeded=True, failing_step=None, output_tail="")

    @staticmethod
    def build_log_path(paths: ProjectPaths) -> Path:
        return paths.logs / BUILD_LOG_FILENAME
