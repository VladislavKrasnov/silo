from __future__ import annotations

import asyncio
import os
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from app.constants import (
    SANDBOX_SCRATCH_MOUNT,
    SANDBOX_VIRTUALENV_MOUNT,
    SANDBOX_WORKSPACE_MOUNT,
)
from app.projects.layout import ProjectPaths
from app.sandbox.environment import build_base_environment, sanitize_project_environment
from app.sandbox.spec import Invocation, SandboxSpec

_PROBE_TIMEOUT_SECONDS: float = 10.0
_READ_ONLY_SYSTEM_PATHS: tuple[str, ...] = ("/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64")
_READ_ONLY_RESOLUTION_PATHS: tuple[str, ...] = (
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/nsswitch.conf",
    "/etc/ssl",
    "/etc/pki",
    "/etc/ca-certificates",
    "/etc/ca-certificates.conf",
)


async def _probe_command(argv: tuple[str, ...]) -> bool:
    if shutil.which(argv[0]) is None:
        return False
    try:
        process = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
    except OSError:
        return False
    try:
        return await asyncio.wait_for(process.wait(), timeout=_PROBE_TIMEOUT_SECONDS) == 0
    except TimeoutError:
        process.kill()
        return False


class IsolationBackend(ABC):
    name: str
    provides_filesystem_isolation: bool

    @abstractmethod
    async def probe(self) -> bool: ...

    @abstractmethod
    def build_invocation(self, spec: SandboxSpec) -> Invocation: ...

    def virtualenv_creation_command(self, paths: ProjectPaths) -> tuple[str, ...]:
        return ("python3", "-m", "venv", SANDBOX_VIRTUALENV_MOUNT)

    async def discard_residue(self, project_slug: str) -> None:
        return None


class BubblewrapIsolationBackend(IsolationBackend):
    name = "bubblewrap"
    provides_filesystem_isolation = True

    async def probe(self) -> bool:
        return await _probe_command(("bwrap", "--version"))

    def build_invocation(self, spec: SandboxSpec) -> Invocation:
        environment = build_base_environment(
            virtualenv_root=SANDBOX_VIRTUALENV_MOUNT,
            virtualenv_bin=f"{SANDBOX_VIRTUALENV_MOUNT}/bin",
            home_directory=SANDBOX_SCRATCH_MOUNT,
            project_slug=spec.paths.slug,
        )
        environment.update(sanitize_project_environment(spec.environment))

        argv: list[str] = [
            "bwrap",
            "--die-with-parent",
            "--new-session",
            "--unshare-user",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--unshare-cgroup-try",
            "--hostname",
            spec.paths.slug,
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/run",
            "--tmpfs",
            "/var",
            "--tmpfs",
            "/etc",
        ]

        if not spec.network_enabled:
            argv.append("--unshare-net")

        for system_path in _READ_ONLY_SYSTEM_PATHS:
            if Path(system_path).exists():
                argv += ["--ro-bind", system_path, system_path]
        for resolution_path in _READ_ONLY_RESOLUTION_PATHS:
            if Path(resolution_path).exists():
                argv += ["--ro-bind-try", resolution_path, resolution_path]

        virtualenv_bind = "--bind" if spec.virtualenv_writable else "--ro-bind"
        argv += [
            "--bind",
            str(spec.paths.workspace),
            SANDBOX_WORKSPACE_MOUNT,
            virtualenv_bind,
            str(spec.paths.virtualenv),
            SANDBOX_VIRTUALENV_MOUNT,
            "--bind",
            str(spec.paths.scratch),
            SANDBOX_SCRATCH_MOUNT,
            "--chdir",
            f"{SANDBOX_WORKSPACE_MOUNT}/{spec.working_directory}".rstrip("/."),
            "--",
            *spec.command,
        ]

        return Invocation(
            argv=tuple(argv),
            environment=environment,
            working_directory=spec.paths.root,
            applies_resource_limits=True,
        )


