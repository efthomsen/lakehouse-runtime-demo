"""Cross-client compatibility check.

Article 2 is explicit that "both products support Delta" is not the same as
interoperable: a table has to actually be readable by a second, independent
client. This test doesn't reach a real Fabric workspace, but it does open
the table through a second, freshly constructed deltalake client rather than
reusing any handle held by the writer -- the minimum bar for "another
engine can read this."
"""

from pathlib import Path

from deltalake import DeltaTable

from ingest.main import run


def test_table_is_readable_by_a_second_independent_client(tmp_path: Path, orders_fixture_path: Path):
    table_uri = str(tmp_path / "bronze" / "orders_raw")
    run(run_id="RUN-COMPAT", table_uri=table_uri, source_path=orders_fixture_path, checkpoint_path=tmp_path / "cp.json")

    writer_view = DeltaTable(table_uri)
    reader_view = DeltaTable(table_uri)  # a second, independent handle

    assert reader_view.version() == writer_view.version()
    assert reader_view.to_pyarrow_table().num_rows == writer_view.to_pyarrow_table().num_rows


def test_table_is_readable_after_a_second_commit(tmp_path: Path, orders_fixture_path: Path):
    table_uri = str(tmp_path / "bronze" / "orders_raw")
    run(run_id="RUN-COMPAT-1", table_uri=table_uri, source_path=orders_fixture_path, checkpoint_path=tmp_path / "cp1.json")
    reader_view = DeltaTable(table_uri)
    version_after_first_run = reader_view.version()

    run(run_id="RUN-COMPAT-2", table_uri=table_uri, source_path=orders_fixture_path, checkpoint_path=tmp_path / "cp2.json")

    # A reader opened before the second commit must still be able to open a
    # fresh view and see the new version -- it should not be pinned to a
    # stale snapshot silently.
    fresh_reader = DeltaTable(table_uri)
    assert fresh_reader.version() > version_after_first_run
