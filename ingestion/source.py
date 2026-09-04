"""A paginated source client.

Standing in for a real ordinary paginated API (per the series brief). It
reads a JSON fixture from synthetic-data/ and paginates over it exactly the
way an HTTP client would, so the ingestion logic in main.py never needs to
know it isn't hitting a real network endpoint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator


class PaginatedSource:
    def __init__(self, fixture_path: Path, *, page_size: int = 2):
        self._records = json.loads(fixture_path.read_text())
        self._page_size = page_size

    def pages(self) -> Iterator[tuple[int, list[dict]]]:
        for page_index in range(0, len(self._records), self._page_size):
            page_number = page_index // self._page_size + 1
            yield page_number, self._records[page_index : page_index + self._page_size]
