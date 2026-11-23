# Everything that differs between environments. Each stack under live/dev reads this.
#
# dev is a full copy of the pipeline that infrastructure and code changes go through before
# prod, and a place to experiment. It reads the same production feed as prod.
locals {
  name               = "data-simulator-elt-dev"
  github_environment = "dev" # deploys run in this GitHub environment

  # dev failures don't email, so dev has no alarm; its logs show failures.
  alert_topic_name = null

  # Nobody looks back far at dev logs.
  log_retention_days = 7
}
