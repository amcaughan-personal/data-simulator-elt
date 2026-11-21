"""Lambda entry point. EventBridge Scheduler invokes it every hour for each source, with
`{"source": "<name>"}` (see `sources/`).

Configuration (environment variables):
- `API_URL`: the API's base URL
- `RAW_BUCKET`: the raw zone's S3 bucket
- `FIRST_HOUR`: where hourly loads start landing, e.g. `2026-11-01T00:00:00Z`
- `MAX_HOURS_PER_RUN`: how many hours one run catches up at most
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from ingest.api import ApiClient
from ingest.pipeline import pull_daily_snapshot, pull_hourly
from ingest.sources import load_source
from ingest.store import S3Store

log = logging.getLogger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    source = load_source(event["source"])
    api = ApiClient(os.environ["API_URL"])
    store = S3Store(os.environ["RAW_BUCKET"])
    now = datetime.now(UTC)

    if source.load == "hourly":
        keys = pull_hourly(
            api,
            store,
            source,
            now,
            first_hour=datetime.fromisoformat(os.environ["FIRST_HOUR"]),
            max_hours=int(os.environ["MAX_HOURS_PER_RUN"]),
            seconds_left=lambda: context.get_remaining_time_in_millis() / 1000,
        )
    else:
        keys = pull_daily_snapshot(api, store, source, now)

    # One line per run, even when there was nothing new to land.
    summary = {"source": source.name, "landed": len(keys), "first": keys[:1], "last": keys[-1:]}
    log.info("run finished: %s landed %d files", source.name, len(keys), extra=summary)
    return summary
