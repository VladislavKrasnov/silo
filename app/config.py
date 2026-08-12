from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT_DIR: Path = PACKAGE_DIR.parent

_ISOLATION_BACKEND_CHOICES: frozenset[str] = frozenset({"auto", "bubblewrap", "docker", "native"})


def parse_admin_identifiers(raw_value: str) -> frozenset[int]:
    return frozenset(
        int(token.strip())
        for token in raw_value.replace(";", ",").split(",")
        if token.strip().lstrip("-").isdigit()
    )


def _resolve_directory(raw_value: str | None, fallback: Path) -> Path:
    return Path(raw_value).expanduser().resolve() if raw_value else fallback


@dataclass(frozen=True, slots=True)
class AppConfig:
    master_bot_token: str | None
    admin_ids: frozenset[int]
    projects_root_dir: Path
    state_dir: Path
    database_path: Path
    master_key_path: Path
    isolation_backend: str
    container_image: str
    autostart_projects: bool
    github_oauth_client_id: str | None

    @classmethod
    def from_environment(cls) -> AppConfig:
        load_dotenv(PROJECT_ROOT_DIR / ".env")

        projects_root_dir = _resolve_directory(os.getenv("PROJECTS_ROOT_DIR"), PROJECT_ROOT_DIR / "projects")
        state_dir = _resolve_directory(os.getenv("STATE_DIR"), PROJECT_ROOT_DIR / "state")
        requested_backend = (os.getenv("ISOLATION_BACKEND") or "auto").strip().lower()

        return cls(
            master_bot_token=(os.getenv("MASTER_BOT_TOKEN") or "").strip() or None,
            admin_ids=parse_admin_identifiers(os.getenv("ADMIN_IDS", "")),
            projects_root_dir=projects_root_dir,
            state_dir=state_dir,
            database_path=_resolve_directory(os.getenv("DATABASE_PATH"), state_dir / "orchestrator.db"),
            master_key_path=_resolve_directory(os.getenv("MASTER_KEY_PATH"), state_dir / "master.key"),
            isolation_backend=(
                requested_backend if requested_backend in _ISOLATION_BACKEND_CHOICES else "auto"
            ),
            container_image=(os.getenv("CONTAINER_IMAGE") or "python:3.12-slim").strip(),
            autostart_projects=(os.getenv("AUTOSTART_PROJECTS") or "true").strip().lower()
            not in {"0", "false", "no", "off"},
            github_oauth_client_id=(os.getenv("GITHUB_OAUTH_CLIENT_ID") or "").strip() or None,
        )

    def ensure_directories(self) -> None:
        self.projects_root_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.state_dir, 0o700)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
