"""Normalization tests for catalog metadata providers and quality ranking."""
from __future__ import annotations

from sqlalchemy import create_engine, text

from app.metadata import (
    DbtManifestProvider,
    MetadataQualityGate,
    OpenMetadataProvider,
    PostgresMetadataProvider,
    rank_assets,
)
from packages.platform_contracts.metadata import MetadataAsset, MetadataSnapshot


def test_postgres_provider_normalizes_columns():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE orders (id INTEGER NOT NULL, status TEXT)"))

    snapshot = PostgresMetadataProvider(engine, schema=None).get_snapshot("orders")

    assert snapshot.provider == "postgres"
    assert [(column.name, column.nullable) for column in snapshot.assets[0].columns] == [
        ("id", False),
        ("status", True),
    ]


def test_dbt_provider_merges_manifest_and_catalog_details():
    provider = DbtManifestProvider(
        {
            "nodes": {
                "model.demo.orders": {
                    "resource_type": "model",
                    "name": "orders",
                    "alias": "fct_orders",
                    "description": "Certified order facts",
                    "tags": ["sales"],
                    "meta": {"owner": "analytics", "certified": True},
                    "columns": {"id": {"description": "Order identifier"}},
                }
            }
        },
        {"nodes": {"model.demo.orders": {"columns": {"id": {"type": "integer"}}}}},
    )

    asset = provider.get_snapshot("orders").assets[0]

    assert asset.physical_name == "fct_orders"
    assert asset.owner_ids == ["analytics"]
    assert asset.columns[0].data_type == "integer"


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeClient:
    def __init__(self):
        self.urls: list[str] = []

    def get(self, url: str) -> FakeResponse:
        self.urls.append(url)
        return FakeResponse(
            {
                "data": {
                    "fullyQualifiedName": "warehouse.orders",
                    "displayName": "Orders",
                    "description": "Certified order facts",
                    "owner": {"name": "analytics"},
                    "certification": {"tagLabel": "Gold"},
                    "tags": [{"tagFQN": "Tier.Gold"}],
                    "columns": [{"name": "id", "dataType": "INT", "constraint": "NOT NULL"}],
                }
            }
        )


def test_openmetadata_provider_normalizes_catalog_response():
    client = FakeClient()
    snapshot = OpenMetadataProvider("https://metadata.example/", "token", client).get_snapshot("orders")

    assert client.urls == ["https://metadata.example/api/v1/tables/name/orders"]
    assert snapshot.assets[0].certified is True
    assert snapshot.assets[0].columns[0].nullable is False


def test_quality_gate_and_ranking_are_deterministic():
    complete = MetadataAsset(
        id="orders",
        display_name="Orders",
        physical_name="fct_orders",
        provider="dbt",
        description="Certified order facts",
        owner_ids=["analytics"],
        certified=True,
        columns=[{"name": "order_id", "data_type": "integer"}],
        tags=["sales"],
    )
    incomplete = complete.model_copy(update={"id": "orders_raw", "certified": False, "owner_ids": []})
    snapshot = MetadataSnapshot(provider="dbt", assets=[incomplete, complete])

    assert MetadataQualityGate().evaluate(complete).actionable is True
    assert MetadataQualityGate().evaluate(incomplete).missing == ["owner", "certification"]
    assert [result.asset.id for result in rank_assets("sales orders", snapshot)] == ["orders", "orders_raw"]
