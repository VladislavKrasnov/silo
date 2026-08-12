from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from dataclasses import dataclass

from app.constants import BUILD_STEP_OUTPUT_RETAINED_BYTES
from app.projects.layout import ProjectPaths
from app.sandbox.backends import (
    BubblewrapIsolationBackend,
    DockerIsolationBackend,
    IsolationBackend,
    NativeIsolationBackend,
)
from app.sandbox.limits import build_process_hardening_hook
from app.sandbox.spec import SandboxSpec
from app.security.redaction import SecretRedactor

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CommandResult:
    exit_code: int
    output: str
    timed_out: bool

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class SandboxLauncher:
    def __init__(self, requested_backend: str, container_image: str):
        self.requested_backend = requested_backend
        self._candidates: tuple[IsolationBackend, ...] = (
            BubblewrapIsolationBackend(),
            DockerIsolationBackend(container_image),
            NativeIsolationBackend(),
        )
        self._backend: IsolationBackend = self._candidates[-1]

    @property
    def backend(self) -> IsolationBackend:
        return self._backend

    async def select_backend(self) -> IsolationBackend:
        ordered = (
            self._candidates
            if self.requested_backend == "auto"
            else tuple(backend for backend in self._candidates if backend.name == self.requested_backend)
        )
        for candidate in ordered or self._candidates:
            if await candidate.probe():
                self._backend = candidate
                break

        if self._backend.provides_filesystem_isolation:
            logger.info("isolation backend selected: %s", self._backend.name)
        else:
            logger.warning(
                "isolation backend selected: native. Filesystem isolation between projects is NOT enforced. "
                "Install bubblewrap or expose a Docker daemon for container-grade isolation."
            )
        return self._backend

    def virtualenv_creation_spec(self, paths: ProjectPaths) -> SandboxSpec:
        return SandboxSpec(
            paths=paths,
            command=self._backend.virtualenv_creation_command(paths),
            working_directory=".",
            network_enabled=False,
            virtualenv_writable=True,
        )

    async def spawn(self, spec: SandboxSpec) -> asyncio.subprocess.Process:
        await self._backend.discard_residue(spec.paths.slug)
        invocation = self._backend.build_invocation(spec)
        hardening_hook = (
            build_process_hardening_hook(spec.limits) if invocation.applies_resource_limits else None
        )
        return await asyncio.create_subprocess_exec(
            *invocation.argv,
            cwd=str(invocation.working_directory),
            env=invocation.environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            preexec_fn=hardening_hook,
            start_new_session=hardening_hook is None and sys.platform != "win32",
        )

    async def run_to_completion(
        self,
        spec: SandboxSpec,
        timeout_seconds: int,
        redactor: SecretRedactor | None = None,
        cancellation_event: asyncio.Event | None = None,
    ) -> CommandResult:
        process = await self.spawn(spec)
        assert process.stdout is not None

        collected = bytearray()

        async def drain_output() -> None:
            while chunk := await process.stdout.read(65536):
                collected.extend(chunk)
                del collected[:-BUILD_STEP_OUTPUT_RETAINED_BYTES]

        drain_task = asyncio.create_task(drain_output())
        try:
            aborted = await self._await_bounded_exit(process, timeout_seconds, cancellation_event)
        finally:
            drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await drain_task

        if aborted:
            await terminate_process_tree(process, grace_seconds=3.0)
            await self._backend.discard_residue(spec.paths.slug)

        output = collected.decode("utf-8", errors="replace")
        return CommandResult(
            exit_code=process.returncode if process.returncode is not None else -1,
            output=redactor.apply(output) if redactor else output,
            timed_out=aborted,
        )

    @staticmethod
    async def _await_bounded_exit(
        process: asyncio.subprocess.Process, timeout_seconds: int, cancellation_event: asyncio.Event | None
    ) -> bool:
        if cancellation_event is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
                return False
            except TimeoutError:
                return True

        exit_task = asyncio.create_task(process.wait())
        cancellation_task = asyncio.create_task(cancellation_event.wait())
        try:
            done, pending = await asyncio.wait(
                (exit_task, cancellation_task),
                timeout=timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (exit_task, cancellation_task):
                task.cancel()
        return exit_task not in done


async def terminate_process_tree(
    process: asyncio.subprocess.Process, grace_seconds: float, stop_signal: int = signal.SIGTERM
) -> None:
    if process.returncode is not None:
        return

    _signal_process_group(process, stop_signal)
    try:
        await asyncio.wait_for(process.wait(), timeout=grace_seconds)
        return
    except TimeoutError:
        pass

    _signal_process_group(process, signal.SIGKILL)
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=grace_seconds)


def _signal_process_group(process: asyncio.subprocess.Process, signal_number: int) -> None:
    if sys.platform == "win32":
        with contextlib.suppress(ProcessLookupError, OSError):
            process.kill()
        return
    try:
        os.killpg(os.getpgid(process.pid), signal_number)
    except (ProcessLookupError, PermissionError, OSError):
        with contextlib.suppress(ProcessLookupError):
            process.send_signal(signal_number)
