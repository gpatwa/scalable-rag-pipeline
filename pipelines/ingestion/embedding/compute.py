# pipelines/ingestion/embedding/compute.py
import httpx
from typing import Dict, Any

class BatchEmbedder:
    """
    Callable Class for Ray Data.
    Maintains a session for efficiency.
    """
    def __init__(self):
        # We hardcode internal DNS for Ray Service
        self.endpoint = "http://ray-serve-embed:8000/embed"
        self.client = httpx.Client(timeout=30.0)

    def __call__(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Receives a batch of text chunks.
        Returns the batch with 'embedding' field added.
        """
        texts = batch["text"]
        
        try:
            response = self.client.post(
                self.endpoint,
                json={"text": texts, "task_type": "document"}
            )
            response.raise_for_status()
            embeddings = response.json()["embeddings"]
            
            # Add embeddings to the batch dictionary
            batch["vector"] = embeddings
            return batch
            
        except Exception as e:
            # In Ray, raising exception triggers retry logic automatically
            raise e