# pipelines/ingestion/context/metadata_enricher.py
"""
Ingestion-time metadata enrichment (Layer 1).

Generates document summaries, extracts tags, and writes metadata
to the document_metadata Postgres table during ingestion.
"""
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def enrich_document_metadata(
    filename: str,
    text: str,
    chunk_count: int,
    tenant_id: str = "default",
    file_type: str = "",
    source_url: str = "",
    db_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a document metadata record during ingestion.

    This is a synchronous function designed to run in Ray map_batches.
    Uses synchronous SQLAlchemy for compatibility with Ray actors.

    Args:
        filename: Original filename.
        text: Full document text (for summary generation).
        chunk_count: Number of chunks the document was split into.
        tenant_id: Tenant scope.
        file_type: File extension (pdf, docx, etc.)
        source_url: Optional origin URL.
        db_url: Postgres connection URL (sync).

    Returns:
        Dict with summary and tags for payload enrichment.
    """
    summary = _generate_summary(text)
    tags = _extract_tags(text, filename)

    # Write to Postgres if URL available
    db_url = db_url or os.getenv("DATABASE_URL", "")
    if db_url:
        try:
            _write_metadata_sync(
                db_url=db_url,
                tenant_id=tenant_id,
                filename=filename,
                file_type=file_type or _detect_file_type(filename),
                chunk_count=chunk_count,
                summary=summary,
                tags=tags,
                source_url=source_url,
            )
        except Exception as e:
            logger.error(f"Failed to write document metadata: {e}")

    return {"summary": summary, "tags": tags}


def _generate_summary(text: str, max_length: int = 200) -> str:
    """Generate a one-line summary from the first portion of text.

    In production, this would call an LLM. For now, uses the first
    meaningful sentences as a simple extractive summary.
    """
    if not text or not text.strip():
        return ""

    # Take the first 500 chars and find the last sentence boundary
    preview = text[:500].strip()
    # Find last period within the preview
    last_period = preview.rfind(".")
    if last_period > 50:
        summary = preview[: last_period + 1]
    else:
        summary = preview

    # Truncate to max length
    if len(summary) > max_length:
        summary = summary[:max_length].rsplit(" ", 1)[0] + "..."

    return summary


def _extract_tags(text: str, filename: str) -> list:
    """Extract basic tags from filename and content.

    In production, this would use NLP/LLM for topic extraction.
    """
    tags = []

    # Tags from filename
    name = os.path.splitext(filename)[0].lower()
    # Split by common separators
    parts = name.replace("-", " ").replace("_", " ").split()
    tags.extend([p for p in parts if len(p) > 2])

    # Tags from file type
    ext = _detect_file_type(filename)
    if ext:
        tags.append(ext)

    return list(set(tags))[:10]  # Max 10 tags


def _detect_file_type(filename: str) -> str:
    """Detect file type from extension."""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext


def _write_metadata_sync(
    db_url: str,
    tenant_id: str,
    filename: str,
    file_type: str,
    chunk_count: int,
    summary: str,
    tags: list,
    source_url: str,
):
    """Write document metadata to Postgres (synchronous for Ray compatibility)."""
    from sqlalchemy import create_engine, text

    # Convert async URL to sync if needed
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    engine = create_engine(sync_url, pool_pre_ping=True)
    with engine.connect() as conn:
        # Upsert: update if filename+tenant exists, insert otherwise
        conn.execute(
            text("""
                INSERT INTO document_metadata
                    (tenant_id, document_id, filename, file_type, ingested_at,
                     chunk_count, summary, tags, source_url, access_count, freshness_score)
                VALUES
                    (:tenant_id, :document_id, :filename, :file_type, :ingested_at,
                     :chunk_count, :summary, :tags, :source_url, 0, 1.0)
                ON CONFLICT (id) DO UPDATE SET
                    chunk_count = :chunk_count,
                    summary = :summary,
                    tags = :tags,
                    ingested_at = :ingested_at
            """),
            {
                "tenant_id": tenant_id,
                "document_id": filename,
                "filename": filename,
                "file_type": file_type,
                "ingested_at": datetime.utcnow(),
                "chunk_count": chunk_count,
                "summary": summary,
                "tags": tags,
                "source_url": source_url,
            },
        )
        conn.commit()
    engine.dispose()
    logger.info(f"  Metadata: recorded for {filename} ({chunk_count} chunks)")
