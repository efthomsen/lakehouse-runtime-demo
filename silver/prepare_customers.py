"""Bronze -> Silver for customers: same shape as prepare_orders.py, for the
customers_raw Bronze table feeding silver.customers (a Gold input to
gold.customer_value)."""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.compute as pc
from deltalake import DeltaTable, write_deltalake

from silver.table_contract import SILVER_CUSTOMERS


def dedupe_by_source_event(bronze: pa.Table) -> pa.Table:
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


def parse_bronze_customers(bronze: pa.Table) -> pa.Table:
    payloads = [json.loads(p) for p in bronze.column("payload").to_pylist()]
    return pa.table(
        {
            "customer_id": [p["customer_id"] for p in payloads],
            "market": [p["market"] for p in payloads],
            "source_updated_at": bronze.column("source_updated_at").to_pylist(),
            "ingestion_run_id": bronze.column("ingestion_run_id").to_pylist(),
        },
        schema=SILVER_CUSTOMERS.schema(),
    )


def prepare_customers(*, bronze_uri: str, silver_uri: str | None = None, storage_options: dict | None = None) -> pa.Table:
    bronze = DeltaTable(bronze_uri, storage_options=storage_options).to_pyarrow_table()
    deduped = dedupe_by_source_event(bronze)
    silver = parse_bronze_customers(deduped)
    SILVER_CUSTOMERS.classify(silver.schema).raise_if_breaking(SILVER_CUSTOMERS.name)

    if silver_uri:
        write_deltalake(silver_uri, silver, mode="overwrite", schema_mode="overwrite", storage_options=storage_options)

    return silver
