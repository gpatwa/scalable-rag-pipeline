# services/api/app/routes/chat.py
import uuid
import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.tenant import TenantContext, get_tenant_context
# Import classes for type hinting
from app.cache.semantic import SemanticCache, semantic_cache as global_cache
from app.memory.postgres import PostgresMemory, postgres_memory as global_memory
from app.clients.ray_llm import RayLLMClient, llm_client as global_llm
from app.agents.graph import agent_app
from app.agents.state import AgentState

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Dependency Providers (DI) ---
# These wrappers allow us to override dependencies easily in pytest
# e.g., app.dependency_overrides[get_llm_client] = MockLLMClient

def get_semantic_cache() -> SemanticCache:
    return global_cache

def get_memory() -> PostgresMemory:
    return global_memory

def get_llm_client() -> RayLLMClient:
    return global_llm

# --- Schemas ---
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's query")
    session_id: Optional[str] = Field(default=None, description="UUID for the conversation thread")

# --- Routes ---

@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(get_tenant_context),
    # Inject dependencies via FastAPI Depends
    cache: SemanticCache = Depends(get_semantic_cache),
    memory: PostgresMemory = Depends(get_memory),
    llm: RayLLMClient = Depends(get_llm_client)
):
    """
    Main Chat Endpoint (Streaming).
    Orchestrates the RAG flow: Cache -> History -> Agent -> Stream.

    Session ownership is enforced: a session_id created by tenant-A / user-A
    cannot be accessed by tenant-B or user-B.
    """
    # 1. Setup Session Context
    session_id = req.session_id or str(uuid.uuid4())
    user_id = ctx.user_id
    tenant_id = ctx.tenant_id

    logger.info(f"Chat request for session {session_id} from user {user_id} (tenant={tenant_id})")

    # 1b. Session Ownership Check (prevents cross-tenant data access)
    if req.session_id:
        # Only validate ownership for existing sessions (user supplied a session_id)
        ownership = await memory.session_belongs_to(session_id, user_id, tenant_id)
        if ownership is False:
            # Session exists but belongs to another user/tenant → 403
            logger.warning(
                f"Session ownership denied: session={session_id} user={user_id} tenant={tenant_id}"
            )
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this session.",
            )
        # ownership is True (same user+tenant) or None (new session) — both OK

    # 2. Semantic Cache Check (Fast Path)
    # Check if we have answered a semantically identical question recently.
    cached_ans = await cache.get_cached_response(req.message, tenant_id=tenant_id)

    if cached_ans:
        logger.info(f"Cache hit for session {session_id}")

        # Generator for cached response
        async def stream_cache():
            yield json.dumps({
                "type": "answer",
                "content": cached_ans,
                "session_id": session_id
            }) + "\n"

        # Async Background: Log interaction even if cached
        background_tasks.add_task(
            memory.add_message, session_id, "user", req.message, user_id, tenant_id
        )
        background_tasks.add_task(
            memory.add_message, session_id, "assistant", cached_ans, user_id, tenant_id
        )

        return StreamingResponse(stream_cache(), media_type="application/x-ndjson")

    # 3. Load Conversation History (Context Window)
    # Fetch last 6 turns — now scoped by tenant_id as well
    history_objs = await memory.get_history(
        session_id, limit=6, user_id=user_id, tenant_id=tenant_id
    )
    history_dicts = [
        {"role": msg.role, "content": msg.content} for msg in history_objs
    ]
    # Append current user message
    history_dicts.append({"role": "user", "content": req.message})

    # 4. Initialize Agent State (LangGraph)
    initial_state = AgentState(
        messages=history_dicts,
        current_query=req.message,
        documents=[],
        plan=[]
    )

    # 5. Define Generator for Streaming Response
    async def event_generator() -> AsyncGenerator[str, None]:
        final_answer = ""

        try:
            # Run the LangGraph
            # Pass tenant context in 'configurable' so agent nodes can use it
            # (e.g. retriever node can filter Qdrant/Neo4j by tenant_id)
            async for event in agent_app.astream(
                initial_state,
                config={
                    "configurable": {
                        "llm": llm,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                    }
                }
            ):

                # event is a dict like {'retriever': {...state updates...}}
                node_name = list(event.keys())[0]
                node_data = event[node_name]

                # Emit Status Update
                yield json.dumps({
                    "type": "status",
                    "node": node_name,
                    "session_id": session_id,
                    "info": f"Completed step: {node_name}"
                }) + "\n"

                # Capture Final Answer from Responder Node
                if node_name == "responder":
                    # The responder node appends the final AI message to state['messages']
                    if "messages" in node_data and node_data["messages"]:
                        ai_msg = node_data["messages"][-1]
                        final_answer = ai_msg.get("content", "")

                        # Stream the chunk
                        yield json.dumps({
                            "type": "answer",
                            "content": final_answer,
                            "session_id": session_id
                        }) + "\n"

            # 6. Post-Processing (Inside Generator Context)
            if final_answer:
                # We await these to ensure data consistency before closing the stream
                await memory.add_message(
                    session_id, "user", req.message, user_id, tenant_id
                )
                await memory.add_message(
                    session_id, "assistant", final_answer, user_id, tenant_id
                )

                # Update Cache
                await cache.set_cached_response(req.message, final_answer, tenant_id=tenant_id)

        except Exception as e:
            logger.error(f"Error in chat stream: {e}", exc_info=True)
            yield json.dumps({
                "type": "error",
                "content": "An internal error occurred."
            }) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
