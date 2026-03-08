# infra/terraform/azure/envs/prod.tfvars
# Production environment — full resources, HA settings.
#
# Usage:
#   terraform init -backend-config="key=prod/terraform.tfstate"
#   terraform apply -var-file=envs/prod.tfvars

environment         = "prod"
resource_group_name = "rag-platform-rg"
cluster_name        = "rag-platform-aks"
acr_name            = "ragplatformacr" # Shared ACR across environments
vnet_cidr           = "10.0.0.0/16"

# Secrets — set via TF_VAR_* or prompt at apply time
# db_password     = ""
# jwt_secret_key  = ""
# neo4j_password  = ""
# openai_api_key  = ""
