from pathlib import Path

import pytest
from deltalake import DeltaTable

from ingest.main import run


def test_append_creates_bronze_table(tmp_path: Path, orders_fixture_path: Path):
    table_uri = str(tmp_path / "bronze" / "orders_raw")
    run(
        run_id="RUN-TEST-001",
        table_uri=table_uri,
        source_path=orders_fixture_path,
        checkpoint_path=tmp_path / "checkpoint.json",
    )

    table = DeltaTable(table_uri).to_pyarrow_table()
    assert table.num_rows == 6
    assert set(table.column("ingestion_run_id").to_pylist()) == {"RUN-TEST-001"}


def test_replay_is_visible_not_silently_ignored(tmp_path: Path, orders_fixture_path: Path):
    """A second run with the same run-id (no checkpoint reset) re-appends --
    Bronze intentionally preserves the replay rather than hiding it. Silver
    is where technical deduplication happens (see test_silver.py)."""
    table_uri = str(tmp_path / "bronze" / "orders_raw")
    checkpoint_path = tmp_path / "checkpoint.json"

    run(run_id="RUN-TEST-002", table_uri=table_uri, source_path=orders_fixture_path, checkpoint_path=checkpoint_path)
    first_version = DeltaTable(table_uri).version()

    # Checkpoint marks every page complete, so a real replay of the *same*
    # checkpoint would be skipped -- simulate the "ghost retry" by wiping
    # only the checkpoint, standing in for a crash that lost that state.
    checkpoint_path.unlink()
    run(run_id="RUN-TEST-002", table_uri=table_uri, source_path=orders_fixture_path, checkpoint_path=checkpoint_path)

    table = DeltaTable(table_uri)
    assert table.version() > first_version
    assert table.to_pyarrow_table().num_rows == 12  # duplicated at the Bronze layer, by design


def test_crash_before_checkpoint(tmp_path: Path, orders_fixture_path: Path):
    """Reproduces article 2's "ghost retry": the Delta commit for page 1
    succeeds, then the process exits before the checkpoint is written."""
    table_uri = str(tmp_path / "bronze" / "orders_raw")
    checkpoint_path = tmp_path / "checkpoint.json"

    with pytest.raises(SystemExit):
        run(
            run_id="RUN-TEST-003",
            table_uri=table_uri,
            source_path=orders_fixture_path,
            checkpoint_path=checkpoint_path,
            crash_after_page=1,
        )

    # The table already has page 1's rows committed...
    table = DeltaTable(table_uri).to_pyarrow_table()
    assert table.num_rows == 2

    # ...but the checkpoint never recorded it as complete, so a retry
    # re-fetches and re-appends page 1 -- this is the duplicate the article
    # says Bronze should make visible rather than silently prevent.
    run(run_id="RUN-TEST-003", table_uri=table_uri, source_path=orders_fixture_path, checkpoint_path=checkpoint_path)
    table_after_retry = DeltaTable(table_uri).to_pyarrow_table()
    assert table_after_retry.num_rows == 8  # 6 original + 2 re-appended from page 1
