#!/usr/bin/env python3
"""
Debug diagnostic — traces each stage of the RAG pipeline.
Usage: python3 scripts/debug_pipeline.py "Who founded Acme Corp?"
"""
import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "api"))

from services.api.app.config import settings


async def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "Who founded Acme Corp?"
    print(f"\n{'='*60}")
    print(f"  DEBUG PIPELINE: '{query}'")
    print(f"{'='*60}")

    # ── Step 1: Check Qdrant collection ──
    print("\n[1/5] Qdrant — checking collection...")
    from qdrant_client import QdrantClient
    qclient = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

    try:
        info = qclient.get_collection(settings.QDRANT_COLLECTION)
        print(f"  ✅ Collection '{settings.QDRANT_COLLECTION}': {info.points_count} vectors, dim={info.config.params.vectors.size}")
    except Exception as e:
        print(f"  ❌ Collection error: {e}")
        return

    if info.points_count == 0:
        print("  ❌ No vectors in collection! Run: python3 scripts/ingest_local.py --sample")
        return

    # ── Step 2: Embed query ──
    print("\n[2/5] Embedding query via Ollama...")
    import httpx
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            settings.RAY_EMBED_ENDPOINT,
            json={"model": settings.EMBED_MODEL, "prompt": query}
        )
        resp.raise_for_status()
        query_vector = resp.json()["embedding"]
        print(f"  ✅ Embedding dim: {len(query_vector)}")

    # Check dim match
    if len(query_vector) != info.config.params.vectors.size:
        print(f"  ❌ DIMENSION MISMATCH! Embedding={len(query_vector)}, Collection={info.config.params.vectors.size}")
        print(f"     Fix: Delete collection, update init_local.py VECTOR_DIM to {len(query_vector)}, re-run make init + ingest")
        return

    # ── Step 3: Search Qdrant ──
    print("\n[3/5] Searching Qdrant (tenant=default)...")
    from qdrant_client.http import models
    results = qclient.search(
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=query_vector,
        limit=5,
        query_filter=models.Filter(
            must=[models.FieldCondition(key="tenant_id", match=models.MatchValue(value="default"))]
        ),
        with_payload=True,
    )
    print(f"  Results: {len(results)} docs")
    for i, r in enumerate(results):
        text = r.payload.get("text", "")[:100]
        score = r.score
        fname = r.payload.get("metadata", {}).get("filename", "unknown")
        print(f"    [{i+1}] score={score:.4f} file={fname}: {text}...")

    if not results:
        # Try without filter
        print("\n  Retrying WITHOUT tenant filter...")
        results_no_filter = qclient.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=query_vector,
            limit=3,
            with_payload=True,
        )
        print(f"  Results (no filter): {len(results_no_filter)}")
        for r in results_no_filter:
            print(f"    tenant_id={r.payload.get('tenant_id', 'MISSING')}, text={r.payload.get('text', '')[:80]}")

    # ── Step 4: Test planner ──
    print("\n[4/5] Testing planner LLM...")
    from app.tools.registry import get_tool_descriptions
    planner_prompt = f"""You are a RAG Planning Agent.
Decision rules: 1."direct_answer" for greetings only. 2."retrieve" DEFAULT for factual questions. 3."tool_use" for calculations/web search.
IMPORTANT: When in doubt, choose "retrieve".
Available tools: {get_tool_descriptions()}
Output ONLY valid JSON: {{"action":"retrieve"|"direct_answer"|"tool_use","refined_query":"...","reasoning":"..."}}"""

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            settings.RAY_LLM_ENDPOINT,
            json={
                "model": settings.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": planner_prompt},
                    {"role": "user", "content": query},
                ],
                "temperature": 0.0,
                "max_tokens": 512,
                "stream": False,
            }
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        print(f"  Raw LLM response: {raw[:300]}")

        from app.agents.json_utils import extract_json
        try:
            plan = extract_json(raw)
            print(f"  ✅ Parsed action: {plan.get('action')}")
            print(f"     Reasoning: {plan.get('reasoning', '')[:100]}")
        except Exception as e:
            print(f"  ❌ JSON parse failed: {e}")

    # ── Step 5: Summary ──
    print(f"\n{'='*60}")
    print("  DIAGNOSIS:")
    if info.points_count == 0:
        print("  → No vectors. Run ingestion first.")
    elif len(query_vector) != info.config.params.vectors.size:
        print(f"  → Dimension mismatch ({len(query_vector)} vs {info.config.params.vectors.size})")
    elif not results:
        print("  → Qdrant search returned 0 results. Possible tenant_id filter issue.")
    else:
        print(f"  → Qdrant returned {len(results)} docs (top score: {results[0].score:.4f})")
        if plan.get("action") == "direct_answer":
            print("  → ⚠️ Planner chose 'direct_answer' — bypassed retrieval!")
        else:
            print(f"  → Planner chose '{plan.get('action')}' — pipeline should work")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
