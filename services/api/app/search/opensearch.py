from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from app.config import Settings, settings
from app.search.mappings import SUPPORT_SEARCH_MAPPING_VERSION, build_support_index_definition
from app.search.models import SearchHealth, SearchIndexSpec

try:
    from opensearchpy import AsyncOpenSearch
except ImportError:  # pragma: no cover - exercised by dependency-install checks
    AsyncOpenSearch = None  # type: ignore[assignment,misc]


ClientFactory = Callable[[dict[str, Any]], Any]


def _default_client_factory(options: dict[str, Any]) -> Any:
    if AsyncOpenSearch is None:
        raise RuntimeError("opensearch-py is required to construct the OpenSearch provider")
    return AsyncOpenSearch(**options)


class OpenSearchProvider:
    """Async OpenSearch lifecycle and health adapter.

    Querying and indexing methods are added in later execution milestones. Keeping
    this foundation small makes connection failures observable before rollout.
    """

    def __init__(
        self,
        *,
        config: Settings | None = None,
        client: Any | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.config = config or settings
        self._client = client
        self._client_factory = client_factory or _default_client_factory
        self._connected = False
        self._server_info: dict[str, Any] = {}

    async def connect(self) -> None:
        if self._connected:
            return

        if self._client is None:
            self._client = self._client_factory(self._client_options())

        try:
            server_info = await self._client.info()
        except Exception:
            self._connected = False
            raise

        self._server_info = server_info if isinstance(server_info, dict) else {}
        self._connected = True

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
        self._connected = False

    async def health(self) -> SearchHealth:
        if not self._connected or self._client is None:
            return SearchHealth(
                status="not_ready",
                index_alias=self.config.OPENSEARCH_INDEX_ALIAS,
                details={"provider": "opensearch", "connected": False},
            )

        cluster = await self._client.cluster.health()
        cluster_status = str(cluster.get("status", "unknown")) if isinstance(cluster, dict) else "unknown"
        status = "ready" if cluster_status in {"green", "yellow"} else "not_ready"
        details: dict[str, Any] = {
            "provider": "opensearch",
            "connected": True,
            "cluster_status": cluster_status,
        }
        for key in ("cluster_name", "number_of_nodes", "active_shards", "unassigned_shards"):
            if isinstance(cluster, dict) and key in cluster:
                details[key] = cluster[key]

        version = self._server_info.get("version")
        if isinstance(version, dict) and version.get("number"):
            details["version"] = version["number"]

        return SearchHealth(
            status=status,
            index_alias=self.config.OPENSEARCH_INDEX_ALIAS,
            document_count=0,
            details=details,
        )

    async def ensure_index(self, spec: SearchIndexSpec) -> None:
        """Create or validate a physical index for a versioned generation."""
        self._require_connected()
        index_name = spec.generation
        definition = build_support_index_definition(spec.vector_dimensions)
        definition["mappings"]["_meta"] = {
            "mapping_version": SUPPORT_SEARCH_MAPPING_VERSION,
            "schema_version": spec.schema_version,
            "embedding_model_version": spec.embedding_model_version,
        }

        if not await self._index_exists(index_name):
            await self._client.indices.create(index=index_name, body=definition)
            return

        existing = await self._client.indices.get_mapping(index=index_name)
        existing_mapping = self._extract_mapping(existing, index_name)
        if existing_mapping != definition["mappings"]:
            raise ValueError(
                f"OpenSearch index {index_name!r} exists with incompatible mapping; "
                "create a new generation before retrying"
            )

    def _require_connected(self) -> None:
        if not self._connected or self._client is None:
            raise RuntimeError("OpenSearch provider must be connected before index operations")

    async def _index_exists(self, index_name: str) -> bool:
        response = await self._client.indices.exists(index=index_name)
        if isinstance(response, bool):
            return response
        body = getattr(response, "body", None)
        return bool(response if body is None else body)

    @staticmethod
    def _extract_mapping(response: Any, index_name: str) -> dict[str, Any]:
        if not isinstance(response, dict):
            return {}
        payload = response.get(index_name)
        if not isinstance(payload, dict):
            if len(response) != 1:
                return {}
            payload = next(iter(response.values()))
        if not isinstance(payload, dict):
            return {}
        mapping = payload.get("mappings", payload)
        return mapping if isinstance(mapping, dict) else {}

    def _client_options(self) -> dict[str, Any]:
        parsed = urlsplit(self.config.get_opensearch_url())
        if not parsed.hostname:
            raise ValueError("OpenSearch URL must include a host")

        options: dict[str, Any] = {
            "hosts": [{"host": parsed.hostname, "port": parsed.port or self.config.OPENSEARCH_PORT}],
            "use_ssl": parsed.scheme.lower() == "https",
            "verify_certs": self.config.OPENSEARCH_VERIFY_CERTS,
            "timeout": self.config.OPENSEARCH_REQUEST_TIMEOUT_SECONDS,
            "max_retries": self.config.OPENSEARCH_MAX_RETRIES,
            "retry_on_timeout": self.config.OPENSEARCH_RETRY_ON_TIMEOUT,
            "pool_maxsize": self.config.OPENSEARCH_POOL_MAXSIZE,
        }

        if self.config.OPENSEARCH_CA_CERT_PATH:
            options["ca_certs"] = self.config.OPENSEARCH_CA_CERT_PATH

        auth_mode = self.config.OPENSEARCH_AUTH_MODE.strip().lower()
        if auth_mode == "basic":
            options["http_auth"] = (
                self.config.OPENSEARCH_USERNAME,
                self.config.OPENSEARCH_PASSWORD,
            )
        elif auth_mode == "api_key":
            options["headers"] = {"Authorization": f"ApiKey {self.config.OPENSEARCH_API_KEY}"}
        elif auth_mode != "none":
            raise ValueError("OPENSEARCH_AUTH_MODE must be one of: none, basic, api_key")

        return options
