# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "deltalake==1.6.3",
#     "pyarrow==25.0.1",
# ]
# ///
"""LEGACY -- the whole workload as a single self-contained script, the shape
it had before ingestion/ and silver/ existed as packages. Runs via
`uv run --script`, which reads the PEP 723 block above and resolves an
ephemeral environment at task start.

Inline metadata like this makes the script self-describing. It does not
make it reproducible on its own -- there is no lockfile, and `main` can move
between the moment this ran and the moment someone tries to reproduce it.
That is the next tier up: a pinned revision plus a lockfile (still `uv`,
still no image). See ../../runtime/image/ for the tier this repo actually
ships.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import pyarrow as pa
from deltalake import write_deltalake


@dataclass(frozen=True)
class RawRecord:
    source_event_id: str
    source_updated_at: str
    ingested_at: str
    ingestion_run_id: str
    source_page: int
    payload: str


def fetch_page(page: int, page_size: int = 100) -> list[dict]:
    """Stands in for an HTTP call to the ordinary paginated source API."""
    return [
        {"event_id": f"evt-{page:06d}-{i:04d}", "updated_at": datetime.now(timezone.utc).isoformat()}
        for i in range(page_size)
    ]


def to_table(records: list[dict], *, run_id: str, page: int) -> pa.Table:
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        RawRecord(
            source_event_id=r["event_id"],
            source_updated_at=r["updated_at"],
            ingested_at=now,
            ingestion_run_id=run_id,
            source_page=page,
            payload=json.dumps(r, sort_keys=True),
        )
        for r in records
    ]
    return pa.Table.from_pylist([asdict(row) for row in rows])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--table-uri", required=True)
    parser.add_argument("--pages", type=int, default=1)
    args = parser.parse_args()

    for page in range(1, args.pages + 1):
        table = to_table(fetch_page(page), run_id=args.run_id, page=page)
        write_deltalake(args.table_uri, table, mode="append")
        print(f"appended page {page}")


if __name__ == "__main__":
    main()
