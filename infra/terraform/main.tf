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
  backend "s3" {
    bucket         = "rag-platform-terraform-state-prod-1" # Unique bucket name
    key            = "platform/terraform.tfstate"            # Path inside bucket
    region         = "us-east-1"                             # AWS Region
    profile        = "rag-prod"                              # Shared AWS CLI profile for backend auth
    encrypt        = true                                    # Encrypt state at rest
    use_lockfile   = true                                    # Enables state locking via lockfile
  }
}

# Configure the AWS Provider
provider "aws" {
  region  = var.aws_region
  profile = "rag-prod"

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