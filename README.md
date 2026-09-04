# lakehouse-runtime-demo

**The lakehouse is not the runtime.**

The companion repository for *Boundaries of the Lakehouse*, a three-part
field report on separating compute, table storage, and business logic in
Microsoft Fabric:

1. **Cheap Compute, Real Engineering**: why application-like Python data
   workloads run on Azure Batch, and how the execution model itself evolved.
2. **Keep the Lakehouse, Move the Compute**: what `delta-rs` makes
   possible, and where open-table interoperability breaks.
3. **Where Python Stops**: why Gold-layer business logic moves back into
   Fabric through Materialized Lake Views.

Articles: <https://esbenthomsen.com/writing> (the site is pre-launch as of
this repo's rev2 restructure; per-article links will be added once
published).

> This series distils patterns from production data-platform work into a
> synthetic architecture. Names, data, scale, and some implementation
> choices have been changed to make the trade-offs reproducible and safe to
> publish.

## The architecture

```text
                     CONTROL
        ┌───────────────────────────────┐
        │ FABRIC PIPELINE               │
        │ submit · monitor · gate       │
        └───────────────┬───────────────┘
                        │
                        ▼
SOURCE ──► AZURE BATCH / PYTHON WORKLOAD
                        │
                        │ delta-rs
                        ▼
              BRONZE / SILVER DELTA TABLES  (OneLake)
                        │
                        ▼
              MATERIALIZED LAKE VIEWS (GOLD)
                        │
                        ▼
                REPORTS / CONSUMERS
```

This repo is the reference architecture, not a sanitised dump of any
production repository: a deliberately designed implementation of that
diagram. The default path runs entirely locally, with zero cloud
dependencies.

## Quickstart

```bash
uv sync
uv run pytest tests/core                                   # default: no cloud, no second engine

# Run the runtime image's workload directly, no Docker needed
uv run python runtime/image/entrypoint.py \
  --run-id RUN-0187 --window-start 2026-09-01T00:00:00Z --window-end 2026-09-02T00:00:00Z \
  --table-uri ./data/bronze/orders_raw --pages 10

# The same workload as the image Azure Batch actually runs
docker compose run --rm runtime

# Opt-in: a pinned Spark/Delta engine reproduces article 2's incident shape
docker compose --profile compatibility run --rm compatibility-test
```

(The two `docker compose` commands need a Docker host. They are not part
of the default no-cloud test path above.)

## Repository layout

```text
lakehouse-runtime-demo/
├── README.md
├── pyproject.toml, uv.lock, .python-version   # dev/test project: ingestion, silver, orchestration
├── runtime/
│   └── image/
│       ├── Dockerfile         # the exact image submitted to Azure Batch
│       ├── pyproject.toml     # the shipped workload's own uv project
│       ├── uv.lock
│       └── entrypoint.py
├── legacy/
│   └── runtime-clone/         # the earlier "clone + uv at task start" model: history, not a peer option
│       ├── README.md
│       ├── task-command.sh
│       └── example-script.py
├── orchestration/
│   ├── submit_batch_job.py        # digest-only Batch task submission
│   └── fabric_pipeline_contract.md
├── ingestion/
│   ├── source.py               # the synthetic paginated source client
│   ├── append_bronze.py        # Bronze append + ingest_window
│   └── checkpoint.py           # source-progress checkpoint, separate from the Delta commit
├── silver/
│   ├── table_contract.py       # explicit schema contracts (additive vs. breaking)
│   ├── prepare_orders.py
│   └── prepare_customers.py
├── gold/
│   └── materialized_lake_views.sql
├── benchmark/
│   └── README.md               # the reproducible Fabric-vs-Batch comparison
├── tests/
│   ├── core/                   # local filesystem Delta, no Azure, fast
│   └── compatibility/          # opt-in cross-engine profile
└── docker-compose.yml          # `--profile compatibility` starts a pinned Spark/Delta engine
```

A few additions beyond the series brief's tree, all needed to make the repo
actually runnable rather than documentation-only scaffolding: the root
`pyproject.toml`/`uv.lock`/`.python-version` (the dev/test project), package
`__init__.py` files, `ingestion/source.py` (the source client itself),
`silver/prepare_customers.py` (so `silver.customers`, a Gold input, is
actually produced), `tests/core/test_submit_batch_job.py`, and
`tests/compatibility/Dockerfile` + `version_matrix.json` (the pinned engine
image and the expectation matrix `test_feature_compatibility.py` checks
against).

## The three execution tiers, and why `runtime/image/` is primary

```text
RUNTIME CHECKOUT              LIGHTWEIGHT VERSIONED ARTIFACT      IMMUTABLE DEPLOYMENT ARTIFACT
git clone HEAD + uv     →     pinned revision + lockfile + uv →   tested image + pinned digest
(legacy/runtime-clone/)                                           (runtime/image/, primary)
```

`uv` is not replaced by Docker: it stays the dependency resolver and
Python runner *inside* the build (see `runtime/image/Dockerfile`). What
moved is *when* the executable version is fixed: at release, not at task
start. See [`legacy/runtime-clone/README.md`](legacy/runtime-clone/README.md)
for the full history and what the earlier model got right.

## Pinning discipline

- The `uv` runtime uses `uv.lock` in both projects (root and
  `runtime/image/`). CI checks the two lockfiles agree on `deltalake` and
  `pyarrow`.
- The Docker deployment example (`orchestration/submit_batch_job.py`)
  refuses any image reference that isn't `repo@sha256:<64 hex>`: a
  floating tag can move under a pinned run record without anyone noticing.
- PEP 723 inline metadata (`legacy/runtime-clone/example-script.py`) makes
  a script self-describing. It is not by itself sufficient
  reproducibility: the reproducible unit is pinned code plus
  deterministic dependency resolution (a lockfile).

## The synthetic domain model

Bronze: `orders_raw`, `customers_raw`. Silver: `silver.orders`,
`silver.customers` (`silver.calendar` is Fabric-maintained, not produced
here). Gold: `gold.customer_value`, `gold.daily_revenue`,
`gold.commercial_summary`. The source is an ordinary paginated API
(`ingestion/source.py`).

An example run record, in the series' shared motifs:

```text
RUN-0187 · COMMIT 8A4C1D · IMAGE SHA256:... · DELTA VERSION 1431 → 1432
```

## What is verified here vs. what still needs a Fabric workspace

Verified in this repo, by test:

- The ghost retry (`tests/core/test_ghost_retry.py`): a committed Delta
  write, an interrupted checkpoint, and a retry, against a real local
  Delta table.
- Schema-contract classification (`tests/core/test_schema_contract.py`):
  additive vs. breaking Bronze/Silver changes.
- Digest-only Batch task submission (`tests/core/test_submit_batch_job.py`).
- The cross-engine incident shape (`tests/compatibility/`, opt-in): real
  behaviour observed against a pinned `deltalake`/Spark/`delta-spark` pair,
  recorded in `tests/compatibility/version_matrix.json`, not asserted from
  memory.

Explicitly **not** verified against a real Fabric workspace. See the
`UNVERIFIED` markers in each file before treating them as final:

- `gold/materialized_lake_views.sql`: the exact MLV syntax and refresh
  behaviour.
- `orchestration/fabric_pipeline_contract.md` §8: which Fabric activity
  type submits the Batch task, its polling cadence, and how it reads the
  run manifest.
- `benchmark/README.md`: the Fabric Python notebook path's setup
  mechanics, and every `[measure]` placeholder.

## License

MIT: see [`LICENSE`](LICENSE).
