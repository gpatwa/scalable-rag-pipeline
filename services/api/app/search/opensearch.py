from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any, Awaitable
from urllib.parse import urlsplit

from app.config import Settings, settings
from app.search.errors import OpenSearchError, normalize_opensearch_exception
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

    RETRY_BASE_DELAY_SECONDS = 0.1
    RETRY_MAX_DELAY_SECONDS = 2.0
    CIRCUIT_FAILURE_THRESHOLD = 3
    CIRCUIT_RESET_SECONDS = 30.0

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
        self._consecutive_failures = 0
        self._circuit_open_until: float | None = None

    async def connect(self) -> None:
        if self._connected:
            return

        if self._client is None:
            self._client = self._client_factory(self._client_options())

        try:
            server_info = await self._with_retry("connect", self._client.info)
        except Exception:
            self._connected = False
            raise

        self._server_info = server_info if isinstance(server_info, dict) else {}
        self._connected = True

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as error:
                raise normalize_opensearch_exception(error, operation="close") from error
        self._connected = False

    async def health(self) -> SearchHealth:
        if not self._connected or self._client is None:
            return SearchHealth(
                status="not_ready",
                index_alias=self.config.OPENSEARCH_INDEX_ALIAS,
                details={"provider": "opensearch", "connected": False},
            )

        cluster = await self._with_retry("health", self._client.cluster.health)
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
            await self._with_retry(
                "create_index",
                lambda: self._client.indices.create(index=index_name, body=definition),
            )
            return

        existing = await self._with_retry(
            "get_mapping",
            lambda: self._client.indices.get_mapping(index=index_name),
        )
        existing_mapping = self._extract_mapping(existing, index_name)
        if existing_mapping != definition["mappings"]:
            raise ValueError(
                f"OpenSearch index {index_name!r} exists with incompatible mapping; "
                "create a new generation before retrying"
            )

    async def activate_alias(self, alias: str, index_name: str) -> None:
        """Atomically point a stable alias at a known physical generation."""
        self._require_connected()
        alias = alias.strip()
        index_name = index_name.strip()
        if not alias or not index_name:
            raise ValueError("alias and index_name cannot be blank")
        if not await self._index_exists(index_name):
            raise ValueError(f"cannot activate unknown OpenSearch index generation: {index_name}")

        try:
            response = await self._client.indices.get_alias(name=alias)
        except Exception as error:
            if _is_not_found(error):
                response = {}
            else:
                raise normalize_opensearch_exception(error, operation="get_alias") from error

        current_indexes = self._extract_alias_indexes(response, alias)
        if current_indexes == (index_name,):
            return

        actions = [
            {"remove": {"index": current_index, "alias": alias}}
            for current_index in current_indexes
        ]
        actions.append(
            {
                "add": {
                    "index": index_name,
                    "alias": alias,
                    "is_write_index": True,
                }
            }
        )
        try:
            await self._client.indices.update_aliases(body={"actions": actions})
        except Exception as error:
            raise normalize_opensearch_exception(error, operation="activate_alias") from error

    def _require_connected(self) -> None:
        if not self._connected or self._client is None:
            raise RuntimeError("OpenSearch provider must be connected before index operations")

    async def _index_exists(self, index_name: str) -> bool:
        response = await self._with_retry(
            "index_exists",
            lambda: self._client.indices.exists(index=index_name),
        )
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

    @staticmethod
    def _extract_alias_indexes(response: Any, alias: str) -> tuple[str, ...]:
        if not isinstance(response, dict):
            return ()
        indexes = []
        for index_name, payload in response.items():
            if not isinstance(payload, dict):
                continue
            aliases = payload.get("aliases", {})
            if isinstance(aliases, dict) and alias in aliases:
                indexes.append(str(index_name))
        return tuple(sorted(indexes))

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

    async def _with_retry(self, operation: str, callback: Callable[[], Awaitable[Any]]) -> Any:
        self._ensure_circuit_closed(operation)
        max_retries = max(0, int(self.config.OPENSEARCH_MAX_RETRIES))
        for attempt in range(max_retries + 1):
            try:
                result = await callback()
            except Exception as error:
                normalized = normalize_opensearch_exception(error, operation=operation)
                if not normalized.retryable or attempt >= max_retries:
                    self._record_failure(normalized)
                    raise normalized from error
                await asyncio.sleep(self._retry_delay(attempt))
            else:
                self._record_success()
                return result

        raise AssertionError("OpenSearch retry loop exited without a result or exception")

    def _retry_delay(self, retry_number: int) -> float:
        return min(self.RETRY_MAX_DELAY_SECONDS, self.RETRY_BASE_DELAY_SECONDS * (2**retry_number))

    def _ensure_circuit_closed(self, operation: str) -> None:
        if self._circuit_open_until is None:
            return
        if time.monotonic() >= self._circuit_open_until:
            self.reset_circuit()
            return
        raise OpenSearchError(
            code="circuit_open",
            message=f"OpenSearch {operation} blocked by circuit breaker",
            retryable=True,
            operation=operation,
        )

    def _record_failure(self, error: Any) -> None:
        if not getattr(error, "retryable", False):
            return
        self._consecutive_failures += 1
        threshold = max(1, int(getattr(self, "CIRCUIT_FAILURE_THRESHOLD", 3)))
        if self._consecutive_failures >= threshold:
            self._circuit_open_until = time.monotonic() + float(self.CIRCUIT_RESET_SECONDS)

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_open_until = None

    def reset_circuit(self) -> None:
        """Close the local circuit after an operator or readiness reset."""
        self._consecutive_failures = 0
        self._circuit_open_until = None


def _is_not_found(error: BaseException) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code == 404:
        return True
    meta = getattr(error, "meta", None)
    if getattr(meta, "status_code", None) == 404:
        return True
    return "notfound" in type(error).__name__.lower() or "not found" in str(error).lower()
