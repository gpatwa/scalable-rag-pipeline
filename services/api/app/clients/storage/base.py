# services/api/app/clients/storage/base.py
"""
Protocol definition for cloud storage clients.
All storage providers must implement this interface.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageClient(Protocol):
    """
    Interface for cloud object storage operations.

    Implementations: S3 (AWS / MinIO), Azure Blob Storage, GCS (future).

    Presigned URLs are used so the frontend uploads directly to the
    storage backend, keeping large files off the API server.
    """

    def generate_presigned_upload_url(
        self,
        key: str,
        content_type: str,
        metadata: dict | None = None,
        expires_in: int = 3600,
    ) -> str:
        """
        Generate a time-limited URL for direct file upload.

        Args:
            key: Object key / path in the bucket/container.
            content_type: MIME type of the file (e.g. "application/pdf").
            metadata: Optional key-value metadata to attach.
            expires_in: URL validity in seconds (default 1 hour).

        Returns:
            A presigned URL string.
        """
        ...

    def generate_presigned_download_url(
        self,
        key: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Generate a time-limited URL for direct file download.

        Args:
            key: Object key / path.
            expires_in: URL validity in seconds.

        Returns:
            A presigned URL string.
        """
        ...

    def download_file(
        self,
        key: str,
        local_path: str,
    ) -> None:
        """
        Download an object to a local file path.

        Args:
            key: Object key / path.
            local_path: Local filesystem path to save to.
        """
        ...

    def list_objects(
        self,
        prefix: str,
        max_keys: int = 1000,
    ) -> list[dict]:
        """
        List objects under a prefix.

        Args:
            prefix: Object key prefix to filter by.
            max_keys: Maximum number of results.

        Returns:
            List of dicts: [{"key": str, "size": int, "last_modified": str}, ...]
        """
        ...
