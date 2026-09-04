"""Reproduces article 2's "ghost retry": a Delta commit succeeds, the
checkpoint write for that page is interrupted, and a retry re-appends the
same source page. Runs entirely against a local filesystem Delta table."""

from pathlib import Path

import pyarrow.compute as pc
import pytest
from deltalake import DeltaTable

from ingestion.append_bronze import ingest_window
from ingestion.checkpoint import Checkpoint, CheckpointWriteInterrupted
from ingestion.source import SyntheticOrdersAPI


def _crash_before_checkpoint_on(page_to_kill: int):
    def hook(page: int, version: int) -> None:
        if page == page_to_kill:
            raise CheckpointWriteInterrupted(
                f"simulated crash after commit v{version}, before checkpoint for page {page}"
            )

    return hook


def test_ghost_retry_naive_append_duplicates_page_42(bronze_uri: str, checkpoint_path: Path, run_id: str):
    source = SyntheticOrdersAPI(pages=3, page_size=5, start_page=41)
    cp = Checkpoint(checkpoint_path)

    with pytest.raises(CheckpointWriteInterrupted):
        ingest_window(
            source=source,
            table_uri=bronze_uri,
            run_id=run_id,
            checkpoint=cp,
            after_commit=_crash_before_checkpoint_on(42),
        )

    table = DeltaTable(bronze_uri)
    assert table.version() == 1  # pages 41 and 42 each committed (v0, v1)
    assert cp.is_complete(run_id, 41)
    assert not cp.is_complete(run_id, 42)  # the table says 42 happened; the checkpoint does not

    result = ingest_window(source=source, table_uri=bronze_uri, run_id=run_id, checkpoint=cp)  # the retry
    assert result.pages_skipped == [41]
    assert result.pages_appended == [42, 43]

    rows = DeltaTable(bronze_uri).to_pyarrow_table()
    assert rows.num_rows == 20  # 15 unique source events + page 42 appended twice
    ids = rows.column("source_event_id").to_pylist()
    assert len(ids) - len(set(ids)) == 5  # exactly page 42's five events are duplicated
    assert rows.filter(pc.equal(rows["source_page"], 42)).num_rows == 10


def test_ghost_retry_is_visible_in_commit_metadata(bronze_uri: str, checkpoint_path: Path, run_id: str):
    source = SyntheticOrdersAPI(pages=3, page_size=5, start_page=41)
    cp = Checkpoint(checkpoint_path)

    with pytest.raises(CheckpointWriteInterrupted):
        ingest_window(
            source=source,
            table_uri=bronze_uri,
            run_id=run_id,
            checkpoint=cp,
            after_commit=_crash_before_checkpoint_on(42),
        )
    ingest_window(source=source, table_uri=bronze_uri, run_id=run_id, checkpoint=cp)

    history = DeltaTable(bronze_uri).history()
    page_42_commits = [entry for entry in history if entry.get("source_page") == "42"]
    assert len(page_42_commits) == 2  # the original commit and the retry's duplicate commit
    for entry in page_42_commits:
        assert entry["ingestion_run_id"] == run_id
