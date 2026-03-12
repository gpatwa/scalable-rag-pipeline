# pipelines/ingestion/indexing/qdrant.py
import os
import uuid
import logging
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = "default"

_MIME_TO_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
}


class QdrantIndexer:
    """
    Writes vectors to Qdrant.
    All vectors are tagged with tenant_id in their payload for isolation.
    Supports multimodal content: text chunks and image references.
    """
    def __init__(self, tenant_id: str = DEFAULT_TENANT_ID):
        host = os.getenv("QDRANT_HOST", "qdrant-service")
        port = int(os.getenv("QDRANT_PORT", 6333))
        self.collection_name = os.getenv("QDRANT_COLLECTION", "rag_collection")
        self.tenant_id = tenant_id
        self.client = QdrantClient(host=host, port=port)

        # S3 client for image storage (lazy-init)
        self._s3_client = None
        self._s3_bucket = os.getenv("S3_BUCKET_NAME")

    def _get_s3_client(self):
        """Lazy-init S3 client for image uploads."""
        if self._s3_client is None:
            import boto3
            kwargs = {"region_name": os.getenv("AWS_REGION", "us-east-1")}
            endpoint_url = os.getenv("S3_ENDPOINT_URL")
            if endpoint_url:
                kwargs["endpoint_url"] = endpoint_url
                kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID")
                kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY")
            self._s3_client = boto3.client("s3", **kwargs)
        return self._s3_client

    def _upload_image_to_storage(self, image_bytes: bytes, key: str, mime_type: str):
        """Upload image bytes to S3/MinIO."""
        client = self._get_s3_client()
        client.put_object(
            Bucket=self._s3_bucket,
            Key=key,
            Body=image_bytes,
            ContentType=mime_type,
        )

    def write(self, batch: List[Dict[str, Any]]):
        """
        Uploads points in batch, each tagged with tenant_id.
        Handles both text and image content types.
        """
        points = []
        image_prefix = os.getenv("IMAGE_STORAGE_PREFIX", "images")

        for row in batch:
            # Skip if embedding failed
            if "vector" not in row or not row["vector"]:
                continue

            content_type = row.get("content_type", "text")

            # Construct Payload (Metadata) — includes tenant_id
            payload = {
                "text": row["text"],
                "content_type": content_type,
                "filename": row["metadata"]["filename"],
                "page": row["metadata"].get("page_number", 0),
                "tenant_id": self.tenant_id,
            }

            # For images: upload to S3 and store reference
            if content_type == "image" and row.get("image_bytes"):
                mime_type = row.get("mime_type", "image/png")
                ext = _MIME_TO_EXT.get(mime_type, "png")
                object_key = f"{image_prefix}/{self.tenant_id}/{uuid.uuid4()}.{ext}"

                try:
                    self._upload_image_to_storage(
                        row["image_bytes"], object_key, mime_type
                    )
                    payload["image_key"] = object_key
                    payload["image_mime_type"] = mime_type
                except Exception as e:
                    logger.error(f"Failed to upload image to S3: {e}")
                    continue

            # Create Point
            points.append(models.PointStruct(
                id=str(uuid.uuid4()),
                vector=row["vector"],
                payload=payload,
            ))

        if points:
            # Upsert is atomic
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
