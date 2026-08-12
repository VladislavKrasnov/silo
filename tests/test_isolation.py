from __future__ import annotations

from pathlib import Path

import pytest

from app.constants import SANDBOX_VIRTUALENV_MOUNT, SANDBOX_WORKSPACE_MOUNT
from app.projects.layout import (
    PathContainmentError,
    ProjectsLayout,
    ProjectSlugError,
    normalize_slug,
    resolve_within,
    validate_slug,
)
from app.sandbox.backends import BubblewrapIsolationBackend, DockerIsolationBackend, NativeIsolationBackend
from app.sandbox.environment import sanitize_project_environment
from app.sandbox.spec import SandboxSpec


class TestSlugValidation:
    @pytest.mark.parametrize(
        "candidate",
        ["../escape", "/absolute", "with space", "Upper", "-leading", "trailing-", "..", "", "a" * 64],
    )
    def test_rejects_unsafe_slugs(self, candidate: str) -> None:
        with pytest.raises(ProjectSlugError):
            validate_slug(candidate)

    @pytest.mark.parametrize("candidate", ["weather-bot", "support_bot", "bot2", "a1"])
    def test_accepts_conventional_slugs(self, candidate: str) -> None:
        assert validate_slug(candidate) == candidate

    def test_normalizes_repository_names(self) -> None:
        assert normalize_slug("My Weather Bot!") == "my-weather-bot"

    def test_neutralizes_traversal_attempts(self) -> None:
        assert normalize_slug("../../etc") == "etc"
        assert normalize_slug("/absolute/path") == "absolute-path"

    @pytest.mark.parametrize("candidate", ["...", "///", "!!!", ""])
    def test_refuses_names_that_carry_no_usable_characters(self, candidate: str) -> None:
        with pytest.raises(ProjectSlugError):
            normalize_slug(candidate)


