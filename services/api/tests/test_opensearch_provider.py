from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.search.opensearch import OpenSearchProvider


def _config(**overrides):
    values = {
        "OPENSEARCH_INDEX_ALIAS": "support-search",
        "OPENSEARCH_URL": "https://search.internal:9200",
        "OPENSEARCH_PORT": 9200,
        "OPENSEARCH_VERIFY_CERTS": True,
        "OPENSEARCH_CA_CERT_PATH": "/etc/certs/search-ca.pem",
        "OPENSEARCH_REQUEST_TIMEOUT_SECONDS": 10.0,
        "OPENSEARCH_MAX_RETRIES": 3,
        "OPENSEARCH_RETRY_ON_TIMEOUT": True,
        "OPENSEARCH_POOL_MAXSIZE": 8,
        "OPENSEARCH_AUTH_MODE": "basic",
        "OPENSEARCH_USERNAME": "search-user",
        "OPENSEARCH_PASSWORD": "search-password",
        "get_opensearch_url": lambda: "https://search.internal:9200",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeCluster:
    def __init__(self, response):
        self.response = response

    async def health(self):
        return self.response


class FakeClient:
    def __init__(self, *, info_response=None, cluster_response=None, info_error=None):
        self.info_response = info_response or {"version": {"number": "2.15.0"}}
        self.cluster = FakeCluster(cluster_response or {"status": "green", "number_of_nodes": 3})
        self.info_error = info_error
        self.closed = False
        self.info_calls = 0
        self.indices = None

    async def info(self):
        self.info_calls += 1
        if self.info_error:
            raise self.info_error
        return self.info_response

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_health_is_not_ready_before_connect():
    provider = OpenSearchProvider(config=_config(), client=FakeClient())

    health = await provider.health()

    assert health.status == "not_ready"
    assert health.index_alias == "support-search"
    assert health.details["connected"] is False


@pytest.mark.asyncio
async def test_connect_health_and_close_use_async_client():
    client = FakeClient(
        cluster_response={
            "status": "yellow",
            "cluster_name": "support-search",
            "number_of_nodes": 2,
            "active_shards": 4,
            "unassigned_shards": 1,
        }
    )
    provider = OpenSearchProvider(config=_config(), client=client)

    await provider.connect()
    health = await provider.health()
    await provider.close()

    assert client.info_calls == 1
    assert health.status == "ready"
    assert health.details["cluster_status"] == "yellow"
    assert health.details["version"] == "2.15.0"
    assert client.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code"),
    [(PermissionError("unauthorized"), "auth"), (TimeoutError("timed out"), "timeout")],
)
async def test_connect_normalizes_authentication_and_timeout_failures(error, code):
    from app.search.errors import OpenSearchError

    provider = OpenSearchProvider(
        config=_config(),
        client=FakeClient(info_error=error),
    )

    with pytest.raises(OpenSearchError) as raised:
        await provider.connect()

    assert raised.value.code == code
    assert raised.value.operation == "connect"


class StatusError(Exception):
    def __init__(self, status_code, *, info=None):
        super().__init__(f"status {status_code}")
        self.status_code = status_code
        self.info = info


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (StatusError(401), "auth", False),
        (
            StatusError(400, info={"error": {"type": "mapper_parsing_exception"}}),
            "mapping",
            False,
        ),
        (StatusError(429), "throttled", True),
        (TimeoutError("request timed out"), "timeout", True),
        (StatusError(503), "unavailable", True),
    ],
)
def test_opensearch_errors_normalize_deterministically(error, code, retryable):
    from app.search.errors import normalize_opensearch_exception

    normalized = normalize_opensearch_exception(error, operation="search")

    assert normalized.code == code
    assert normalized.retryable is retryable
    assert normalized.operation == "search"
    assert normalized.cause is error


@pytest.mark.asyncio
async def test_provider_wraps_transport_errors_with_operation_context():
    from app.search.errors import OpenSearchError

    error = StatusError(503)
    provider = OpenSearchProvider(config=_config(), client=FakeClient(info_error=error))

    with pytest.raises(OpenSearchError) as raised:
        await provider.connect()

    assert raised.value.code == "unavailable"
    assert raised.value.operation == "connect"


