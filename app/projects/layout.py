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


def normalize_slug(raw: str) -> str:
    slug = re.sub(r"[ .]+", "-", raw.strip().lower())
    if not PROJECT_SLUG_PATTERN.match(slug):
        raise ProjectSlugError(
            f"invalid project name {raw!r}: must match {PROJECT_SLUG_PATTERN.pattern}"
        )
    return slug


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

    def destroy(self, slug: str) -> None:
        shutil.rmtree(self.projects_root_dir / slug, ignore_errors=True)
