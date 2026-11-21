include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "${get_repo_root()}/infra/terragrunt/modules/ingest"
}

dependency "raw_zone" {
  config_path = "../raw-zone"

  mock_outputs = {
    bucket_name = "mock-raw-bucket"
    bucket_arn  = "arn:aws:s3:::mock-raw-bucket"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan", "providers"]
}

inputs = {
  function_name = "${local.env.name}-ingest"
  package_dir   = "${get_repo_root()}/src" # zipped with the ingest package at its root
  sources_dir   = "${get_repo_root()}/src/ingest/sources"

  # To this pipeline the API is an external source: both environments read its production
  # feed, whose URL the API publishes here.
  api_url_parameter = "/services/data-simulator-api/prod/url"

  raw_bucket_name  = dependency.raw_zone.outputs.bucket_name
  raw_bucket_arn   = dependency.raw_zone.outputs.bucket_arn
  alert_topic_name = local.env.alert_topic_name

  # Land everything since 1 November; after that, each hourly run pulls one hour. A run
  # catches up at most 31 days, a request per day (see hours_per_request in the source file).
  first_hour        = "2026-11-01T00:00:00Z"
  max_hours_per_run = 744
}
