"""Ingestion entrypoint: fetch a bounded window from the source and append it
to a Bronze Delta table via delta-rs.

    python -m ingest.main \
      --run-id RUN-0001 \
      --window-start 2026-09-01T00:00:00Z \
      --window-end   2026-09-02T00:00:00Z \
      --table-uri ./data/bronze/orders_raw \
      --source synthetic-data/orders_sample.json

The same command runs on a laptop, in CI, or in the container submitted to
Azure Batch -- only --table-uri changes (a local path vs. an
abfss://...@onelake.dfs.fabric.microsoft.com/... URI).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

import pyarrow as pa
from deltalake import DeltaTable, write_deltalake
from deltalake.exceptions import TableNotFoundError

from ingest.source import PaginatedSource
from shared.checkpoint import Checkpoint
from shared.models import RawOrderRecord


def append_page(table_uri: str, records: list[RawOrderRecord]) -> None:
    if not records:
        return
    table = pa.Table.from_pylist([asdict(r) for r in records])
    write_deltalake(table_uri, table, mode="append")


def table_version(table_uri: str) -> int | None:
    try:
        return DeltaTable(table_uri).version()
    except TableNotFoundError:
        return None


def run(*, run_id: str, table_uri: str, source_path: Path, checkpoint_path: Path, crash_after_page: int | None = None) -> None:
    source = PaginatedSource(source_path)
    checkpoint = Checkpoint(checkpoint_path)

    for page_number, raw_records in source.pages():
        if checkpoint.is_complete(run_id, page_number):
            print(f"page {page_number} already ingested for {run_id}, skipping")
            continue

        records = [RawOrderRecord.from_source_payload(r, run_id=run_id, page=page_number) for r in raw_records]
        append_page(table_uri, records)
        print(f"appended page {page_number} ({len(records)} records) -> version {table_version(table_uri)}")

        if crash_after_page == page_number:
            # Simulates the "ghost retry" from article 2: the Delta commit
            # above already succeeded, but we exit before the checkpoint
            # below is written. Re-running with the same --run-id will
            # re-fetch and re-append this same page.
            print("simulated crash before checkpoint write", file=sys.stderr)
            sys.exit(1)

        checkpoint.mark_complete(run_id, page_number)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--table-uri", required=True)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--checkpoint-path", type=Path, default=Path(".ingest-checkpoint.json"))
    parser.add_argument("--crash-after-page", type=int, default=None, help="testing hook: exit before checkpointing this page")
    args = parser.parse_args(argv)

    # window-start/window-end bound which source records this run is
    # responsible for; the fixture source here doesn't filter by them, but a
    # real HTTP source would pass them through as query parameters.
    run(
        run_id=args.run_id,
        table_uri=args.table_uri,
        source_path=args.source,
        checkpoint_path=args.checkpoint_path,
        crash_after_page=args.crash_after_page,
    )


if __name__ == "__main__":
    main()
