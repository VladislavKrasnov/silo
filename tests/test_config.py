from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppConfig, parse_admin_identifiers


class TestParseAdminIdentifiers:
    def test_parses_comma_separated_values(self) -> None:
        assert parse_admin_identifiers("111,222,333") == frozenset({111, 222, 333})

    def test_accepts_semicolons_as_separators(self) -> None:
        assert parse_admin_identifiers("111;222") == frozenset({111, 222})

    def test_trims_whitespace(self) -> None:
        assert parse_admin_identifiers(" 111 , 222 ") == frozenset({111, 222})

    def test_ignores_non_numeric_tokens(self) -> None:
        assert parse_admin_identifiers("111,abc,222") == frozenset({111, 222})

    def test_empty_input_yields_empty_set(self) -> None:
        assert parse_admin_identifiers("") == frozenset()


class TestAppConfig:
    def test_reads_directories_from_the_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROJECTS_ROOT_DIR", str(tmp_path / "projects"))
        monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
        monkeypatch.setenv("MASTER_BOT_TOKEN", "token")
        monkeypatch.setenv("ADMIN_IDS", "1,2")

        config = AppConfig.from_environment()

        assert config.projects_root_dir == (tmp_path / "projects").resolve()
        assert config.database_path == (tmp_path / "state" / "orchestrator.db").resolve()
        assert config.admin_ids == frozenset({1, 2})

    def test_falls_back_to_the_automatic_isolation_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ISOLATION_BACKEND", "chroot-please")
        assert AppConfig.from_environment().isolation_backend == "auto"

    def test_honours_an_explicit_isolation_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ISOLATION_BACKEND", "docker")
        assert AppConfig.from_environment().isolation_backend == "docker"

    def test_state_directory_is_created_private(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROJECTS_ROOT_DIR", str(tmp_path / "projects"))
        monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))

        config = AppConfig.from_environment()
        config.ensure_directories()

        assert config.state_dir.stat().st_mode & 0o077 == 0
