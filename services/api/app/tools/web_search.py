# services/api/app/tools/web_search.py
import httpx
import os

async def web_search_tool(query: str) -> str:
    """
    Tool: Search the Internet.
    Use this for current events or public info not in the internal DB.
    """
    api_key = os.getenv("TAVILY_API_KEY") # Or SERPAPI_KEY
    if not api_key:
        return "Web search is disabled (API Key missing)."

    try:
        async with httpx.AsyncClient() as client:
            # Example using Tavily AI Search (optimized for LLMs)
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 3
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            formatted = "\n".join([f"- {r['title']}: {r['content']} ({r['url']})" for r in results])
            
            return formatted if formatted else "No results found on the web."
            
    except Exception as e:
        return f"Web Search Error: {str(e)}"