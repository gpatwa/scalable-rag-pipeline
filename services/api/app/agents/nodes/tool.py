# services/api/app/agents/nodes/tool.py
import asyncio
import logging
from app.agents.state import AgentState
from app.tools.calculator import calculate
from app.tools.graph_search import search_graph_tool
from app.tools.vector_search import search_vector_tool
from app.tools.sandbox import run_python_code
from app.tools.web_search import web_search_tool

logger = logging.getLogger(__name__)

# Dispatch table mapping tool names to their handler functions.
# Sync tools (calculator) are wrapped in the execution logic below.
TOOL_DISPATCH = {
    "calculator": calculate,
    "vector_search": search_vector_tool,
    "graph_search": search_graph_tool,
    "code_sandbox": run_python_code,
    "web_search": web_search_tool,
}


async def tool_node(state: AgentState) -> dict:
    """
    Executes the tool selected by the planner.
    Reads tool_name and tool_input from state, dispatches to the
    appropriate handler, and stores the result in tool_result.
    """
    tool_name = state.get("tool_name", "")
    tool_input = state.get("tool_input", "")

    if not tool_name:
        logger.warning("Tool node called with no tool_name in state")
        return {
            "tool_result": "No tool was selected.",
            "messages": [{"role": "assistant", "content": "[Tool] No tool was selected."}],
        }

    handler = TOOL_DISPATCH.get(tool_name)
    if not handler:
        logger.error(f"Unknown tool requested: {tool_name}")
        result = f"Unknown tool: {tool_name}"
    else:
        logger.info(f"Executing tool: {tool_name} with input: {tool_input[:100]}")
        try:
            result = handler(tool_input)
            # Handle both sync and async tool functions
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} — {e}")
            result = f"Tool error ({tool_name}): {e}"

    logger.info(f"Tool {tool_name} completed, result length: {len(str(result))}")

    return {
        "tool_result": result,
        "messages": [{"role": "assistant", "content": f"[Tool: {tool_name}] {result}"}],
    }
