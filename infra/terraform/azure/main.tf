# infra/terraform/azure/main.tf
# Azure provider configuration and backend state storage.
# Equivalent to the AWS main.tf with S3 backend.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.47"
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

  # REMOTE STATE STORAGE (Azure Storage Account)
  # Create this manually once before running terraform init:
  #   az storage account create -n ragterraformstate -g rag-platform-tfstate -l eastus --sku Standard_LRS
  #   az storage container create -n tfstate --account-name ragterraformstate
  backend "azurerm" {
    resource_group_name  = "rag-platform-tfstate"
    storage_account_name = "ragterraformstate"
    container_name       = "tfstate"
    key                  = "platform/terraform.tfstate"
  }
}

# Configure the Azure Provider
provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false # Allow destroy in dev
    }
    key_vault {
      purge_soft_delete_on_destroy = true
    }
  }
}

provider "azuread" {}

# Data source: current Azure subscription and client
data "azurerm_client_config" "current" {}

# Resource Group — all Azure resources live here
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    Project     = "Enterprise-RAG"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Kubernetes provider — configured after AKS is created
provider "kubernetes" {
  host                   = azurerm_kubernetes_cluster.aks.kube_config[0].host
  client_certificate     = base64decode(azurerm_kubernetes_cluster.aks.kube_config[0].client_certificate)
  client_key             = base64decode(azurerm_kubernetes_cluster.aks.kube_config[0].client_key)
  cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.aks.kube_config[0].cluster_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = azurerm_kubernetes_cluster.aks.kube_config[0].host
    client_certificate     = base64decode(azurerm_kubernetes_cluster.aks.kube_config[0].client_certificate)
    client_key             = base64decode(azurerm_kubernetes_cluster.aks.kube_config[0].client_key)
    cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.aks.kube_config[0].cluster_ca_certificate)
  }
}
