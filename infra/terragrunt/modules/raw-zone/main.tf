# The raw zone: an S3 bucket the ingest Lambda writes to, and a Glue database whose tables
# let Athena query it. The tables' columns come from the source files the ingest code
# checks responses against, so the two can't disagree.
#
# Partition projection computes partitions from the key layout, so there are no crawlers
# and nothing to repair when new data lands.

data "aws_caller_identity" "current" {}

locals {
  bucket_name   = "${var.name}-raw-${data.aws_caller_identity.current.account_id}"
  database_name = "${replace(var.name, "-", "_")}_raw"

  # API column types -> Athena types. Timestamps stay as the API's ISO 8601 strings in the
  # raw tables; the analytics models parse them.
  athena_types = {
    integer   = "bigint"
    number    = "double"
    string    = "string"
    boolean   = "boolean"
    timestamp = "string"
  }

  tables = {
    transactions = {
      description    = "Card transactions, one file per hour, as the API returned them."
      partition_keys = ["dt", "hour"]
      projection = {
        "projection.dt.type"          = "date"
        "projection.dt.format"        = "yyyy-MM-dd"
        "projection.dt.range"         = "2026-01-01,NOW"
        "projection.dt.interval"      = "1"
        "projection.dt.interval.unit" = "DAYS"
        "projection.hour.type"        = "integer"
        "projection.hour.range"       = "0,23"
        "projection.hour.digits"      = "2"
      }
      template = "dt=$${dt}/hour=$${hour}/"
    }
    merchants = {
      description    = "Daily full snapshots of the merchants, as the API returned them."
      partition_keys = ["snapshot_date"]
      projection = {
        "projection.snapshot_date.type"          = "date"
        "projection.snapshot_date.format"        = "yyyy-MM-dd"
        "projection.snapshot_date.range"         = "2026-01-01,NOW"
        "projection.snapshot_date.interval"      = "1"
        "projection.snapshot_date.interval.unit" = "DAYS"
      }
      template = "snapshot_date=$${snapshot_date}/"
    }
  }

  columns = {
    for name in keys(local.tables) :
    name => jsondecode(file("${var.sources_dir}/${name}.json")).columns
  }
}

# --------------------------------------------------------------------------------------
# Bucket
# --------------------------------------------------------------------------------------

resource "aws_s3_bucket" "raw" {
  #checkov:skip=CKV_AWS_21:Versioning isn't needed: every object can be pulled again from the API at the same key
  #checkov:skip=CKV_AWS_18:Access logging would cost more than the data it protects; CloudTrail covers the account
  #checkov:skip=CKV_AWS_144:Cross-region replication isn't worth it for data that can be pulled again
  #checkov:skip=CKV_AWS_145:SSE-S3 is enough; a customer-managed KMS key adds cost and key management
  #checkov:skip=CKV2_AWS_62:Nothing reacts to new objects; downstream jobs run on a schedule
  bucket = local.bucket_name

  # The data can always be pulled again, so destroying the stack may delete it.
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.raw.arn,
      "${aws_s3_bucket.raw.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "raw" {
  bucket = aws_s3_bucket.raw.id
  policy = data.aws_iam_policy_document.tls_only.json

  depends_on = [aws_s3_bucket_public_access_block.raw]
}

# --------------------------------------------------------------------------------------
# Glue catalog
# --------------------------------------------------------------------------------------

resource "aws_glue_catalog_database" "raw" {
  name        = local.database_name
  description = "Raw data from the data-simulator API, as it was returned. Managed by data-simulator-elt."
}

resource "aws_glue_catalog_table" "raw" {
  for_each = local.tables

  database_name = aws_glue_catalog_database.raw.name
  name          = each.key
  description   = each.value.description
  table_type    = "EXTERNAL_TABLE"

  parameters = merge(each.value.projection, {
    "classification"            = "json"
    "projection.enabled"        = "true"
    "storage.location.template" = "s3://${aws_s3_bucket.raw.id}/${each.key}/${each.value.template}"
  })

  dynamic "partition_keys" {
    for_each = each.value.partition_keys
    content {
      name = partition_keys.value
      type = "string"
    }
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.raw.id}/${each.key}/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    dynamic "columns" {
      for_each = local.columns[each.key]
      content {
        name = columns.key
        type = local.athena_types[columns.value]
      }
    }
  }
}
