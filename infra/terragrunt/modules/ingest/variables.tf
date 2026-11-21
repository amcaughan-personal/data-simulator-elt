variable "function_name" {
  type = string
}

variable "source_dir" {
  description = "Directory holding the ingest package (src), zipped to create the function"
  type        = string
}

variable "api_url_parameter" {
  description = "SSM parameter holding the data-simulator API's base URL"
  type        = string
}

variable "raw_bucket_name" {
  type = string
}

variable "raw_bucket_arn" {
  type = string
}

variable "first_hour" {
  description = "Where the transactions stream starts landing (ISO 8601, on the hour)"
  type        = string
}

variable "max_hours_per_run" {
  description = "How many hours one run catches up at most"
  type        = number
}

variable "timeout_seconds" {
  type    = number
  default = 300
}

variable "alert_topic_name" {
  description = "SNS topic to email when the alarm fires; null for no email"
  type        = string
  default     = null
}

variable "log_retention_days" {
  type    = number
  default = 30
}
