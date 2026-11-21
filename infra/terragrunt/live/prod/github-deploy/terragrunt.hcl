include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl")).locals
}

terraform {
  source = "${get_repo_root()}/infra/terragrunt/modules/github-deploy"
}

dependency "ingest" {
  config_path = "../ingest"

  mock_outputs = {
    function_name = "mock-ingest"
    function_arn  = "arn:aws:lambda:us-east-2:000000000000:function:mock-ingest"
  }
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan", "providers"]
}

inputs = {
  function_name      = dependency.ingest.outputs.function_name
  function_arn       = dependency.ingest.outputs.function_arn
  github_repository  = "data-simulator-elt"
  github_environment = local.env.github_environment
}
