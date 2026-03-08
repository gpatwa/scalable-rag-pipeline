# services/api/app/agents/nodes/responder.py
import logging
from app.agents.state import AgentState
from app.clients.ray_llm import llm_client
from app.tools.web_search import web_search_tool

logger = logging.getLogger(__name__)


async def generate_node(state: AgentState) -> dict:
    """
    Synthesizes the final answer using retrieved documents.
    Falls back to web search when no internal documents are found.
    """
    query = state["current_query"]
    documents = state.get("documents", [])
    tool_result = state.get("tool_result", "")

    # Construct Context String
    context_str = "\n\n".join(documents)
    if tool_result:
        context_str += f"\n\nTool Result:\n{tool_result}"

    # Include accumulated results from multi-step planning
    step_results = state.get("step_results", [])
    if step_results:
        context_str += "\n\nPrevious Step Results:\n" + "\n---\n".join(step_results)

    # Include long-term user memories
    user_memories = state.get("user_memories", [])
    if user_memories:
        context_str += "\n\nUser Preferences/Facts:\n" + "\n".join(user_memories)

    # Fallback: if no context from retrieval or tools, try web search
    if not context_str.strip():
        logger.info(f"No internal documents found for '{query}', trying web search...")
        try:
            web_result = await web_search_tool(query)
            if web_result and "disabled" not in web_result.lower() and "error" not in web_result.lower():
                context_str = f"Web Search Results:\n{web_result}"
                logger.info("Web search returned results as fallback")
            else:
                logger.info(f"Web search unavailable: {web_result}")
        except Exception as e:
            logger.warning(f"Web search fallback failed: {e}")

    logger.info(f"Responder context length: {len(context_str)} chars, docs: {len(documents)}")

    prompt = f"""You are a helpful Enterprise Assistant. Use the context below to answer the user's question.

Context:
{context_str}

Question:
{query}

Instructions:
1. If context contains relevant information, answer using it and cite sources with [Source: filename].
2. If context is from web search results, answer using it and mention the source URLs.
3. If no context is available, provide a helpful answer from your general knowledge and note that no internal documents were found.
4. Be concise and professional."""

    # Call LLM
    answer = await llm_client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    # Return dictionary to update state (add the AI message)
    return {
        "messages": [{"role": "assistant", "content": answer}]
    }
