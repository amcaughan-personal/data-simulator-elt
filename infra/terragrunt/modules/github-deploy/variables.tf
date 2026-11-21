variable "function_name" {
  type = string
}

variable "function_arn" {
  type = string
}

variable "github_repository" {
  description = "Repository name within the amcaughan-personal org"
  type        = string
}

variable "github_environment" {
  description = "The GitHub environment whose jobs may deploy (staging or production)"
  type        = string
}
