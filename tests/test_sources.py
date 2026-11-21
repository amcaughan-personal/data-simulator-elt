from ingest.sources import load_source


def test_every_transaction_merchant_is_in_the_merchants_snapshot():
    """Merchant IDs come from profile names and counts, so the two specs must list the same ones."""
    transactions = load_source("transactions").spec["profiles"]
    merchants = load_source("merchants").spec["profiles"]

    assert {name: p["count"] for name, p in transactions.items()} == {
        name: p["count"] for name, p in merchants.items()
    }
