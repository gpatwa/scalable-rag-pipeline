# infra/terraform/envs/prod.tfvars
# Production environment — full resources, HA settings.
#
# Usage:
#   terraform init -backend-config="key=prod/terraform.tfstate" -backend-config="profile=rag-prod"
#   terraform apply -var-file=envs/prod.tfvars

environment  = "prod"
cluster_name = "rag-platform-cluster"
vpc_cidr     = "10.0.0.0/16"

# db_password — set via TF_VAR_db_password or prompt at apply time
