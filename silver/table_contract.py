"""Explicit source/table contracts, used to detect breaking vs. additive
schema changes before Silver runs.

Silver tables entering Gold should already have "stable names and types;
canonical identifiers; standardised timestamps; explicit null behaviour;
technical duplicates resolved... a documented grain" (article 3). This
module makes that contract a checkable object instead of a paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pyarrow as pa


class SchemaContractViolation(ValueError):
    """The observed schema breaks the contract (a column was removed,
    retyped, or a non-null guarantee was loosened)."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    dtype: pa.DataType
    nullable: bool = True


@dataclass(frozen=True)
class SchemaChange:
    kind: Literal["none", "additive", "breaking"]
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    retyped: tuple[tuple[str, str, str], ...] = ()
    loosened_nullability: tuple[str, ...] = ()

    def raise_if_breaking(self, contract_name: str) -> None:
        if self.kind != "breaking":
            return
        parts = []
        if self.removed:
            parts.append(f"removed columns {self.removed}")
        if self.retyped:
            parts.append(f"retyped columns {self.retyped}")
        if self.loosened_nullability:
            parts.append(f"columns no longer guaranteed non-null {self.loosened_nullability}")
        raise SchemaContractViolation(
            f"breaking schema change against contract '{contract_name}': {'; '.join(parts)}"
        )


@dataclass(frozen=True)
class TableContract:
    name: str
    grain: str
    columns: tuple[ColumnSpec, ...]

    def schema(self) -> pa.Schema:
        return pa.schema([pa.field(c.name, c.dtype, nullable=c.nullable) for c in self.columns])

    def classify(self, observed: pa.Schema) -> SchemaChange:
        expected_by_name = {c.name: c for c in self.columns}
        observed_by_name = {f.name: f for f in observed}

        added = tuple(name for name in observed_by_name if name not in expected_by_name)
        removed = tuple(name for name in expected_by_name if name not in observed_by_name)

        retyped: list[tuple[str, str, str]] = []
        loosened_nullability: list[str] = []
        for name, expected in expected_by_name.items():
            observed_field = observed_by_name.get(name)
            if observed_field is None:
                continue
            if observed_field.type != expected.dtype:
                retyped.append((name, str(expected.dtype), str(observed_field.type)))
            # A contract column that guarantees non-null but is observed as
            # nullable has had that guarantee loosened -- downstream code
            # relying on "never null" is now unsafe. The reverse (contract
            # allows null, observed is non-nullable) is strictly stronger
            # than promised and is compatible.
            if not expected.nullable and observed_field.nullable:
                loosened_nullability.append(name)

        if removed or retyped or loosened_nullability:
            kind = "breaking"
        elif added:
            kind = "additive"
        else:
            kind = "none"

        return SchemaChange(
            kind=kind,
            added=added,
            removed=removed,
            retyped=tuple(retyped),
            loosened_nullability=tuple(loosened_nullability),
        )


BRONZE_ORDERS_RAW = TableContract(
    name="orders_raw",
    grain="one row per delivered source event (replays visible)",
    columns=(
        ColumnSpec("source_event_id", pa.string(), nullable=False),
        ColumnSpec("source_updated_at", pa.timestamp("us", "UTC"), nullable=False),
        ColumnSpec("ingested_at", pa.timestamp("us", "UTC"), nullable=False),
        ColumnSpec("ingestion_run_id", pa.string(), nullable=False),
        ColumnSpec("source_page", pa.int32(), nullable=False),
        ColumnSpec("payload", pa.string(), nullable=False),
    ),
)

SILVER_ORDERS = TableContract(
    name="silver.orders",
    grain="one row per order_id",
    columns=(
        ColumnSpec("order_id", pa.string(), nullable=False),
        ColumnSpec("customer_id", pa.string(), nullable=False),
        ColumnSpec("order_date", pa.date32(), nullable=False),
        ColumnSpec("order_status", pa.string(), nullable=False),
        ColumnSpec("net_amount", pa.decimal128(18, 2), nullable=False),
        ColumnSpec("source_updated_at", pa.timestamp("us", "UTC"), nullable=False),
        ColumnSpec("ingestion_run_id", pa.string(), nullable=False),
    ),
)

SILVER_CUSTOMERS = TableContract(
    name="silver.customers",
    grain="one row per customer_id",
    columns=(
        ColumnSpec("customer_id", pa.string(), nullable=False),
        ColumnSpec("market", pa.string(), nullable=False),
        ColumnSpec("source_updated_at", pa.timestamp("us", "UTC"), nullable=False),
        ColumnSpec("ingestion_run_id", pa.string(), nullable=False),
    ),
)
