# services/api/app/agents/nodes/planner.py
import json
import logging
from app.agents.state import AgentState
from app.clients.ray_llm import llm_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a RAG Planning Agent.
Analyze the User Query and Conversation History.

Decide the next step:
1. If the user greets (Hello/Hi), output "direct_answer".
2. If the user asks a specific question requiring data, output "retrieve".
3. If the user asks for math/code, output "tool_use".

Output JSON format ONLY:
{
    "action": "retrieve" | "direct_answer" | "tool_use",
    "refined_query": "The standalone search query",
    "reasoning": "Why you chose this action"
}
"""

async def planner_node(state: AgentState) -> dict:
    """
    Decides the path through the LangGraph.
    """
    logger.info("Planner Node: Analyzing query...")
    
    # Extract latest user message
    # state['messages'] is a list of dicts or objects
    last_message = state["messages"][-1]
    user_query = last_message.content if hasattr(last_message, 'content') else last_message['content']

    # Call LLM to plan
    try:
        response_text = await llm_client.chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_query}
            ],
            temperature=0.0 # Deterministic planning
        )
        
        # Parse JSON
        plan = json.loads(response_text)
        
        logger.info(f"Plan derived: {plan['action']}")
        
        # Update State
        return {
            "current_query": plan.get("refined_query", user_query),
            "plan": [plan["reasoning"]]
        }
        
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        # Fallback: Assume we need to search
        return {
            "current_query": user_query,
            "plan": ["Error in planning, defaulting to retrieval."]
        }