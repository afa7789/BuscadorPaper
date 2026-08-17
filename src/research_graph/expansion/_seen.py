"""research_graph.expansion._seen — bounded LRU set for paper_id dedup.

Used by ``expand_seeds`` to cap memory when walking large citation graphs.
Eviction policy: oldest-first by insertion order. After eviction the
paper_id is kept in a shadow set so we never re-fetch the same paper
within the same run.

Type-erased generic: values() returns the underlying type ``Paper`` at the
call site; we keep the container itself untyped to remain stdlib-only.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Generic, TypeVar


_PaperT = TypeVar("_PaperT")


class BoundedSeenSet(Generic[_PaperT]):
    """OrderedDict-backed LRU with shadow eviction tracking.

    On overflow the oldest entry is pushed into ``_evicted`` so duplicate
    fetches return ``False`` from ``add()`` without keeping the full Paper.
    """

    def __init__(self, capacity: int = 10_000) -> None:
        # Honor user-requested capacity even if < 100. The 100-floor was
        # misguided: tests and small-graph runs want small N.
        self._items: OrderedDict[str, _PaperT] = OrderedDict()
        self._evicted: set[str] = set()
        self._capacity = max(1, int(capacity))

    def __contains__(self, key: str) -> bool:
        return key in self._items or key in self._evicted

    def add(self, key: str, paper: _PaperT) -> bool:
        """Return True if newly inserted, False if already known."""
        if key in self._evicted:
            return False
        if key in self._items:
            self._items.move_to_end(key)  # LRU touch
            return False
        self._items[key] = paper
        if len(self._items) > self._capacity:
            old_key, _ = self._items.popitem(last=False)
            self._evicted.add(old_key)
        return True

    def values(self) -> list[_PaperT]:
        return list(self._items.values())

    def keys(self) -> list[str]:
        return list(self._items.keys())

    def __len__(self) -> int:
        return len(self._items)

    @property
    def capacity(self) -> int:
        return self._capacity
