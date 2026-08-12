from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from app.constants import FORBIDDEN_WORKSPACE_FILENAMES

_STRIPPED_MODE_BITS: int = stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX | stat.S_IWOTH | stat.S_IROTH


class WorkspaceTooLargeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SanitizationReport:
    removed_links: int
    removed_sensitive_paths: int
    file_count: int
    total_bytes: int


def sanitize_workspace(workspace: Path, size_limit_bytes: int) -> SanitizationReport:
    removed_links = 0
    removed_sensitive_paths = 0
    file_count = 0
    total_bytes = 0

    for current_directory, subdirectory_names, file_names in os.walk(workspace, topdown=True):
        current_path = Path(current_directory)
        retained_subdirectories: list[str] = []

        for subdirectory_name in subdirectory_names:
            subdirectory_path = current_path / subdirectory_name
            if subdirectory_path.is_symlink():
                subdirectory_path.unlink(missing_ok=True)
                removed_links += 1
            elif subdirectory_name in FORBIDDEN_WORKSPACE_FILENAMES:
                shutil.rmtree(subdirectory_path, ignore_errors=True)
                removed_sensitive_paths += 1
            else:
                retained_subdirectories.append(subdirectory_name)
                os.chmod(subdirectory_path, subdirectory_path.stat().st_mode & ~_STRIPPED_MODE_BITS)

        subdirectory_names[:] = retained_subdirectories

        for file_name in file_names:
            file_path = current_path / file_name
            if file_path.is_symlink():
                file_path.unlink(missing_ok=True)
                removed_links += 1
                continue
            if file_name in FORBIDDEN_WORKSPACE_FILENAMES:
                file_path.unlink(missing_ok=True)
                removed_sensitive_paths += 1
                continue

            file_status = file_path.lstat()
            if not stat.S_ISREG(file_status.st_mode):
                file_path.unlink(missing_ok=True)
                removed_sensitive_paths += 1
                continue

            os.chmod(file_path, file_status.st_mode & ~_STRIPPED_MODE_BITS)
            file_count += 1
            total_bytes += file_status.st_size
            if total_bytes > size_limit_bytes:
                raise WorkspaceTooLargeError(
                    f"project exceeds the {size_limit_bytes // (1024 * 1024)}mb workspace limit"
                )

    return SanitizationReport(
        removed_links=removed_links,
        removed_sensitive_paths=removed_sensitive_paths,
        file_count=file_count,
        total_bytes=total_bytes,
    )
