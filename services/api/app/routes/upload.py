# services/api/app/routes/upload.py
import boto3
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.api.app.config import settings
from services.api.app.auth.jwt import get_current_user # Assume auth exists
import uuid

router = APIRouter()

# Initialize S3 Client (boto3 is synchronous, but presigning is fast/CPU-bound)
# For local dev, point to MinIO via S3_ENDPOINT_URL
_s3_kwargs = {"region_name": settings.AWS_REGION}
if settings.S3_ENDPOINT_URL:
    _s3_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    _s3_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
    _s3_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

s3_client = boto3.client("s3", **_s3_kwargs)

class PresignedURLRequest(BaseModel):
    filename: str
    content_type: str # e.g., "application/pdf"

class PresignedURLResponse(BaseModel):
    upload_url: str
    file_id: str
    s3_key: str

@router.post("/generate-presigned-url", response_model=PresignedURLResponse)
async def generate_upload_url(
    req: PresignedURLRequest,
    user: dict = Depends(get_current_user) # Secure endpoint
):
    """
    Generates a secure, temporary URL for the frontend to upload a file directly to S3.
    Use case: Handling 1GB+ PDF/Video files without blocking the API server.
    """
    # 1. Generate a unique file ID (UUID) to prevent overwrites
    file_id = str(uuid.uuid4())
    extension = req.filename.split('.')[-1] if '.' in req.filename else "bin"
    s3_key = f"uploads/{user['id']}/{file_id}.{extension}"

    try:
        # 2. Generate the Presigned URL
        # The frontend uses this URL with a PUT request.
        url = s3_client.generate_presigned_url(
            ClientMethod='put_object',
            Params={
                'Bucket': settings.S3_BUCKET_NAME,
                'Key': s3_key,
                'ContentType': req.content_type,
                'Metadata': {
                    'original_filename': req.filename,
                    'user_id': user['id']
                }
            },
            ExpiresIn=3600 # URL valid for 1 hour
        )
        
        return PresignedURLResponse(
            upload_url=url,
            file_id=file_id,
            s3_key=s3_key
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))