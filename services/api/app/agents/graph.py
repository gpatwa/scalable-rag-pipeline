# services/api/app/agents/graph.py
from langgraph.graph import StateGraph, END
from services.api.app.agents.state import AgentState
from services.api.app.agents.nodes.retriever import retrieve_node
from services.api.app.agents.nodes.responder import generate_node
from services.api.app.agents.nodes.planner import planner_node

# Initialize the Graph
workflow = StateGraph(AgentState)

# 1. Define Nodes (The Logic Steps)
# These functions (imported above) will be implemented in the 'nodes/' folder next
workflow.add_node("planner", planner_node)       # Rewrites query / Decides steps
workflow.add_node("retriever", retrieve_node)    # Hits Qdrant & Neo4j
workflow.add_node("responder", generate_node)    # Calls Ray Serve LLM

# 2. Define Edges (The Flow)
# Start -> Plan -> Retrieve -> Generate -> End
workflow.set_entry_point("planner")

workflow.add_edge("planner", "retriever")
workflow.add_edge("retriever", "responder")
workflow.add_edge("responder", END) # In a more complex agent, we could loop back if answer is bad

# 3. Compile the Graph
# This creates the runnable application
agent_app = workflow.compile()