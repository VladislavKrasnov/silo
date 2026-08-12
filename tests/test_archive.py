from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.constants import ARCHIVE_MAX_COMPRESSED_BYTES, ARCHIVE_MAX_ENTRY_COUNT
from app.ingest.archive import ArchiveValidationError, build_extraction_plan, extract_archive


class TestPathTraversalDefenses:
    def test_rejects_parent_directory_escape(self, zip_builder, tmp_path: Path) -> None:
        payload = zip_builder({"../escaped.py": b"print(1)"})
        with pytest.raises(ArchiveValidationError, match="escapes"):
            extract_archive(payload, tmp_path)

    def test_rejects_absolute_paths(self, zip_builder, tmp_path: Path) -> None:
        payload = zip_builder({"/etc/passwd": b"root"})
        with pytest.raises(ArchiveValidationError, match="absolute"):
            extract_archive(payload, tmp_path)

    def test_rejects_windows_drive_paths(self, zip_builder, tmp_path: Path) -> None:
        payload = zip_builder({"C:/windows/system32/evil.dll": b"x"})
        with pytest.raises(ArchiveValidationError):
            extract_archive(payload, tmp_path)

    def test_rejects_backslash_separators(self, zip_builder, tmp_path: Path) -> None:
        payload = zip_builder({"..\\escaped.py": b"x"})
        with pytest.raises(ArchiveValidationError, match="illegal name"):
            extract_archive(payload, tmp_path)

    def test_rejects_deeply_nested_entries(self, zip_builder, tmp_path: Path) -> None:
        payload = zip_builder({"/".join(["level"] * 40) + "/file.py": b"x"})
        with pytest.raises(ArchiveValidationError, match="nested too deeply"):
            extract_archive(payload, tmp_path)


class TestSpecialFileDefenses:
    def test_rejects_symbolic_links(self, zip_builder, tmp_path: Path) -> None:
        payload = zip_builder(
            {"main.py": b"x", "link": b"/etc/passwd"},
            external_attributes={"link": 0o120777 << 16},
        )
        with pytest.raises(ArchiveValidationError, match="symbolic link"):
            extract_archive(payload, tmp_path)

    def test_rejects_special_files(self, zip_builder, tmp_path: Path) -> None:
        payload = zip_builder({"fifo": b""}, external_attributes={"fifo": 0o010644 << 16})
        with pytest.raises(ArchiveValidationError, match="special file"):
            extract_archive(payload, tmp_path)

    def test_rejects_encrypted_archives(self, zip_builder) -> None:
        with zipfile.ZipFile(io.BytesIO(zip_builder({"main.py": b"x"}))) as archive:
            archive.infolist()[0].flag_bits |= 0x1
            with pytest.raises(ArchiveValidationError, match="password protected"):
                build_extraction_plan(archive)

    def test_rejects_unsupported_compression_methods(self, zip_builder) -> None:
        with zipfile.ZipFile(io.BytesIO(zip_builder({"main.py": b"x"}))) as archive:
            archive.infolist()[0].compress_type = zipfile.ZIP_LZMA
            with pytest.raises(ArchiveValidationError, match="compression method"):
                build_extraction_plan(archive)


class TestResourceExhaustionDefenses:
    def test_rejects_oversized_payloads(self, tmp_path: Path) -> None:
        with pytest.raises(ArchiveValidationError, match="upload limit"):
            extract_archive(b"\x00" * (ARCHIVE_MAX_COMPRESSED_BYTES + 1), tmp_path)

    def test_rejects_compression_bombs(self, tmp_path: Path) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("bomb.txt", b"\x00" * (8 * 1024 * 1024))
        with pytest.raises(ArchiveValidationError, match="compression ratio"):
            extract_archive(buffer.getvalue(), tmp_path)

    def test_rejects_excessive_entry_counts(self, zip_builder, tmp_path: Path) -> None:
        payload = zip_builder({f"file_{index}.txt": b"x" for index in range(ARCHIVE_MAX_ENTRY_COUNT + 1)})
        with pytest.raises(ArchiveValidationError, match="entries"):
            extract_archive(payload, tmp_path)

    def test_rejects_empty_archives(self, zip_builder, tmp_path: Path) -> None:
        with pytest.raises(ArchiveValidationError, match="empty"):
            extract_archive(zip_builder({}), tmp_path)

    def test_rejects_unreadable_payloads(self, tmp_path: Path) -> None:
        with pytest.raises(ArchiveValidationError, match="readable zip"):
            extract_archive(b"not a zip file at all", tmp_path)


class TestSuccessfulExtraction:
    def test_writes_files_with_owner_only_permissions(self, zip_builder, tmp_path: Path) -> None:
        extract_archive(zip_builder({"main.py": b"print(1)"}), tmp_path)
        extracted = tmp_path / "main.py"

        assert extracted.read_bytes() == b"print(1)"
        assert extracted.stat().st_mode & 0o077 == 0

    def test_strips_a_single_github_style_root_directory(self, zip_builder, tmp_path: Path) -> None:
        payload = zip_builder({"repository-main/main.py": b"x", "repository-main/lib/util.py": b"y"})
        plan = extract_archive(payload, tmp_path)

        assert plan.stripped_root == "repository-main"
        assert (tmp_path / "main.py").is_file()
        assert (tmp_path / "lib" / "util.py").is_file()

    def test_strips_multiple_nested_wrapper_directories(self, zip_builder, tmp_path: Path) -> None:
        payload = zip_builder({"outer/inner/main.py": b"x", "outer/inner/lib/util.py": b"y"})
        plan = extract_archive(payload, tmp_path)

        assert plan.stripped_root == "outer"
        assert (tmp_path / "main.py").is_file()
        assert (tmp_path / "lib" / "util.py").is_file()

    def test_keeps_flat_archives_intact(self, zip_builder, tmp_path: Path) -> None:
        plan = extract_archive(zip_builder({"main.py": b"x", "util.py": b"y"}), tmp_path)

        assert plan.stripped_root is None
        assert (tmp_path / "main.py").is_file()
        assert (tmp_path / "util.py").is_file()
