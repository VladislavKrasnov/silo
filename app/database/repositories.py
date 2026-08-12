from __future__ import annotations

import time
from dataclasses import dataclass

from app.constants import EVENT_RETENTION_LIMIT
from app.database.engine import Database


@dataclass(frozen=True, slots=True)
class GitHubAccountRecord:
    id: int
    label: str
    username: str
    token_ciphertext: bytes
    created_at: float


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    id: int
    slug: str
    display_name: str
    source_kind: str
    source_reference: str
    git_reference: str | None
    github_account_id: int | None
    autostart: bool
    created_at: float
    updated_at: float


@dataclass(frozen=True, slots=True)
class SecretRecord:
    name: str
    value_ciphertext: bytes
    updated_at: float


@dataclass(frozen=True, slots=True)
class AlertRuleRecord:
    kind: str
    enabled: bool
    throttle_seconds: int


@dataclass(frozen=True, slots=True)
class EventRecord:
    id: int
    kind: str
    severity: str
    project_slug: str | None
    message: str
    created_at: float


class GitHubAccountRepository:
    def __init__(self, database: Database):
        self._database = database

    async def add(self, label: str, username: str, token_ciphertext: bytes) -> int:
        return await self._database.execute_returning_id(
            "INSERT INTO github_accounts (label, username, token_ciphertext, created_at) VALUES (?, ?, ?, ?)",
            (label, username, token_ciphertext, time.time()),
        )

    async def list_all(self) -> list[GitHubAccountRecord]:
        rows = await self._database.fetch_all(
            "SELECT id, label, username, token_ciphertext, created_at FROM github_accounts ORDER BY label"
        )
        return [GitHubAccountRecord(**dict(row)) for row in rows]

    async def get(self, account_id: int) -> GitHubAccountRecord | None:
        row = await self._database.fetch_one(
            "SELECT id, label, username, token_ciphertext, created_at FROM github_accounts WHERE id = ?",
            (account_id,),
        )
        return GitHubAccountRecord(**dict(row)) if row else None

    async def delete(self, account_id: int) -> bool:
        return await self._database.execute("DELETE FROM github_accounts WHERE id = ?", (account_id,)) > 0


class ProjectRepository:
    def __init__(self, database: Database):
        self._database = database

    async def add(
        self,
        slug: str,
        display_name: str,
        source_kind: str,
        source_reference: str,
        git_reference: str | None,
        github_account_id: int | None,
    ) -> int:
        moment = time.time()
        return await self._database.execute_returning_id(
            "INSERT INTO projects "
            "(slug, display_name, source_kind, source_reference, git_reference, github_account_id, "
            "autostart, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (
                slug,
                display_name,
                source_kind,
                source_reference,
                git_reference,
                github_account_id,
                moment,
                moment,
            ),
        )

    async def list_all(self) -> list[ProjectRecord]:
        rows = await self._database.fetch_all(
            "SELECT id, slug, display_name, source_kind, source_reference, git_reference, "
            "github_account_id, autostart, created_at, updated_at FROM projects ORDER BY slug"
        )
        return [self._to_record(dict(row)) for row in rows]

    async def get_by_slug(self, slug: str) -> ProjectRecord | None:
        row = await self._database.fetch_one(
            "SELECT id, slug, display_name, source_kind, source_reference, git_reference, "
            "github_account_id, autostart, created_at, updated_at FROM projects WHERE slug = ?",
            (slug,),
        )
        return self._to_record(dict(row)) if row else None

    async def set_autostart(self, slug: str, autostart: bool) -> None:
        await self._database.execute(
            "UPDATE projects SET autostart = ?, updated_at = ? WHERE slug = ?",
            (int(autostart), time.time(), slug),
        )

    async def touch(self, slug: str) -> None:
        await self._database.execute("UPDATE projects SET updated_at = ? WHERE slug = ?", (time.time(), slug))

    async def delete(self, slug: str) -> bool:
        return await self._database.execute("DELETE FROM projects WHERE slug = ?", (slug,)) > 0

    @staticmethod
    def _to_record(row: dict) -> ProjectRecord:
        row["autostart"] = bool(row["autostart"])
        return ProjectRecord(**row)


class SecretRepository:
    def __init__(self, database: Database):
        self._database = database

    async def replace_all(self, project_id: int, encrypted_entries: dict[str, bytes]) -> None:
        moment = time.time()
        async with self._database.transaction() as connection:
            await connection.execute("DELETE FROM project_secrets WHERE project_id = ?", (project_id,))
            await connection.executemany(
                "INSERT INTO project_secrets (project_id, name, value_ciphertext, updated_at) "
                "VALUES (?, ?, ?, ?)",
                [(project_id, name, payload, moment) for name, payload in encrypted_entries.items()],
            )

    async def upsert_many(self, project_id: int, encrypted_entries: dict[str, bytes]) -> None:
        moment = time.time()
        await self._database.execute_many(
            "INSERT INTO project_secrets (project_id, name, value_ciphertext, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(project_id, name) DO UPDATE SET "
            "value_ciphertext = excluded.value_ciphertext, updated_at = excluded.updated_at",
            [(project_id, name, payload, moment) for name, payload in encrypted_entries.items()],
        )

    async def list_for_project(self, project_id: int) -> list[SecretRecord]:
        rows = await self._database.fetch_all(
            "SELECT name, value_ciphertext, updated_at FROM project_secrets "
            "WHERE project_id = ? ORDER BY name",
            (project_id,),
        )
        return [SecretRecord(**dict(row)) for row in rows]

    async def list_every_ciphertext(self) -> list[tuple[int, str, bytes]]:
        rows = await self._database.fetch_all(
            "SELECT project_id, name, value_ciphertext FROM project_secrets"
        )
        return [(row["project_id"], row["name"], row["value_ciphertext"]) for row in rows]

    async def delete(self, project_id: int, name: str) -> bool:
        return (
            await self._database.execute(
                "DELETE FROM project_secrets WHERE project_id = ? AND name = ?", (project_id, name)
            )
            > 0
        )

    async def purge(self, project_id: int) -> int:
        return await self._database.execute("DELETE FROM project_secrets WHERE project_id = ?", (project_id,))


