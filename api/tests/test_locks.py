"""KeyedLocks: one lock per key, pruned when no holder or waiter is left."""

import asyncio
import itertools

import pytest

from sagaloom.locks import KeyedLocks


async def _yield(n: int = 5) -> None:
    for _ in range(n):
        await asyncio.sleep(0)


async def test_waiter_and_newcomer_never_overlap():
    """The prune trap: A releases while B waits; C asks in the same tick, before B resumes. A
    lock deleted on A's release would give C a fresh lock and run C alongside B."""
    locks = KeyedLocks()
    tick = itertools.count()
    intervals: dict[str, tuple[int, int]] = {}

    async def held(name: str) -> None:
        enter = next(tick)
        await asyncio.sleep(0.01)  # stay inside long enough for an overlap to show
        intervals[name] = (enter, next(tick))

    a = locks.hold("w")
    await a.__aenter__()
    enter_a = next(tick)

    async def b_body() -> None:
        async with locks.hold("w"):
            await held("B")

    b = asyncio.create_task(b_body())
    await _yield()  # B is now waiting on the lock
    assert not b.done()

    intervals["A"] = (enter_a, next(tick))
    await a.__aexit__(None, None, None)  # wakes B, which has not resumed yet
    async with locks.hold("w"):  # C, in the same tick
        await held("C")
    await b

    spans = sorted(intervals.values())
    assert len(spans) == 3
    for (_, first_exit), (second_enter, _) in itertools.pairwise(spans):
        assert first_exit < second_enter, intervals
    assert len(locks) == 0


async def test_key_removed_when_last_holder_leaves():
    locks = KeyedLocks()
    async with locks.hold("w"):
        assert len(locks) == 1
    assert len(locks) == 0


async def test_key_kept_while_a_waiter_exists():
    locks = KeyedLocks()
    a = locks.hold("w")
    await a.__aenter__()
    entered = asyncio.Event()

    async def waiter() -> None:
        async with locks.hold("w"):
            entered.set()

    b = asyncio.create_task(waiter())
    await _yield()
    await a.__aexit__(None, None, None)
    assert len(locks) == 1  # B still counts: its key is kept
    await b
    assert entered.is_set()
    assert len(locks) == 0


async def test_cancelled_waiter_does_not_leak():
    locks = KeyedLocks()
    a = locks.hold("w")
    await a.__aenter__()

    async def waiter() -> None:
        async with locks.hold("w"):
            pass

    b = asyncio.create_task(waiter())
    await _yield()
    b.cancel()
    with pytest.raises(asyncio.CancelledError):
        await b
    await a.__aexit__(None, None, None)
    assert len(locks) == 0


async def test_keys_are_independent():
    locks = KeyedLocks()
    async with locks.hold("w1"):
        async with locks.hold("w2"):  # would deadlock if keys shared a lock
            assert len(locks) == 2
    assert len(locks) == 0
