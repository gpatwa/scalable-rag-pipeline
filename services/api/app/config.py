# services/api/app/config.py
from pydantic_settings import BaseSettings
from typing import Optional
from urllib.parse import quote_plus


class Settings(BaseSettings):
    """
    Application Configuration.
    Reads environment variables automatically (case-insensitive).

    Secrets Strategy
    ----------------
    For **dev / env-based** deployments, provide DATABASE_URL and REDIS_URL
    directly (with embedded credentials).

    For **Key Vault / Secrets Manager** deployments, provide the individual
    parts (DB_HOST, DB_PASSWORD, etc.) and set SECRETS_PROVIDER to
    "azure_kv" or "aws_sm".  The lifespan hook will inject secrets from the
    vault and build the connection URLs at startup.
    """

    # General
    ENV: str = "prod"
    LOG_LEVEL: str = "INFO"

    # -----------------------------------------------------------------
    # Database (Aurora Postgres / Azure Flexible Server)
    # -----------------------------------------------------------------
    # Option A: Full URL with embedded password (legacy / dev).
    DATABASE_URL: Optional[str] = None  # e.g., postgresql+asyncpg://user:pass@host:5432/db

    # Option B: Individual parts — password fetched from Key Vault at startup.
    DB_HOST: Optional[str] = None      # Postgres FQDN
    DB_USER: str = "ragadmin"          # Postgres login
    DB_PASSWORD: Optional[str] = None  # Fetched from Key Vault at runtime
    DB_NAME: str = "ragdb"             # Postgres database name
    DB_PORT: int = 5432

    # -----------------------------------------------------------------
    # Redis (Cache)
    # -----------------------------------------------------------------
    # Option A: Full URL (legacy / dev).
    REDIS_URL: Optional[str] = None    # e.g., redis://host:6379/0

    # Option B: Individual parts — password fetched from Key Vault at startup.
    REDIS_HOST: Optional[str] = None
    REDIS_PORT: int = 6380
    REDIS_PASSWORD: Optional[str] = None  # Fetched from Key Vault at runtime
    REDIS_SSL: bool = True                # True for Azure (rediss://), False for local dev

    # -----------------------------------------------------------------
    # Vector DB — Provider Selection
    # -----------------------------------------------------------------
    VECTORDB_PROVIDER: str = "qdrant"  # "qdrant" | "azure_ai_search" | "pinecone"
    QDRANT_HOST: str = "qdrant-service"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "rag_collection"

    # -----------------------------------------------------------------
    # Graph DB — Provider Selection
    # -----------------------------------------------------------------
    GRAPHDB_PROVIDER: str = "neo4j"  # "neo4j" | "cosmosdb" | "none"
    NEO4J_URI: str = "bolt://neo4j-cluster:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: Optional[str] = None  # Fetched from Key Vault at runtime

    # -----------------------------------------------------------------
    # Cloud Provider (for storage, build scripts, infra)
    # -----------------------------------------------------------------
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

    # -----------------------------------------------------------------
    # LLM / Embeddings — Provider Selection
    # -----------------------------------------------------------------
    LLM_PROVIDER: str = "ray"       # "ray" (self-hosted vLLM) | "openai" (API)
    EMBED_PROVIDER: str = "ray"     # "ray" (self-hosted BGE)  | "openai" (API)

    # Ray/vLLM endpoints (used when provider = "ray")
    RAY_LLM_ENDPOINT: str = "http://llm-service:8000/llm"
    RAY_EMBED_ENDPOINT: str = "http://embed-service:8000/embed"
    LLM_MODEL: str = "llama3"  # Model name for Ollama / vLLM
    EMBED_MODEL: str = "nomic-embed-text"  # Embedding model (separate from LLM)

    # OpenAI (used when provider = "openai"; also works with Azure/compatible APIs)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None       # Set for Azure or compatible APIs
    OPENAI_MODEL: str = "gpt-4o-mini"           # Cheap default for dev
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"  # 1536 dims

    # -----------------------------------------------------------------
    # Security & Authentication
    # -----------------------------------------------------------------
    JWT_SECRET_KEY: Optional[str] = None  # Fetched from Key Vault at runtime
    JWT_ALGORITHM: str = "HS256"  # "HS256" (symmetric) or "RS256" (JWKS / IdP)
    AUTH_PROVIDER: str = "local"  # "local" | "auth0" | "azure_ad" | "cognito"
    JWT_JWKS_URL: Optional[str] = None  # e.g. https://your-tenant.auth0.com/.well-known/jwks.json
    JWT_AUDIENCE: Optional[str] = None  # Expected 'aud' claim for RS256 tokens
    JWT_ISSUER: Optional[str] = None    # Expected 'iss' claim for RS256 tokens

    # -----------------------------------------------------------------
    # Tenant Configuration
    # -----------------------------------------------------------------
    TENANT_CONFIG_SOURCE: str = "static"  # "static" | "database" | "redis"

    # -----------------------------------------------------------------
    # Secrets Management — Provider Selection
    # -----------------------------------------------------------------
    SECRETS_PROVIDER: str = "env"  # "env" | "aws_sm" | "azure_kv"
    SECRETS_PREFIX: str = ""  # Prefix for secret names (e.g. "rag-platform/prod/")
    AZURE_KEY_VAULT_URL: Optional[str] = None  # e.g. https://my-vault.vault.azure.net

    # -----------------------------------------------------------------
    # Observability — Cloud-specific exporter
    # -----------------------------------------------------------------
    OTEL_EXPORTER: str = "otlp"  # "otlp" | "xray" | "azure_monitor" | "none"
    OTEL_SERVICE_NAME: str = "rag-api-service"
    OTEL_ENDPOINT: Optional[str] = None  # OTLP collector endpoint
    AZURE_MONITOR_CONNECTION_STRING: Optional[str] = None  # Azure App Insights

    # -----------------------------------------------------------------
    # Agentic Pipeline — Tool Configuration
    # -----------------------------------------------------------------
    TAVILY_API_KEY: Optional[str] = None  # Web search tool (tavily.com)
    SANDBOX_URL: str = "http://sandbox-service:8080/execute"  # Code sandbox endpoint

    # -----------------------------------------------------------------
    # Re-ranking — Provider Selection
    # -----------------------------------------------------------------
    RERANKER_PROVIDER: str = "none"  # "llm" | "cross_encoder" | "none"
    RERANKER_SCORE_THRESHOLD: float = 0.3  # Min score to keep (0.0-1.0)
    RERANKER_ENDPOINT: str = "http://reranker-service:8000/rerank"  # cross_encoder only

    # CORS (comma-separated origins, e.g., "http://localhost:3000,https://your-domain.com")
    CORS_ORIGINS: str = "*"  # Default: allow all for dev. Restrict in production!

    # =================================================================
    # Computed helpers (build connection URLs from parts)
    # =================================================================

    def get_database_url(self) -> str:
        """Return a usable DATABASE_URL, preferring the full URL if set."""
        if self.DATABASE_URL:
            # If DB_PASSWORD is provided separately, inject it into the URL
            if self.DB_PASSWORD and ":@" in self.DATABASE_URL:
                return self.DATABASE_URL.replace(
                    ":@", f":{quote_plus(self.DB_PASSWORD)}@"
                )
            return self.DATABASE_URL
        if self.DB_HOST and self.DB_PASSWORD:
            pw = quote_plus(self.DB_PASSWORD)
            return (
                f"postgresql+asyncpg://{self.DB_USER}:{pw}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        raise ValueError(
            "Either DATABASE_URL or (DB_HOST + DB_PASSWORD) must be set."
        )

    def get_redis_url(self) -> str:
        """Return a usable REDIS_URL, preferring the full URL if set."""
        if self.REDIS_URL:
            return self.REDIS_URL
        if self.REDIS_HOST:
            scheme = "rediss" if self.REDIS_SSL else "redis"
            pw_part = f":{quote_plus(self.REDIS_PASSWORD)}@" if self.REDIS_PASSWORD else ""
            return f"{scheme}://{pw_part}{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        raise ValueError(
            "Either REDIS_URL or REDIS_HOST must be set."
        )

    class Config:
        env_file = ".env"


# Instantiate singleton
settings = Settings()
