# services/api/app/clients/storage/factory.py
"""
Factory for creating cloud storage client instances.
Provider is selected via STORAGE_PROVIDER env var.

Supported providers:
  "s3"         — AWS S3 / MinIO (default)
  "azure_blob" — Azure Blob Storage
"""
import logging

logger = logging.getLogger(__name__)


def create_storage_client(provider: str):
    """
    Create a StorageClient based on the provider name.

    Args:
        provider: "s3" or "azure_blob"

    Returns:
        A StorageClient instance.
    """
    provider = provider.lower().strip()

    if provider == "s3":
        from app.clients.storage.s3 import S3StorageClient
        from app.config import settings

        logger.info("Using S3 storage provider")
        return S3StorageClient(
            bucket=settings.S3_BUCKET_NAME,
            region=settings.AWS_REGION,
            endpoint_url=settings.S3_ENDPOINT_URL,
            access_key_id=settings.AWS_ACCESS_KEY_ID,
            secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    elif provider == "azure_blob":
        from app.clients.storage.azure_blob import AzureBlobStorageClient
        from app.config import settings

        logger.info("Using Azure Blob storage provider")
        return AzureBlobStorageClient(
            account_name=settings.AZURE_STORAGE_ACCOUNT_NAME,
            account_key=settings.AZURE_STORAGE_ACCOUNT_KEY,
            connection_string=settings.AZURE_STORAGE_CONNECTION_STRING,
            container=settings.AZURE_STORAGE_CONTAINER,
        )

    else:
        raise ValueError(
            f"Unknown STORAGE_PROVIDER: '{provider}'. "
            f"Supported: 's3', 'azure_blob'"
        )
