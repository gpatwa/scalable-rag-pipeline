# libs/schemas/chat.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class Message(BaseModel):
    role: str # "user", "assistant", "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    stream: bool = True
    
    # Optional filters for advanced users (e.g., "only search HR docs")
    filters: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    """
    Standard response structure for non-streaming calls
    """
    answer: str
    session_id: str
    # Citations are critical for "Industrial" RAG to build trust
    citations: List[Dict[str, str]] = [] # [{"source": "doc.pdf", "text": "..."}]
    latency_ms: float

class RetrievalResult(BaseModel):
    """
    Used by Retriever Node
    """
    content: str
    source: str
    score: float
    metadata: Dict[str, Any]