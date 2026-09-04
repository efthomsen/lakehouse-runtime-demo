"""Tests the Silver schema-contract validation (additive-safe vs breaking
changes) against local Delta tables -- the mechanism article 3 assumes when
it says Silver tables entering Gold should have stable names and types.
"""

import pyarrow as pa
import pytest
from deltalake import write_deltalake

from silver.prepare_orders import prepare_orders
from silver.table_contract import (
    BRONZE_ORDERS_RAW,
    SILVER_ORDERS,
    SchemaContractViolation,
)


def test_identical_schema_is_no_change():
    change = BRONZE_ORDERS_RAW.classify(BRONZE_ORDERS_RAW.schema())
    assert change.kind == "none"


def test_extra_column_is_additive():
    extended = BRONZE_ORDERS_RAW.schema().append(pa.field("source_region", pa.string()))
    change = BRONZE_ORDERS_RAW.classify(extended)
    assert change.kind == "additive"
    assert change.added == ("source_region",)


def test_missing_column_is_breaking():
    reduced = pa.schema([f for f in BRONZE_ORDERS_RAW.schema() if f.name != "payload"])
    change = BRONZE_ORDERS_RAW.classify(reduced)
    assert change.kind == "breaking"
    assert change.removed == ("payload",)


def test_retyped_column_is_breaking():
    retyped_fields = [
        pa.field("source_page", pa.int64()) if f.name == "source_page" else f for f in BRONZE_ORDERS_RAW.schema()
    ]
    change = BRONZE_ORDERS_RAW.classify(pa.schema(retyped_fields))
    assert change.kind == "breaking"
    assert change.retyped == (("source_page", "int32", "int64"),)


def test_silver_orders_schema_has_the_columns_gold_needs():
    names = set(SILVER_ORDERS.schema().names)
    assert {"order_id", "customer_id", "order_date", "order_status", "net_amount"} <= names


def test_prepare_orders_raises_on_missing_bronze_column(bronze_uri: str):
    broken_schema = pa.schema([f for f in BRONZE_ORDERS_RAW.schema() if f.name != "payload"])
    write_deltalake(bronze_uri, pa.table({n: [] for n in broken_schema.names}, schema=broken_schema))

    with pytest.raises(SchemaContractViolation, match="orders_raw") as excinfo:
        prepare_orders(bronze_uri=bronze_uri)
    assert "payload" in str(excinfo.value)
