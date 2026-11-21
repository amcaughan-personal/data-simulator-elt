# Everything that differs between environments. Each stack under live/staging reads this.
locals {
  name              = "data-simulator-elt-staging"
  api_url_parameter = "/services/data-simulator-api/staging/url" # published by data-simulator-api

  # Staging failures don't email.
  alert_topic_name = null
}
