# infra/terraform/variables.tf

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1" # N. Virginia has the best GPU availability
}

variable "environment" {
  description = "Environment name (e.g., dev, prod)"
  type        = string
  default     = "prod"
}

variable "cluster_name" {
  description = "Name of the EKS Cluster"
  type        = string
  default     = "rag-platform-cluster"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16" # Gives us 65,536 IPs
}

variable "db_password" {
  description = "Master password for Aurora Postgres"
  type        = string
  sensitive   = true # Terraform will hide this in logs
}