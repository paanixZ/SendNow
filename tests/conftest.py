from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "build"
ADDON = FIXTURES / "addon"
REFERENCE = ROOT / "templates" / "sbox" / "reference"


@pytest.fixture
def addon_dir() -> Path:
    return ADDON


@pytest.fixture
def gma_path() -> Path:
    return FIXTURES / "sourcebridge_fixtures.gma"


@pytest.fixture
def vpk_path() -> Path:
    return FIXTURES / "sourcebridge_fixtures_dir.vpk"


def read(rel: str) -> bytes:
    return (ADDON / rel).read_bytes()
