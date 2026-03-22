from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def isolated_ppt_db():
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is required for PPT integration tests")

    from src.services.storage import db

    db._engine = None
    engine = db.get_engine()
    db._metadata.drop_all(engine, checkfirst=True)
    db._metadata.create_all(engine)
    db._ensure_additive_schema(engine)
    yield
    db._metadata.drop_all(engine, checkfirst=True)


@pytest.fixture
def ppt_service(project_root: Path):
    from src.services.export.ppt_project_service import PptProjectService

    return PptProjectService(project_root)
