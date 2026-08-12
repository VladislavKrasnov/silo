from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.database.engine import Database
from app.projects.layout import ProjectsLayout
from app.security.crypto import SecretCipher
from app.security.redaction import SecretRedactor


@pytest.fixture
def projects_layout(tmp_path: Path) -> ProjectsLayout:
    layout = ProjectsLayout(tmp_path / "projects")
    layout.prepare_root()
    return layout


@pytest.fixture
async def database(tmp_path: Path):
    engine = Database(tmp_path / "state" / "orchestrator.db", reader_pool_size=2)
    await engine.connect()
    yield engine
    await engine.close()


@pytest.fixture
def cipher() -> SecretCipher:
    return SecretCipher(bytes(range(32)))


@pytest.fixture
def redactor() -> SecretRedactor:
    return SecretRedactor()


@pytest.fixture
def zip_builder():
    def build(entries: dict[str, bytes], *, external_attributes: dict[str, int] | None = None) -> bytes:
        buffer = io.BytesIO()
        attributes = external_attributes or {}
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in entries.items():
                info = zipfile.ZipInfo(name)
                info.external_attr = attributes.get(name, 0o100644 << 16)
                archive.writestr(info, payload)
        return buffer.getvalue()

    return build
