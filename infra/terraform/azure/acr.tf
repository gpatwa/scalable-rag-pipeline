# infra/terraform/azure/acr.tf
# Azure Container Registry — equivalent to AWS ECR.
# Stores Docker images for the RAG API.

resource "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic" # Dev: Basic (~$5/mo) (prod: Standard or Premium)
  admin_enabled       = false   # Use Managed Identity instead of admin password

  tags = {
    Project     = "Enterprise-RAG"
    Environment = var.environment
  }
}
