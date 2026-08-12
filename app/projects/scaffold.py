from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.constants import MANIFEST_FILENAME
from app.projects.manifest import RuntimeKind


@dataclass(frozen=True, slots=True)
class DetectedRuntime:
    runtime_kind: RuntimeKind
    run_command: tuple[str, ...]
    build_steps: tuple[tuple[str, ...], ...]


def _find_package_with_main(workspace: Path) -> str | None:
    for entry in sorted(workspace.iterdir()):
        if entry.is_dir() and (entry / "__main__.py").is_file():
            return entry.name
    return None


def _detect_python_runtime(workspace: Path) -> DetectedRuntime:
    build_steps: list[tuple[str, ...]] = []
    if (workspace / "requirements.txt").is_file():
        build_steps.append(("pip", "install", "-r", "requirements.txt"))

    if (workspace / "main.py").is_file():
        run_command = ("python", "-u", "main.py")
    else:
        package = _find_package_with_main(workspace)
        run_command = ("python", "-u", "-m", package) if package else ("python", "-u", "main.py")

    return DetectedRuntime(RuntimeKind.PYTHON, run_command, tuple(build_steps))


def _detect_node_runtime(workspace: Path) -> DetectedRuntime:
    try:
        manifest = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}

    scripts = manifest.get("scripts", {}) if isinstance(manifest, dict) else {}
    run_command = ("npm", "run", "start") if "start" in scripts else ("npm", "start")
    return DetectedRuntime(RuntimeKind.NODE, run_command, (("npm", "install"),))


def detect_runtime(workspace: Path) -> DetectedRuntime:
    if (workspace / "package.json").is_file():
        return _detect_node_runtime(workspace)
    return _detect_python_runtime(workspace)


def render_manifest_document(project_name: str, detected: DetectedRuntime) -> str:
    lines = [
        "[run]",
        f"command = {json.dumps(list(detected.run_command))}",
        f'kind = "{detected.runtime_kind.value}"',
        'restart = "on-failure"',
        "",
    ]

    if detected.build_steps:
        steps = json.dumps([list(step) for step in detected.build_steps])
        lines += ["[build]", f"steps = {steps}", ""]

    lines += ["[resources]", "memory_mb = 512", "cpu = 1.0", ""]
    return "\n".join(lines)


def ensure_manifest(workspace: Path, project_name: str) -> bool:
    manifest_path = workspace / MANIFEST_FILENAME
    if manifest_path.exists():
        return False
    detected = detect_runtime(workspace)
    manifest_path.write_text(render_manifest_document(project_name, detected), encoding="utf-8")
    return True
