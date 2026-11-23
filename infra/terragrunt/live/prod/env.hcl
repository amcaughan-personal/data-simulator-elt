# Everything that differs between environments. Each stack under live/prod reads this.
locals {
  name               = "data-simulator-elt"
  github_environment = "production" # deploys run in this GitHub environment

  # Email when ingest fails two hours running (the topic is from personal-infra).
  alert_topic_name = "security-alerts"

  # Well past the 31 days a run can catch up, so a failure's logs are still there when
  # someone looks into it.
  log_retention_days = 90
}
