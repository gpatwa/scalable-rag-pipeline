# pipelines/ingestion/loaders/image.py
"""
Loader for standalone image files (PNG, JPEG).
Returns the same 3-tuple format as other loaders for multimodal pipeline consistency.
"""
import logging
from typing import Tuple, Dict, Any, List
from io import BytesIO

logger = logging.getLogger(__name__)

# Supported image extensions and their MIME types
_MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def detect_mime_type(filename: str) -> str:
    """Detect MIME type from filename extension."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _MIME_MAP.get(ext, "image/png")


def parse_image_bytes(
    file_bytes: bytes, filename: str
) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    """
    Parse a standalone image file.

    Args:
        file_bytes: Raw image bytes.
        filename: Original filename.

    Returns:
        Tuple of (text_content, metadata, images) matching the multimodal
        loader contract. text_content is empty for standalone images.
    """
    try:
        from PIL import Image
        img = Image.open(BytesIO(file_bytes))
        img.verify()
    except Exception as e:
        logger.error(f"Invalid image file {filename}: {e}")
        raise ValueError(f"Invalid image file: {filename}") from e

    mime_type = detect_mime_type(filename)

    images = [
        {
            "image_bytes": file_bytes,
            "mime_type": mime_type,
            "page": 0,
            "description": "",
            "source_type": "standalone_upload",
        }
    ]

    metadata = {
        "filename": filename,
        "type": "image",
        "has_tables": False,
        "table_count": 0,
    }

    return "", metadata, images
