# data-simulator-elt

Pulls a small payments business's data from the
[data-simulator API](https://github.com/amcaughan-personal/data-simulator-api) into a raw zone in
S3, incrementally, for querying with Athena. Downstream, `data-simulator-analytics` transforms it
with dbt and publishes a dashboard.

```
EventBridge Scheduler (hourly) ─► ingest Lambda ─► S3 raw zone ─► Glue tables ─► Athena
```

- **Transactions:** an endless stream (`POST /v1/streams/window`), pulled one complete hour at a
  time. A watermark records the last hour landed, so runs continue from there and catch up after
  an outage.
- **Merchants:** a daily full snapshot (`POST /v1/datasets`).

Raw data lands as the API returned it, as gzipped JSON lines partitioned by date and hour. Each
hour has one fixed key, so pulling it again replaces it instead of duplicating it.

Each source is one file in [`src/ingest/sources/`](src/ingest/sources): the spec sent to the API
and the columns and types expected back. Every response is checked against those types before
anything lands, so a change in the API stops the pipeline instead of quietly breaking the tables.

## Status

The ingest code runs locally against the API. Its AWS infrastructure (bucket, Glue tables,
Lambda, schedules) is built next.

## Run it locally

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

uv uses the Python version in `.python-version`. For infrastructure work, open the repo in the dev
container (VS Code: *Reopen in Container*): the org's base image (from
[dev-environment](https://github.com/amcaughan-personal/dev-environment)) plus the Terraform,
Terragrunt and uv versions from `.tool-versions`.

## Repository layout

```
src/ingest/
  sources/         what each source asks the API for, and the columns it expects back
  windows.py       which hours to pull next, and where each lands
  pipeline.py      pull, check against the contract, land, move the watermark
  api.py, store.py the API client and the S3 raw zone
  handler.py       Lambda entry point
tests/
infra/terragrunt/  Terraform/Terragrunt for AWS
```

## License

MIT
