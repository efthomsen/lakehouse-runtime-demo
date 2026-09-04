from pathlib import Path

from deltalake import DeltaTable

from ingest.main import run
from silver.main import main as silver_main


def _ingest_twice(tmp_path: Path, orders_fixture_path: Path) -> str:
    """Simulate a replayed ingestion run: the same source page lands in
    Bronze twice (see test_ingest.py::test_replay_is_visible_not_silently_ignored).
    """
    table_uri = str(tmp_path / "bronze" / "orders_raw")
    run(run_id="RUN-A", table_uri=table_uri, source_path=orders_fixture_path, checkpoint_path=tmp_path / "cp-a.json")
    run(run_id="RUN-B", table_uri=table_uri, source_path=orders_fixture_path, checkpoint_path=tmp_path / "cp-b.json")
    return table_uri


def test_dedup_on_replay(tmp_path: Path, orders_fixture_path: Path):
    bronze_uri = _ingest_twice(tmp_path, orders_fixture_path)
    silver_uri = str(tmp_path / "silver" / "orders")

    silver_main(["--bronze-uri", bronze_uri, "--silver-uri", silver_uri])

    silver = DeltaTable(silver_uri).to_pyarrow_table()
    assert silver.num_rows == 6  # 12 Bronze rows (2 runs x 6), deduped by source_event_id
    assert len(set(silver.column("order_id").to_pylist())) == 6


def test_silver_normalises_status_case(tmp_path: Path, orders_fixture_path: Path):
    bronze_uri = str(tmp_path / "bronze" / "orders_raw")
    run(run_id="RUN-C", table_uri=bronze_uri, source_path=orders_fixture_path, checkpoint_path=tmp_path / "cp-c.json")
    silver_uri = str(tmp_path / "silver" / "orders")

    silver_main(["--bronze-uri", bronze_uri, "--silver-uri", silver_uri])

    statuses = set(DeltaTable(silver_uri).to_pyarrow_table().column("order_status").to_pylist())
    assert statuses <= {"completed", "cancelled"}
    assert all(s == s.lower() for s in statuses)


def test_silver_does_not_decide_business_meaning(tmp_path: Path, orders_fixture_path: Path):
    """Silver's schema has no notion of "completed" being business-relevant --
    it just standardises the case. Whether a cancelled order counts is a
    Gold decision (see fabric/gold_materialized_lake_views.sql)."""
    bronze_uri = str(tmp_path / "bronze" / "orders_raw")
    run(run_id="RUN-D", table_uri=bronze_uri, source_path=orders_fixture_path, checkpoint_path=tmp_path / "cp-d.json")
    silver_uri = str(tmp_path / "silver" / "orders")

    silver_main(["--bronze-uri", bronze_uri, "--silver-uri", silver_uri])

    silver = DeltaTable(silver_uri).to_pyarrow_table()
    # The cancelled order from the fixture is still present in Silver --
    # Silver preserves it; Gold's customer_value MLV excludes it explicitly.
    assert "cancelled" in silver.column("order_status").to_pylist()
