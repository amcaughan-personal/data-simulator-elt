variable "name" {
  description = "Name prefix for this environment, e.g. data-simulator-elt-dev"
  type        = string
}

variable "sources_dir" {
  description = "Directory holding the source files (src/ingest/sources); their columns define the tables"
  type        = string
}

variable "window_days" {
  description = "How many days back the routine tables reach. Bounds what any query on them lists; must cover the longest gap analytics catches up after."
  type        = number
  default     = 14
}

variable "first_day" {
  description = "The first day of data (yyyy-MM-dd): where the _history tables start. Matches the ingest stack's first_hour."
  type        = string
}
