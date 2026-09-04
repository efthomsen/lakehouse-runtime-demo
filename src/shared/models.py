"""Schemas shared between the ingest and silver stages.

Kept deliberately small: this repo demonstrates the runtime/table boundary,
not a full order-management domain model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RawOrderRecord:
    """A single Bronze-layer order record, as it arrived from the source."""

    source_event_id: str
    source_updated_at: str
    ingested_at: str
    ingestion_run_id: str
    source_page: int
    customer_id: str
    order_date: str
    order_status: str
    net_amount: float

    @staticmethod
    def from_source_payload(payload: dict, *, run_id: str, page: int) -> "RawOrderRecord":
        return RawOrderRecord(
            source_event_id=payload["event_id"],
            source_updated_at=payload["updated_at"],
            ingested_at=datetime.now(timezone.utc).isoformat(),
            ingestion_run_id=run_id,
            source_page=page,
            customer_id=payload["customer_id"],
            order_date=payload["order_date"],
            order_status=payload["status"],
            net_amount=float(payload["net_amount"]),
        )


@dataclass(frozen=True)
class SilverOrderRecord:
    """A technically dependable order record, ready for Gold-layer meaning."""

    order_id: str
    customer_id: str
    order_date: str
    order_status: str
    net_amount: float
