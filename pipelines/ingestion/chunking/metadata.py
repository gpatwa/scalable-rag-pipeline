# pipelines/ingestion/chunking/metadata.py
import datetime
import hashlib

def enrich_metadata(base_metadata: dict, content: str) -> dict:
    """
    Adds calculated fields to the chunk metadata.
    """
    # 1. Compute Hash (For deduplication)
    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    
    # 2. Timestamp
    ingest_time = datetime.datetime.utcnow().isoformat()
    
    # 3. Merge
    enriched = base_metadata.copy()
    enriched.update({
        "chunk_hash": content_hash,
        "ingested_at": ingest_time,
        "length": len(content)
    })
    
    return enriched