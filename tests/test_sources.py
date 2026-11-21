from ingest.sources import SOURCES_DIR, load_source


def test_every_transaction_merchant_is_in_the_merchants_snapshot():
    """Merchant IDs come from profile names and counts, so the two specs must list the same ones."""
    transactions = load_source("transactions").spec["profiles"]
    merchants = load_source("merchants").spec["profiles"]

    assert {name: p["count"] for name, p in transactions.items()} == {
        name: p["count"] for name, p in merchants.items()
    }


def test_a_days_request_stays_well_inside_the_cell_limit():
    """At the stream's rate, `hours_per_request` hours must fit in a response with room to spare
    (the API allows 100,000 cells; the rate is an average, so leave at least half free)."""
    source = load_source("transactions")
    assert source.spec["rows"]["per"] == "1h"
    cells = source.spec["rows"]["rate"] * source.hours_per_request * len(source.columns)
    assert cells <= 50_000


def test_every_source_file_loads():
    for path in SOURCES_DIR.glob("*.json"):
        assert load_source(path.stem).columns