class TestPathContainment:
    def test_rejects_parent_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(PathContainmentError):
            resolve_within(tmp_path, "../outside")

    def test_rejects_absolute_paths(self, tmp_path: Path) -> None:
        with pytest.raises(PathContainmentError):
            resolve_within(tmp_path, "/etc/passwd")

    def test_rejects_symlink_escapes(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside"
        outside.mkdir(exist_ok=True)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "link").symlink_to(outside)

        with pytest.raises(PathContainmentError):
            resolve_within(workspace, "link")

    def test_accepts_contained_paths(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        assert resolve_within(tmp_path, "src") == (tmp_path / "src").resolve()


class TestProjectsLayout:
    def test_each_project_gets_its_own_private_tree(self, projects_layout: ProjectsLayout) -> None:
        paths = projects_layout.create("alpha")

        assert paths.root.parent == projects_layout.projects_root_dir
        assert paths.workspace.is_dir() and paths.virtualenv.is_dir()
        assert paths.scratch.is_dir() and paths.logs.is_dir()
        assert paths.root.stat().st_mode & 0o077 == 0

    def test_refuses_to_create_a_duplicate(self, projects_layout: ProjectsLayout) -> None:
        projects_layout.create("alpha")
        with pytest.raises(FileExistsError):
            projects_layout.create("alpha")

    def test_discovery_ignores_staging_and_hidden_directories(self, projects_layout: ProjectsLayout) -> None:
        projects_layout.create("alpha")
        (projects_layout.projects_root_dir / ".staging-abcdef").mkdir()

        assert projects_layout.discovered_slugs() == ["alpha"]

    def test_destroy_removes_the_whole_tree(self, projects_layout: ProjectsLayout) -> None:
        projects_layout.create("alpha")
        projects_layout.destroy("alpha")

        assert projects_layout.discovered_slugs() == []


class TestEnvironmentSanitization:
    def test_strips_interpreter_hijacking_variables(self) -> None:
        sanitized = sanitize_project_environment(
            {
                "BOT_TOKEN": "safe",
                "LD_PRELOAD": "/tmp/evil.so",
                "LD_LIBRARY_PATH": "/tmp",
                "PYTHONPATH": "/other/project",
                "PATH": "/tmp",
                "NODE_OPTIONS": "--require /tmp/evil.js",
                "HOME": "/root",
            }
        )
        assert sanitized == {"BOT_TOKEN": "safe"}


def _sandbox_spec(projects_layout: ProjectsLayout) -> SandboxSpec:
    paths = projects_layout.create("alpha")
    return SandboxSpec(
        paths=paths,
        command=("python", "main.py"),
        working_directory=".",
        environment={"BOT_TOKEN": "secret-value"},
        network_enabled=False,
    )


class TestBubblewrapInvocation:
    def test_binds_only_the_project_and_unshares_namespaces(self, projects_layout: ProjectsLayout) -> None:
        spec = _sandbox_spec(projects_layout)
        invocation = BubblewrapIsolationBackend().build_invocation(spec)
        argv = invocation.argv

        assert argv[0] == "bwrap"
        for required_flag in ("--unshare-pid", "--unshare-user", "--unshare-net", "--die-with-parent"):
            assert required_flag in argv

        bound_sources = {argv[index + 1] for index, token in enumerate(argv) if token == "--bind"}
        assert bound_sources == {str(spec.paths.workspace), str(spec.paths.scratch)}
        assert str(projects_layout.projects_root_dir) not in bound_sources

    def test_mounts_the_virtualenv_read_only_at_runtime(self, projects_layout: ProjectsLayout) -> None:
        invocation = BubblewrapIsolationBackend().build_invocation(_sandbox_spec(projects_layout))
        argv = invocation.argv
        read_only_sources = {argv[index + 1] for index, token in enumerate(argv) if token == "--ro-bind"}

        assert any(source.endswith("/venv") for source in read_only_sources)

    def test_never_places_secret_values_in_the_argument_vector(self, projects_layout: ProjectsLayout) -> None:
        invocation = BubblewrapIsolationBackend().build_invocation(_sandbox_spec(projects_layout))

        assert "secret-value" not in " ".join(invocation.argv)
        assert invocation.environment["BOT_TOKEN"] == "secret-value"

    def test_workspace_is_the_only_visible_project_path(self, projects_layout: ProjectsLayout) -> None:
        invocation = BubblewrapIsolationBackend().build_invocation(_sandbox_spec(projects_layout))
        chdir_index = invocation.argv.index("--chdir")

        assert invocation.argv[chdir_index + 1] == SANDBOX_WORKSPACE_MOUNT


class TestDockerInvocation:
    def test_drops_capabilities_and_isolates_the_network(self, projects_layout: ProjectsLayout) -> None:
        invocation = DockerIsolationBackend("python:3.12-slim").build_invocation(
            _sandbox_spec(projects_layout)
        )
        argv = invocation.argv

        assert argv[:2] == ("docker", "run")
        assert "--read-only" in argv
        assert "no-new-privileges" in argv
        assert argv[argv.index("--network") + 1] == "none"
        assert argv[argv.index("--cap-drop") + 1] == "ALL"

    def test_forwards_secrets_by_name_only(self, projects_layout: ProjectsLayout) -> None:
        invocation = DockerIsolationBackend("python:3.12-slim").build_invocation(
            _sandbox_spec(projects_layout)
        )

        assert "secret-value" not in " ".join(invocation.argv)
        assert "BOT_TOKEN" in invocation.argv
        assert invocation.environment["BOT_TOKEN"] == "secret-value"

    def test_mounts_the_virtualenv_read_only(self, projects_layout: ProjectsLayout) -> None:
        invocation = DockerIsolationBackend("python:3.12-slim").build_invocation(
            _sandbox_spec(projects_layout)
        )
        volumes = [
            invocation.argv[index + 1] for index, token in enumerate(invocation.argv) if token == "--volume"
        ]

        assert any(volume.endswith(f"{SANDBOX_VIRTUALENV_MOUNT}:ro") for volume in volumes)


class TestNativeInvocation:
    def test_confines_the_working_directory_to_the_workspace(self, projects_layout: ProjectsLayout) -> None:
        spec = _sandbox_spec(projects_layout)
        invocation = NativeIsolationBackend().build_invocation(spec)

        assert invocation.working_directory == spec.paths.workspace / "."
        assert invocation.applies_resource_limits is True

    def test_path_points_at_the_project_virtualenv(self, projects_layout: ProjectsLayout) -> None:
        spec = _sandbox_spec(projects_layout)
        invocation = NativeIsolationBackend().build_invocation(spec)

        assert invocation.environment["PATH"].startswith(str(spec.paths.virtualenv))
        assert invocation.environment["VIRTUAL_ENV"] == str(spec.paths.virtualenv)
