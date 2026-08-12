from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from app.constants import MEMORY_LIMIT_CEILING_MEGABYTES
from app.projects.manifest import ManifestError, RestartPolicy, RuntimeKind, load_manifest, parse_manifest
from app.projects.scaffold import ensure_manifest, render_manifest_document

MINIMAL_DOCUMENT: dict = {"run": {"command": ["python", "main.py"]}}


class TestManifestDefaults:
    def test_applies_conservative_defaults(self) -> None:
        manifest = parse_manifest(MINIMAL_DOCUMENT, "fallback")

        assert manifest.name == "fallback"
        assert manifest.runtime_kind is RuntimeKind.PYTHON
        assert manifest.restart_policy is RestartPolicy.ON_FAILURE
        assert manifest.network_enabled is True
        assert manifest.resources.memory_megabytes == 512

    def test_requires_a_run_command(self) -> None:
        with pytest.raises(ManifestError, match="run.command"):
            parse_manifest({}, "fallback")


class TestManifestValidation:
    def test_rejects_unknown_tables(self) -> None:
        with pytest.raises(ManifestError, match="unknown top-level tables"):
            parse_manifest({**MINIMAL_DOCUMENT, "danger": {}}, "fallback")

    def test_rejects_unknown_keys(self) -> None:
        with pytest.raises(ManifestError, match="unknown keys"):
            parse_manifest({"run": {"command": ["python"], "shell": "rm -rf /"}}, "fallback")

    def test_rejects_shell_style_commands(self) -> None:
        with pytest.raises(ManifestError, match="non-empty array"):
            parse_manifest({"run": {"command": "python main.py && curl evil"}}, "fallback")

    def test_rejects_absolute_executables(self) -> None:
        with pytest.raises(ManifestError, match="program name"):
            parse_manifest({"run": {"command": ["/bin/sh", "-c", "id"]}}, "fallback")

    def test_rejects_traversing_executables(self) -> None:
        with pytest.raises(ManifestError, match="program name"):
            parse_manifest({"run": {"command": ["../../../bin/sh"]}}, "fallback")

    def test_rejects_escaping_working_directories(self) -> None:
        with pytest.raises(ManifestError, match="working_directory"):
            parse_manifest(
                {**MINIMAL_DOCUMENT, "run": {"command": ["python"], "working_directory": "../.."}}, "x"
            )

    def test_rejects_invalid_environment_names(self) -> None:
        with pytest.raises(ManifestError, match="invalid variable name"):
            parse_manifest({**MINIMAL_DOCUMENT, "environment": {"required": ["lowercase"]}}, "x")

    def test_rejects_non_printable_arguments(self) -> None:
        with pytest.raises(ManifestError, match="non-printable"):
            parse_manifest({"run": {"command": ["python", "main\x00.py"]}}, "fallback")


class TestResourceClamping:
    def test_clamps_limits_to_the_ceiling(self) -> None:
        manifest = parse_manifest({**MINIMAL_DOCUMENT, "resources": {"memory_mb": 10**9}}, "x")
        assert manifest.resources.memory_megabytes == MEMORY_LIMIT_CEILING_MEGABYTES

    def test_rejects_non_positive_limits(self) -> None:
        with pytest.raises(ManifestError, match="positive integer"):
            parse_manifest({**MINIMAL_DOCUMENT, "resources": {"memory_mb": 0}}, "x")


class TestScaffolding:
    def test_generates_a_manifest_for_a_flat_python_project(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("print(1)")
        (tmp_path / "requirements.txt").write_text("aiogram\n")

        assert ensure_manifest(tmp_path, "alpha") is True

        manifest = load_manifest(tmp_path / "fleet.toml", "alpha")
        assert manifest.run_command == ("python", "-u", "main.py")
        assert manifest.build_steps[0][:2] == ("pip", "install")

    def test_generates_a_manifest_for_a_package_python_project(self, tmp_path: Path) -> None:
        package = tmp_path / "bot"
        package.mkdir()
        (package / "__main__.py").write_text("")
        ensure_manifest(tmp_path, "alpha")

        assert load_manifest(tmp_path / "fleet.toml", "alpha").run_command == ("python", "-u", "-m", "bot")

    def test_generates_a_manifest_for_a_node_project(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"scripts": {"start": "node index.js"}}')
        ensure_manifest(tmp_path, "alpha")

        manifest = load_manifest(tmp_path / "fleet.toml", "alpha")
        assert manifest.runtime_kind is RuntimeKind.NODE
        assert manifest.run_command == ("npm", "run", "start")

    def test_never_overwrites_an_existing_manifest(self, tmp_path: Path) -> None:
        (tmp_path / "fleet.toml").write_text('[run]\ncommand = ["python", "custom.py"]\n')

        assert ensure_manifest(tmp_path, "alpha") is False
        assert load_manifest(tmp_path / "fleet.toml", "alpha").run_command == ("python", "custom.py")

    def test_rendered_document_round_trips_through_the_parser(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("")
        from app.projects.scaffold import detect_runtime

        document = render_manifest_document("alpha", detect_runtime(tmp_path))
        assert parse_manifest(tomllib.loads(document), "alpha").name == "alpha"
