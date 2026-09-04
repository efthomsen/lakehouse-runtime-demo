from pathlib import Path

import pytest


@pytest.fixture
def run_id() -> str:
    """The series' canonical example run — see the motifs in the series brief
    (RUN-0187, COMMIT 8A4C1D, DELTA VERSION 1431 -> 1432)."""
    return "RUN-0187"


@pytest.fixture
def bronze_uri(tmp_path: Path) -> str:
    return str(tmp_path / "bronze" / "orders_raw")


@pytest.fixture
def silver_uri(tmp_path: Path) -> str:
    return str(tmp_path / "silver" / "orders")


@pytest.fixture
def checkpoint_path(tmp_path: Path) -> Path:
    return tmp_path / "checkpoint.json"
