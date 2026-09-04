"""Source-progress checkpointing, kept separate from the Delta transaction.

Article 2 ("The Lakehouse Is Not the Runtime") is explicit that a committed
Delta write is not the same thing as a completed ingestion window: the table
can be valid while the source progress is ambiguous. This module represents
that second, distinct piece of state as a plain JSON file so the "ghost
retry" scenario in tests/test_ingest.py has something concrete to crash
before writing.
"""

from __future__ import annotations

import json
from pathlib import Path


class Checkpoint:
    def __init__(self, path: Path):
        self.path = path

    def is_complete(self, run_id: str, page: int) -> bool:
        if not self.path.exists():
            return False
        state = json.loads(self.path.read_text())
        return state.get(run_id, {}).get(str(page)) is True

    def mark_complete(self, run_id: str, page: int) -> None:
        state = {}
        if self.path.exists():
            state = json.loads(self.path.read_text())
        state.setdefault(run_id, {})[str(page)] = True
        self.path.write_text(json.dumps(state))
