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
    
    # Vector DB — Provider Selection
    VECTORDB_PROVIDER: str = "qdrant"  # "qdrant" | "azure_ai_search" | "pinecone"
    QDRANT_HOST: str = "qdrant-service"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "rag_collection"

    # Graph DB — Provider Selection
    GRAPHDB_PROVIDER: str = "neo4j"  # "neo4j" | "cosmosdb" | "none"
    NEO4J_URI: str = "bolt://neo4j-cluster:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str  # Sensitive

    # Cloud Provider (for storage, build scripts, infra)
    CLOUD_PROVIDER: str = "aws"  # "aws" | "azure"

    # Storage — Provider Selection
    STORAGE_PROVIDER: str = "s3"  # "s3" | "azure_blob"

    # AWS S3 / MinIO (Documents)
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: Optional[str] = None   # Required only when STORAGE_PROVIDER=s3
    S3_ENDPOINT_URL: Optional[str] = None  # Set to MinIO URL for local dev
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # Azure Blob Storage (when STORAGE_PROVIDER=azure_blob)
    AZURE_STORAGE_ACCOUNT_NAME: Optional[str] = None
    AZURE_STORAGE_ACCOUNT_KEY: Optional[str] = None
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = None
    AZURE_STORAGE_CONTAINER: str = "documents"
    
    # LLM / Embeddings — Provider Selection
    LLM_PROVIDER: str = "ray"       # "ray" (self-hosted vLLM) | "openai" (API)
    EMBED_PROVIDER: str = "ray"     # "ray" (self-hosted BGE)  | "openai" (API)

    # Ray/vLLM endpoints (used when provider = "ray")
    RAY_LLM_ENDPOINT: str = "http://llm-service:8000/llm"
    RAY_EMBED_ENDPOINT: str = "http://embed-service:8000/embed"
    LLM_MODEL: str = "llama3"  # Model name for Ollama / vLLM

    # OpenAI (used when provider = "openai"; also works with Azure/compatible APIs)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None       # Set for Azure or compatible APIs
    OPENAI_MODEL: str = "gpt-4o-mini"           # Cheap default for dev
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"  # 1536 dims
    
    # Security & Authentication
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"  # "HS256" (symmetric) or "RS256" (JWKS / IdP)
    AUTH_PROVIDER: str = "local"  # "local" | "auth0" | "azure_ad" | "cognito"
    JWT_JWKS_URL: Optional[str] = None  # e.g. https://your-tenant.auth0.com/.well-known/jwks.json
    JWT_AUDIENCE: Optional[str] = None  # Expected 'aud' claim for RS256 tokens
    JWT_ISSUER: Optional[str] = None    # Expected 'iss' claim for RS256 tokens

    # Tenant Configuration
    TENANT_CONFIG_SOURCE: str = "static"  # "static" | "database" | "redis"

    # Secrets Management — Provider Selection
    SECRETS_PROVIDER: str = "env"  # "env" | "aws_sm" | "azure_kv"
    SECRETS_PREFIX: str = ""  # Prefix for secret names (e.g. "rag-platform/prod/")
    AZURE_KEY_VAULT_URL: Optional[str] = None  # e.g. https://my-vault.vault.azure.net

    # Observability — Cloud-specific exporter
    OTEL_EXPORTER: str = "otlp"  # "otlp" | "xray" | "azure_monitor" | "none"
    OTEL_SERVICE_NAME: str = "rag-api-service"
    OTEL_ENDPOINT: Optional[str] = None  # OTLP collector endpoint
    AZURE_MONITOR_CONNECTION_STRING: Optional[str] = None  # Azure App Insights

    # CORS (comma-separated origins, e.g., "http://localhost:3000,https://your-domain.com")
    CORS_ORIGINS: str = "*"  # Default: allow all for dev. Restrict in production!

    class Config:
        env_file = ".env"

# Instantiate singleton
settings = Settings()