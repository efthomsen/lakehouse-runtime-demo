import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent.parent / "synthetic-data"


@pytest.fixture
def orders_fixture_path() -> Path:
    return FIXTURE_DIR / "orders_sample.json"


@pytest.fixture
def orders_fixture(orders_fixture_path: Path) -> list[dict]:
    return json.loads(orders_fixture_path.read_text())
