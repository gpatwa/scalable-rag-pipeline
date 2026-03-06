# services/api/app/agents/nodes/responder.py
from app.agents.state import AgentState
from app.clients.ray_llm import llm_client

async def generate_node(state: AgentState) -> dict:
    """
    Synthesizes the final answer using retrieved documents.
    """
    query = state["current_query"]
    documents = state.get("documents", [])
    
    # Construct Context String
    context_str = "\n\n".join(documents)
    
    prompt = f"""
    You are a helpful Enterprise Assistant. Use the context below to answer the user's question.
    
    Context:
    {context_str}
    
    Question: 
    {query}
    
    Instructions:
    1. Cite sources using [Source: Filename].
    2. If the answer is not in the context, say "I don't have that information in my documents."
    3. Be concise and professional.
    """
    
    # Call LLM
    answer = await llm_client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3 # Low creativity, high fidelity
    )
    
    # Return dictionary to update state (add the AI message)
    return {
        "messages": [{"role": "assistant", "content": answer}]
    }