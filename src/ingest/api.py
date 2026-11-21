"""A small client for the data-simulator API, and the check that responses match the contract."""

import json
import random
import time
import urllib.error
import urllib.request
from typing import Any

# Worth retrying: the API is briefly unavailable or at its concurrency limit. Anything else
# (an invalid spec, or WAF's 403 for too many requests) won't succeed a few seconds later.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# A server's `Retry-After` is honoured up to this many seconds.
MAX_RETRY_AFTER_SECONDS = 30


class ApiError(Exception):
    pass


class ContractError(Exception):
    """The API returned columns or types other than the ones the raw tables expect."""


class ApiClient:
    def __init__(self, base_url: str, attempts: int = 3, backoff_seconds: float = 2.0, timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.attempts = attempts
        self.backoff_seconds = backoff_seconds
        self.timeout = timeout

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        for attempt in range(1, self.attempts + 1):
            wait = self.backoff_seconds * attempt * random.uniform(0.5, 1.5)  # jitter
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code not in RETRYABLE_STATUSES or attempt == self.attempts:
                    raise ApiError(f"POST {path}: HTTP {error.code}: {error.read()[:500]!r}") from error
                wait = _retry_after(error) or wait
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt == self.attempts:
                    raise ApiError(f"POST {path}: {error}") from error
            time.sleep(wait)
        raise AssertionError("unreachable")


def _retry_after(error: urllib.error.HTTPError) -> float | None:
    """The server's `Retry-After` (in seconds), if it sent a usable one."""
    value = error.headers.get("Retry-After") if error.headers else None
    if value and value.isdigit():
        return min(float(value), MAX_RETRY_AFTER_SECONDS)
    return None


def check_contract(response: dict[str, Any], expected: dict[str, str]) -> None:
    """Fail loudly if the response's column types differ from what the raw tables expect."""
    actual = response["types"]
    if actual != expected:
        missing = sorted(expected.keys() - actual.keys())
        extra = sorted(actual.keys() - expected.keys())
        changed = sorted(c for c in expected.keys() & actual.keys() if expected[c] != actual[c])
        raise ContractError(f"missing columns {missing}, unexpected columns {extra}, changed types {changed}")
