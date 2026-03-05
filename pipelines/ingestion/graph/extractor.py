# pipelines/ingestion/graph/extractor.py
import json
import httpx
from typing import Dict, Any, List
from pipelines.ingestion.graph.schema import GraphSchema

class GraphExtractor:
    """
    Ray Actor Class for Graph Extraction.
    Calls the internal LLM Service to extract entities.
    """
    def __init__(self):
        # Point to the internal Ray Serve LLM endpoint
        # We use the internal K8s DNS name
        self.llm_endpoint = "http://ray-serve-llm:8000/llm/chat"
        self.client = httpx.Client(timeout=60.0) # Long timeout for reasoning

    def __call__(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a batch of text chunks.
        """
        nodes_list = []
        edges_list = []
        
        # Iterate through chunks in the batch
        for text in batch["text"]:
            try:
                # 1. Construct Prompt
                prompt = f"""
                {GraphSchema.get_system_prompt()}
                
                Input Text:
                {text}
                """
                
                # 2. Call LLM (Llama-3-70B)
                response = self.client.post(
                    self.llm_endpoint,
                    json={
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0, # Deterministic output
                        "max_tokens": 1024
                    }
                )
                response.raise_for_status()
                
                # 3. Parse JSON Output
                # We assume the model returns valid JSON (guaranteed by constrained decoding or post-processing)
                content = response.json()["choices"][0]["message"]["content"]
                graph_data = json.loads(content)
                
                # 4. Append to results
                nodes_list.append(graph_data.get("nodes", []))
                edges_list.append(graph_data.get("edges", []))
                
            except Exception as e:
                # Log error but don't crash the pipeline; return empty graph for this chunk
                print(f"Graph extraction failed for chunk: {e}")
                nodes_list.append([])
                edges_list.append([])

        # Add graph data to the batch
        batch["graph_nodes"] = nodes_list
        batch["graph_edges"] = edges_list
        return batch