class DockerIsolationBackend(IsolationBackend):
    name = "docker"
    provides_filesystem_isolation = True

    def __init__(self, container_image: str):
        self.container_image = container_image

    async def probe(self) -> bool:
        return await _probe_command(("docker", "version", "--format", "{{.Server.Version}}"))

    @staticmethod
    def container_name(project_slug: str) -> str:
        return f"fleet-{project_slug}"

    async def discard_residue(self, project_slug: str) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                "docker",
                "rm",
                "--force",
                self.container_name(project_slug),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return
        await process.wait()

    def build_invocation(self, spec: SandboxSpec) -> Invocation:
        base_environment = build_base_environment(
            virtualenv_root=SANDBOX_VIRTUALENV_MOUNT,
            virtualenv_bin=f"{SANDBOX_VIRTUALENV_MOUNT}/bin",
            home_directory=SANDBOX_SCRATCH_MOUNT,
            project_slug=spec.paths.slug,
        )
        project_environment = sanitize_project_environment(spec.environment)

        argv: list[str] = [
            "docker",
            "run",
            "--rm",
            "--init",
            "--name",
            self.container_name(spec.paths.slug),
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--network",
            "bridge" if spec.network_enabled else "none",
            "--hostname",
            spec.paths.slug,
            "--workdir",
            f"{SANDBOX_WORKSPACE_MOUNT}/{spec.working_directory}".rstrip("/."),
            "--volume",
            f"{spec.paths.workspace}:{SANDBOX_WORKSPACE_MOUNT}:rw",
            "--volume",
            f"{spec.paths.virtualenv}:{SANDBOX_VIRTUALENV_MOUNT}:"
            f"{'rw' if spec.virtualenv_writable else 'ro'}",
            "--volume",
            f"{spec.paths.scratch}:{SANDBOX_SCRATCH_MOUNT}:rw",
        ]

        if spec.limits is not None:
            argv += [
                "--memory",
                f"{spec.limits.memory_megabytes}m",
                "--memory-swap",
                f"{spec.limits.memory_megabytes}m",
                "--cpus",
                f"{spec.limits.cpu_quota:.2f}",
                "--pids-limit",
                str(spec.limits.processes_max),
                "--ulimit",
                f"nofile={spec.limits.open_files_max}:{spec.limits.open_files_max}",
            ]

        for key, value in base_environment.items():
            argv += ["--env", f"{key}={value}"]
        for key in project_environment:
            argv += ["--env", key]

        argv += [self.container_image, *spec.command]

        forwarded_environment = {
            key: os.environ[key]
            for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "PATH", "HOME")
            if key in os.environ
        }
        forwarded_environment.update(project_environment)

        return Invocation(
            argv=tuple(argv),
            environment=forwarded_environment,
            working_directory=spec.paths.root,
            applies_resource_limits=False,
        )


class NativeIsolationBackend(IsolationBackend):
    name = "native"
    provides_filesystem_isolation = False

    async def probe(self) -> bool:
        return True

    def virtualenv_creation_command(self, paths: ProjectPaths) -> tuple[str, ...]:
        return (sys.executable, "-m", "venv", str(paths.virtualenv))

    def build_invocation(self, spec: SandboxSpec) -> Invocation:
        virtualenv_bin = spec.paths.virtualenv / ("Scripts" if os.name == "nt" else "bin")
        environment = build_base_environment(
            virtualenv_root=str(spec.paths.virtualenv),
            virtualenv_bin=str(virtualenv_bin),
            home_directory=str(spec.paths.scratch),
            project_slug=spec.paths.slug,
        )
        environment.update(sanitize_project_environment(spec.environment))

        executable, *arguments = spec.command
        resolved_executable = shutil.which(executable, path=environment["PATH"]) or executable

        return Invocation(
            argv=(resolved_executable, *arguments),
            environment=environment,
            working_directory=spec.paths.workspace / spec.working_directory,
            applies_resource_limits=True,
        )
