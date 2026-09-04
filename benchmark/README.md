# Benchmark: Fabric Python notebook vs. Azure Batch

The article series is explicit that dramatic percentages from private
systems are unauditable, so it does not publish them. This is the
reproducible synthetic benchmark instead: one workload — paginate a source
API, validate, append to a Delta table — implemented for both execution
paths.

> Production experience with this workload class motivated the benchmark;
> the published figures come from the reproducible synthetic
> implementation.

**Do not publish a single number.** Batch and Fabric have different
purchasing models; forcing them into one number is the mistake this
benchmark exists to avoid. Report the two views below every time.

## Workload definition

The same `ingestion` package (`ingestion.append_bronze.ingest_window` via
`runtime/image/entrypoint.py`) runs on both paths, with a fixed synthetic
volume:

```bash
--pages 200 --page-size 10000    # 2,000,000 rows, fixed for every run measured
```

## How to run

**Batch path** (image-based, this repo's primary runtime):

```bash
docker compose run --rm runtime -- \
  --run-id RUN-BENCH-BATCH --window-start 2026-09-01T00:00:00Z --window-end 2026-09-02T00:00:00Z \
  --table-uri /data/bronze/orders_raw --pages 200 --page-size 10000 \
  --manifest-path /data/manifests/RUN-BENCH-BATCH.json
```

Time the container from submission to exit; read `rows_appended`,
`pages_appended`, and the version delta from the manifest.

**Fabric Python notebook path** — **UNVERIFIED mechanics.** The intent is a
notebook cell that installs the same pinned `ingestion` wheel
(`uv build` in `runtime/image/` produces it) and calls
`ingest_window` directly against a OneLake `abfss://` table URI. The exact
notebook setup (environment, `%pip install` vs. a custom environment, which
Fabric capacity SKU) has not been run in a real workspace — record it here
once it has, alongside the LAST TESTED stamp the articles require.

Time from notebook cell start to completion; Fabric's own run-history view
supplies compute startup and execution duration separately.

## What to time and where it comes from

| Timestamp | Batch source | Fabric notebook source |
|---|---|---|
| Compute startup | container scheduling → first log line | Fabric session start → first cell output |
| Processing duration | first `page_committed` log → `run_complete` log | notebook cell start → cell completion |
| Peak memory | container stats (`docker stats` / cgroup) | Fabric monitoring hub, per-session |

## Measured execution

Report exactly this table; every cell is a placeholder until a real run
fills it in — do not fabricate numbers.

| Metric | Value |
|---|---|
| Wall-clock duration | `[measure]` |
| Compute startup time | `[measure]` |
| Processing duration | `[measure]` |
| Peak memory | `[measure]` |
| Rows / files processed | `[fixed synthetic volume]` (2,000,000 rows / `--pages 200 --page-size 10000`) |
| Output file count | `[measure]` |
| Developer setup / deploy steps | `[count]` |

## Economic interpretation

```text
Batch:
  Metered VM cost for this execution

Fabric Python notebook:
  Capacity consumption for the execution
  Incremental invoice cost may be zero when capacity is already purchased
  Opportunity cost is shared-capacity consumption and possible contention
```

Prepaid Fabric capacity converts a billing question into a contention
question. It does not make compute free; it makes its cost harder to see.

## Secondary comparison: clone+uv vs. image-based startup

There is no useful *cost* competition between clone+`uv`
(`legacy/runtime-clone/`) and container+`uv` (`runtime/image/`) — same
underlying Batch compute. Their difference is release behaviour and cold
start only:

- Code acquisition: `git clone` vs. image pull.
- Dependency preparation: `uv` resolving at task start vs. already baked
  into image layers.
- Time to first application instruction.

This is a release-behaviour and cold-start difference, not an economic
one — report it separately from the primary comparison above and never
combine it with the Batch-vs-Fabric cost figures.

## Benchmark matrix

Nine dimensions across three execution paths. Quantitative cells are
`[measure]`; qualitative cells reflect this repo's actual design.

| Dimension | Fabric Python notebook | Batch + pinned `uv` workload (`legacy/runtime-clone/`) | Batch + container (`runtime/image/`) |
|---|---|---|---|
| Startup time | `[measure]` | `[measure]` | `[measure]` |
| Runtime | `[measure]` | `[measure]` | `[measure]` |
| Incremental billing | capacity consumption, may be $0 on prepaid capacity | metered VM cost | metered VM cost |
| Capacity consumption | shared Fabric capacity, contention risk | dedicated Batch node | dedicated Batch node |
| Dependency model | notebook environment / `%pip install` | `uv` resolves at task start | pinned in the image, resolved at build |
| Deployment identity | notebook + environment version | repository HEAD (or a pinned revision + lockfile) | immutable image digest |
| Local reproducibility | low — needs a Fabric workspace | high — `uv run` locally | high — `docker run` locally |
| Provider portability | low — Fabric-specific | high — any container-capable batch compute | high — any container-capable batch compute |
| Operational responsibility | Fabric-managed runtime | node OS + `uv`, unmanaged | image lifecycle, self-managed |
