from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.constants import (
    LOG_DIRECTORY_NAME,
    MANIFEST_FILENAME,
    PROJECT_SLUG_PATTERN,
    SCRATCH_DIRECTORY_NAME,
    VIRTUALENV_DIRECTORY_NAME,
    WORKSPACE_DIRECTORY_NAME,
)


class ProjectSlugError(ValueError):
    pass


class PathContainmentError(ValueError):
    pass


def validate_slug(raw: str) -> str:
    if not PROJECT_SLUG_PATTERN.match(raw):
        raise ProjectSlugError(f"invalid project slug {raw!r}: must match {PROJECT_SLUG_PATTERN.pattern}")
    return raw


def normalize_slug(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", raw.strip().lower()).strip("-")
    return validate_slug(slug)


def resolve_within(base: Path, relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise PathContainmentError(f"{relative!r} is an absolute path")

    resolved_base = base.resolve()
    candidate = (base / relative_path).resolve()
    try:
        candidate.relative_to(resolved_base)
    except ValueError:
        raise PathContainmentError(f"{relative!r} escapes {base}") from None
    return candidate


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    slug: str
    root: Path

    @property
    def workspace(self) -> Path:
        return self.root / WORKSPACE_DIRECTORY_NAME

    @property
    def virtualenv(self) -> Path:
        return self.root / VIRTUALENV_DIRECTORY_NAME

    @property
    def scratch(self) -> Path:
        return self.root / SCRATCH_DIRECTORY_NAME

    @property
    def logs(self) -> Path:
        return self.root / LOG_DIRECTORY_NAME

    @property
    def manifest(self) -> Path:
        return self.workspace / MANIFEST_FILENAME


class ProjectsLayout:
    def __init__(self, projects_root_dir: Path) -> None:
        self.projects_root_dir = projects_root_dir

    def prepare_root(self) -> None:
        self.projects_root_dir.mkdir(parents=True, exist_ok=True)

    def paths_for(self, slug: str) -> ProjectPaths:
        return ProjectPaths(slug=slug, root=self.projects_root_dir / slug)

    def exists(self, slug: str) -> bool:
        return (self.projects_root_dir / slug).is_dir()

    def create(self, slug: str) -> ProjectPaths:
        paths = self.paths_for(slug)
        paths.root.mkdir(parents=True, exist_ok=False)
        paths.root.chmod(0o700)
        for directory in (paths.workspace, paths.virtualenv, paths.scratch, paths.logs):
            directory.mkdir(parents=True, exist_ok=True)
        return paths

    def discovered_slugs(self) -> list[str]:
        if not self.projects_root_dir.is_dir():
            return []
        return sorted(
            entry.name
            for entry in self.projects_root_dir.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )

    def destroy(self, slug: str) -> None:
        shutil.rmtree(self.projects_root_dir / slug, ignore_errors=True)
