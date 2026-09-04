"""A deterministic stand-in for an ordinary paginated source API.

The series brief is explicit that the source is "an ordinary paginated API" —
nothing exotic. This client never talks to a network; it generates the same
page content every time it is asked for a given page number, so a checkpoint
crash-and-retry (see tests/core/test_ghost_retry.py) re-fetches byte-for-byte
the same records rather than new ones, exactly as a real replay would.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator, Literal

_STATUS_CYCLE = ["completed", "completed", "cancelled", "Completed", "COMPLETED"]
_MARKET_CYCLE = ["DK", "DE", "SE"]
_WINDOW_START = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SourcePage:
    page: int
    records: list[dict]
    has_more: bool


class SyntheticOrdersAPI:
    """Deterministic paginated source.

    ``seed`` and ``start_page`` fix the content: the same (seed, page) pair
    always yields the same records, whether this is the first fetch or a
    retry after a crash.
    """

    def __init__(
        self,
        *,
        pages: int,
        page_size: int = 100,
        start_page: int = 1,
        seed: int = 187,
        dataset: Literal["orders", "customers"] = "orders",
    ):
        self._pages = pages
        self._page_size = page_size
        self._start_page = start_page
        self._seed = seed
        self._dataset = dataset

    def fetch(self, page: int) -> SourcePage:
        records = [self._record(page, i) for i in range(self._page_size)]
        has_more = page < self._start_page + self._pages - 1
        return SourcePage(page=page, records=records, has_more=has_more)

    def pages(self) -> Iterator[SourcePage]:
        for page in range(self._start_page, self._start_page + self._pages):
            yield self.fetch(page)

    def _record(self, page: int, index: int) -> dict:
        slot = page * 10_007 + index
        updated_at = _WINDOW_START + timedelta(minutes=slot % (60 * 24))
        base = {
            "event_id": f"evt-{page:06d}-{index:04d}",
            "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
        }
        if self._dataset == "customers":
            base["customer_id"] = f"CUST-{(self._seed + page * 7 + index) % 200:04d}"
            base["market"] = _MARKET_CYCLE[slot % len(_MARKET_CYCLE)]
            return base

        base["order_id"] = f"ORD-{page:06d}-{index:04d}"
        base["customer_id"] = f"CUST-{(self._seed + page * 7 + index) % 200:04d}"
        base["order_date"] = (_WINDOW_START + timedelta(days=page % 3)).date().isoformat()
        base["status"] = _STATUS_CYCLE[slot % len(_STATUS_CYCLE)]
        base["net_amount"] = f"{10 + (slot * 37 % 50000) / 100:.2f}"
        return base
