"""Bronze -> Silver for orders: technical normalisation and deduplication.

This module decides types, identity, and shape (article 2's "Silver gate").
It must not decide business meaning -- there is deliberately no "completed
order" concept here beyond lower-casing the status string. That logic lives
in gold/materialized_lake_views.sql, not here.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pyarrow as pa
import pyarrow.compute as pc
from deltalake import DeltaTable, write_deltalake

from silver.table_contract import BRONZE_ORDERS_RAW, SILVER_ORDERS


def dedupe_by_source_event(bronze: pa.Table) -> pa.Table:
    """Keep the most recently updated record for each source_event_id, then
    the most recently ingested one -- the technical uniqueness rule article
    2 assigns to Silver."""
    if bronze.num_rows == 0:
        return bronze

    order = pc.sort_indices(
        bronze,
        sort_keys=[("source_updated_at", "descending"), ("ingested_at", "descending")],
    )
    sorted_table = bronze.take(order)

    seen: set[str] = set()
    keep_rows: list[int] = []
    for i, event_id in enumerate(sorted_table.column("source_event_id").to_pylist()):
        if event_id in seen:
            continue
        seen.add(event_id)
        keep_rows.append(i)

    return sorted_table.take(keep_rows)


def parse_bronze_orders(bronze: pa.Table) -> pa.Table:
    payloads = [json.loads(p) for p in bronze.column("payload").to_pylist()]
    source_updated_at = bronze.column("source_updated_at").to_pylist()
    ingestion_run_id = bronze.column("ingestion_run_id").to_pylist()

    return pa.table(
        {
            "order_id": [p["order_id"] for p in payloads],
            "customer_id": [p["customer_id"] for p in payloads],
            "order_date": [_parse_date(p["order_date"]) for p in payloads],
            "order_status": [p["status"].lower() for p in payloads],
            "net_amount": [Decimal(p["net_amount"]) for p in payloads],
            "source_updated_at": source_updated_at,
            "ingestion_run_id": ingestion_run_id,
        },
        schema=SILVER_ORDERS.schema(),
    )


def _parse_date(value: str):
    from datetime import date

    return date.fromisoformat(value)


def prepare_orders(*, bronze_uri: str, silver_uri: str | None = None, storage_options: dict | None = None) -> pa.Table:
    bronze = DeltaTable(bronze_uri, storage_options=storage_options).to_pyarrow_table()
    BRONZE_ORDERS_RAW.classify(bronze.schema).raise_if_breaking(BRONZE_ORDERS_RAW.name)

    deduped = dedupe_by_source_event(bronze)
    silver = parse_bronze_orders(deduped)
    SILVER_ORDERS.classify(silver.schema).raise_if_breaking(SILVER_ORDERS.name)

    if silver_uri:
        # Silver is a derived, rebuildable table -- overwrite rather than merge.
        write_deltalake(silver_uri, silver, mode="overwrite", schema_mode="overwrite", storage_options=storage_options)

    return silver
