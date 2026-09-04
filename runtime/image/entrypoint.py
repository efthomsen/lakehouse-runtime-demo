"""The runtime image's entrypoint: paginate the source, validate, append to
Bronze via delta-rs. This is the exact command Azure Batch runs, unchanged
between a laptop, CI, and a container submitted by orchestration/submit_batch_job.py
-- only --table-uri (and the environment it points into) changes.

    entrypoint.py --run-id RUN-0187 \
      --window-start 2026-09-01T00:00:00Z --window-end 2026-09-02T00:00:00Z \
      --table-uri /data/bronze/orders_raw --pages 10

Exit codes: 0 ok, 2 source/payload validation error, 3 schema contract
violation, 4 checkpoint write interrupted, 1 anything else. The run manifest
written to --manifest-path is the final status record the Fabric pipeline
reads to decide whether to gate downstream work on this run (see
orchestration/fabric_pipeline_contract.md) -- deliberately separate from the
process exit code (article 1: "a final status record separate from the raw
process exit").
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from deltalake import DeltaTable
from deltalake.exceptions import TableNotFoundError

from ingestion.append_bronze import SourcePayloadError, ingest_window
from ingestion.checkpoint import Checkpoint, CheckpointWriteInterrupted
from ingestion.source import SyntheticOrdersAPI
from silver.prepare_customers import prepare_customers
from silver.prepare_orders import prepare_orders
from silver.table_contract import SchemaContractViolation


def _table_version(table_uri: str) -> int | None:
    try:
        return DeltaTable(table_uri).version()
    except TableNotFoundError:
        return None


def _log(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--table-uri", required=True)
    parser.add_argument("--dataset", choices=["orders", "customers"], default="orders")
    parser.add_argument("--pages", type=int, default=10)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=187)
    parser.add_argument("--checkpoint-path", type=Path, default=Path(".ingest-checkpoint.json"))
    parser.add_argument("--manifest-path", type=Path, default=Path("run-manifest.json"))
    parser.add_argument("--prepare-silver", default=None, help="Silver table URI; if set, run Bronze->Silver after ingest")
    args = parser.parse_args(argv)

    manifest = {
        "run_id": args.run_id,
        "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
        "image_digest": os.environ.get("IMAGE_DIGEST", "unknown"),
        "window": {"start": args.window_start, "end": args.window_end},
        "table_uri": args.table_uri,
        "delta_version_before": _table_version(args.table_uri),
    }

    source = SyntheticOrdersAPI(pages=args.pages, page_size=args.page_size, seed=args.seed, dataset=args.dataset)
    checkpoint = Checkpoint(args.checkpoint_path)

    def after_commit(page: int, version: int) -> None:
        _log("page_committed", run_id=args.run_id, page=page, delta_version=version)

    status = "ok"
    exit_code = 0
    try:
        result = ingest_window(source=source, table_uri=args.table_uri, run_id=args.run_id, checkpoint=checkpoint, after_commit=after_commit)
        manifest.update(
            pages_appended=result.pages_appended,
            pages_skipped=result.pages_skipped,
            rows_appended=result.rows_appended,
        )
        if args.prepare_silver:
            prepare = prepare_orders if args.dataset == "orders" else prepare_customers
            prepare(bronze_uri=args.table_uri, silver_uri=args.prepare_silver)
    except SourcePayloadError as exc:
        status, exit_code = f"validation_error: {exc}", 2
    except SchemaContractViolation as exc:
        status, exit_code = f"schema_contract_violation: {exc}", 3
    except CheckpointWriteInterrupted as exc:
        status, exit_code = f"checkpoint_write_interrupted: {exc}", 4
    except Exception as exc:  # noqa: BLE001 -- the manifest is the record; re-raise nothing, just report
        status, exit_code = f"error: {exc}", 1

    manifest["status"] = status
    manifest["delta_version_after"] = _table_version(args.table_uri)
    args.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_path.write_text(json.dumps(manifest, indent=2))
    _log("run_complete", run_id=args.run_id, status=status, manifest_path=str(args.manifest_path))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
