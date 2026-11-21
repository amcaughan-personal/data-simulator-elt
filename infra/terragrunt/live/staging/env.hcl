# Everything that differs between environments. Each stack under live/staging reads this.
locals {
  name               = "data-simulator-elt-staging"
  github_environment = "staging" # deploys run in this GitHub environment

  # Staging failures don't email.
  alert_topic_name = null
}
