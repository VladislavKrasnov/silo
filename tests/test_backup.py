from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

from app.backup import build_backup_archive


def _touch(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE projects (slug TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO projects (slug) VALUES ('demo')")
        connection.commit()
    finally:
        connection.close()


class TestExclusions:
    def test_skips_junk_directories_and_secrets(self, tmp_path: Path) -> None:
        project_root = tmp_path / "silo"
        _touch(project_root / "app" / "main.py")
        _touch(project_root / "app" / "__pycache__" / "main.cpython-312.pyc")
        _touch(project_root / ".venv" / "lib" / "site.py")
        _touch(project_root / "projects" / "demo" / "venv" / "lib" / "site.py")
        _touch(project_root / "projects" / "demo" / "workspace" / "bot.py")
        _touch(project_root / "projects" / "demo" / "scratch" / "leftover.tmp")
        _touch(project_root / ".git" / "HEAD")
        _touch(project_root / ".env", b"MASTER_BOT_TOKEN=secret")
        _touch(project_root / ".env.example", b"MASTER_BOT_TOKEN=")
        _touch(project_root / ".DS_Store")

        destination = tmp_path / "backup.zip"
        archive = build_backup_archive(project_root, tmp_path / "missing.db", destination)

        with zipfile.ZipFile(archive.path) as opened:
            names = set(opened.namelist())

        assert "app/main.py" in names
        assert "projects/demo/workspace/bot.py" in names
        assert ".env.example" in names

        assert not any("__pycache__" in name for name in names)
        assert not any(name.startswith(".venv/") for name in names)
        assert not any("/venv/" in name for name in names)
        assert not any("scratch" in name for name in names)
        assert not any(name.startswith(".git/") for name in names)
        assert ".env" not in names
        assert ".DS_Store" not in names

    def test_reports_accurate_file_count(self, tmp_path: Path) -> None:
        project_root = tmp_path / "silo"
        _touch(project_root / "a.py")
        _touch(project_root / "b.py")
        _touch(project_root / "__pycache__" / "a.pyc")

        destination = tmp_path / "backup.zip"
        archive = build_backup_archive(project_root, tmp_path / "missing.db", destination)

        assert archive.file_count == 2


class TestDatabaseSnapshot:
    def test_replaces_live_database_with_a_consistent_snapshot(self, tmp_path: Path) -> None:
        project_root = tmp_path / "silo"
        database_path = project_root / "state" / "orchestrator.db"
        _make_database(database_path)
        _touch(project_root / "state" / "orchestrator.db-wal", b"wal-bytes")
        _touch(project_root / "state" / "master.key", b"key-bytes")

        destination = tmp_path / "backup.zip"
        archive = build_backup_archive(project_root, database_path, destination)

        with zipfile.ZipFile(archive.path) as opened:
            names = set(opened.namelist())
            assert "state/orchestrator.db" in names
            assert "state/master.key" in names
            assert "state/orchestrator.db-wal" not in names

            opened.extract("state/orchestrator.db", tmp_path / "extracted")

        connection = sqlite3.connect(tmp_path / "extracted" / "state" / "orchestrator.db")
        try:
            rows = connection.execute("SELECT slug FROM projects").fetchall()
        finally:
            connection.close()
        assert rows == [("demo",)]

    def test_tolerates_a_missing_database(self, tmp_path: Path) -> None:
        project_root = tmp_path / "silo"
        _touch(project_root / "app" / "main.py")

        destination = tmp_path / "backup.zip"
        archive = build_backup_archive(project_root, project_root / "state" / "orchestrator.db", destination)

        assert archive.file_count == 1
