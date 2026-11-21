import io
import json
import urllib.error

import pytest

from ingest import api as api_module
from ingest.api import ApiClient, ApiError, ContractError, check_contract


def http_error(status, headers=None):
    return urllib.error.HTTPError("https://api.test/x", status, "error", headers or {}, io.BytesIO(b"{}"))


def responding_with(*outcomes):
    """A stand-in for urlopen that raises or returns each outcome in turn."""
    calls = []

    def urlopen(request, timeout):
        outcome = outcomes[len(calls)]
        calls.append(request)
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(json.dumps(outcome).encode())

    return urlopen, calls


@pytest.fixture
def sleeps(monkeypatch):
    waits = []
    monkeypatch.setattr(api_module.time, "sleep", waits.append)
    return waits


@pytest.fixture
def client(sleeps):
    return ApiClient("https://api.test/", attempts=3, backoff_seconds=2)


def test_retries_when_the_api_is_briefly_unavailable(client, monkeypatch):
    urlopen, calls = responding_with(http_error(503), http_error(429), {"rows": []})
    monkeypatch.setattr(api_module.urllib.request, "urlopen", urlopen)

    assert client.post("/v1/datasets", {"seed": 1}) == {"rows": []}
    assert len(calls) == 3
    assert calls[0].full_url == "https://api.test/v1/datasets"


def test_waits_as_long_as_the_server_asks_within_reason(client, monkeypatch, sleeps):
    urlopen, _ = responding_with(
        http_error(429, {"Retry-After": "7"}), http_error(429, {"Retry-After": "600"}), {"rows": []}
    )
    monkeypatch.setattr(api_module.urllib.request, "urlopen", urlopen)

    client.post("/v1/datasets", {})
    assert sleeps == [7, 30]


def test_backs_off_with_jitter(client, monkeypatch, sleeps):
    urlopen, _ = responding_with(http_error(503), http_error(503), {"rows": []})
    monkeypatch.setattr(api_module.urllib.request, "urlopen", urlopen)

    client.post("/v1/datasets", {})
    assert 1 <= sleeps[0] <= 3 and 2 <= sleeps[1] <= 6


def test_gives_up_after_the_last_attempt(client, monkeypatch):
    urlopen, calls = responding_with(http_error(503), http_error(503), http_error(503))
    monkeypatch.setattr(api_module.urllib.request, "urlopen", urlopen)

    with pytest.raises(ApiError, match="HTTP 503"):
        client.post("/v1/datasets", {})
    assert len(calls) == 3


@pytest.mark.parametrize("status", [403, 422])
def test_does_not_retry_errors_that_wont_go_away(client, monkeypatch, status):
    urlopen, calls = responding_with(http_error(status))
    monkeypatch.setattr(api_module.urllib.request, "urlopen", urlopen)

    with pytest.raises(ApiError, match=f"HTTP {status}"):
        client.post("/v1/datasets", {})
    assert len(calls) == 1


def test_contract_names_what_changed():
    expected = {"id": "string", "amount": "number", "city": "string"}
    actual = {"id": "string", "amount": "integer", "country": "string"}

    with pytest.raises(ContractError) as error:
        check_contract({"types": actual}, expected)
    assert (
        str(error.value)
        == "missing columns ['city'], unexpected columns ['country'], changed types ['amount']"
    )
