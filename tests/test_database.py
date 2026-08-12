from __future__ import annotations

import asyncio
import sqlite3

import pytest

from app.alerts.kinds import ALERT_DEFINITIONS
from app.alerts.settings import AlertSettingsStore
from app.database.engine import Database
from app.database.repositories import (
    AlertPreferenceRepository,
    AlertRuleRepository,
    EventRepository,
    GitHubAccountRepository,
    ProjectRepository,
    SecretRepository,
)
from app.security.crypto import SecretCipher
from app.security.redaction import REDACTION_PLACEHOLDER, SecretRedactor
from app.security.vault import SecretsVault


class TestEngine:
    async def test_applies_performance_pragmas(self, database: Database) -> None:
        assert await database.fetch_scalar("PRAGMA journal_mode") == "wal"
        assert await database.fetch_scalar("PRAGMA foreign_keys") == 1
        assert await database.fetch_scalar("PRAGMA synchronous") == 1

    async def test_readers_reject_writes(self, database: Database) -> None:
        async with database.reader() as connection:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                await connection.execute("CREATE TABLE intruder (id INTEGER)")

    async def test_rolls_back_a_failed_transaction(self, database: Database) -> None:
        repository = ProjectRepository(database)
        await repository.add("alpha", "alpha", "archive", "upload", None, None)

        with pytest.raises(RuntimeError, match="aborted"):
            async with database.transaction() as connection:
                await connection.execute(
                    "INSERT INTO projects (slug, display_name, source_kind, source_reference, "
                    "autostart, created_at, updated_at) VALUES ('beta', 'beta', 'archive', 'upload', 1, 0, 0)"
                )
                raise RuntimeError("aborted")

        assert await repository.get_by_slug("beta") is None
        assert await repository.get_by_slug("alpha") is not None

    async def test_concurrent_writes_serialize_without_corruption(self, database: Database) -> None:
        repository = ProjectRepository(database)
        await asyncio.gather(
            *(
                repository.add(f"project-{index}", f"project-{index}", "archive", "upload", None, None)
                for index in range(32)
            )
        )
        assert len(await repository.list_all()) == 32


class TestProjectRepository:
    async def test_rejects_duplicate_slugs(self, database: Database) -> None:
        repository = ProjectRepository(database)
        await repository.add("alpha", "alpha", "archive", "upload", None, None)

        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            await repository.add("alpha", "alpha", "archive", "upload", None, None)

    async def test_rejects_unknown_source_kinds(self, database: Database) -> None:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            await ProjectRepository(database).add("alpha", "alpha", "ftp", "upload", None, None)

    async def test_toggles_autostart(self, database: Database) -> None:
        repository = ProjectRepository(database)
        await repository.add("alpha", "alpha", "archive", "upload", None, None)
        await repository.set_autostart("alpha", False)

        record = await repository.get_by_slug("alpha")
        assert record is not None and record.autostart is False


