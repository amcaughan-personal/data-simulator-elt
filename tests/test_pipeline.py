import gzip
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ingest.api import ApiError, ContractError
from ingest.pipeline import pull_snapshot, pull_stream
from ingest.sources import Source
from ingest.store import encode_rows

STREAM = Source(
    "transactions", "/v1/streams/window", {"timestamp": "timestamp", "amount": "number"}, {"seed": 1}
)
SNAPSHOT = Source("merchants", "/v1/datasets", {"merchant_id": "string"}, {"seed": 1})
FIRST_HOUR = datetime(2026, 11, 1, tzinfo=UTC)


class FakeApi:
    """Answers like the API: for a stream window, one row at the start of each hour except
    those in `empty_hours`. Fails on request number `fail_on`."""

    def __init__(self, types, fail_on=None, empty_hours=()):
        self.types = types
        self.fail_on = fail_on
        self.empty_hours = empty_hours
        self.requests = []

    def post(self, path, body):
        self.requests.append((path, body))
        if len(self.requests) == self.fail_on:
            raise ApiError("HTTP 503")
        rows = [{"merchant_id": "grocery_0001"}]
        if "window" in body:
            start, end = (datetime.fromisoformat(body["window"][k]) for k in ("from", "to"))
            hours = [start + timedelta(hours=n) for n in range((end - start) // timedelta(hours=1))]
            rows = [
                {"timestamp": h.isoformat().replace("+00:00", "Z")}
                for h in hours
                if h not in self.empty_hours
            ]
        return {"seed": 1, "row_count": len(rows), "types": self.types, "rows": rows}


class FakeStore:
    def __init__(self, state=None):
        self.objects = dict(state or {})

    def read_json(self, key):
        return self.objects.get(key)

    def write_json(self, key, value):
        self.objects[key] = value

    def write_rows(self, key, rows, metadata):
        self.objects[key] = rows


def test_lands_each_hour_and_moves_the_watermark():
    api, store = FakeApi(STREAM.columns), FakeStore()

    keys = pull_stream(api, store, STREAM, datetime(2026, 11, 1, 2, 30, tzinfo=UTC), FIRST_HOUR, max_hours=24)

    assert keys == [
        "transactions/dt=2026-11-01/hour=00/transactions-20261101T00.jsonl.gz",
        "transactions/dt=2026-11-01/hour=01/transactions-20261101T01.jsonl.gz",
    ]
    assert store.objects[keys[1]] == [{"timestamp": "2026-11-01T01:00:00Z"}]
    assert store.objects["_state/transactions.json"] == {"loaded_through": "2026-11-01T02:00:00Z"}


def test_fetches_several_hours_per_request_and_splits_them_into_hourly_files():
    api, store = FakeApi(STREAM.columns), FakeStore()
    source = replace(STREAM, hours_per_request=2)

    keys = pull_stream(api, store, source, datetime(2026, 11, 1, 5, 0, tzinfo=UTC), FIRST_HOUR, max_hours=24)

    assert [body["window"] for _, body in api.requests] == [
        {"from": "2026-11-01T00:00:00Z", "to": "2026-11-01T02:00:00Z"},
        {"from": "2026-11-01T02:00:00Z", "to": "2026-11-01T04:00:00Z"},
        {"from": "2026-11-01T04:00:00Z", "to": "2026-11-01T05:00:00Z"},
    ]
    assert len(keys) == 5
    assert store.objects[keys[3]] == [{"timestamp": "2026-11-01T03:00:00Z"}]


def test_an_hour_without_rows_still_gets_a_file():
    store = FakeStore()
    api = FakeApi(STREAM.columns, empty_hours=[datetime(2026, 11, 1, 1, tzinfo=UTC)])

    keys = pull_stream(api, store, STREAM, datetime(2026, 11, 1, 2, tzinfo=UTC), FIRST_HOUR, max_hours=24)

    assert store.objects[keys[1]] == []


def test_continues_from_the_watermark():
    store = FakeStore({"_state/transactions.json": {"loaded_through": "2026-11-05T10:00:00Z"}})

    keys = pull_stream(
        FakeApi(STREAM.columns), store, STREAM, datetime(2026, 11, 5, 11, 5, tzinfo=UTC), FIRST_HOUR, 24
    )

    assert keys == ["transactions/dt=2026-11-05/hour=10/transactions-20261105T10.jsonl.gz"]


def test_a_failure_keeps_the_requests_already_landed():
    api, store = FakeApi(STREAM.columns, fail_on=2), FakeStore()
    source = replace(STREAM, hours_per_request=2)

    with pytest.raises(ApiError):
        pull_stream(api, store, source, datetime(2026, 11, 1, 5, tzinfo=UTC), FIRST_HOUR, max_hours=24)

    assert store.objects["_state/transactions.json"] == {"loaded_through": "2026-11-01T02:00:00Z"}
    assert "transactions/dt=2026-11-01/hour=02/transactions-20261101T02.jsonl.gz" not in store.objects


def test_a_contract_change_lands_nothing():
    store = FakeStore()
    changed = {"timestamp": "timestamp", "amount": "string"}

    with pytest.raises(ContractError, match=r"changed types \['amount'\]"):
        pull_stream(FakeApi(changed), store, STREAM, datetime(2026, 11, 1, 5, tzinfo=UTC), FIRST_HOUR, 24)

    assert store.objects == {}


def test_snapshot_lands_at_the_days_key():
    api, store = FakeApi(SNAPSHOT.columns), FakeStore()

    keys = pull_snapshot(api, store, SNAPSHOT, datetime(2026, 11, 20, 6, 15, tzinfo=UTC))

    assert keys == ["merchants/snapshot_date=2026-11-20/merchants-20261120.jsonl.gz"]
    assert api.requests == [("/v1/datasets", {"seed": 1})]
    assert store.objects[keys[0]] == [{"merchant_id": "grocery_0001"}]


def test_rows_are_stored_as_gzipped_json_lines():
    rows = [{"id": "a", "amount": 1.5}, {"id": "b", "amount": None}]
    lines = gzip.decompress(encode_rows(rows)).decode().splitlines()
    assert [json.loads(line) for line in lines] == rows
