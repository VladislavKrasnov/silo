from __future__ import annotations

import io
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.constants import (
    ARCHIVE_CHUNK_BYTES,
    ARCHIVE_MAX_COMPRESSED_BYTES,
    ARCHIVE_MAX_COMPRESSION_RATIO,
    ARCHIVE_MAX_ENTRY_BYTES,
    ARCHIVE_MAX_ENTRY_COUNT,
    ARCHIVE_MAX_PATH_DEPTH,
    ARCHIVE_MAX_UNCOMPRESSED_BYTES,
)

_ALLOWED_COMPRESSION_METHODS: frozenset[int] = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_ENCRYPTED_FLAG: int = 0x1
_SYMLINK_MODE: int = 0o120000
_REGULAR_FILE_MODE: int = 0o100000
_UNSET_MODE: int = 0o000000

_MACOS_METADATA_PREFIXES: tuple[str, ...] = ("__MACOSX/", "__MACOSX")
_MACOS_DS_STORE: str = ".DS_Store"


class ArchiveValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArchivePlan:
    entries: tuple[tuple[zipfile.ZipInfo, PurePosixPath], ...]
    total_uncompressed_bytes: int
    stripped_root: str | None


def _normalized_entry_path(raw_name: str) -> PurePosixPath:
    if "\x00" in raw_name or "\\" in raw_name:
        raise ArchiveValidationError(f"archive entry has an illegal name: {raw_name[:64]!r}")

    candidate = PurePosixPath(raw_name)
    if candidate.is_absolute() or (len(raw_name) > 1 and raw_name[1] == ":"):
        raise ArchiveValidationError(f"archive entry uses an absolute path: {raw_name[:64]!r}")

    parts = tuple(part for part in candidate.parts if part not in {".", ""})
    if any(part == ".." for part in parts):
        raise ArchiveValidationError(f"archive entry escapes the destination: {raw_name[:64]!r}")
    if len(parts) > ARCHIVE_MAX_PATH_DEPTH:
        raise ArchiveValidationError(f"archive entry is nested too deeply: {raw_name[:64]!r}")
    return PurePosixPath(*parts) if parts else PurePosixPath()


def _assert_regular_entry(entry: zipfile.ZipInfo) -> None:
    unix_mode = entry.external_attr >> 16
    file_type = stat.S_IFMT(unix_mode)
    if file_type == _SYMLINK_MODE:
        raise ArchiveValidationError(f"archive contains a symbolic link: {entry.filename[:64]!r}")
    if file_type not in {_REGULAR_FILE_MODE, _UNSET_MODE}:
        raise ArchiveValidationError(f"archive contains a special file: {entry.filename[:64]!r}")


def _detect_common_root(entry_paths: tuple[PurePosixPath, ...]) -> str | None:
    roots = {path.parts[0] for path in entry_paths if path.parts}
    if len(roots) != 1:
        return None
    root = roots.pop()
    return root if any(len(path.parts) > 1 for path in entry_paths) else None


def _is_macos_metadata(entry: zipfile.ZipInfo) -> bool:
    name = entry.filename
    if any(name == prefix or name.startswith(prefix + "/") for prefix in _MACOS_METADATA_PREFIXES):
        return True
    basename = name.rstrip("/").rsplit("/", 1)[-1]
    return basename == _MACOS_DS_STORE


def build_extraction_plan(archive: zipfile.ZipFile) -> ArchivePlan:
    entries = archive.infolist()
    if not entries:
        raise ArchiveValidationError("archive is empty")
    if len(entries) > ARCHIVE_MAX_ENTRY_COUNT:
        raise ArchiveValidationError(f"archive holds more than {ARCHIVE_MAX_ENTRY_COUNT} entries")

    planned: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    total_uncompressed = 0

    for entry in entries:
        if _is_macos_metadata(entry):
            continue

        if entry.flag_bits & _ENCRYPTED_FLAG:
            raise ArchiveValidationError("archive is password protected")
        if entry.compress_type not in _ALLOWED_COMPRESSION_METHODS:
            raise ArchiveValidationError(
                f"archive uses an unsupported compression method: {entry.compress_type}"
            )

        relative_path = _normalized_entry_path(entry.filename)
        if entry.is_dir():
            planned.append((entry, relative_path))
            continue

        _assert_regular_entry(entry)

        if entry.file_size > ARCHIVE_MAX_ENTRY_BYTES:
            raise ArchiveValidationError(
                f"archive entry exceeds the per-file size limit: {entry.filename[:64]!r}"
            )
        if entry.compress_size > 0 and entry.file_size / entry.compress_size > ARCHIVE_MAX_COMPRESSION_RATIO:
            raise ArchiveValidationError(
                f"archive entry has a suspicious compression ratio: {entry.filename[:64]!r}"
            )

        total_uncompressed += entry.file_size
        if total_uncompressed > ARCHIVE_MAX_UNCOMPRESSED_BYTES:
            raise ArchiveValidationError("archive expands beyond the total size limit")

        if not relative_path.parts:
            raise ArchiveValidationError("archive contains a file entry without a name")
        planned.append((entry, relative_path))

    outermost_stripped_root: str | None = None
    for _ in range(ARCHIVE_MAX_PATH_DEPTH):
        stripped_root = _detect_common_root(tuple(path for _entry, path in planned))
        if stripped_root is None:
            break
        if outermost_stripped_root is None:
            outermost_stripped_root = stripped_root
        planned = [(entry, PurePosixPath(*path.parts[1:])) for entry, path in planned if len(path.parts) > 1]

    return ArchivePlan(
        entries=tuple(planned),
        total_uncompressed_bytes=total_uncompressed,
        stripped_root=outermost_stripped_root,
    )


def _write_entry(archive: zipfile.ZipFile, entry: zipfile.ZipInfo, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    remaining_budget = entry.file_size + ARCHIVE_CHUNK_BYTES

    descriptor = os.open(destination_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as destination_file, archive.open(entry, "r") as source_stream:
        while chunk := source_stream.read(ARCHIVE_CHUNK_BYTES):
            remaining_budget -= len(chunk)
            if remaining_budget < 0:
                raise ArchiveValidationError(
                    f"archive entry expanded beyond its declared size: {entry.filename[:64]!r}"
                )
            destination_file.write(chunk)


def extract_archive(payload: bytes, destination: Path) -> ArchivePlan:
    if len(payload) > ARCHIVE_MAX_COMPRESSED_BYTES:
        raise ArchiveValidationError(
            f"archive exceeds the {ARCHIVE_MAX_COMPRESSED_BYTES // (1024 * 1024)}mb upload limit"
        )

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            plan = build_extraction_plan(archive)
            for entry, relative_path in plan.entries:
                target_path = destination / relative_path
                if entry.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    os.chmod(target_path, 0o700)
                    continue
                _write_entry(archive, entry, target_path)
    except zipfile.BadZipFile as error:
        raise ArchiveValidationError(f"archive is not a readable zip file: {error}") from error

    return plan
