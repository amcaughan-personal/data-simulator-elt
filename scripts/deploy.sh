#!/usr/bin/env bash
# Upload a built package to one environment's ingest function and wait until it's live:
#
#   scripts/deploy.sh <function-name> <path/to/ingest.zip>
#
# Scheduled runs use the function's latest code, so the next run after this uses it.
# Rolling back is re-running an earlier deploy.
set -euo pipefail

function_name="$1"
package="$2"

echo "Uploading $package to $function_name"
aws lambda update-function-code --function-name "$function_name" \
  --zip-file "fileb://$package" --query CodeSha256 --output text
aws lambda wait function-updated-v2 --function-name "$function_name"
echo "$function_name is running the new code"
