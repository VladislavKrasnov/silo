from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.constants import CLONE_TIMEOUT_SECONDS, GIT_REFERENCE_PATTERN, GITHUB_REPOSITORY_PATH_PATTERN
from app.security.redaction import SecretRedactor

ALLOWED_GIT_HOSTS: frozenset[str] = frozenset({"github.com", "www.github.com"})

_CREDENTIAL_HELPER: str = (
    '!f() { test "$1" = get && '
    'echo "username=${GIT_HTTP_USERNAME}" && '
    'echo "password=${GIT_HTTP_PASSWORD}"; }; f'
)

_HARDENED_GIT_OPTIONS: tuple[str, ...] = (
    "-c",
    "protocol.version=2",
    "-c",
    "protocol.allow=never",
    "-c",
    "protocol.https.allow=always",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.symlinks=false",
    "-c",
    "core.askPass=",
    "-c",
    "http.followRedirects=false",
    "-c",
    "credential.helper=",
)


class GitHubCloneError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RepositoryCoordinates:
    owner: str
    repository: str
    normalized_url: str

    @property
    def default_slug_source(self) -> str:
        return self.repository


def parse_repository_url(raw_url: str) -> RepositoryCoordinates:
    parts = urlsplit(raw_url.strip())

    if parts.scheme != "https":
        raise GitHubCloneError("only https repository URLs are accepted")
    if parts.username or parts.password:
        raise GitHubCloneError("credentials embedded in the URL are not accepted")
    if parts.query or parts.fragment:
        raise GitHubCloneError("repository URL must not carry a query string or fragment")
    if parts.hostname is None or parts.hostname.lower() not in ALLOWED_GIT_HOSTS:
        raise GitHubCloneError(f"repository host is not allowed: {parts.hostname}")
    if parts.port is not None:
        raise GitHubCloneError("repository URL must not specify a port")

    path = parts.path[:-4] if parts.path.endswith(".git") else parts.path
    path = path.rstrip("/")
    if not GITHUB_REPOSITORY_PATH_PATTERN.match(path):
        raise GitHubCloneError("repository URL must have the form https://github.com/owner/repository")

    owner, repository = path.lstrip("/").split("/", 1)
    return RepositoryCoordinates(
        owner=owner, repository=repository, normalized_url=f"https://github.com/{owner}/{repository}.git"
    )


def validate_git_reference(raw_reference: str) -> str:
    reference = raw_reference.strip()
    if not GIT_REFERENCE_PATTERN.match(reference) or ".." in reference or reference.endswith(("/", ".lock")):
        raise GitHubCloneError(f"invalid git reference: {raw_reference[:64]!r}")
    return reference


class GitHubCloner:
    def __init__(self, redactor: SecretRedactor):
        self._redactor = redactor

    async def clone(
        self,
        coordinates: RepositoryCoordinates,
        destination: Path,
        git_reference: str | None = None,
        username: str | None = None,
        token: str | None = None,
    ) -> None:
        argv: list[str] = [
            "git",
            *_HARDENED_GIT_OPTIONS,
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--no-tags",
            "--no-recurse-submodules",
            "--quiet",
        ]
        if git_reference:
            argv += ["--branch", validate_git_reference(git_reference)]

        environment: dict[str, str] = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(destination.parent),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_ADVICE": "0",
            "LC_ALL": "C",
        }

        if token:
            argv[1:1] = ["-c", f"credential.helper={_CREDENTIAL_HELPER}"]
            environment["GIT_HTTP_USERNAME"] = username or "x-access-token"
            environment["GIT_HTTP_PASSWORD"] = token

        argv += [coordinates.normalized_url, str(destination)]

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
                env=environment,
                start_new_session=True,
            )
        except FileNotFoundError as error:
            raise GitHubCloneError("git is not installed on the orchestrator host") from error

        try:
            raw_output, _ = await asyncio.wait_for(process.communicate(), timeout=CLONE_TIMEOUT_SECONDS)
        except TimeoutError as error:
            process.kill()
            await process.wait()
            raise GitHubCloneError(f"clone timed out after {CLONE_TIMEOUT_SECONDS}s") from error

        if process.returncode != 0:
            detail = self._redactor.apply(raw_output.decode("utf-8", errors="replace").strip())[-512:]
            raise GitHubCloneError(detail or f"git exited with code {process.returncode}")
