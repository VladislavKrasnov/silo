from __future__ import annotations

from pathlib import Path

from app.constants import MANIFEST_FILENAME

_MANIFEST_TEMPLATE = """\
[project]
name = "{name}"

[runtime]
kind    = "python"
run     = "python main.py"
restart = "on-failure"

[build]
steps = [
    ["pip", "install", "-r", "requirements.txt"],
]

[resources]
memory_mb = 512
cpu       = 1.0
"""


def ensure_manifest(workspace: Path, project_name: str) -> bool:
    manifest_path = workspace / MANIFEST_FILENAME
    if manifest_path.exists():
        return False
    manifest_path.write_text(_MANIFEST_TEMPLATE.format(name=project_name), encoding="utf-8")
    return True
