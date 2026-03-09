# services/data-plane/app/routes/upload.py
"""
Data plane upload endpoint.

Generates presigned URLs for direct-to-storage file uploads.
In data plane mode, files are stored without tenant prefix
(the entire storage bucket belongs to one customer).
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.tenant import TenantContext

# Data plane auth
from dp_app.auth.control_plane_auth import get_data_plane_context

router = APIRouter()

# Storage client — set during app lifespan
_storage_client = None


def set_storage_client(client):
    """Called during app startup to inject the storage client."""
    global _storage_client
    _storage_client = client


class UploadRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"


@router.post("/generate-presigned-url")
async def generate_presigned_url(
    req: UploadRequest,
    ctx: TenantContext = Depends(get_data_plane_context),
):
    """
    Generate a presigned URL for direct file upload.

    In data plane mode, files are stored at:
      uploads/{user_id}/{file_id}.{ext}
    (No tenant_id prefix — single-tenant storage)
    """
    if not _storage_client:
        raise HTTPException(status_code=503, detail="Storage client not initialized")

    file_id = str(uuid.uuid4())
    ext = req.filename.rsplit(".", 1)[-1] if "." in req.filename else "bin"

    # Single-tenant: no tenant_id in path
    object_key = f"uploads/{ctx.user_id}/{file_id}.{ext}"

    url = _storage_client.generate_presigned_upload_url(
        key=object_key,
        content_type=req.content_type,
        metadata={
            "user_id": ctx.user_id,
            "original_filename": req.filename,
        },
        expires_in=3600,
    )

    return {
        "upload_url": url,
        "file_id": file_id,
        "object_key": object_key,
    }