class TestSecretsVault:
    async def _build_vault(self, database: Database, cipher: SecretCipher, redactor: SecretRedactor):
        project_id = await ProjectRepository(database).add("alpha", "alpha", "archive", "upload", None, None)
        vault = SecretsVault(SecretRepository(database), GitHubAccountRepository(database), cipher, redactor)
        return project_id, vault

    async def test_values_are_encrypted_at_rest(
        self, database: Database, cipher: SecretCipher, redactor: SecretRedactor
    ) -> None:
        project_id, vault = await self._build_vault(database, cipher, redactor)
        await vault.store(project_id, {"BOT_TOKEN": "plaintext-token"}, replace_existing=True)

        stored = await database.fetch_scalar("SELECT value_ciphertext FROM project_secrets")
        assert b"plaintext-token" not in stored
        assert await vault.materialize(project_id) == {"BOT_TOKEN": "plaintext-token"}

    async def test_replace_clears_previous_variables(
        self, database: Database, cipher: SecretCipher, redactor: SecretRedactor
    ) -> None:
        project_id, vault = await self._build_vault(database, cipher, redactor)
        await vault.store(project_id, {"A": "1", "B": "2"}, replace_existing=True)
        await vault.store(project_id, {"C": "3"}, replace_existing=True)

        assert await vault.names(project_id) == ["C"]

    async def test_merge_preserves_previous_variables(
        self, database: Database, cipher: SecretCipher, redactor: SecretRedactor
    ) -> None:
        project_id, vault = await self._build_vault(database, cipher, redactor)
        await vault.store(project_id, {"A": "1"}, replace_existing=True)
        await vault.store(project_id, {"B": "2"}, replace_existing=False)

        assert await vault.names(project_id) == ["A", "B"]

    async def test_stored_values_become_redacted_in_logs(
        self, database: Database, cipher: SecretCipher, redactor: SecretRedactor
    ) -> None:
        project_id, vault = await self._build_vault(database, cipher, redactor)
        await vault.store(project_id, {"BOT_TOKEN": "very-secret-token"}, replace_existing=True)

        assert redactor.apply("using very-secret-token") == f"using {REDACTION_PLACEHOLDER}"

    async def test_deleting_a_project_purges_its_secrets(
        self, database: Database, cipher: SecretCipher, redactor: SecretRedactor
    ) -> None:
        project_id, vault = await self._build_vault(database, cipher, redactor)
        await vault.store(project_id, {"BOT_TOKEN": "value"}, replace_existing=True)
        await ProjectRepository(database).delete("alpha")

        assert await database.fetch_scalar("SELECT COUNT(*) FROM project_secrets") == 0

    async def test_github_tokens_are_encrypted_and_redacted(
        self, database: Database, cipher: SecretCipher, redactor: SecretRedactor
    ) -> None:
        vault = SecretsVault(SecretRepository(database), GitHubAccountRepository(database), cipher, redactor)
        await vault.store_github_token("work", "octocat", "ghp_supersecretvalue")

        stored = await database.fetch_scalar("SELECT token_ciphertext FROM github_accounts")
        assert b"ghp_supersecretvalue" not in stored
        assert redactor.apply("ghp_supersecretvalue") == REDACTION_PLACEHOLDER


class TestAlertSettings:
    async def _build_store(self, database: Database) -> AlertSettingsStore:
        store = AlertSettingsStore(AlertRuleRepository(database), AlertPreferenceRepository(database))
        await store.load()
        return store

    async def test_seeds_every_defined_rule(self, database: Database) -> None:
        store = await self._build_store(database)
        assert set(store.all_rules()) == {str(definition.kind) for definition in ALERT_DEFINITIONS}

    async def test_toggles_persist_across_reloads(self, database: Database) -> None:
        store = await self._build_store(database)
        await store.set_enabled("project.started", False)

        reloaded = await self._build_store(database)
        assert reloaded.rule_for("project.started").enabled is False

    async def test_clamps_out_of_range_thresholds(self, database: Database) -> None:
        store = await self._build_store(database)
        await store.set_preference("cpu_threshold_percent", "9999")

        assert store.preferences.cpu_threshold_percent == 100

    async def test_quiet_hours_only_suppress_below_critical(self, database: Database) -> None:
        store = await self._build_store(database)
        await store.set_preference("quiet_hours_enabled", "1")
        await store.set_preference("quiet_hours_start", "0")
        await store.set_preference("quiet_hours_end", "23")

        assert store.suppresses("info") is True
        assert store.suppresses("critical") is False

    async def test_minimum_severity_filters_lower_severities(self, database: Database) -> None:
        store = await self._build_store(database)
        await store.set_preference("minimum_severity", "warning")

        assert store.suppresses("info") is True
        assert store.suppresses("warning") is False


class TestEventRepository:
    async def test_returns_the_newest_events_first(self, database: Database) -> None:
        repository = EventRepository(database)
        for index in range(5):
            await repository.record("project.started", "info", "alpha", f"event {index}")

        recent = await repository.recent(3)
        assert [record.message for record in recent] == ["event 4", "event 3", "event 2"]
        assert await repository.count() == 5

    async def test_filters_by_project(self, database: Database) -> None:
        repository = EventRepository(database)
        await repository.record("project.started", "info", "alpha", "a")
        await repository.record("project.started", "info", "beta", "b")

        assert await repository.count("alpha") == 1
