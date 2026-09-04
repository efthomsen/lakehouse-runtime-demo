"""Ingestion: fetch a bounded window from the source and append it to a
Bronze Delta table via delta-rs.

Bronze represents what arrived, not what the business eventually wants the
data to mean (article 2): source identity is preserved (``source_event_id``,
``source_updated_at``), ingestion metadata is explicit, and the raw payload
is kept verbatim so a replay is visible rather than silently absorbed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import pyarrow as pa
from deltalake import CommitProperties, DeltaTable, write_deltalake
from deltalake.exceptions import TableNotFoundError

from ingestion.checkpoint import Checkpoint
from ingestion.source import SourcePage
from silver.table_contract import BRONZE_ORDERS_RAW

# The contract is the single source of truth for this schema; the writer and
# the schema-contract check must never drift apart.
BRONZE_SCHEMA = BRONZE_ORDERS_RAW.schema()


class SourcePayloadError(ValueError):
    """A source record is missing a field Bronze requires to preserve identity."""


def validate_page(page: SourcePage) -> None:
    for record in page.records:
        if "event_id" not in record or not record["event_id"]:
            raise SourcePayloadError(f"page {page.page}: record missing event_id")
        if "updated_at" not in record or not record["updated_at"]:
            raise SourcePayloadError(f"page {page.page}: record {record.get('event_id')} missing updated_at")


def _parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def to_bronze_table(records: list[dict], *, run_id: str, page: int, ingested_at: datetime) -> pa.Table:
    columns: dict[str, list] = {name: [] for name in BRONZE_SCHEMA.names}
    for record in records:
        columns["source_event_id"].append(record["event_id"])
        columns["source_updated_at"].append(_parse_iso8601(record["updated_at"]))
        columns["ingested_at"].append(ingested_at)
        columns["ingestion_run_id"].append(run_id)
        columns["source_page"].append(page)
        columns["payload"].append(json.dumps(record, sort_keys=True))
    return pa.table(columns, schema=BRONZE_SCHEMA)


def append_page(
    table_uri: str,
    table: pa.Table,
    *,
    run_id: str,
    page: int,
    storage_options: dict | None = None,
) -> int:
    write_deltalake(
        table_uri,
        table,
        mode="append",
        storage_options=storage_options,
        commit_properties=CommitProperties(
            custom_metadata={"ingestion_run_id": run_id, "source_page": str(page)}
        ),
    )
    return DeltaTable(table_uri, storage_options=storage_options).version()


def _table_version(table_uri: str) -> int | None:
    try:
        return DeltaTable(table_uri).version()
    except TableNotFoundError:
        return None


@dataclass(frozen=True)
class IngestResult:
    run_id: str
    pages_appended: list[int] = field(default_factory=list)
    pages_skipped: list[int] = field(default_factory=list)
    first_version: int | None = None
    last_version: int | None = None
    rows_appended: int = 0


def ingest_window(
    *,
    source,
    table_uri: str,
    run_id: str,
    checkpoint: Checkpoint,
    after_commit: Callable[[int, int], None] | None = None,
) -> IngestResult:
    """Fetch and append every page the source yields, skipping pages the
    checkpoint already marks complete for this run_id.

    ``after_commit`` is the fault-injection seam used to reproduce the ghost
    retry: it runs after the Delta commit but before the checkpoint write,
    and raising from it (see CheckpointWriteInterrupted) leaves the table
    ahead of the checkpoint, exactly as a real crash would.
    """
    pages_appended: list[int] = []
    pages_skipped: list[int] = []
    first_version: int | None = None
    last_version: int | None = None
    rows_appended = 0

    for page in source.pages():
        if checkpoint.is_complete(run_id, page.page):
            pages_skipped.append(page.page)
            continue

        validate_page(page)
        table = to_bronze_table(page.records, run_id=run_id, page=page.page, ingested_at=datetime.now(timezone.utc))
        version = append_page(table_uri, table, run_id=run_id, page=page.page)

        if first_version is None:
            first_version = version
        last_version = version
        rows_appended += len(page.records)
        pages_appended.append(page.page)

        if after_commit is not None:
            after_commit(page.page, version)

        checkpoint.mark_complete(run_id, page.page, delta_version=version)

    return IngestResult(
        run_id=run_id,
        pages_appended=pages_appended,
        pages_skipped=pages_skipped,
        first_version=first_version,
        last_version=last_version,
        rows_appended=rows_appended,
    )
