from __future__ import annotations

import shlex
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.constants import (
    BUILD_TIMEOUT_CEILING_SECONDS,
    CPU_QUOTA_CEILING,
    DEFAULT_CPU_QUOTA,
    DEFAULT_MEMORY_LIMIT_MEGABYTES,
    DEFAULT_OPEN_FILE_LIMIT,
    DEFAULT_PROCESS_LIMIT,
    DEFAULT_WRITE_LIMIT_MEGABYTES,
    MEMORY_LIMIT_CEILING_MEGABYTES,
    OPEN_FILE_LIMIT_CEILING,
    PROCESS_LIMIT_CEILING,
    WRITE_LIMIT_CEILING_MEGABYTES,
)


class ManifestError(ValueError):
    pass


class RuntimeKind(StrEnum):
    PYTHON = "python"
    NODE = "node"
    SHELL = "shell"


class RestartPolicy(StrEnum):
    ALWAYS = "always"
    ON_FAILURE = "on-failure"
    NEVER = "never"


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    memory_megabytes: int
    cpu_quota: float
    processes_max: int
    open_files_max: int
    write_limit_megabytes: int


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    display_name: str
    runtime_kind: RuntimeKind
    run_command: tuple[str, ...]
    build_steps: tuple[tuple[str, ...], ...]
    working_directory: str
    restart_policy: RestartPolicy
    stop_signal: str
    stop_timeout_seconds: float
    build_timeout_seconds: int
    network_enabled: bool
    required_environment: tuple[str, ...]
    resources: ResourceLimits


_VALID_STOP_SIGNALS: frozenset[str] = frozenset(
    {"SIGTERM", "SIGINT", "SIGQUIT", "SIGHUP", "SIGKILL", "SIGUSR1", "SIGUSR2"}
)


def _clamp(value: int | float, lo: int | float, hi: int | float) -> int | float:
    return max(lo, min(hi, value))


def _parse_command(raw: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(raw, str):
        parts = shlex.split(raw)
    elif isinstance(raw, list) and all(isinstance(p, str) for p in raw):
        parts = raw
    else:
        raise ManifestError(f"{field_name}: expected a string or list of strings")
    if not parts:
        raise ManifestError(f"{field_name}: command must not be empty")
    return tuple(parts)


def _parse_build_steps(raw: Any) -> tuple[tuple[str, ...], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ManifestError("build.steps: expected a list")
    return tuple(_parse_command(step, f"build.steps[{i}]") for i, step in enumerate(raw))


def _parse_resources(raw: dict[str, Any]) -> ResourceLimits:
    def _int(key: str, default: int, ceiling: int) -> int:
        val = raw.get(key, default)
        if not isinstance(val, int) or val <= 0:
            raise ManifestError(f"resources.{key}: expected a positive integer, got {val!r}")
        return int(_clamp(val, 1, ceiling))

    def _float(key: str, default: float, ceiling: float) -> float:
        val = raw.get(key, default)
        if not isinstance(val, (int, float)) or val <= 0:
            raise ManifestError(f"resources.{key}: expected a positive number, got {val!r}")
        return float(_clamp(val, 0.01, ceiling))

    return ResourceLimits(
        memory_megabytes=_int("memory_mb", DEFAULT_MEMORY_LIMIT_MEGABYTES, MEMORY_LIMIT_CEILING_MEGABYTES),
        cpu_quota=_float("cpu", DEFAULT_CPU_QUOTA, CPU_QUOTA_CEILING),
        processes_max=_int("processes", DEFAULT_PROCESS_LIMIT, PROCESS_LIMIT_CEILING),
        open_files_max=_int("open_files", DEFAULT_OPEN_FILE_LIMIT, OPEN_FILE_LIMIT_CEILING),
        write_limit_megabytes=_int("write_mb", DEFAULT_WRITE_LIMIT_MEGABYTES, WRITE_LIMIT_CEILING_MEGABYTES),
    )


def load_manifest(path: Path, project_name: str) -> ProjectManifest:
    try:
        data: dict[str, Any] = tomllib.loads(path.read_bytes().decode("utf-8", errors="replace"))
    except OSError as exc:
        raise ManifestError(f"could not read {path.name}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"TOML parse error: {exc}") from exc

    project = data.get("project", {})
    display_name: str = project.get("name", project_name)
    if not isinstance(display_name, str) or not display_name.strip():
        raise ManifestError("project.name: must be a non-empty string")

    runtime = data.get("runtime", {})

    raw_kind = runtime.get("kind", "python")
    try:
        runtime_kind = RuntimeKind(str(raw_kind).lower())
    except ValueError:
        raise ManifestError(f"runtime.kind: unknown value {raw_kind!r}")

    raw_restart = runtime.get("restart", RestartPolicy.ON_FAILURE.value)
    try:
        restart_policy = RestartPolicy(str(raw_restart).lower())
    except ValueError:
        raise ManifestError(f"runtime.restart: unknown value {raw_restart!r}")

    stop_signal: str = runtime.get("stop_signal", "SIGTERM")
    if stop_signal not in _VALID_STOP_SIGNALS:
        raise ManifestError(f"runtime.stop_signal: unknown value {stop_signal!r}")

    raw_stop_timeout = runtime.get("stop_timeout_seconds", 10.0)
    if not isinstance(raw_stop_timeout, (int, float)) or raw_stop_timeout < 0:
        raise ManifestError("runtime.stop_timeout_seconds: expected a non-negative number")

    network_enabled: bool = bool(runtime.get("network", True))

    raw_working_dir = runtime.get("working_directory", "")
    if not isinstance(raw_working_dir, str):
        raise ManifestError("runtime.working_directory: expected a string")

    build = data.get("build", {})
    raw_build_timeout = build.get("timeout_seconds", 300)
    if not isinstance(raw_build_timeout, int) or raw_build_timeout <= 0:
        raise ManifestError("build.timeout_seconds: expected a positive integer")

    env = data.get("environment", {})
    raw_required = env.get("required", [])
    if not isinstance(raw_required, list) or not all(isinstance(k, str) for k in raw_required):
        raise ManifestError("environment.required: expected a list of strings")

    return ProjectManifest(
        display_name=display_name,
        runtime_kind=runtime_kind,
        run_command=_parse_command(runtime.get("run", ""), "runtime.run"),
        build_steps=_parse_build_steps(build.get("steps")),
        working_directory=raw_working_dir.strip().strip("/"),
        restart_policy=restart_policy,
        stop_signal=stop_signal,
        stop_timeout_seconds=float(raw_stop_timeout),
        build_timeout_seconds=int(_clamp(raw_build_timeout, 1, BUILD_TIMEOUT_CEILING_SECONDS)),
        network_enabled=network_enabled,
        required_environment=tuple(raw_required),
        resources=_parse_resources(data.get("resources", {})),
    )
