"""One asyncio lock per key, pruned when no holder or waiter is left.

The count covers holders and waiters alike: it is taken before awaiting the lock and given back
in a `finally` after release, so a cancelled waiter gives it back too. A key's lock is deleted
only when its count reaches 0. Deleting on release alone is wrong once a key has waiters: the
woken waiter has not resumed yet, a newcomer would make a fresh lock and both would run.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

__all__ = ["KeyedLocks"]


class KeyedLocks:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._counts: dict[str, int] = {}

    def hold(self, key: str) -> contextlib.AbstractAsyncContextManager[None]:
        return self._hold(key)

    @contextlib.asynccontextmanager
    async def _hold(self, key: str) -> AsyncIterator[None]:
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._counts[key] = self._counts.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._counts[key] -= 1
            if self._counts[key] == 0:
                del self._counts[key]
                del self._locks[key]

    def __len__(self) -> int:
        """The number of keys held or awaited."""
        return len(self._locks)
