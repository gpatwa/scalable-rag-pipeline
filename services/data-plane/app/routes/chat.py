# services/data-plane/app/routes/chat.py
"""
Data plane chat endpoint.

Thin wrapper around the shared agent pipeline. The key differences from the
monolith chat route:
  - Auth via control plane API key (not JWT)
  - No multi-tenant resolution (single-tenant mode)
  - User identity from X-User-Id/X-User-Role headers
"""
import uuid
import json
import logging
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

# Shared code from services/api/app/ (added to sys.path in main.py)
from app.auth.tenant import TenantContext
from app.agents.graph import create_agent
from app.agents.state import AgentState
from app.cache.semantic import semantic_cache
from app.memory.postgres import postgres_memory, extract_and_store_memories

# Data plane auth
from dp_app.auth.control_plane_auth import get_data_plane_context

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    ctx: TenantContext = Depends(get_data_plane_context),
):
    """
    Data plane chat stream endpoint.

    Processes the query through the LangGraph agent pipeline and streams
    NDJSON events back to the caller (control plane proxy).
    """
    session_id = req.session_id or str(uuid.uuid4())
    user_id = ctx.user_id

    # Session ownership check
    ownership = await postgres_memory.session_belongs_to(
        session_id, user_id, ctx.tenant_id
    )
    if ownership is False:
        async def error_stream():
            yield json.dumps({"type": "error", "content": "Session access denied"}) + "\n"
        return StreamingResponse(error_stream(), media_type="application/x-ndjson", status_code=403)

    # Check semantic cache (fast path)
    cached_ans = await semantic_cache.get_cached_response(
        req.message, tenant_id=ctx.tenant_id
    )
    if cached_ans:
        async def cached_stream():
            yield json.dumps({"type": "status", "node": "cache", "content": "Cache hit"}) + "\n"
            yield json.dumps({"type": "answer", "content": cached_ans, "session_id": session_id}) + "\n"
        asyncio.create_task(_log_messages(session_id, user_id, ctx.tenant_id, req.message, cached_ans))
        return StreamingResponse(cached_stream(), media_type="application/x-ndjson")

    # Load conversation history
    history_rows = await postgres_memory.get_history(
        session_id, limit=6, user_id=user_id, tenant_id=ctx.tenant_id
    )
    history_dicts = [{"role": h.role, "content": h.content} for h in history_rows]
    history_dicts.append({"role": "user", "content": req.message})

    # Load long-term memories
    user_memories = await postgres_memory.get_user_memories(user_id, ctx.tenant_id, limit=10)
    memory_texts = [m.content for m in user_memories]

    # Build initial state
    initial_state = AgentState(
        messages=history_dicts,
        documents=[],
        current_query=req.message,
        plan=[],
        action="",
        tool_name="",
        tool_input="",
        tool_result="",
        iteration_count=0,
        plan_steps=[],
        current_step_index=-1,
        step_results=[],
        eval_score=0,
        eval_reasoning="",
        retry_count=0,
        user_memories=memory_texts,
    )

    agent_app = create_agent()

    async def event_generator():
        final_answer = ""
        try:
            async for event in agent_app.astream(
                initial_state,
                config={
                    "configurable": {
                        "tenant_id": ctx.tenant_id,
                        "user_id": user_id,
                    }
                },
            ):
                for node_name, node_output in event.items():
                    if node_name == "__end__":
                        continue

                    yield json.dumps({
                        "type": "status",
                        "node": node_name,
                        "content": f"{node_name} completed",
                    }) + "\n"

                    if "eval_score" in node_output and node_output.get("eval_score"):
                        yield json.dumps({
                            "type": "evaluation",
                            "score": node_output["eval_score"],
                            "reasoning": node_output.get("eval_reasoning", ""),
                        }) + "\n"

                    if "tool_result" in node_output and node_output.get("tool_result"):
                        yield json.dumps({
                            "type": "tool_result",
                            "tool": node_output.get("tool_name", ""),
                            "content": node_output["tool_result"],
                        }) + "\n"

                    if "messages" in node_output:
                        msgs = node_output["messages"]
                        if msgs:
                            last_msg = msgs[-1]
                            if last_msg.get("role") == "assistant":
                                final_answer = last_msg["content"]

            if final_answer:
                yield json.dumps({
                    "type": "answer",
                    "content": final_answer,
                    "session_id": session_id,
                }) + "\n"

        except Exception as e:
            logger.error(f"Agent execution error: {e}")
            yield json.dumps({"type": "error", "content": str(e)}) + "\n"

        if final_answer:
            asyncio.create_task(
                _log_messages(session_id, user_id, ctx.tenant_id, req.message, final_answer)
            )
            asyncio.create_task(
                _cache_and_memorize(req.message, final_answer, user_id, ctx.tenant_id)
            )

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


async def _log_messages(session_id, user_id, tenant_id, user_msg, assistant_msg):
    """Background task: persist messages to Postgres."""
    try:
        await postgres_memory.add_message(session_id, "user", user_msg, user_id, tenant_id)
        await postgres_memory.add_message(session_id, "assistant", assistant_msg, user_id, tenant_id)
    except Exception as e:
        logger.error(f"Failed to persist messages: {e}")


async def _cache_and_memorize(query, answer, user_id, tenant_id):
    """Background task: update semantic cache and extract memories."""
    try:
        await semantic_cache.set_cached_response(query, answer, tenant_id)
        await extract_and_store_memories(query, answer, user_id, tenant_id)
    except Exception as e:
        logger.error(f"Cache/memory background task failed: {e}")
