"""Pull from the API and land the rows in the raw zone.

Every load can be re-run safely, and a failed run is retried by the next scheduled one:
- Hourly loads land one file per hour, from a watermark (see `windows.py`). Consecutive
  hours are fetched together, up to the source's `hours_per_request`, so catching up takes
  a request per day rather than per hour. The watermark moves after each request's hours
  land, so a failed or timed-out run keeps what it finished and the next run continues.
- Daily snapshots run every hour too, but only pull when today's file doesn't exist yet.

Every response is checked against the source's contract before anything is written.
"""

import logging
import math
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from itertools import batched
from typing import Any, Protocol

from ingest.api import ContractError, check_contract
from ingest.sources import Source
from ingest.windows import Window, next_windows

log = logging.getLogger(__name__)

# A run stops starting new requests when less time than this is left, so it ends cleanly
# instead of being cut off mid-request. One request, with retries, fits comfortably.
MIN_SECONDS_FOR_A_REQUEST = 60


class Api(Protocol):
    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...


class Store(Protocol):
    def exists(self, key: str) -> bool: ...
    def read_json(self, key: str) -> dict[str, Any] | None: ...
    def write_json(self, key: str, value: dict[str, Any]) -> None: ...
    def write_rows(self, key: str, rows: list[dict[str, Any]], metadata: dict[str, str]) -> None: ...


def watermark_key(source: Source) -> str:
    return f"_state/{source.name}.json"


def pull_hourly(
    api: Api,
    store: Store,
    source: Source,
    now: datetime,
    first_hour: datetime,
    max_hours: int,
    seconds_left: Callable[[], float] = lambda: math.inf,
) -> list[str]:
    """Land each complete hour since the watermark (up to `max_hours`). Returns the keys written."""
    state = store.read_json(watermark_key(source))
    loaded_through = datetime.fromisoformat(state["loaded_through"]) if state else None

    keys = []
    windows = next_windows(loaded_through, now, first_hour, max_hours)
    for hours in batched(windows, source.hours_per_request, strict=False):
        if seconds_left() < MIN_SECONDS_FOR_A_REQUEST:
            log.warning("out of time at %s; the next run continues from there", _iso(hours[0].start))
            break
        start, end = hours[0].start, hours[-1].end
        body = {"stream": source.spec, "window": {"from": _iso(start), "to": _iso(end)}}
        response = api.post(source.endpoint, body)
        check_contract(response, source.columns)

        rows_by_hour = _split_by_hour(response["rows"], hours)
        for window in hours:
            rows = rows_by_hour.get(window.start, [])
            store.write_rows(window.raw_key(source.name), rows, _metadata(response["seed"], len(rows), now))
            keys.append(window.raw_key(source.name))
        store.write_json(watermark_key(source), {"loaded_through": _iso(end)})
        log.info("landed %s rows for %s to %s", response["row_count"], _iso(start), _iso(end))
    return keys


def pull_daily_snapshot(api: Api, store: Store, source: Source, now: datetime) -> list[str]:
    """Land today's full snapshot, unless it has already landed."""
    key = snapshot_key(source, now.astimezone(UTC).date())
    if store.exists(key):
        return []

    response = api.post(source.endpoint, source.spec)
    check_contract(response, source.columns)
    store.write_rows(key, response["rows"], _metadata(response["seed"], response["row_count"], now))
    log.info("landed %s rows at %s", response["row_count"], key)
    return [key]


def snapshot_key(source: Source, day: date) -> str:
    return f"{source.name}/snapshot_date={day:%Y-%m-%d}/{source.name}-{day:%Y%m%d}.jsonl.gz"


def _split_by_hour(
    rows: list[dict[str, Any]], hours: tuple[Window, ...]
) -> dict[datetime, list[dict[str, Any]]]:
    """Group rows by the hour they fall in. A row outside the hours asked for means the API
    broke its promise, so fail rather than drop it."""
    wanted = {window.start for window in hours}
    by_hour = defaultdict(list)
    for row in rows:
        hour = datetime.fromisoformat(row["timestamp"]).replace(minute=0, second=0, microsecond=0)
        if hour not in wanted:
            raise ContractError(f"row at {row['timestamp']} is outside the window asked for")
        by_hour[hour].append(row)
    return by_hour


def _metadata(seed: int, row_count: int, now: datetime) -> dict[str, str]:
    """Kept with each object, so any file can be traced back to the request that made it."""
    return {"seed": str(seed), "row-count": str(row_count), "pulled-at": _iso(now)}


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
