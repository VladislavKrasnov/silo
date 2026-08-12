from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Page(Sequence[T]):
    items: tuple[T, ...]
    page_index: int
    total_pages: int

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, position):
        return self.items[position]

    @property
    def has_previous(self) -> bool:
        return self.page_index > 0

    @property
    def has_next(self) -> bool:
        return self.page_index < self.total_pages - 1


def paginate(items: Sequence[T], requested_index: int, page_size: int) -> Page[T]:
    total_pages = max(1, math.ceil(len(items) / page_size))
    clamped_index = max(0, min(requested_index, total_pages - 1))
    start = clamped_index * page_size
    page_items = tuple(items[start : start + page_size])
    return Page(items=page_items, page_index=clamped_index, total_pages=total_pages)
