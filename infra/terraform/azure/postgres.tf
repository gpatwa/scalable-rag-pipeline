# infra/terraform/azure/postgres.tf
# Azure Database for PostgreSQL Flexible Server — equivalent to AWS Aurora Serverless v2.
# Burstable tier for dev, scalable to General Purpose for production.

resource "azurerm_postgresql_flexible_server" "main" {
  name                   = "${var.cluster_name}-postgres"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "15" # Match Aurora PostgreSQL 15
  administrator_login    = "ragadmin"
  administrator_password = var.db_password
  storage_mb             = 32768 # 32 GB (minimum for Burstable)
  backup_retention_days  = 7

  # Dev: Burstable B1ms (1 vCPU, 2 GB) — ~$13/mo
  # Prod: General Purpose D2s_v3 (2 vCPU, 8 GB) or higher
  sku_name = "B_Standard_B1ms"

  # VNet integration — PostgreSQL is accessible only from within the VNet
  delegated_subnet_id = azurerm_subnet.database.id
  private_dns_zone_id = azurerm_private_dns_zone.postgres.id

  # High Availability — disabled for dev (enable for prod)
  # high_availability {
  #   mode = "ZoneRedundant"
  # }

  tags = {
    Project     = "Enterprise-RAG"
    Environment = var.environment
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

# Database within the server
resource "azurerm_postgresql_flexible_server_database" "ragdb" {
  name      = "ragdb"
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "utf8"
}

# Firewall rule — allow Azure services (for dev access from portal)
resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name      = "allow-azure-services"
  server_id = azurerm_postgresql_flexible_server.main.id
  # 0.0.0.0 to 0.0.0.0 = allow Azure internal services
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
