from __future__ import annotations

from app.database.repositories import GitHubAccountRepository, SecretRepository
from app.security.crypto import SecretCipher, SecretDecryptionError
from app.security.redaction import SecretRedactor


class SecretsVault:
    def __init__(
        self,
        secret_repository: SecretRepository,
        account_repository: GitHubAccountRepository,
        cipher: SecretCipher,
        redactor: SecretRedactor,
    ):
        self._secret_repository = secret_repository
        self._account_repository = account_repository
        self._cipher = cipher
        self._redactor = redactor

    @staticmethod
    def _context(project_id: int, name: str) -> str:
        return f"project-secret:{project_id}:{name}"

    async def store(self, project_id: int, entries: dict[str, str], replace_existing: bool) -> int:
        encrypted = {
            name: self._cipher.encrypt(value, self._context(project_id, name))
            for name, value in entries.items()
        }
        if replace_existing:
            await self._secret_repository.replace_all(project_id, encrypted)
        else:
            await self._secret_repository.upsert_many(project_id, encrypted)
        await self.refresh_redaction()
        return len(encrypted)

    async def names(self, project_id: int) -> list[str]:
        return [record.name for record in await self._secret_repository.list_for_project(project_id)]

    async def materialize(self, project_id: int) -> dict[str, str]:
        return {
            record.name: self._cipher.decrypt(record.value_ciphertext, self._context(project_id, record.name))
            for record in await self._secret_repository.list_for_project(project_id)
        }

    async def delete(self, project_id: int, name: str) -> bool:
        deleted = await self._secret_repository.delete(project_id, name)
        if deleted:
            await self.refresh_redaction()
        return deleted

    async def purge(self, project_id: int) -> int:
        purged = await self._secret_repository.purge(project_id)
        await self.refresh_redaction()
        return purged

    @staticmethod
    def account_context(label: str) -> str:
        return f"github-account:{label}"

    async def store_github_token(self, label: str, username: str, token: str) -> int:
        account_id = await self._account_repository.add(
            label, username, self._cipher.encrypt(token, self.account_context(label))
        )
        await self.refresh_redaction()
        return account_id

    async def reveal_github_token(self, label: str, token_ciphertext: bytes) -> str:
        return self._cipher.decrypt(token_ciphertext, self.account_context(label))

    async def delete_github_account(self, account_id: int) -> bool:
        deleted = await self._account_repository.delete(account_id)
        if deleted:
            await self.refresh_redaction()
        return deleted

    async def refresh_redaction(self) -> None:
        secret_values: list[str] = []

        for account in await self._account_repository.list_all():
            try:
                secret_values.append(
                    self._cipher.decrypt(account.token_ciphertext, self.account_context(account.label))
                )
            except SecretDecryptionError:
                continue

        for project_id, name, ciphertext in await self._secret_repository.list_every_ciphertext():
            try:
                secret_values.append(self._cipher.decrypt(ciphertext, self._context(project_id, name)))
            except SecretDecryptionError:
                continue

        self._redactor.replace_values(secret_values)
