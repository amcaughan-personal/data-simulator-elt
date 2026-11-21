include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "${get_repo_root()}/infra/terragrunt/modules/raw-zone"
}

inputs = {
  name        = local.env.name
  sources_dir = "${get_repo_root()}/src/ingest/sources"
}
