variable "name" {
  description = "Name prefix for this environment, e.g. data-simulator-elt-staging"
  type        = string
}

variable "sources_dir" {
  description = "Directory holding the source files (src/ingest/sources); their columns define the tables"
  type        = string
}