class AlertRuleRepository:
    def __init__(self, database: Database):
        self._database = database

    async def seed_missing(self, defaults: dict[str, tuple[bool, int]]) -> None:
        await self._database.execute_many(
            "INSERT INTO alert_rules (kind, enabled, throttle_seconds, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(kind) DO NOTHING",
            [
                (kind, int(enabled), throttle_seconds, time.time())
                for kind, (enabled, throttle_seconds) in defaults.items()
            ],
        )

    async def reset_to_defaults(self, defaults: dict[str, tuple[bool, int]]) -> None:
        await self._database.execute_many(
            "INSERT INTO alert_rules (kind, enabled, throttle_seconds, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(kind) DO UPDATE SET enabled = excluded.enabled, "
            "throttle_seconds = excluded.throttle_seconds, updated_at = excluded.updated_at",
            [
                (kind, int(enabled), throttle_seconds, time.time())
                for kind, (enabled, throttle_seconds) in defaults.items()
            ],
        )

    async def list_all(self) -> list[AlertRuleRecord]:
        rows = await self._database.fetch_all("SELECT kind, enabled, throttle_seconds FROM alert_rules")
        return [
            AlertRuleRecord(
                kind=row["kind"], enabled=bool(row["enabled"]), throttle_seconds=row["throttle_seconds"]
            )
            for row in rows
        ]

    async def set_enabled(self, kind: str, enabled: bool) -> None:
        await self._database.execute(
            "UPDATE alert_rules SET enabled = ?, updated_at = ? WHERE kind = ?",
            (int(enabled), time.time(), kind),
        )

    async def set_throttle(self, kind: str, throttle_seconds: int) -> None:
        await self._database.execute(
            "UPDATE alert_rules SET throttle_seconds = ?, updated_at = ? WHERE kind = ?",
            (throttle_seconds, time.time(), kind),
        )


class AlertPreferenceRepository:
    def __init__(self, database: Database):
        self._database = database

    async def load_all(self) -> dict[str, str]:
        rows = await self._database.fetch_all("SELECT key, value FROM alert_preferences")
        return {row["key"]: row["value"] for row in rows}

    async def set(self, key: str, value: str) -> None:
        await self._database.execute(
            "INSERT INTO alert_preferences (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


class UserPreferenceRepository:
    def __init__(self, database: Database):
        self._database = database

    async def get(self, user_id: int, key: str) -> str | None:
        row = await self._database.fetch_one(
            "SELECT value FROM user_preferences WHERE user_id = ? AND key = ?", (user_id, key)
        )
        return row["value"] if row else None

    async def set(self, user_id: int, key: str, value: str) -> None:
        await self._database.execute(
            "INSERT INTO user_preferences (user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (user_id, key, value),
        )


class EventRepository:
    def __init__(self, database: Database):
        self._database = database
        self._writes_since_trim = 0

    async def record(self, kind: str, severity: str, project_slug: str | None, message: str) -> None:
        await self._database.execute(
            "INSERT INTO events (kind, severity, project_slug, message, created_at) VALUES (?, ?, ?, ?, ?)",
            (kind, severity, project_slug, message, time.time()),
        )
        self._writes_since_trim += 1
        if self._writes_since_trim >= 256:
            self._writes_since_trim = 0
            await self._database.execute(
                "DELETE FROM events WHERE id <= (SELECT MAX(id) FROM events) - ?", (EVENT_RETENTION_LIMIT,)
            )

    async def recent(self, limit: int, offset: int = 0, project_slug: str | None = None) -> list[EventRecord]:
        if project_slug is None:
            rows = await self._database.fetch_all(
                "SELECT id, kind, severity, project_slug, message, created_at FROM events "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        else:
            rows = await self._database.fetch_all(
                "SELECT id, kind, severity, project_slug, message, created_at FROM events "
                "WHERE project_slug = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (project_slug, limit, offset),
            )
        return [EventRecord(**dict(row)) for row in rows]

    async def count(self, project_slug: str | None = None) -> int:
        if project_slug is None:
            return int(await self._database.fetch_scalar("SELECT COUNT(*) FROM events") or 0)
        return int(
            await self._database.fetch_scalar(
                "SELECT COUNT(*) FROM events WHERE project_slug = ?", (project_slug,)
            )
            or 0
        )
