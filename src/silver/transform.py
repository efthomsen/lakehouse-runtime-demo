"""Bronze -> Silver: technical normalisation and deduplication.

This module decides types, identity, and shape (per article 2's Silver
gate). It must not decide business meaning -- there is deliberately no
"active customer" or "completed order" concept here. That logic lives in
fabric/gold_materialized_lake_views.sql, not in this package.
"""

from __future__ import annotations

import pyarrow as pa
import pyarrow.compute as pc
from deltalake import DeltaTable, write_deltalake


def bronze_to_silver_table(bronze: pa.Table) -> pa.Table:
    """Resolve technical duplicates and normalise types.

    The technical dedup rule: the most recently ingested record for a given
    source_event_id wins. This is a Silver decision (identity), not a Gold
    one (which order counts as "completed").
    """
    if bronze.num_rows == 0:
        return bronze.select(["customer_id", "order_date", "order_status", "net_amount"]).rename_columns(
            ["customer_id", "order_date", "order_status", "net_amount"]
        )

    sorted_table = bronze.sort_by([("ingested_at", "descending")])
    seen: set[str] = set()
    keep_rows: list[int] = []
    event_ids = sorted_table.column("source_event_id").to_pylist()
    for i, event_id in enumerate(event_ids):
        if event_id in seen:
            continue
        seen.add(event_id)
        keep_rows.append(i)

    deduped = sorted_table.take(keep_rows)
    return pa.table(
        {
            "order_id": deduped.column("source_event_id"),
            "customer_id": deduped.column("customer_id"),
            "order_date": pc.cast(deduped.column("order_date"), pa.date32()),
            "order_status": pc.utf8_lower(deduped.column("order_status")),
            "net_amount": pc.cast(deduped.column("net_amount"), pa.float64()),
        }
    )


def run_bronze_to_silver(bronze_uri: str, silver_uri: str) -> int:
    bronze = DeltaTable(bronze_uri).to_pyarrow_table()
    silver = bronze_to_silver_table(bronze)
    write_deltalake(silver_uri, silver, mode="overwrite")
    return silver.num_rows
