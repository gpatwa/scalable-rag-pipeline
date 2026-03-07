# infra/terraform/azure/storage.tf
# Azure Storage Account + Blob Container — equivalent to AWS S3.
# Used for document uploads (PDFs, videos, etc.).

resource "azurerm_storage_account" "documents" {
  name                     = "${replace(var.cluster_name, "-", "")}docs" # Must be 3-24 chars, alphanumeric
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard" # Dev: Standard (prod: Premium for high IOPS)
  account_replication_type = "LRS"      # Dev: locally redundant (prod: GRS or ZRS)
  account_kind             = "StorageV2"

  # Blob versioning + CORS + retention (single blob_properties block)
  blob_properties {
    versioning_enabled = true

    # Soft delete for accidental deletion recovery
    delete_retention_policy {
      days = 7
    }

    # CORS for direct browser uploads (equivalent to S3 CORS)
    cors_rule {
      allowed_headers    = ["*"]
      allowed_methods    = ["PUT", "POST", "GET"]
      allowed_origins    = ["https://your-rag-domain.com"]
      exposed_headers    = ["ETag"]
      max_age_in_seconds = 3000
    }
  }

  tags = {
    Project     = "Enterprise-RAG"
    Environment = var.environment
    Name        = "Documents Storage"
  }
}

# Blob Container for documents (equivalent to S3 bucket)
resource "azurerm_storage_container" "documents" {
  name                  = "documents"
  storage_account_name  = azurerm_storage_account.documents.name
  container_access_type = "private" # No public access
}
