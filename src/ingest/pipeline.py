"""Pull from the API and land the rows in the raw zone.

- Streams are pulled hour by hour from a watermark (see `windows.py`). The watermark moves
  after each hour lands, so a failed run keeps the hours it finished and the next run
  continues from there.
- Snapshots are pulled whole, once a day, to a key for that day.

Every response is checked against the source's contract before anything is written.
"""

import logging
from datetime import UTC, date, datetime
from typing import Any, Protocol

from ingest.api import check_contract
from ingest.sources import Source
from ingest.windows import next_windows

log = logging.getLogger(__name__)


class Api(Protocol):
    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...


class Store(Protocol):
    def read_json(self, key: str) -> dict[str, Any] | None: ...
    def write_json(self, key: str, value: dict[str, Any]) -> None: ...
    def write_rows(self, key: str, rows: list[dict[str, Any]], metadata: dict[str, str]) -> None: ...


def watermark_key(source: Source) -> str:
    return f"_state/{source.name}.json"


def pull_stream(
    api: Api, store: Store, source: Source, now: datetime, first_hour: datetime, max_hours: int
) -> list[str]:
    """Land each complete hour since the watermark (up to `max_hours`). Returns the keys written."""
    state = store.read_json(watermark_key(source))
    loaded_through = datetime.fromisoformat(state["loaded_through"]) if state else None

    keys = []
    for window in next_windows(loaded_through, now, first_hour, max_hours):
        body = {"stream": source.spec, "window": {"from": _iso(window.start), "to": _iso(window.end)}}
        response = api.post(source.endpoint, body)
        check_contract(response, source.columns)

        key = window.raw_key(source.name)
        store.write_rows(key, response["rows"], _metadata(response, now))
        store.write_json(watermark_key(source), {"loaded_through": _iso(window.end)})
        log.info("landed %s rows at %s", response["row_count"], key)
        keys.append(key)
    return keys


def pull_snapshot(api: Api, store: Store, source: Source, now: datetime) -> list[str]:
    """Land today's full snapshot. Pulling again the same day replaces it."""
    response = api.post(source.endpoint, source.spec)
    check_contract(response, source.columns)

    key = snapshot_key(source, now.astimezone(UTC).date())
    store.write_rows(key, response["rows"], _metadata(response, now))
    log.info("landed %s rows at %s", response["row_count"], key)
    return [key]


def snapshot_key(source: Source, day: date) -> str:
    return f"{source.name}/snapshot_date={day:%Y-%m-%d}/{source.name}-{day:%Y%m%d}.jsonl.gz"


def _metadata(response: dict[str, Any], now: datetime) -> dict[str, str]:
    """Kept with each object, so any file can be traced back to the request that made it."""
    return {"seed": str(response["seed"]), "row-count": str(response["row_count"]), "pulled-at": _iso(now)}


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
