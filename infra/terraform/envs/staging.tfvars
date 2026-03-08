# infra/terraform/envs/staging.tfvars
# Staging environment — lightweight, cost-optimized for pre-prod validation.
#
# Usage:
#   terraform init -backend-config="key=staging/terraform.tfstate" -backend-config="profile=rag-staging"
#   terraform apply -var-file=envs/staging.tfvars

environment  = "staging"
cluster_name = "rag-platform-staging"
vpc_cidr     = "10.1.0.0/16" # Non-overlapping with prod (10.0.0.0/16)

# db_password — set via TF_VAR_db_password or prompt at apply time
