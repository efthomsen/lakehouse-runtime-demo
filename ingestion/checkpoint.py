"""Source-progress checkpointing, kept separate from the Delta transaction.

Article 2 ("Keep the Lakehouse, Move the Compute") is explicit that a
committed Delta write is not the same thing as a completed ingestion window:
"Delta makes the table commit atomic. It does not make the source-to-table
operation automatically idempotent." This module represents that second,
distinct piece of state as a plain JSON file, separate from the table, so a
crash between the two can actually happen (see tests/core/test_ghost_retry.py).
"""

from __future__ import annotations

import json
from pathlib import Path


class CheckpointWriteInterrupted(RuntimeError):
    """Raised (typically by a caller's after-commit hook) to simulate a
    process crash after a Delta commit succeeds but before the checkpoint
    for that page is written — the "ghost retry" from article 2."""


class Checkpoint:
    def __init__(self, path: Path):
        self.path = path

    def is_complete(self, run_id: str, page: int) -> bool:
        if not self.path.exists():
            return False
        state = json.loads(self.path.read_text())
        return state.get(run_id, {}).get(str(page), {}).get("complete") is True

    def mark_complete(self, run_id: str, page: int, *, delta_version: int) -> None:
        state = {}
        if self.path.exists():
            state = json.loads(self.path.read_text())
        state.setdefault(run_id, {})[str(page)] = {"complete": True, "delta_version": delta_version}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state))

    def delta_version_for(self, run_id: str, page: int) -> int | None:
        if not self.path.exists():
            return None
        state = json.loads(self.path.read_text())
        return state.get(run_id, {}).get(str(page), {}).get("delta_version")
