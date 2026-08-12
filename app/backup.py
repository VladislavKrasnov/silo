from __future__ import annotations

import os
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

_EXCLUDED_DIRECTORY_NAMES: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        "htmlcov",
        "dist",
        "build",
        "scratch",
    }
)
_EXCLUDED_DIRECTORY_SUFFIXES: tuple[str, ...] = (".egg-info",)
_EXCLUDED_FILE_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo", ".swp", ".db-wal", ".db-shm")
_EXCLUDED_FILE_NAMES: frozenset[str] = frozenset({".DS_Store", ".coverage"})
_ENVIRONMENT_FILENAME: str = ".env"
_ENVIRONMENT_TEMPLATE_FILENAME: str = ".env.example"


def _is_excluded_directory(name: str) -> bool:
    return name in _EXCLUDED_DIRECTORY_NAMES or name.endswith(_EXCLUDED_DIRECTORY_SUFFIXES)


def _is_excluded_file(name: str) -> bool:
    if name == _ENVIRONMENT_TEMPLATE_FILENAME:
        return False
    if name == _ENVIRONMENT_FILENAME or name.startswith(f"{_ENVIRONMENT_FILENAME}."):
        return True
    return name in _EXCLUDED_FILE_NAMES or name.endswith(_EXCLUDED_FILE_SUFFIXES)


@dataclass(frozen=True, slots=True)
class BackupArchive:
    path: Path
    file_count: int
    uncompressed_bytes: int


def _snapshot_sqlite_database(source_path: Path, destination_path: Path) -> None:
    source_connection = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        destination_connection = sqlite3.connect(destination_path)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
    finally:
        source_connection.close()


def build_backup_archive(project_root: Path, database_path: Path, archive_destination: Path) -> BackupArchive:
    file_count = 0
    uncompressed_bytes = 0

    database_is_inside_project = project_root in database_path.parents

    with tempfile.TemporaryDirectory(prefix="silo-backup-") as scratch_directory_name:
        scratch_directory = Path(scratch_directory_name)
        database_snapshot_path: Path | None = None
        if database_is_inside_project and database_path.is_file():
            database_snapshot_path = scratch_directory / database_path.name
            _snapshot_sqlite_database(database_path, database_snapshot_path)

        with zipfile.ZipFile(archive_destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for current_directory, subdirectory_names, file_names in os.walk(project_root, topdown=True):
                current_path = Path(current_directory)
                subdirectory_names[:] = sorted(
                    name for name in subdirectory_names if not _is_excluded_directory(name)
                )

                for file_name in sorted(file_names):
                    if _is_excluded_file(file_name):
                        continue
                    file_path = current_path / file_name
                    if file_path == database_path:
                        continue
                    if not file_path.is_file() or file_path.is_symlink():
                        continue

                    archive.write(file_path, file_path.relative_to(project_root))
                    file_count += 1
                    uncompressed_bytes += file_path.stat().st_size

            if database_snapshot_path is not None:
                archive.write(database_snapshot_path, database_path.relative_to(project_root))
                file_count += 1
                uncompressed_bytes += database_snapshot_path.stat().st_size

    return BackupArchive(
        path=archive_destination, file_count=file_count, uncompressed_bytes=uncompressed_bytes
    )
