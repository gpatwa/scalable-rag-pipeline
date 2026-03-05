# docs/request_flow.md

# Request Lifecycle

This details the journey of a user's chat message through the system.

1.  **Client Request:** The user sends a `POST` request to `api.your-rag-platform.com/api/v1/chat/stream`.
2.  **Load Balancer:** AWS ALB receives the request and forwards it to the EKS Ingress.
3.  **Ingress Controller (Nginx/Kong):**
    *   Applies TLS termination.
    *   Executes Lua script for rate limiting.
    *   Routes the request to the `api-service`.
4.  **FastAPI Orchestrator (`chat.py`):**
    *   **Auth:** `jwt.py` validates the Bearer token.
    *   **Semantic Cache:** `semantic.py` embeds the query and checks Qdrant/Redis for a similar past query. If a match > 0.95 is found, the cached answer is streamed back immediately (**Path A - Fast Path**).
5.  **LangGraph Execution (Path B - RAG Path):**
    *   **Planner Node:** The query is sent to Llama-3 to be refined or to decide on a tool.
    *   **Retriever Node:**
        *   The query is embedded via the Ray Embedding Engine.
        *   `asyncio.gather` runs Vector Search (Qdrant) and Graph Search (Neo4j) in parallel.
    *   **Responder Node:** The retrieved context and the query are sent to the Ray vLLM Engine (Llama-3-70B) to synthesize the final answer.
6.  **Streaming Response:**
    *   The FastAPI `StreamingResponse` sends events back to the user as each LangGraph node completes.
    *   The final answer is streamed to the client.
7.  **Background Tasks:**
    *   The Q&A pair is saved to the Aurora database.
    *   The new Q&A pair is added to the semantic cache.