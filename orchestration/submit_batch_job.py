"""Submit the pinned runtime image to Azure Batch, and build the task
envelope the Fabric pipeline expects (see fabric_pipeline_contract.md).

"Fabric orchestrates; Batch executes; delta-rs commits; Fabric consumes"
(article 1). Fabric submits a task, waits for a terminal state, and gates
downstream work on the result -- so the image this module submits must be
addressed by digest, never a floating tag: a tag can move under a pinned
run record without anyone noticing.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass

IMAGE_DIGEST_RE = re.compile(r"^(?P<repo>[a-z0-9.\-/:]+)@sha256:(?P<digest>[a-f0-9]{64})$")


class FloatingImageReference(ValueError):
    """The image reference is a mutable tag (or bare repository), not a
    pinned digest. See legacy/runtime-clone/README.md for what that costs:
    a run record can no longer be bound to exactly what executed."""


@dataclass(frozen=True)
class TaskEnvelope:
    run_id: str
    image: str
    window_start: str
    window_end: str
    table_uri: str
    git_commit: str
    managed_identity_resource_id: str
    manifest_uri: str
    max_retries: int = 0


def require_digest(image: str) -> str:
    if not IMAGE_DIGEST_RE.match(image):
        raise FloatingImageReference(
            f"'{image}' is not a digest-pinned image reference (expected '<repo>@sha256:<64 hex>')"
        )
    return image


def build_task(envelope: TaskEnvelope) -> dict:
    image = require_digest(envelope.image)
    command_line = (
        "--run-id " + envelope.run_id
        + " --window-start " + envelope.window_start
        + " --window-end " + envelope.window_end
        + " --table-uri " + envelope.table_uri
        + " --manifest-path " + envelope.manifest_uri
    )
    return {
        "id": envelope.run_id,
        "commandLine": command_line,
        "containerSettings": {
            "imageName": image,
            "containerRunOptions": "--rm",
        },
        "environmentSettings": [
            {"name": "RUN_ID", "value": envelope.run_id},
            {"name": "GIT_COMMIT", "value": envelope.git_commit.upper()},
            {"name": "IMAGE_DIGEST", "value": image},
            {"name": "WINDOW_START", "value": envelope.window_start},
            {"name": "WINDOW_END", "value": envelope.window_end},
        ],
        "constraints": {
            # Batch retries are compute retries, not safe business retries
            # (article 1: "A compute retry is not the same as a safe
            # business retry"). Retrying is the pipeline's decision after
            # reading the run manifest, not Batch's.
            "maxTaskRetryCount": envelope.max_retries,
            "retentionTime": "PT1H",
        },
        "userIdentity": {
            "autoUser": {"scope": "task", "elevationLevel": "nonadmin"},
        },
    }


def submit(envelope: TaskEnvelope, *, account_url: str, pool_id: str, job_id: str) -> str:
    """Submit the task to a real Azure Batch job. Not exercised by tests --
    requires an actual Batch account and a managed identity."""
    from azure.batch import BatchServiceClient
    from azure.batch.models import TaskAddParameter
    from azure.identity import DefaultAzureCredential

    task = build_task(envelope)
    credential = DefaultAzureCredential()
    client = BatchServiceClient(credential=credential, batch_url=account_url)
    client.task.add(job_id, TaskAddParameter(**task))
    return envelope.run_id


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--image", required=True, help="digest-pinned image reference, e.g. repo@sha256:...")
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--table-uri", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--managed-identity-resource-id", required=True)
    parser.add_argument("--manifest-uri", required=True)
    parser.add_argument("--dry-run", action="store_true", help="print the task body instead of submitting")
    parser.add_argument("--account-url")
    parser.add_argument("--pool-id")
    parser.add_argument("--job-id")
    args = parser.parse_args(argv)

    envelope = TaskEnvelope(
        run_id=args.run_id,
        image=args.image,
        window_start=args.window_start,
        window_end=args.window_end,
        table_uri=args.table_uri,
        git_commit=args.git_commit,
        managed_identity_resource_id=args.managed_identity_resource_id,
        manifest_uri=args.manifest_uri,
    )

    if args.dry_run:
        print(json.dumps(build_task(envelope), indent=2))
        return

    submit(envelope, account_url=args.account_url, pool_id=args.pool_id, job_id=args.job_id)


if __name__ == "__main__":
    main()
