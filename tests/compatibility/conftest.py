import json
import os
import uuid
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[1]")
        .appName("lakehouse-runtime-demo-compatibility")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.driver.memory", "1g")
        .getOrCreate()
    )
    yield session
    session.stop()


@pytest.fixture(scope="session")
def version_matrix() -> dict:
    path = Path(__file__).parent / "version_matrix.json"
    return json.loads(path.read_text())


@pytest.fixture
def compat_table_uri() -> str:
    # The volume backing COMPAT_WORKDIR persists across `docker compose run`
    # invocations, so each run gets its own subdirectory -- otherwise a
    # second run appends onto a table an earlier run already created.
    workdir = Path(os.environ.get("COMPAT_WORKDIR", "/tmp/compat-work")) / uuid.uuid4().hex
    workdir.mkdir(parents=True, exist_ok=True)
    return str(workdir / "orders_raw")
