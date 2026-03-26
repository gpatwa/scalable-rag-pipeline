# infra/terraform/azure/variables.tf

variable "location" {
  description = "Azure region to deploy resources"
  type        = string
  default     = "eastus" # East US has good GPU availability and competitive pricing
}

variable "environment" {
  description = "Environment name (e.g., dev, prod)"
  type        = string
  default     = "prod"
}

variable "resource_group_name" {
  description = "Name of the Azure Resource Group"
  type        = string
  default     = "rag-platform-rg"
}

variable "cluster_name" {
  description = "Name of the AKS Cluster"
  type        = string
  default     = "rag-platform-aks"
}

variable "vnet_cidr" {
  description = "CIDR block for the VNet"
  type        = string
  default     = "10.0.0.0/16" # Same as AWS VPC for parity
}

variable "db_password" {
  description = "Administrator password for PostgreSQL Flexible Server"
  type        = string
  sensitive   = true
}

variable "acr_name" {
  description = "Name of the Azure Container Registry (must be globally unique, alphanumeric only)"
  type        = string
  default     = "ragplatformacr"
}

variable "jwt_secret_key" {
  description = "JWT signing secret for HS256 tokens"
  type        = string
  sensitive   = true
}

variable "neo4j_password" {
  description = "Password for Neo4j graph database"
  type        = string
  sensitive   = true
  default     = "password" # Override via tfvars for production
}

variable "openai_api_key" {
  description = "OpenAI API key (leave empty to skip Key Vault storage)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "Google Gemini API key for multimodal embeddings (leave empty to skip)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "tavily_api_key" {
  description = "Tavily API key for web search tool (leave empty to skip)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "kubernetes_version" {
  description = "Kubernetes version for AKS"
  type        = string
  default     = "1.29" # Match AWS EKS version for parity
}
