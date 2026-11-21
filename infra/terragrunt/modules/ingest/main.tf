# The ingest Lambda and its schedules: every hour it pulls the transactions stream (catching
# up from its watermark), and once a day the merchants snapshot. See src/ingest.
#
# Terraform owns the function's configuration; CI owns its code. The package built here is
# only for creating the function. Deploys upload new code after that.

# The API publishes its URL here; looking it up means following it if it ever changes
# (on the next apply).
data "aws_ssm_parameter" "api_url" {
  name = var.api_url_parameter
}

data "aws_sns_topic" "alerts" {
  count = var.alert_topic_name == null ? 0 : 1
  name  = var.alert_topic_name
}

data "archive_file" "initial_package" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${path.root}/.build/ingest.zip"
  excludes    = ["**/__pycache__/**"]
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
}

# --------------------------------------------------------------------------------------
# Function: writes its own logs and the raw bucket, nothing else
# --------------------------------------------------------------------------------------

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "function" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }

  statement {
    sid       = "ReadAndWriteRawZone"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${var.raw_bucket_arn}/*"]
  }

  # Without it, reading a watermark that doesn't exist yet is "access denied", not "no such key".
  statement {
    sid       = "ListRawZone"
    actions   = ["s3:ListBucket"]
    resources = [var.raw_bucket_arn]
  }
}

resource "aws_iam_role" "function" {
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy" "function" {
  name   = "ingest"
  role   = aws_iam_role.function.id
  policy = data.aws_iam_policy_document.function.json
}

resource "aws_lambda_function" "this" {
  #checkov:skip=CKV_AWS_117:No VPC: the function calls a public API and S3, so a VPC would add cost (NAT or endpoints) without isolating anything
  #checkov:skip=CKV_AWS_50:X-Ray tracing isn't needed for a single small function
  #checkov:skip=CKV_AWS_272:Code signing adds a signing profile and process for no real gain here
  #checkov:skip=CKV_AWS_173:The environment holds no secrets, only names and settings
  #checkov:skip=CKV_AWS_116:Failed runs aren't retried or kept: the next hourly run catches up from the watermark, and the error alarm reports failures
  function_name = var.function_name
  description   = "Pulls the data-simulator API into the raw zone (data-simulator-elt)"
  role          = aws_iam_role.function.arn
  runtime       = "python3.14"
  architectures = ["arm64"]
  handler       = "ingest.handler.handler"

  filename         = data.archive_file.initial_package.output_path
  source_code_hash = data.archive_file.initial_package.output_base64sha256

  memory_size = 256
  timeout     = var.timeout_seconds

  # One run at a time, so two runs can never race on the watermark.
  reserved_concurrent_executions = 1

  environment {
    variables = {
      API_URL           = data.aws_ssm_parameter.api_url.insecure_value
      RAW_BUCKET        = var.raw_bucket_name
      FIRST_HOUR        = var.first_hour
      MAX_HOURS_PER_RUN = tostring(var.max_hours_per_run)
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.this.name
  }

  depends_on = [aws_iam_role_policy.function]

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

# Scheduler invokes asynchronously. A failed run isn't retried: the next one catches up.
resource "aws_lambda_function_event_invoke_config" "this" {
  function_name                = aws_lambda_function.this.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 3600
}

# --------------------------------------------------------------------------------------
# Schedules
# --------------------------------------------------------------------------------------

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.this.arn]
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.function_name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "invoke-ingest"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

locals {
  schedules = {
    transactions = "cron(5 * * * ? *)"  # 5 minutes past every hour (UTC)
    merchants    = "cron(15 6 * * ? *)" # 06:15 UTC every day
  }
}

resource "aws_scheduler_schedule" "this" {
  #checkov:skip=CKV_AWS_297:The schedule's only data is {"source": "<name>"}; AWS-owned encryption is enough
  for_each = local.schedules

  name                = "${var.function_name}-${each.key}"
  schedule_expression = each.value

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.this.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ source = each.key })

    retry_policy {
      maximum_retry_attempts       = 3
      maximum_event_age_in_seconds = 3600
    }
  }
}

# --------------------------------------------------------------------------------------
# Alarm: two failed hours in a row
# --------------------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.function_name}-errors"
  alarm_description   = "${var.function_name} failed in two consecutive hours. Its logs say why; the next successful run catches up."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.this.function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = data.aws_sns_topic.alerts[*].arn
  ok_actions          = data.aws_sns_topic.alerts[*].arn
}