class FakeIndices:
    def __init__(self, *, exists=False, mapping=None):
        self.exists_response = exists
        self.mapping = mapping
        self.created = []
        self.get_mapping_calls = 0

    async def exists(self, *, index):
        return self.exists_response

    async def create(self, *, index, body):
        self.created.append((index, body))

    async def get_mapping(self, *, index):
        self.get_mapping_calls += 1
        return {index: {"mappings": self.mapping}}


@pytest.mark.asyncio
async def test_ensure_index_creates_versioned_physical_index():
    client = FakeClient()
    client.indices = FakeIndices()
    provider = OpenSearchProvider(config=_config(), client=client)
    await provider.connect()

    from app.search.models import SearchIndexSpec

    await provider.ensure_index(
        SearchIndexSpec(
            alias="support-search",
            generation="support-search-v1",
            schema_version="support-search-v1",
            vector_dimensions=768,
            embedding_model_version="embed-v1",
        )
    )

    assert len(client.indices.created) == 1
    index_name, definition = client.indices.created[0]
    assert index_name == "support-search-v1"
    assert definition["mappings"]["properties"]["embedding"]["dimension"] == 768
    assert definition["mappings"]["_meta"]["schema_version"] == "support-search-v1"


@pytest.mark.asyncio
async def test_ensure_index_is_idempotent_for_matching_mapping():
    from app.search.mappings import SUPPORT_SEARCH_MAPPING_VERSION, build_support_index_definition
    from app.search.models import SearchIndexSpec

    expected = build_support_index_definition(768)
    expected["mappings"]["_meta"] = {
        "mapping_version": SUPPORT_SEARCH_MAPPING_VERSION,
        "schema_version": "support-search-v1",
        "embedding_model_version": "embed-v1",
    }
    client = FakeClient()
    client.indices = FakeIndices(exists=True, mapping=expected["mappings"])
    provider = OpenSearchProvider(config=_config(), client=client)
    await provider.connect()

    await provider.ensure_index(
        SearchIndexSpec(
            alias="support-search",
            generation="support-search-v1",
            schema_version="support-search-v1",
            vector_dimensions=768,
            embedding_model_version="embed-v1",
        )
    )

    assert client.indices.created == []
    assert client.indices.get_mapping_calls == 1


@pytest.mark.asyncio
async def test_ensure_index_rejects_incompatible_existing_mapping():
    from app.search.mappings import build_support_index_definition
    from app.search.models import SearchIndexSpec

    existing = build_support_index_definition(1536)["mappings"]
    client = FakeClient()
    client.indices = FakeIndices(exists=True, mapping=existing)
    provider = OpenSearchProvider(config=_config(), client=client)
    await provider.connect()

    with pytest.raises(ValueError, match="support-search-v1.*incompatible mapping"):
        await provider.ensure_index(
            SearchIndexSpec(
                alias="support-search",
                generation="support-search-v1",
                schema_version="support-search-v1",
                vector_dimensions=768,
                embedding_model_version="embed-v1",
            )
        )


def test_client_options_include_tls_and_basic_auth():
    provider = OpenSearchProvider(config=_config())

    options = provider._client_options()

    assert options["hosts"] == [{"host": "search.internal", "port": 9200}]
    assert options["use_ssl"] is True
    assert options["verify_certs"] is True
    assert options["ca_certs"] == "/etc/certs/search-ca.pem"
    assert options["http_auth"] == ("search-user", "search-password")
    assert options["max_retries"] == 3


def test_client_options_use_api_key_header():
    provider = OpenSearchProvider(
        config=_config(
            OPENSEARCH_AUTH_MODE="api_key",
            OPENSEARCH_USERNAME=None,
            OPENSEARCH_PASSWORD=None,
            OPENSEARCH_API_KEY="encoded-key",
        )
    )

    assert provider._client_options()["headers"] == {"Authorization": "ApiKey encoded-key"}
