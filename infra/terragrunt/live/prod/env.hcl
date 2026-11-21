# Everything that differs between environments. Each stack under live/prod reads this.
locals {
  name              = "data-simulator-elt"
  api_url_parameter = "/services/data-simulator-api/prod/url" # published by data-simulator-api

  # Email when ingest fails two hours running (the topic is from personal-infra).
  alert_topic_name = "security-alerts"
}
