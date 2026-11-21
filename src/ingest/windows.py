"""Which hours of the transactions stream to pull next, and where each one lands.

The stream is pulled one complete hour at a time. A watermark records the end of the last
hour landed, so each run continues from there: after an outage, the next runs catch up,
oldest hour first, a limited number of hours per run.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class Window:
    """One hour of the stream: rows with `start <= timestamp < end`."""

    start: datetime
    end: datetime

    def raw_key(self, source: str) -> str:
        """The S3 key this hour lands at. The same hour always lands at the same key, so
        pulling it again replaces it rather than duplicating it."""
        partition = f"dt={self.start:%Y-%m-%d}/hour={self.start:%H}"
        return f"{source}/{partition}/{source}-{self.start:%Y%m%dT%H}.jsonl.gz"


def next_windows(
    loaded_through: datetime | None, now: datetime, first_hour: datetime, max_windows: int
) -> list[Window]:
    """The hours to pull now, oldest first.

    `loaded_through` is the watermark (None before the first run, which starts at
    `first_hour`). Only hours that have ended by `now` are pulled.
    """
    start = loaded_through or first_hour
    _require_hour(start)
    last_end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)

    windows = []
    while start + HOUR <= last_end and len(windows) < max_windows:
        windows.append(Window(start, start + HOUR))
        start += HOUR
    return windows


def _require_hour(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{value} has no time zone")
    if value.astimezone(UTC) != value.astimezone(UTC).replace(minute=0, second=0, microsecond=0):
        raise ValueError(f"{value} is not on the hour")
