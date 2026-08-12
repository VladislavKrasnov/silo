from __future__ import annotations

import asyncio
import os
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.alerts.dispatcher import AlertDispatcher
from app.alerts.kinds import AlertKind
from app.constants import (
    CLONE_MAX_WORKSPACE_BYTES,
    LOG_DIRECTORY_NAME,
    MANIFEST_FILENAME,
    SCRATCH_DIRECTORY_NAME,
    VIRTUALENV_DIRECTORY_NAME,
    WORKSPACE_DIRECTORY_NAME,
)
from app.database.repositories import GitHubAccountRepository, ProjectRepository
from app.ingest.archive import ArchiveValidationError, extract_archive
from app.ingest.github import GitHubCloneError, GitHubCloner, RepositoryCoordinates, validate_git_reference
from app.ingest.sanitizer import SanitizationReport, WorkspaceTooLargeError, sanitize_workspace
from app.projects.layout import ProjectsLayout, ProjectSlugError, normalize_slug
from app.projects.manifest import ManifestError, load_manifest
from app.projects.scaffold import ensure_manifest
from app.security.crypto import SecretCipher
from app.security.vault import SecretsVault


class IngestError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    slug: str
    display_name: str
    manifest_generated: bool
    report: SanitizationReport


class ProjectIngestionPipeline:
    def __init__(
        self,
        layout: ProjectsLayout,
        project_repository: ProjectRepository,
        account_repository: GitHubAccountRepository,
        cipher: SecretCipher,
        cloner: GitHubCloner,
        alerts: AlertDispatcher,
    ):
        self._layout = layout
        self._project_repository = project_repository
        self._account_repository = account_repository
        self._cipher = cipher
        self._cloner = cloner
        self._alerts = alerts

    async def _reserve_slug(self, requested_slug: str) -> str:
        try:
            slug = normalize_slug(requested_slug)
        except ProjectSlugError as error:
            raise IngestError(str(error)) from error
        if self._layout.exists(slug) or await self._project_repository.get_by_slug(slug) is not None:
            raise IngestError(f"a project named {slug} already exists")
        return slug

    def _create_staging_root(self) -> Path:
        staging_root = self._layout.projects_root_dir / f".staging-{secrets.token_hex(8)}"
        for directory in (
            staging_root / WORKSPACE_DIRECTORY_NAME,
            staging_root / VIRTUALENV_DIRECTORY_NAME,
            staging_root / SCRATCH_DIRECTORY_NAME,
            staging_root / LOG_DIRECTORY_NAME,
        ):
            directory.mkdir(parents=True, exist_ok=False)
            os.chmod(directory, 0o700)
        os.chmod(staging_root, 0o700)
        return staging_root

    def _finalize_workspace(self, workspace: Path, project_name: str) -> tuple[bool, SanitizationReport]:
        try:
            report = sanitize_workspace(workspace, CLONE_MAX_WORKSPACE_BYTES)
        except WorkspaceTooLargeError as error:
            raise IngestError(str(error)) from error

        if report.file_count == 0:
            raise IngestError("the uploaded project contains no files")

        manifest_generated = ensure_manifest(workspace, project_name)
        try:
            load_manifest(workspace / MANIFEST_FILENAME, project_name)
        except ManifestError as error:
            raise IngestError(f"fleet.toml is invalid: {error}") from error

        return manifest_generated, report

    async def ingest_archive(self, payload: bytes, requested_slug: str) -> IngestOutcome:
        slug = await self._reserve_slug(requested_slug)
        staging_root = await asyncio.to_thread(self._create_staging_root)

        try:
            workspace = staging_root / WORKSPACE_DIRECTORY_NAME
            try:
                await asyncio.to_thread(extract_archive, payload, workspace)
            except ArchiveValidationError as error:
                self._alerts.publish(
                    AlertKind.SECURITY_INGEST_REJECTED, f"archive upload rejected: {error}", slug
                )
                raise IngestError(str(error)) from error

            manifest_generated, report = await asyncio.to_thread(self._finalize_workspace, workspace, slug)
            await asyncio.to_thread(os.rename, staging_root, self._layout.paths_for(slug).root)
        except BaseException:
            await asyncio.to_thread(shutil.rmtree, staging_root, True)
            raise

        await self._project_repository.add(
            slug=slug,
            display_name=slug,
            source_kind="archive",
            source_reference="upload",
            git_reference=None,
            github_account_id=None,
        )
        return IngestOutcome(
            slug=slug, display_name=slug, manifest_generated=manifest_generated, report=report
        )

    async def ingest_github(
        self,
        coordinates: RepositoryCoordinates,
        requested_slug: str,
        git_reference: str | None,
        account_id: int | None,
    ) -> IngestOutcome:
        slug = await self._reserve_slug(requested_slug)
        username, token = await self._resolve_credentials(account_id)
        staging_root = await asyncio.to_thread(self._create_staging_root)
        workspace = staging_root / WORKSPACE_DIRECTORY_NAME

        try:
            await asyncio.to_thread(shutil.rmtree, workspace)
            try:
                await self._cloner.clone(coordinates, workspace, git_reference, username, token)
            except GitHubCloneError as error:
                self._alerts.publish(AlertKind.SECURITY_INGEST_REJECTED, f"clone rejected: {error}", slug)
                raise IngestError(str(error)) from error

            manifest_generated, report = await asyncio.to_thread(self._finalize_workspace, workspace, slug)
            await asyncio.to_thread(os.rename, staging_root, self._layout.paths_for(slug).root)
        except BaseException:
            await asyncio.to_thread(shutil.rmtree, staging_root, True)
            raise

        await self._project_repository.add(
            slug=slug,
            display_name=slug,
            source_kind="github",
            source_reference=coordinates.normalized_url,
            git_reference=validate_git_reference(git_reference) if git_reference else None,
            github_account_id=account_id,
        )
        return IngestOutcome(
            slug=slug, display_name=slug, manifest_generated=manifest_generated, report=report
        )

    async def refresh_from_github(self, slug: str) -> IngestOutcome:
        from app.ingest.github import parse_repository_url

        record = await self._project_repository.get_by_slug(slug)
        if record is None or record.source_kind != "github":
            raise IngestError("only projects installed from GitHub can be refreshed")

        coordinates = parse_repository_url(record.source_reference)
        username, token = await self._resolve_credentials(record.github_account_id)
        staging_root = await asyncio.to_thread(self._create_staging_root)
        staged_workspace = staging_root / WORKSPACE_DIRECTORY_NAME
        paths = self._layout.paths_for(slug)
        retired_workspace = staging_root / "retired"

        try:
            await asyncio.to_thread(shutil.rmtree, staged_workspace)
            try:
                await self._cloner.clone(coordinates, staged_workspace, record.git_reference, username, token)
            except GitHubCloneError as error:
                raise IngestError(str(error)) from error

            manifest_generated, report = await asyncio.to_thread(
                self._finalize_workspace, staged_workspace, slug
            )
            await asyncio.to_thread(os.rename, paths.workspace, retired_workspace)
            await asyncio.to_thread(os.rename, staged_workspace, paths.workspace)
        finally:
            await asyncio.to_thread(shutil.rmtree, staging_root, True)

        await self._project_repository.touch(slug)
        return IngestOutcome(
            slug=slug, display_name=record.display_name, manifest_generated=manifest_generated, report=report
        )

    async def _resolve_credentials(self, account_id: int | None) -> tuple[str | None, str | None]:
        if account_id is None:
            return None, None
        account = await self._account_repository.get(account_id)
        if account is None:
            raise IngestError("the selected GitHub account no longer exists")
        return account.username, self._cipher.decrypt(
            account.token_ciphertext, SecretsVault.account_context(account.label)
        )

    async def remove(self, slug: str) -> bool:
        deleted = await self._project_repository.delete(slug)
        await asyncio.to_thread(self._layout.destroy, slug)
        if deleted:
            self._alerts.publish(AlertKind.PROJECT_REMOVED, "project and its secrets were deleted", slug)
        return deleted

    async def purge_staging_residue(self) -> None:
        for entry in self._layout.projects_root_dir.glob(".staging-*"):
            await asyncio.to_thread(shutil.rmtree, entry, True)
