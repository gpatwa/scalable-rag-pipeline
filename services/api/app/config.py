# services/api/app/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """
    Application Configuration.
    Reads environment variables automatically (case-insensitive).
    """
    # General
    ENV: str = "prod"
    LOG_LEVEL: str = "INFO"
    
    # Database (Aurora Postgres)
    DATABASE_URL: str  # e.g., postgresql+asyncpg://user:pass@host:5432/db
    
    # Redis (Cache)
    REDIS_URL: str     # e.g., redis://elasticache-endpoint:6379/0
    
    # Vector DB (Qdrant)
    QDRANT_HOST: str = "qdrant-service"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "rag_collection"
    
    # Graph DB (Neo4j)
    NEO4J_URI: str = "bolt://neo4j-cluster:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str # Sensitive
    
    # AWS S3 / MinIO (Documents)
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str
    S3_ENDPOINT_URL: Optional[str] = None  # Set to MinIO URL for local dev
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    # LLM / Embeddings
    RAY_LLM_ENDPOINT: str = "http://llm-service:8000/llm"
    RAY_EMBED_ENDPOINT: str = "http://embed-service:8000/embed"
    LLM_MODEL: str = "llama3"  # Model name for Ollama / vLLM
    
    # Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"

    # CORS (comma-separated origins, e.g., "http://localhost:3000,https://your-domain.com")
    CORS_ORIGINS: str = "*"  # Default: allow all for dev. Restrict in production!

    class Config:
        env_file = ".env"

# Instantiate singleton
settings = Settings()