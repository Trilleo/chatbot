"""Sending replies at a human pace: account safety on a normal QQ account."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Pacing:
    """Random delays (seconds): before the first message and between messages."""

    first_min: float
    first_max: float
    part_min: float
    part_max: float


async def send_paced(
    send: Callable[[str], Awaitable[Any]],
    parts: Sequence[str],
    pacing: Pacing,
    started_at: float,
    *,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
    rng: random.Random | None = None,
) -> None:
    """Send `parts` one by one with random pauses.

    The first pause counts from `started_at` (a `clock()` reading taken when the
    message arrived), so time spent waiting for the model counts towards it.
    """
    rng = rng or random.Random()
    for i, part in enumerate(parts):
        if i == 0:
            delay = rng.uniform(pacing.first_min, pacing.first_max) - (
                clock() - started_at
            )
        else:
            delay = rng.uniform(pacing.part_min, pacing.part_max)
        if delay > 0:
            await sleep(delay)
        await send(part)
