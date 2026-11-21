"""The two sources pulled from the API, each defined by a JSON file in `sources/`.

A source file holds the API endpoint, the spec sent to it, and `columns`: the column names
and types the pipeline expects back. The Glue table definitions read the same file, so the
raw tables and the ingest check can't disagree.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SOURCES_DIR = Path(__file__).parent / "sources"


@dataclass(frozen=True)
class Source:
    name: str
    endpoint: str
    columns: dict[str, str]
    spec: dict[str, Any]


def load_source(name: str) -> Source:
    data = json.loads((SOURCES_DIR / f"{name}.json").read_text())
    return Source(name=name, endpoint=data["endpoint"], columns=data["columns"], spec=data["spec"])
