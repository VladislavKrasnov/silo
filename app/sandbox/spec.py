from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.projects.layout import ProjectPaths
from app.projects.manifest import ResourceLimits


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    paths: ProjectPaths
    command: tuple[str, ...]
    working_directory: str
    environment: dict[str, str] = field(default_factory=dict)
    limits: ResourceLimits | None = None
    network_enabled: bool = True
    virtualenv_writable: bool = False


@dataclass(frozen=True, slots=True)
class Invocation:
    argv: tuple[str, ...]
    environment: dict[str, str]
    working_directory: Path
    applies_resource_limits: bool
