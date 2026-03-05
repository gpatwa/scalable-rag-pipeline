# services/api/app/agents/nodes/tool.py
import logging
from services.api.app.agents.state import AgentState
from services.api.app.tools.calculator import calculate
from services.api.app.tools.graph_search import search_graph_tool
# from services.api.app.tools.web_search import web_search (Future)

logger = logging.getLogger(__name__)

async def tool_node(state: AgentState) -> dict:
    """
    Executes the tool specified in the plan.
    """
    # Get the last message or plan to see what tool to call
    # In a real implementation, the Planner outputs a structured tool call.
    # Here we simplify based on the 'plan' field.
    
    plan_data = state.get("plan", [])
    if not plan_data:
        return {"messages": [{"role": "system", "content": "No tool selected."}]}

    # Assume Planner passed specific instruction in state (simplified)
    # Real implementations use OpenAI function calling API or JSON parsing
    tool_name = state.get("tool_choice", "calculator") 
    tool_input = state.get("tool_input", "0+0")
    
    result = ""
    
    if tool_name == "calculator":
        logger.info(f"Executing Calculator: {tool_input}")
        result = calculate(tool_input)
        
    elif tool_name == "graph_search":
        logger.info(f"Executing Graph Search: {tool_input}")
        result = await search_graph_tool(tool_input)
        
    else:
        result = "Unknown tool requested."

    # Return the observation
    return {
        "messages": [
            {"role": "user", "content": f"Tool Output: {result}"}
        ]
    }