# services/api/app/tools/registry.py
from pydantic import BaseModel


class ToolSchema(BaseModel):
    """Schema describing a tool available to the planning agent."""
    name: str
    description: str
    parameter_name: str
    parameter_description: str


TOOL_REGISTRY: dict[str, ToolSchema] = {
    "calculator": ToolSchema(
        name="calculator",
        description="Evaluate a mathematical expression. Use for arithmetic, unit conversions, percentages.",
        parameter_name="expression",
        parameter_description="A math expression like '2 + 2' or '15% of 200'",
    ),
    "vector_search": ToolSchema(
        name="vector_search",
        description="Search internal documents by semantic similarity. Use when user asks to find or look up specific documents.",
        parameter_name="query",
        parameter_description="The search query to find relevant documents",
    ),
    "graph_search": ToolSchema(
        name="graph_search",
        description="Search the knowledge graph for entity relationships. Use when user asks about connections between people, orgs, or concepts.",
        parameter_name="query",
        parameter_description="A question about entity relationships",
    ),
    "code_sandbox": ToolSchema(
        name="code_sandbox",
        description="Execute Python code in an isolated sandbox. Use for data analysis, complex calculations, or code generation.",
        parameter_name="code",
        parameter_description="Python code to execute",
    ),
    "web_search": ToolSchema(
        name="web_search",
        description="Search the internet for current information. Use for recent events or public information not in internal documents.",
        parameter_name="query",
        parameter_description="The search query",
    ),
}


def get_tool_descriptions() -> str:
    """Format tool schemas for inclusion in the planner prompt."""
    lines = []
    for tool in TOOL_REGISTRY.values():
        lines.append(
            f"- {tool.name}: {tool.description} "
            f"(parameter: {tool.parameter_name} — {tool.parameter_description})"
        )
    return "\n".join(lines)
