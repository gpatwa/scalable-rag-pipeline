# pipelines/ingestion/chunking/splitter.py
from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_text(text: str, chunk_size: int = 512, overlap: int = 50) -> List[Dict[str, Any]]:
    """
    Splits text into overlapping chunks.
    Standard optimization for Embedding Models (most have 512 or 8192 limits).
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ".", " ", ""]
    )

    chunks = splitter.create_documents([text])

    return [
        {
            "text": chunk.page_content,
            "metadata": {
                "chunk_index": i
            }
        }
        for i, chunk in enumerate(chunks)
    ]


def split_multimodal(
    text: str,
    images: List[Dict[str, Any]],
    chunk_size: int = 512,
    overlap: int = 50,
) -> List[Dict[str, Any]]:
    """
    Split text into chunks and treat each image as an atomic chunk.

    Text chunks get content_type="text". Each image becomes its own
    chunk with content_type="image" (images are atomic, not splittable).

    Args:
        text: The extracted text content.
        images: List of image dicts from the loader (image_bytes, mime_type, page, etc.)
        chunk_size: Max characters per text chunk.
        overlap: Character overlap between text chunks.

    Returns:
        Unified list of chunk dicts, each with a "content_type" field.
    """
    # 1. Split text as before
    text_chunks = split_text(text, chunk_size, overlap) if text.strip() else []
    for chunk in text_chunks:
        chunk["content_type"] = "text"

    # 2. Each image becomes its own atomic "chunk"
    image_chunks = []
    for i, img in enumerate(images):
        image_chunks.append({
            "content_type": "image",
            "text": img.get("description", ""),
            "image_bytes": img["image_bytes"],
            "mime_type": img["mime_type"],
            "metadata": {
                "chunk_index": len(text_chunks) + i,
                "page_number": img.get("page", 0),
                "source_type": img.get("source_type", "extracted"),
            },
        })

    return text_chunks + image_chunks
