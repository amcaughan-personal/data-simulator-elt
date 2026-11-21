#!/usr/bin/env bash
# Run the ingest function once for each source, as the schedules do, and fail if any run
# fails:
#
#   scripts/smoke-test.sh <function-name>
#
# Runs are safe to repeat: each lands only what hasn't landed yet. The function runs one at
# a time, so if a scheduled run is in progress, wait and try again.
set -euo pipefail

function_name="$1"
out=$(mktemp)

for source in src/ingest/sources/*.json; do
  name=$(basename "$source" .json)
  for attempt in 1 2 3 4 5; do
    if error=$(aws lambda invoke --function-name "$function_name" \
      --cli-binary-format raw-in-base64-out --payload "{\"source\": \"$name\"}" \
      --query FunctionError --output text "$out" 2>&1); then
      break
    fi
    if [[ "$error" != *TooManyRequestsException* || "$attempt" == 5 ]]; then
      echo "$error" >&2
      exit 1
    fi
    echo "$name: a scheduled run is in progress; retrying in 30 s"
    sleep 30
  done

  if [[ "$error" != "None" ]]; then
    echo "$name: the run failed ($error):" >&2
    cat "$out" >&2
    exit 1
  fi
  echo "$name: $(cat "$out")"
done
