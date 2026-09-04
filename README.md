# lakehouse-runtime-demo

A small, runnable reference architecture for **Boundaries of the Lakehouse** —
a three-part write-up on separating compute, table storage, and business
logic in Microsoft Fabric:

1. [Cheap Compute, Real Engineering](https://esbenthomsen.com/writing/cheap-compute-real-engineering) — why the ingestion/Silver job runs as a plain container on Azure Batch, not a notebook.
2. [The Lakehouse Is Not the Runtime](https://esbenthomsen.com/writing/the-lakehouse-is-not-the-runtime) — how `delta-rs` lets that container write Delta tables Fabric can read, without Spark.
3. [Where I Stop Using Python](https://esbenthomsen.com/writing/where-i-stop-using-python) — why Gold-layer business logic moves back into Fabric Materialized Lake Views.

This repo is the evidence, not a slide. Every claim in the articles about the
ingestion/Silver boundary is backed by code and tests here.

```text
SOURCE (synthetic paginated API)
      │
      ▼
python -m ingest.main   ──append──►  bronze.orders_raw / bronze.customers_raw
      │                                          │
      ▼                                          ▼
python -m silver.main   ──normalise─►  silver.orders / silver.customers
                                                  │
                                                  ▼
                                   fabric/gold_materialized_lake_views.sql
                                                  │
                                                  ▼
                                     gold.customer_value / daily_revenue /
                                            commercial_summary
```

## What this demonstrates

- **Same package, three environments** — `src/ingest` and `src/silver` run
  identically on a laptop (`--table-uri ./data/bronze`), in CI (a `tmp_path`
  Delta table), and in a container on Azure Batch (`--table-uri
  abfss://...@onelake.dfs.fabric.microsoft.com/...`).
- **Repeat-safe ingestion** — re-running the same `--run-id`/window is
  detected via a stable `source_event_id` and does not duplicate rows in
  Silver (see `tests/test_silver.py::test_dedup_on_replay`).
- **Bronze/Silver/Gold ownership boundary** — Bronze and Silver are written
  by this package via `delta-rs`; Gold is defined declaratively in
  `fabric/gold_materialized_lake_views.sql` as Materialized Lake Views. This
  repo does not compute Gold in Python, on purpose — that boundary is the
  subject of article 3.
- **A failure/retry demonstration** — `tests/test_ingest.py::test_crash_before_checkpoint`
  reproduces the "ghost retry" scenario from article 2: a committed Delta
  write followed by a crash before the source-progress checkpoint is saved.
- **A compatibility check** — `tests/test_compat.py` reads a table written by
  this package back with a second, independent `deltalake` client instance,
  standing in for "another engine."

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Ingest two synthetic pages into a local Bronze table
python -m ingest.main \
  --run-id RUN-0001 \
  --window-start 2026-09-01T00:00:00Z \
  --window-end   2026-09-02T00:00:00Z \
  --table-uri ./data/bronze/orders_raw \
  --source synthetic-data/orders_sample.json

# Normalise Bronze into Silver
python -m silver.main \
  --bronze-uri ./data/bronze/orders_raw \
  --silver-uri ./data/silver/orders

pytest
```

## Repository layout

```text
lakehouse-runtime-demo/
├── README.md
├── pyproject.toml
├── src/
│   ├── ingest/         # source interaction, pagination, append to Bronze
│   ├── silver/         # technical normalisation, dedup, Bronze -> Silver
│   └── shared/         # config, schemas, run-id/window helpers
├── tests/              # unit + roundtrip + cross-client compatibility tests
├── docker/Dockerfile   # the exact image submitted to Azure Batch
├── batch/task-template.json   # Azure Batch task envelope (see article 1)
├── fabric/gold_materialized_lake_views.sql   # the Gold-layer MLV definitions
├── synthetic-data/     # fixture pages standing in for the source API
└── diagrams/           # pointer to the animated figures on esbenthomsen.com
```

## What this repo deliberately does not do

- It does not implement Gold transformations in Python. That is the point of
  article 3 — Gold logic lives in `fabric/gold_materialized_lake_views.sql`,
  not here.
- It does not include a real Azure Batch pool or Fabric workspace — those are
  environment-specific. `batch/task-template.json` and the Fabric SQL are
  provided as the exact artefacts you would deploy, not a live demo
  environment.
- It does not benchmark cost. The articles are explicit that cost claims
  should be backed by measurements from your own workload, not this repo's
  synthetic data.

## License

MIT — see `LICENSE`.
