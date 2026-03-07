# infra/terraform/azure/aks.tf
# Azure Kubernetes Service — equivalent to AWS EKS.
# Uses system + app node pools (like EKS managed node groups).
# Cluster Autoscaler is built into AKS (no Karpenter needed).

resource "azurerm_kubernetes_cluster" "aks" {
  name                = var.cluster_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = var.cluster_name
  kubernetes_version  = var.kubernetes_version

  # System node pool — runs CoreDNS, metrics-server, etc.
  default_node_pool {
    name                 = "system"
    vm_size              = "Standard_B2s" # Burstable 2 vCPU, 4 GB — similar to t3a.medium
    node_count           = 1
    min_count            = 1
    max_count            = 2
    auto_scaling_enabled = true
    os_disk_size_gb      = 30
    vnet_subnet_id       = azurerm_subnet.aks.id

    # Taint system nodes so app pods don't schedule here
    node_taints = ["CriticalAddonsOnly=true:NoSchedule"]

    node_labels = {
      "nodepool" = "system"
    }

    # Spot pricing is not available on the default pool — use regular VMs
    # (Azure requires at least one non-spot pool as default)
  }

  # Managed Identity (replaces AWS IRSA with Azure Workload Identity)
  identity {
    type = "SystemAssigned"
  }

  # Enable OIDC issuer for Workload Identity (equivalent to EKS IRSA)
  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  # Networking: Azure CNI for pod-level VNet integration
  network_profile {
    network_plugin    = "azure"
    network_policy    = "calico"
    load_balancer_sku = "standard"
    service_cidr      = "10.1.0.0/16"
    dns_service_ip    = "10.1.0.10"
  }

  tags = {
    Project     = "Enterprise-RAG"
    Environment = var.environment
  }
}

# App node pool — runs API, Qdrant, Neo4j pods (like EKS app node group)
resource "azurerm_kubernetes_cluster_node_pool" "app" {
  name                  = "app"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.aks.id
  vm_size               = "Standard_B2s" # Dev: burstable (prod: Standard_D4s_v5+)
  node_count            = 1
  min_count             = 1
  max_count             = 3
  auto_scaling_enabled  = true
  os_disk_size_gb       = 30
  vnet_subnet_id        = azurerm_subnet.aks.id
  priority              = "Spot" # Spot VMs for dev cost savings (~70% cheaper)
  eviction_policy       = "Delete"
  spot_max_price        = -1 # Pay up to on-demand price

  node_labels = {
    "nodepool"                              = "app"
    "kubernetes.azure.com/scalesetpriority" = "spot"
  }

  node_taints = ["kubernetes.azure.com/scalesetpriority=spot:NoSchedule"]

  tags = {
    Project     = "Enterprise-RAG"
    Environment = var.environment
  }
}

# Assign AcrPull role so AKS can pull images from ACR
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.aks.kubelet_identity[0].object_id
}
