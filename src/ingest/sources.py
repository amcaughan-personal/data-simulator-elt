"""The sources pulled from the API, each defined by one JSON file in `sources/`.

A source file holds:
- `endpoint` and `spec`: what to ask the API for.
- `load`: how it's loaded.
  - `hourly`: an endless stream, landed one complete hour per file from a watermark.
  - `daily_snapshot`: the whole dataset, landed once a day.
- `columns`: the column names and types expected back. Every response is checked against
  them before anything lands.
- `hours_per_request` (hourly only): how many hours one request may cover while staying
  well inside the API's 100,000-cell response limit at the stream's rate.

The infrastructure reads the same files: each source gets a Glue table (columns from
`columns`, partitions from `load`) and a schedule. Adding a source means adding a file.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SOURCES_DIR = Path(__file__).parent / "sources"
LOADS = {"hourly", "daily_snapshot"}


@dataclass(frozen=True)
class Source:
    name: str
    endpoint: str
    load: str
    columns: dict[str, str]
    spec: dict[str, Any]
    hours_per_request: int = 1


def load_source(name: str) -> Source:
    data = json.loads((SOURCES_DIR / f"{name}.json").read_text())
    if data["load"] not in LOADS:
        raise ValueError(f"{name}: load must be one of {sorted(LOADS)}, not {data['load']!r}")
    return Source(
        name=name,
        endpoint=data["endpoint"],
        load=data["load"],
        columns=data["columns"],
        spec=data["spec"],
        hours_per_request=data.get("hours_per_request", 1),
    )
