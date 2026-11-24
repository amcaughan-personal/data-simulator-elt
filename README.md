# data-simulator-elt

> **Paused (November 2026).** The AWS resources are torn down to save cost, so nothing is
> ingesting; the code, infrastructure and CI are all here. [Resuming](#resuming) brings it
> back.

Pulls a small payments business's data from an external API into a raw zone in S3,
incrementally, for querying with Athena. The source is the
[data-simulator API](https://github.com/amcaughan-personal/data-simulator-api), but nothing
here depends on how it's built: to this pipeline it's a third-party feed. Downstream,
`data-simulator-analytics` transforms the raw tables with dbt and publishes a dashboard.

```
EventBridge Scheduler (hourly) ─► ingest Lambda ─► S3 raw zone ─► Glue tables ─► Athena
```

- **Transactions:** an endless stream (`POST /v1/streams/window`), landed one complete hour per
  file. A watermark records the last hour landed, so runs continue from there and catch up after
  an outage, fetching up to a day per request.
- **Merchants:** a full snapshot (`POST /v1/datasets`) once a day. It's checked every hour and
  pulled when today's hasn't landed, so a failed pull is retried an hour later.

Raw data lands as the API returned it, as gzipped JSON lines. Each hour (or day) has one fixed
key, so pulling it again replaces it instead of duplicating it.

Each source is one file in [`src/ingest/sources/`](src/ingest/sources): the spec sent to the API,
how it's loaded, and the columns and types expected back. Every response is checked against
those types before anything lands, so a change in the API stops the pipeline instead of quietly
breaking the tables. The Glue tables and schedules are built from the same files, so adding a
source means adding a file.

Why it's built this way: [design decisions](docs/design-decisions.md).

## AWS

Two Terragrunt stacks per environment, with `env.hcl` holding the only differences. `dev` is a
full copy of the pipeline that infrastructure and code changes go through before `prod`, and a
place to experiment; both read the same production feed.

| Stack | What it holds |
|---|---|
| `raw-zone` | the raw S3 bucket and a Glue database with two tables per source (partition projection, so no crawlers): `<source>` covers the last 14 days, `<source>_history` everything since the first day |
| `ingest` | the Lambda (one run at a time, so runs can't race on the watermark), an hourly EventBridge schedule per source (at :05 UTC) and, in prod, an alarm that emails after two failed hours in a row |

The role GitHub Actions deploys code as lives in personal-infra (`github-ci-roles/data-simulator-elt/deploy-<env>`): only that GitHub environment's jobs can assume it, and it can update and invoke this one function. Every IAM role created here carries personal-infra's permissions boundary for this repo.

The API's URL is looked up from `/services/data-simulator-api/prod/url`, where the API
publishes it. Both environments read the production API, as they would any external feed.

Cost: about $0.12 a month, nearly all of it prod's one alarm ($0.10 beyond CloudWatch's 10 free
alarms). Lambda, EventBridge Scheduler and the Glue catalog stay within the free tier at this
volume, and S3 holds a few MB per month per environment.

## Deploys

Infrastructure changes get a plan comment on their pull request, and
[terragrunt-apply](.github/workflows/terragrunt-apply.yml) applies them after merging: dev, then
prod once approved. It can create and change this repo's resources but not delete them, so a
change that would destroy or replace anything stops there and is applied by hand. Code ships
through [the deploy workflow](.github/workflows/deploy.yml) on every merge that changes it:
build the package once, deploy to dev and run each source once as a smoke test, then the same
for prod. Rolling back is re-running an earlier deploy.

A [daily drift check](.github/workflows/drift.yml) plans `main` read-only and fails if AWS
doesn't match it: a change made outside Terraform, or one merged but not applied.

## Operations

**Failures retry themselves.** Every load is safe to re-run, and each hourly run picks up
whatever the last one didn't finish: hours after the watermark, or today's snapshot if it's
missing. A run that's running out of time stops between requests and the next continues.
There are no Lambda retries or dead-letter queues, because the next run is the retry.

**The alarm** (`data-simulator-elt-ingest-errors`, prod only) emails when runs fail in two
consecutive hours. The Lambda's JSON logs say why: every run logs a `run finished` line with
how many files it landed, and failures log the error. Common causes are the API being down or rate-limiting, or a
contract error (the API changed its columns or types). Fix the cause; the next run catches up
on its own.

**Replaying or backfilling** a range: set the watermark back, and the next run re-pulls from
there, overwriting the same files.

```bash
echo '{"loaded_through": "2026-11-10T00:00:00Z"}' |
  aws s3 cp - s3://<raw-bucket>/_state/transactions.json
```

To re-pull a day's merchants snapshot, delete that day's file.

**Querying the raw data** (Athena, database `<name>_raw`). `transactions` and `merchants`
cover the last 14 days; `transactions_history` and `merchants_history` reach back to the first
day, for full rebuilds. Filter on `dt` (or `snapshot_date`) where you can: Athena lists one S3
prefix per partition it can't rule out.

```sql
select dt, count(*) as transactions
from transactions
where dt >= '2026-11-20'
group by dt
order by dt;
```

## Resuming

1. Revert the pause PR, which turns the automatic triggers back on (deploy, apply, drift).
2. Run [terragrunt-apply](.github/workflows/terragrunt-apply.yml) by hand (Actions, *Run
   workflow*), or apply `raw-zone` then `ingest` in each environment locally. CI's apply role
   can create everything here, including the function from the code in `src/`.
3. The first hourly runs land everything since `first_hour` (1 November), at most 31 days per
   run; data-simulator-analytics can then be resumed.

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
  sources/         one file per source: the request, how it's loaded, the columns expected
  windows.py       which hours to pull next, and where each lands
  pipeline.py      pull, check against the contract, land, move the watermark
  api.py, store.py the API client (retries with backoff) and the S3 raw zone
  handler.py       Lambda entry point
tests/
scripts/           build, deploy and smoke-test the Lambda (used by the deploy workflow)
infra/terragrunt/  Terraform/Terragrunt for AWS
docs/              design decisions
```

## License

MIT
