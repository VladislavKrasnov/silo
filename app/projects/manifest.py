from __future__ import annotations

import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from app.constants import (
    BUILD_TIMEOUT_CEILING_SECONDS,
    CPU_QUOTA_CEILING,
    DEFAULT_CPU_QUOTA,
    DEFAULT_MEMORY_LIMIT_MEGABYTES,
    DEFAULT_OPEN_FILE_LIMIT,
    DEFAULT_PROCESS_LIMIT,
    DEFAULT_WRITE_LIMIT_MEGABYTES,
    ENVIRONMENT_KEY_PATTERN,
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
    name: str
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

_TOP_LEVEL_TABLES: frozenset[str] = frozenset({"run", "build", "environment", "resources"})
_RUN_KEYS: frozenset[str] = frozenset(
    {"command", "kind", "restart", "stop_signal", "stop_timeout_seconds", "network", "working_directory"}
)
_BUILD_KEYS: frozenset[str] = frozenset({"steps", "timeout_seconds"})
_ENVIRONMENT_KEYS: frozenset[str] = frozenset({"required"})
_RESOURCES_KEYS: frozenset[str] = frozenset({"memory_mb", "cpu", "processes", "open_files", "write_mb"})


def _clamp(value: int | float, lo: int | float, hi: int | float) -> int | float:
    return max(lo, min(hi, value))


def _reject_unknown_keys(table: dict[str, Any], allowed: frozenset[str], table_name: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ManifestError(f"{table_name}: unknown keys {unknown}")


def _validate_command_parts(parts: tuple[str, ...], field_name: str) -> None:
    for part in parts:
        if not part.isprintable():
            raise ManifestError(f"{field_name}: argument {part!r} contains non-printable characters")

    program = parts[0]
    if PurePosixPath(program).is_absolute() or ".." in PurePosixPath(program).parts:
        raise ManifestError(f"{field_name}: program name {program!r} must be a relative, non-traversing path")


def _parse_command(raw: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw or not all(isinstance(part, str) for part in raw):
        raise ManifestError(f"{field_name}: expected a non-empty array of strings")
    parts = tuple(raw)
    _validate_command_parts(parts, field_name)
    return parts


def _parse_build_steps(raw: Any) -> tuple[tuple[str, ...], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ManifestError("build.steps: expected a list")
    return tuple(_parse_command(step, f"build.steps[{i}]") for i, step in enumerate(raw))


def _parse_working_directory(raw: Any) -> str:
    if not isinstance(raw, str):
        raise ManifestError("run.working_directory: expected a string")
    normalized = raw.strip().strip("/")
    if normalized in ("", "."):
        return ""
    if PurePosixPath(normalized).is_absolute() or ".." in PurePosixPath(normalized).parts:
        raise ManifestError(f"run.working_directory: {raw!r} escapes the workspace")
    return normalized


def _parse_required_environment(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(key, str) for key in raw):
        raise ManifestError("environment.required: expected a list of strings")
    for name in raw:
        if not ENVIRONMENT_KEY_PATTERN.match(name):
            raise ManifestError(f"environment.required: invalid variable name {name!r}")
    return tuple(raw)


def _parse_resources(raw: dict[str, Any]) -> ResourceLimits:
    _reject_unknown_keys(raw, _RESOURCES_KEYS, "resources")

    def _int(key: str, default: int, ceiling: int) -> int:
        val = raw.get(key, default)
        if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
            raise ManifestError(f"resources.{key}: expected a positive integer, got {val!r}")
        return int(_clamp(val, 1, ceiling))

    def _float(key: str, default: float, ceiling: float) -> float:
        val = raw.get(key, default)
        if not isinstance(val, (int, float)) or isinstance(val, bool) or val <= 0:
            raise ManifestError(f"resources.{key}: expected a positive number, got {val!r}")
        return float(_clamp(val, 0.01, ceiling))

    return ResourceLimits(
        memory_megabytes=_int("memory_mb", DEFAULT_MEMORY_LIMIT_MEGABYTES, MEMORY_LIMIT_CEILING_MEGABYTES),
        cpu_quota=_float("cpu", DEFAULT_CPU_QUOTA, CPU_QUOTA_CEILING),
        processes_max=_int("processes", DEFAULT_PROCESS_LIMIT, PROCESS_LIMIT_CEILING),
        open_files_max=_int("open_files", DEFAULT_OPEN_FILE_LIMIT, OPEN_FILE_LIMIT_CEILING),
        write_limit_megabytes=_int("write_mb", DEFAULT_WRITE_LIMIT_MEGABYTES, WRITE_LIMIT_CEILING_MEGABYTES),
    )


def parse_manifest(document: dict[str, Any], project_name: str) -> ProjectManifest:
    unknown_tables = sorted(set(document) - _TOP_LEVEL_TABLES)
    if unknown_tables:
        raise ManifestError(f"unknown top-level tables: {unknown_tables}")

    run = document.get("run", {})
    if not isinstance(run, dict):
        raise ManifestError("run: expected a table")
    _reject_unknown_keys(run, _RUN_KEYS, "run")

    build = document.get("build", {})
    if not isinstance(build, dict):
        raise ManifestError("build: expected a table")
    _reject_unknown_keys(build, _BUILD_KEYS, "build")

    environment = document.get("environment", {})
    if not isinstance(environment, dict):
        raise ManifestError("environment: expected a table")
    _reject_unknown_keys(environment, _ENVIRONMENT_KEYS, "environment")

    raw_kind = run.get("kind", "python")
    try:
        runtime_kind = RuntimeKind(str(raw_kind).lower())
    except ValueError:
        raise ManifestError(f"run.kind: unknown value {raw_kind!r}") from None

    raw_restart = run.get("restart", RestartPolicy.ON_FAILURE.value)
    try:
        restart_policy = RestartPolicy(str(raw_restart).lower())
    except ValueError:
        raise ManifestError(f"run.restart: unknown value {raw_restart!r}") from None

    stop_signal: str = run.get("stop_signal", "SIGTERM")
    if stop_signal not in _VALID_STOP_SIGNALS:
        raise ManifestError(f"run.stop_signal: unknown value {stop_signal!r}")

    raw_stop_timeout = run.get("stop_timeout_seconds", 10.0)
    is_numeric = isinstance(raw_stop_timeout, (int, float)) and not isinstance(raw_stop_timeout, bool)
    if not is_numeric or raw_stop_timeout < 0:
        raise ManifestError("run.stop_timeout_seconds: expected a non-negative number")

    network_enabled: bool = bool(run.get("network", True))
    working_directory = _parse_working_directory(run.get("working_directory", ""))

    raw_build_timeout = build.get("timeout_seconds", 300)
    build_timeout_is_int = isinstance(raw_build_timeout, int) and not isinstance(raw_build_timeout, bool)
    if not build_timeout_is_int or raw_build_timeout <= 0:
        raise ManifestError("build.timeout_seconds: expected a positive integer")

    return ProjectManifest(
        name=project_name,
        runtime_kind=runtime_kind,
        run_command=_parse_command(run.get("command"), "run.command"),
        build_steps=_parse_build_steps(build.get("steps")),
        working_directory=working_directory,
        restart_policy=restart_policy,
        stop_signal=stop_signal,
        stop_timeout_seconds=float(raw_stop_timeout),
        build_timeout_seconds=int(_clamp(raw_build_timeout, 1, BUILD_TIMEOUT_CEILING_SECONDS)),
        network_enabled=network_enabled,
        required_environment=_parse_required_environment(environment.get("required", [])),
        resources=_parse_resources(document.get("resources", {})),
    )


def load_manifest(path: Path, project_name: str) -> ProjectManifest:
    try:
        document: dict[str, Any] = tomllib.loads(path.read_bytes().decode("utf-8", errors="replace"))
    except OSError as exc:
        raise ManifestError(f"could not read {path.name}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"TOML parse error: {exc}") from exc

    return parse_manifest(document, project_name)
