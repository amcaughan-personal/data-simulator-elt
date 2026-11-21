"""Lambda entry point. EventBridge Scheduler invokes it with `{"source": "transactions"}` every
hour and `{"source": "merchants"}` once a day.

Configuration (environment variables):
- `API_URL`: the data-simulator API's base URL
- `RAW_BUCKET`: the raw zone's S3 bucket
- `FIRST_HOUR`: where the transactions stream starts landing, e.g. `2026-11-01T00:00:00Z`
- `MAX_HOURS_PER_RUN`: how many hours one run catches up at most
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from ingest.api import ApiClient
from ingest.pipeline import pull_snapshot, pull_stream
from ingest.sources import load_source
from ingest.store import S3Store

logging.getLogger().setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    source = load_source(event["source"])
    api = ApiClient(os.environ["API_URL"])
    store = S3Store(os.environ["RAW_BUCKET"])
    now = datetime.now(UTC)

    if source.endpoint == "/v1/streams/window":
        keys = pull_stream(
            api,
            store,
            source,
            now,
            first_hour=datetime.fromisoformat(os.environ["FIRST_HOUR"]),
            max_hours=int(os.environ["MAX_HOURS_PER_RUN"]),
        )
    else:
        keys = pull_snapshot(api, store, source, now)
    return {"source": source.name, "landed": keys}
