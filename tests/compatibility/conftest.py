import json
import os
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
    workdir = Path(os.environ.get("COMPAT_WORKDIR", "/tmp/compat-work"))
    workdir.mkdir(parents=True, exist_ok=True)
    return str(workdir / "orders_raw")
