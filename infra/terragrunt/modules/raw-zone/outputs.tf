output "bucket_name" {
  value = aws_s3_bucket.raw.id
}

output "bucket_arn" {
  value = aws_s3_bucket.raw.arn
}

output "database_name" {
  value = aws_glue_catalog_database.raw.name
}
