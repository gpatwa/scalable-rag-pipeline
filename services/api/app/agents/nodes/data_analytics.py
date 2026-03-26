# services/api/app/agents/nodes/data_analytics.py
"""
LangGraph node for the Data Analytics Agent.

Generates SQL from natural language, executes against a read-only
Postgres connection, and returns structured results for the responder
to synthesize into a natural language answer.
"""
import json
import logging
from typing import Dict

from app.agents.state import AgentState
from app.analytics.formatter import format_for_llm_context

logger = logging.getLogger(__name__)

# Late-initialized — set from main.py lifespan
_llm_client = None


def set_analytics_llm(llm_client):
    """Wire the LLM client at startup (called from main.py)."""
    global _llm_client
    _llm_client = llm_client


async def data_analytics_node(state: AgentState, config=None) -> Dict:
    """
    Data analytics LangGraph node.

    Flow:
    1. Generate SQL from the user's natural language query
    2. Validate and execute against read-only Postgres
    3. Format results for the responder and frontend

    Returns state updates: data_query_sql, data_query_result,
    data_query_time_ms, data_query_error, and documents (formatted table).
    """
    from app.analytics.engine import run_data_query

    query = state.get("current_query", "")
    logger.info("Data analytics node: processing query '%s'", query[:100])

    # Use injected LLM client or fall back to config
    llm = _llm_client
    if llm is None and config:
        configurable = config.get("configurable", {})
        llm = configurable.get("llm")

    if llm is None:
        logger.error("Data analytics node: no LLM client available")
        return {
            "data_query_sql": "",
            "data_query_result": "",
            "data_query_error": "LLM client not configured for data analytics.",
            "data_query_time_ms": 0,
        }

    # Run the full pipeline: generate SQL → validate → execute
    result = await run_data_query(query, llm)

    # Serialize result for state (must be JSON string)
    result_json = ""
    if result["rows"]:
        result_json = json.dumps({
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": result["row_count"],
            "truncated": result.get("truncated", False),
        })

    # Add formatted data as a document so the responder can use it
    documents = []
    if result["rows"]:
        table_text = format_for_llm_context(result["columns"], result["rows"])
        documents.append(
            f"[Data Query Results]\n{table_text}\n\n"
            f"SQL: {result['sql']}\n"
            f"Rows returned: {result['row_count']} (query took {result['time_ms']}ms)"
        )

    logger.info(
        "Data analytics complete: %d rows, %dms, error=%s",
        result["row_count"], result["time_ms"], result["error"] or "none",
    )

    return {
        "data_query_sql": result["sql"],
        "data_query_result": result_json,
        "data_query_error": result["error"],
        "data_query_time_ms": result["time_ms"],
        "documents": documents,
    }
