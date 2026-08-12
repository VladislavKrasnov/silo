from __future__ import annotations

from types import SimpleNamespace

from app.database.engine import Database
from app.database.repositories import GitHubAccountRepository, SecretRepository
from app.ingest.github_oauth import GitHubIdentity
from app.security.redaction import SecretRedactor
from app.security.vault import SecretsVault
from app.telegram.routers.settings import _reserve_account_label, _store_identity


def _context(database: Database, cipher):
    account_repository = GitHubAccountRepository(database)
    vault = SecretsVault(
        secret_repository=SecretRepository(database),
        account_repository=account_repository,
        cipher=cipher,
        redactor=SecretRedactor(),
    )
    return SimpleNamespace(account_repository=account_repository, vault=vault)


class TestAccountLabelReservation:
    async def test_uses_the_username_verbatim_when_free(self, database: Database, cipher) -> None:
        context = _context(database, cipher)
        assert await _reserve_account_label(context, "octocat") == "octocat"

    async def test_disambiguates_a_collision_with_a_numeric_suffix(self, database: Database, cipher) -> None:
        context = _context(database, cipher)
        await _store_identity(context, GitHubIdentity(username="octocat", token="first-token"))

        label = await _reserve_account_label(context, "octocat")
        assert label == "octocat-2"

    async def test_stacks_suffixes_across_repeated_collisions(self, database: Database, cipher) -> None:
        context = _context(database, cipher)
        await _store_identity(context, GitHubIdentity(username="octocat", token="first-token"))
        await _store_identity(context, GitHubIdentity(username="octocat", token="second-token"))

        label = await _reserve_account_label(context, "octocat")
        assert label == "octocat-3"

    async def test_truncates_usernames_longer_than_the_label_limit(self, database: Database, cipher) -> None:
        context = _context(database, cipher)
        long_username = "a" * 60

        label = await _reserve_account_label(context, long_username)
        assert len(label) <= 32
