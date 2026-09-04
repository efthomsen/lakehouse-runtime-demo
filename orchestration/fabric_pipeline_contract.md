# Fabric pipeline contract for the Batch activity

> **STATUS: partially UNVERIFIED.** Sections 1-5 describe the envelope and
> the run manifest, both implemented and tested in this repo. Section 8 is
> explicitly marked unverified: which Fabric activity type performs the
> submission, its polling cadence, and how it reads the manifest have not
> been checked against a real Fabric workspace. Do not treat section 8 as
> settled before that happens (see the series' "Before publishing" gates).

## 1. Roles

> Fabric orchestrates; Batch executes; delta-rs commits; Fabric consumes.

Fabric is the scheduler, the dependency gate, and the monitoring surface for
the pipeline as a whole. Batch is the execution plane underneath one
activity in that pipeline:

> The pipeline submits a task, waits for a terminal state, and gates
> downstream work on the result.

Batch supplies compute, starts the requested work, passes in a bounded set
of parameters, and reports what happened. It does not decide how the
application is structured.

## 2. The task envelope

Standardise the envelope; let the workload vary inside it. Only the values
change between runs — the shape stays fixed.

| Slot | Fixed per | Source |
|---|---|---|
| `IMAGE DIGEST` | release | CI build, promoted between environments unchanged |
| `ENTRYPOINT` | image | baked into `runtime/image/Dockerfile` |
| `RUN ID` | run | Fabric pipeline run, format `RUN-####` |
| `INPUT WINDOW` | run | `--window-start` / `--window-end`, ISO-8601 `Z` |
| `IDENTITY` | environment | managed identity resource ID |
| `RETRY POLICY` | release | `maxTaskRetryCount` — defaults to `0`; see §3 |
| `OUTPUT CONTRACT` | release | the run manifest schema, §4 |

`orchestration/submit_batch_job.py` builds this envelope
(`TaskEnvelope` / `build_task`) and refuses to build a task whose image is
not pinned by digest (`require_digest` raises `FloatingImageReference` for
a tag or a bare repository reference) — a tag can move under a pinned run
record without anyone noticing, which defeats the whole point of the
release-bound model (see `legacy/runtime-clone/README.md`).

## 3. Inputs the pipeline supplies

- `run_id`: `RUN-####` (example throughout the series: `RUN-0187`).
- `window_start` / `window_end`: ISO-8601 UTC, e.g. `2026-09-01T00:00:00Z`.
- `table_uri`: the Bronze table this run appends to.
- `image`: **must** be a digest reference (`repo@sha256:<64 hex>`), never a
  tag — the same rule `orchestration/submit_batch_job.py` enforces in code.
- `managed_identity_resource_id`: the identity Batch assumes to read the
  source and write to OneLake.

A compute retry is not the same as a safe business retry: Batch can rerun a
failed task, but it cannot know whether the task committed data immediately
before losing its connection or crashed before writing its checkpoint. That
is why `maxTaskRetryCount` defaults to `0` here — retrying is the pipeline's
decision after reading the manifest (§4), not Batch's.

## 4. The run manifest — the output contract

`runtime/image/entrypoint.py` writes a manifest to `--manifest-path` on
every run, regardless of outcome:

```json
{
  "run_id": "RUN-0187",
  "git_commit": "8A4C1D",
  "image_digest": "...",
  "window": {"start": "...", "end": "..."},
  "table_uri": "...",
  "delta_version_before": 1430,
  "delta_version_after": 1431,
  "pages_appended": [1, 2, 3],
  "pages_skipped": [],
  "rows_appended": 300,
  "status": "ok"
}
```

This is "a final status record separate from the raw process exit"
(article 1). The pipeline should gate on the manifest, not the exit code
alone — a task can exit non-zero after a partial success (some pages
committed before failure) and the manifest still says exactly which pages.

## 5. Terminal states → pipeline outcome

| Batch outcome | Manifest `status` | Pipeline action |
|---|---|---|
| completed, exit 0 | `ok` | Proceed — gate downstream on `delta_version_after` |
| completed, exit 2 | `validation_error: ...` | Fail the run; do not retry without investigating the source payload |
| completed, exit 3 | `schema_contract_violation: ...` | Fail the run; a breaking schema change needs a deliberate decision, not a retry |
| completed, exit 4 | `checkpoint_write_interrupted: ...` | **Safe to resubmit the same `run_id`.** The checkpoint makes the retry visible and repairable (article 2), not silent — this is the ghost-retry path, by design |
| timeout / unknown | — | Treat as unknown outcome; inspect the manifest (if written) before deciding whether to resubmit |

Gate the next stage on `delta_version_after > <last version this pipeline
already gated on>` — not merely on "the task succeeded" — so a run that
appended nothing new (e.g., every page already checkpointed) does not
trigger a redundant downstream refresh.

## 6. Before triggering a Gold refresh

> Refresh submission is not the same as concurrency control. An
> orchestration layer must account for an existing scheduled or in-flight
> refresh rather than assuming another invocation is safe.

Before the pipeline triggers a Materialized Lake View refresh: check for an
active run on the same lineage. **UNVERIFIED** — the exact Fabric API/UI
surface for checking in-flight refreshes has not been exercised against a
real workspace.

## 7. Three-owner failure model

```text
RUNTIME  — task failed              (this activity; see §5)
TABLE    — commit / compatibility failed   (see tests/compatibility)
LOGIC    — definition / refresh failed     (see gold/materialized_lake_views.sql)
```

The Fabric control plane arcs over all three: `RUN · COMMIT · DEFINE`. A
pipeline built only to watch for Batch task failure misses the other two
failure classes entirely.

## 8. UNVERIFIED — real Fabric mechanics

Not yet checked against a real Fabric workspace:

- Which Fabric activity type actually performs the Batch submission (Web
  activity calling the Batch REST API directly, an Azure Function activity,
  or a Custom activity) and how each authenticates with the managed
  identity above.
- The pipeline's polling cadence against the Batch task's terminal state.
- How the pipeline reads the run manifest back (Lookup activity / Get
  Metadata / a direct OneLake read) to make the gating decision in §5.
- The concurrency check in §6.

Do not present any of the above as verified behaviour before it has been
run once against a real Fabric pipeline and workspace.
