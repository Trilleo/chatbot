import random

from src.llm.sender import Pacing, send_paced

PACING = Pacing(first_min=1.0, first_max=3.0, part_min=1.0, part_max=3.0)


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []
        self.sent: list[str] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    async def send(self, text: str) -> None:
        self.sent.append(text)


async def test_pauses_before_and_between_messages() -> None:
    fake = FakeTime()
    await send_paced(
        fake.send,
        ["a", "b", "c"],
        PACING,
        started_at=fake.now,
        sleep=fake.sleep,
        clock=fake.clock,
        rng=random.Random(1),
    )
    assert fake.sent == ["a", "b", "c"]
    assert len(fake.sleeps) == 3
    assert all(1.0 <= s <= 3.0 for s in fake.sleeps)


async def test_time_spent_thinking_counts_towards_the_first_pause() -> None:
    fake = FakeTime()
    started_at = fake.now
    fake.now += 10.0  # the model took 10 s
    await send_paced(
        fake.send,
        ["a", "b"],
        PACING,
        started_at=started_at,
        sleep=fake.sleep,
        clock=fake.clock,
        rng=random.Random(1),
    )
    assert fake.sent == ["a", "b"]
    assert len(fake.sleeps) == 1  # only between the two parts


async def test_first_pause_is_shortened_by_elapsed_time() -> None:
    fake = FakeTime()
    expected = random.Random(7).uniform(1.0, 3.0) - 0.5
    started_at = fake.now
    fake.now += 0.5
    await send_paced(
        fake.send,
        ["a"],
        PACING,
        started_at=started_at,
        sleep=fake.sleep,
        clock=fake.clock,
        rng=random.Random(7),
    )
    assert fake.sleeps == [expected]
