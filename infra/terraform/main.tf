# infra/terraform/main.tf

# Define the Terraform configuration
terraform {
  # We require a recent version of Terraform for stability
  required_version = ">= 1.5.0"

  # Define the providers we need to interact with AWS and Kubernetes
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0" # Use version 5.x for latest features
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }

  # REMOTE STATE STORAGE (Industry Standard)
  # This saves the infrastructure state to S3 so multiple engineers can work safely.
  # Note: You must create this bucket manually once before running terraform init.
  # Per-environment state isolation — set key at init time:
  #   terraform init -backend-config="key=staging/terraform.tfstate" -backend-config="profile=rag-staging"
  #   terraform init -backend-config="key=prod/terraform.tfstate"    -backend-config="profile=rag-prod"
  backend "s3" {
    bucket       = "rag-platform-terraform-state-prod-1"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

# Configure the AWS Provider
provider "aws" {
  region = var.aws_region

  # Apply default tags to ALL resources for cost tracking (FinOps)
  default_tags {
    tags = {
      Project     = "Enterprise-RAG"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

provider "helm" {
  kubernetes {
    config_path = "~/.kube/config"
  }
}