# Design decisions

Why the pipeline is built the way it is, and what each choice gives up.

- [The source is treated as a third-party feed](#the-source-is-treated-as-a-third-party-feed)
- [Extract and load only; transformation lives downstream](#extract-and-load-only-transformation-lives-downstream)
- [One file per hour, with a watermark](#one-file-per-hour-with-a-watermark)
- [The next run is the retry](#the-next-run-is-the-retry)
- [A contract checked on every response](#a-contract-checked-on-every-response)
- [Raw stays JSON, exactly as received](#raw-stays-json-exactly-as-received)
- [One file defines a source](#one-file-defines-a-source)
- [No look-back for late data](#no-look-back-for-late-data)
- [Lambda and a schedule, no orchestrator or VPC](#lambda-and-a-schedule-no-orchestrator-or-vpc)
- [CI ships code and applies infrastructure, but never deletes](#ci-ships-code-and-applies-infrastructure-but-never-deletes)
- [dev, then prod, without a canary](#dev-then-prod-without-a-canary)

## The source is treated as a third-party feed

**Decision:** the pipeline knows the API only by its URL and its documented behaviour. Both
environments read the API's production endpoint.

**Why:** the point is a pipeline that could pull from any API. A real platform's non-production
environments usually read a vendor's production feed, and the API's own staging environment
belongs to the API's deploys, so coupling to it would break this pipeline for reasons that
aren't its own.

**Trade-off:** an API change reaches this pipeline's dev and prod at the same time.
The contract check (below) stops both rather than letting bad data through.

## Extract and load only; transformation lives downstream

**Decision:** this repo lands data and makes it queryable. Cleaning, typing, joining and
modelling happen in `data-simulator-analytics` with dbt, reading the Glue raw tables.

**Why:** that's where the line usually falls between a data platform and an analytics team. The
raw tables are the contract between them, so each side changes on its own schedule.

## One file per hour, with a watermark

**Decision:** the transactions stream lands one file per hour, at a key fixed by the hour. A small
state object (`_state/transactions.json`) records the end of the last hour landed. Each run lands
the complete hours since then, fetching up to a day per request.

**Why:** fixed keys make every write idempotent: pulling an hour again replaces its file, so
re-runs and replays can't duplicate data. The watermark makes runs self-healing: after an outage,
the next run catches up, oldest first, and moves the watermark after each request.

**Trade-off:** the watermark is a single object written without a lock. Running one Lambda at a
time (reserved concurrency 1) is what keeps two runs from racing on it.

## The next run is the retry

**Decision:**
- Requests to the API retry briefly: three attempts, jittered backoff, honouring `Retry-After`.
- Lambda doesn't retry failed runs, and there's no dead-letter queue.
- Daily snapshots are checked hourly and pulled if today's is missing.
- A run nearly out of time stops between requests.

**Why:** with idempotent writes and a watermark, the next hourly run does exactly what a retry
would, without a second mechanism to reason about. An alarm on two failed hours in a row
separates a blip from a real problem.

**Trade-off:** after a failure, data is up to an hour later than it would be with immediate
retries. For hourly data that's acceptable.

## A contract checked on every response

**Decision:** each source file lists the columns and types it expects. A response with missing,
extra or retyped columns, or rows outside the window asked for, fails the run and lands nothing.

**Why:** schema drift caught at ingestion is one clear error. Caught downstream, it's broken
models or, worse, quietly wrong numbers.

**Trade-off:** any upstream change, even an added column, stops ingestion until the source file
is updated. For a feed that the tables are built from, that's the safer default.

## Raw stays JSON, exactly as received

**Decision:** rows land as gzipped JSON lines, unchanged. Timestamps stay ISO 8601 strings in the
raw tables.

**Why:** raw is the record of what the source said; it can always be re-processed if a model
changes. Converting to Parquet here would add a dependency (pyarrow) and a transformation step
to the one component that should be the simplest. Columnar formats start in the dbt layers.

**Trade-off:** Athena scans more bytes on raw JSON than on Parquet, which at this volume is a
fraction of a cent.

## One file defines a source

**Decision:** a source's file holds its request, how it's loaded (`hourly` or `daily_snapshot`)
and its columns. The Lambda reads it, and so does Terraform: each file gets a Glue table, whose
partitions follow from the load type, and an hourly schedule.

**Why:** adding or changing a source happens in one place, and the tables can't disagree with
the checks.

## No look-back for late data

**Decision:** an hour is pulled once, after it has ended.

**Why:** this source is deterministic: an hour's rows never change after the fact. Many real APIs
do deliver late records, and the usual answer is to re-pull the last few hours each run. With
fixed keys that would be a small change (start each run a few hours before the watermark), but
here it would only add requests.

## Lambda and a schedule, no orchestrator or VPC

**Decision:** EventBridge Scheduler invokes one small Lambda per source every hour. No Step
Functions, Airflow or VPC.

**Why:** each run is a single short step, so an orchestrator would add cost and concepts without
adding control. The function calls a public API and S3, so a VPC would only add NAT or endpoint
costs. Everything is pay-per-use and stays near $0.

## CI ships code and applies infrastructure, but never deletes

**Decision:** Terraform creates the function and then ignores its code. Every code change ships
through the deploy workflow. Infrastructure changes are planned on the pull request and applied
from `main` by CI, dev first, prod after approval. CI's apply role can create and change this
repo's resources but not delete them; anything that would destroy or replace a resource is
applied by hand.

**Why:** code changes are frequent and low-risk to roll back. Infrastructure changes are rarer,
and the risky ones are deletes, so those keep a person in the loop. Each CI role is as narrow as
its job, and all of them are defined in personal-infra, out of this repo's reach:

- The deploy role can update and invoke one function, from that GitHub environment on `main`.
- The apply role can act only on `data-simulator-elt*` resources, only from the `infra-*`
  environments. Roles it creates must carry a permissions boundary that caps them at this
  repo's logs, buckets and functions, so an apply can't hand out more than it has.
- The plan role used on pull requests is read-only and can't read data or secrets.

## dev, then prod, without a canary

**Decision:** each deploy goes to dev, runs every source once as a smoke test, then repeats both
for prod. There's no gradual rollout.

**Why:** a canary splits live traffic between versions, and a batch job has no traffic to split:
a run either works or doesn't. The smoke test is a real run, and since runs are idempotent it
lands real data rather than a test case. If a bad version gets through, the alarm fires, and
re-running an earlier deploy restores the last good code; the next run catches up.
