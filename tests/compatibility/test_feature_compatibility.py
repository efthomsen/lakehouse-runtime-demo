"""Reproduces article 2's incident shape as an opt-in, version-keyed test:

    1. create a table with the external delta-rs writer
    2. enable column mapping through a pinned Spark/Delta engine
    3. retry the external write
    4. record and assert against the behaviour expected for the pinned
       version matrix -- explicitly NOT a hard-coded "must fail"

If a future `deltalake` version changes the observed outcome, the fix is to
update tests/compatibility/version_matrix.json (an article update), not to
special-case this test.
"""

from __future__ import annotations

import importlib.metadata
import platform
from datetime import datetime, timezone

from deltalake import DeltaTable

from ingestion.append_bronze import append_page, to_bronze_table
from ingestion.source import SyntheticOrdersAPI


def _pinned_pair() -> str:
    deltalake_version = importlib.metadata.version("deltalake")
    delta_spark_version = importlib.metadata.version("delta-spark")
    return f"deltalake={deltalake_version}|delta-spark={delta_spark_version}"


def _expectation(version_matrix: dict) -> dict:
    pair = _pinned_pair()
    expected = version_matrix["expectations"].get(pair)
    if expected is None:
        import pytest

        pytest.fail(
            f"No recorded expectation for {pair}. Run the compatibility profile, record the "
            f"observed behaviour in tests/compatibility/version_matrix.json, and treat the "
            f"change as an article update -- do not hard-code pass/fail."
        )
    return expected


def _attempt(fn) -> dict:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 -- we want the exact class/message for the record
        return {
            "outcome": "refused",
            "exception": [c.__name__ for c in type(exc).__mro__],
            "message": str(exc),
        }
    return {"outcome": "succeeds"}


def _assert_matches(observed: dict, expected: dict) -> None:
    assert observed["outcome"] == expected["outcome"], (observed, expected)
    if expected["outcome"] != "refused":
        return
    assert expected["exception"] in observed["exception"], (observed, expected)
    assert expected["message_contains"] in observed["message"], (observed, expected)


def _append_page(table_uri: str, *, page: int, run_id: str = "RUN-0187") -> int:
    source_page = SyntheticOrdersAPI(pages=1, page_size=20, start_page=page).fetch(page)
    table = to_bronze_table(source_page.records, run_id=run_id, page=page, ingested_at=datetime.now(timezone.utc))
    return append_page(table_uri, table, run_id=run_id, page=page)


def test_feature_compatibility_incident_shape(spark, version_matrix, compat_table_uri):
    expected = _expectation(version_matrix)

    # 1. External writer creates the table.
    _append_page(compat_table_uri, page=41)
    assert expected["append_plain"] == "succeeds"

    # Spark reads what the external writer committed.
    spark_row_count = spark.read.format("delta").load(compat_table_uri).count()
    assert spark_row_count == 20
    assert expected["spark_read_after_external_append"] == "succeeds"

    # 2. Spark enables column mapping -- the maintenance change from the
    # article 2 field note ("A Spark-side maintenance change deliberately
    # enabled column mapping on a table originally written through delta-rs").
    spark.sql(f"ALTER TABLE delta.`{compat_table_uri}` SET TBLPROPERTIES ('delta.columnMapping.mode' = 'name')")

    protocol = DeltaTable(compat_table_uri).protocol()
    expected_protocol = expected["protocol_after_column_mapping"]
    assert protocol.min_reader_version == expected_protocol["min_reader_version"]
    assert protocol.min_writer_version == expected_protocol["min_writer_version"]
    for feature in expected_protocol["reader_features_include"]:
        assert feature in (protocol.reader_features or [])
    for feature in expected_protocol["writer_features_include"]:
        assert feature in (protocol.writer_features or [])

    # The table format itself remained open -- "the table format remained
    # open; the practical interoperability envelope had changed" (article
    # 2). Whether the *external reader* can still read it is a separate,
    # version-keyed question, same as the writer question below: at the
    # pinned versions here, plain `ALTER TABLE ... columnMapping.mode`
    # leaves the table at reader version 2, which delta-rs 1.6.x's
    # to_pyarrow_table() path refuses outright (it only handles version 1
    # or the table-features-encoded version 3) -- the envelope narrowed on
    # the read side too, not only the write side.
    observed_read = _attempt(lambda: DeltaTable(compat_table_uri).to_pyarrow_table())
    _assert_matches(observed_read, expected["external_read_after_column_mapping_name"])

    # 3. External writer retries a plain append.
    observed_append = _attempt(lambda: _append_page(compat_table_uri, page=42))
    _assert_matches(observed_append, expected["external_append_after_column_mapping_name"])

    # And a schema-evolving append (this is where the envelope narrows further).
    def _schema_merge_append():
        import pyarrow as pa
        from deltalake import write_deltalake

        extra_page = SyntheticOrdersAPI(pages=1, page_size=5, start_page=43).fetch(43)
        table = to_bronze_table(extra_page.records, run_id="RUN-0187", page=43, ingested_at=datetime.now(timezone.utc))
        table = table.append_column("source_region", pa.array([None] * table.num_rows, type=pa.string()))
        write_deltalake(compat_table_uri, table, mode="append", schema_mode="merge")

    observed_merge = _attempt(_schema_merge_append)
    _assert_matches(observed_merge, expected["external_schema_merge_after_column_mapping_name"])

    # 4. The readout that fills the article's LAST TESTED placeholders.
    print("\n// LAST TESTED")
    print(f"delta-rs (deltalake): {importlib.metadata.version('deltalake')}    "
          f"Spark / Delta runtime: {importlib.metadata.version('pyspark')} / "
          f"delta-spark {importlib.metadata.version('delta-spark')}")
    print(f"Observed: {datetime.now(timezone.utc).date().isoformat()}  on: {platform.node()}")
    print(f"external read after column mapping (name): {observed_read['outcome']}")
    print(f"external append after column mapping (name): {observed_append['outcome']}")
    print(f"external schema-merge after column mapping (name): {observed_merge['outcome']}")
    print(f"protocol: reader {protocol.min_reader_version} / writer {protocol.min_writer_version}  "
          f"features: {protocol.writer_features}")
