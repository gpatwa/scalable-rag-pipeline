# services/api/app/clients/storage/__init__.py
"""
Cloud storage client abstraction layer.
Supports: S3 (default), Azure Blob Storage (future).
"""
from app.clients.storage.base import StorageClient
from app.clients.storage.factory import create_storage_client

__all__ = ["StorageClient", "create_storage_client"]
