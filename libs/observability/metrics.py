# libs/observability/metrics.py
from prometheus_client import Counter, Histogram

# 1. Counter: Only goes up (e.g., Total Requests)
REQUEST_COUNT = Counter(
    "rag_api_requests_total", 
    "Total number of requests",
    ["method", "endpoint", "status"]
)

# 2. Histogram: Tracks distribution (e.g., Latency, Token Count)
REQUEST_LATENCY = Histogram(
    "rag_api_latency_seconds",
    "Request latency",
    ["endpoint"]
)

TOKEN_USAGE = Counter(
    "rag_llm_tokens_total",
    "Total LLM tokens consumed",
    ["model", "type"] # type=prompt vs completion
)

def track_request(method: str, endpoint: str, status: int):
    """Helper to increment request counter"""
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()