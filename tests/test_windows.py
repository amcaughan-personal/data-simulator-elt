from datetime import UTC, datetime

import pytest

from ingest.windows import Window, next_windows

FIRST_HOUR = datetime(2026, 11, 1, tzinfo=UTC)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def test_first_run_starts_at_the_first_hour():
    windows = next_windows(None, now=at(1, 3, 10), first_hour=FIRST_HOUR, max_windows=24)
    assert windows == [Window(at(1, 0), at(1, 1)), Window(at(1, 1), at(1, 2)), Window(at(1, 2), at(1, 3))]


def test_continues_from_the_watermark_and_pulls_only_ended_hours():
    windows = next_windows(at(5, 10), now=at(5, 12, 59), first_hour=FIRST_HOUR, max_windows=24)
    assert windows == [Window(at(5, 10), at(5, 11)), Window(at(5, 11), at(5, 12))]


def test_nothing_to_pull_when_up_to_date():
    assert next_windows(at(5, 12), now=at(5, 12, 59), first_hour=FIRST_HOUR, max_windows=24) == []


def test_catching_up_takes_the_oldest_hours_first_up_to_the_limit():
    windows = next_windows(at(2, 0), now=at(9, 0), first_hour=FIRST_HOUR, max_windows=3)
    assert [w.start for w in windows] == [at(2, 0), at(2, 1), at(2, 2)]


def test_windows_join_up_across_days():
    windows = next_windows(at(1, 23), now=at(2, 1), first_hour=FIRST_HOUR, max_windows=24)
    assert windows == [Window(at(1, 23), at(2, 0)), Window(at(2, 0), at(2, 1))]


@pytest.mark.parametrize("watermark", [at(5, 10, 30), datetime(2026, 11, 5, 10)])
def test_rejects_a_watermark_off_the_hour_or_without_a_time_zone(watermark):
    with pytest.raises(ValueError):
        next_windows(watermark, now=at(6, 0), first_hour=FIRST_HOUR, max_windows=24)


def test_each_hour_has_its_own_partitioned_key():
    window = Window(at(5, 9), at(5, 10))
    assert window.raw_key("transactions") == (
        "transactions/dt=2026-11-05/hour=09/transactions-20261105T09.jsonl.gz"
    )
