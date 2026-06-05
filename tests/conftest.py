import json
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def usaspending_response(fixtures_dir: Path) -> dict:
    with open(fixtures_dir / "usaspending" / "20260605_awards_response.json") as f:
        return json.load(f)
