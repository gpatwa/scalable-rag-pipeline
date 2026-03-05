# infra/terraform/outputs.tf

output "eks_cluster_name" {
  description = "The name of the EKS cluster."
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "The endpoint for the EKS cluster's API server."
  value       = module.eks.cluster_endpoint
}

output "aurora_db_endpoint" {
  description = "The writer endpoint for the Aurora PostgreSQL cluster."
  value       = module.aurora.cluster_endpoint
}

output "redis_primary_endpoint" {
  description = "The primary endpoint for the ElastiCache Redis cluster."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "s3_documents_bucket_name" {
  description = "The name of the S3 bucket for document storage."
  value       = aws_s3_bucket.documents.id
}