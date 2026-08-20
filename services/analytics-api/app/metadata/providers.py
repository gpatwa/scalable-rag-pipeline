"""Metadata provider protocols and read-only normalizing adapters."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx
from sqlalchemy import inspect

from app.semantic_registry import SemanticRegistry
from packages.platform_contracts.metadata import MetadataAsset, MetadataColumn, MetadataSnapshot
from packages.platform_contracts.semantic import SemanticContract, SemanticPolicy


class MetadataProvider(Protocol):
    provider_name: str

    def get_snapshot(self, asset_name: str) -> MetadataSnapshot:
        ...


class SemanticModelProvider(Protocol):
    def get_contract(self, contract_id: str, version: str) -> SemanticContract:
        ...


class PolicyProvider(Protocol):
    def get_policies(self, contract: SemanticContract) -> list[SemanticPolicy]:
        ...


class PostgresMetadataProvider:
    provider_name = "postgres"

    def __init__(self, engine: Any, schema: str | None = "public"):
        self.engine = engine
        self.schema = schema

    def get_snapshot(self, asset_name: str) -> MetadataSnapshot:
        inspector = inspect(self.engine)
        columns = [
            MetadataColumn(
                name=column["name"],
                data_type=str(column["type"]),
                nullable=bool(column.get("nullable", True)),
            )
            for column in inspector.get_columns(asset_name, schema=self.schema)
        ]
        return MetadataSnapshot(
            provider=self.provider_name,
            assets=[
                MetadataAsset(
                    id=f"{self.schema}.{asset_name}",
                    display_name=asset_name,
                    physical_name=asset_name,
                    provider=self.provider_name,
                    columns=columns,
                    observed_at=datetime.now(timezone.utc),
                )
            ],
        )


class DbtManifestProvider:
    provider_name = "dbt"

    def __init__(self, manifest: dict[str, Any], catalog: dict[str, Any] | None = None):
        self.manifest = manifest
        self.catalog = catalog or {}

    @classmethod
    def from_files(cls, manifest_path: Path | str, catalog_path: Path | str | None = None) -> "DbtManifestProvider":
        manifest = json.loads(Path(manifest_path).read_text())
        catalog = json.loads(Path(catalog_path).read_text()) if catalog_path else None
        return cls(manifest, catalog)

    def get_snapshot(self, asset_name: str) -> MetadataSnapshot:
        assets = []
        for node_id, node in self.manifest.get("nodes", {}).items():
            if node.get("resource_type") != "model" or node.get("name") != asset_name:
                continue
            catalog_node = self.catalog.get("nodes", {}).get(node_id, {})
            catalog_columns = catalog_node.get("columns", {})
            columns = [
                MetadataColumn(
                    name=name,
                    data_type=str(details.get("type", "unknown")),
                    description=details.get("comment") or info.get("description"),
                )
                for name, info in node.get("columns", {}).items()
                for details in [catalog_columns.get(name, {})]
            ]
            assets.append(
                MetadataAsset(
                    id=node_id,
                    display_name=node.get("name", asset_name),
                    physical_name=node.get("alias") or node.get("name", asset_name),
                    provider=self.provider_name,
                    description=node.get("description"),
                    owner_ids=[str(node.get("meta", {}).get("owner"))] if node.get("meta", {}).get("owner") else [],
                    tags=[str(tag) for tag in node.get("tags", [])],
                    certified=bool(node.get("meta", {}).get("certified", False)),
                    columns=columns,
                )
            )
        return MetadataSnapshot(provider=self.provider_name, assets=assets)


class OpenMetadataProvider:
    """Read-only OpenMetadata adapter with an injectable HTTP client."""

    provider_name = "openmetadata"

    def __init__(self, base_url: str, token: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(headers={"Authorization": f"Bearer {token}"})

    def get_snapshot(self, asset_name: str) -> MetadataSnapshot:
        response = self.client.get(f"{self.base_url}/api/v1/tables/name/{asset_name}")
        response.raise_for_status()
        body = response.json()
        payload = body.get("data", body)
        columns = [
            MetadataColumn(
                name=column.get("name", "unknown"),
                data_type=str(column.get("dataType", "unknown")),
                description=column.get("description"),
                nullable=column.get("constraint", "").upper() != "NOT NULL",
            )
            for column in payload.get("columns", [])
        ]
        owner = payload.get("owner") or {}
        return MetadataSnapshot(
            provider=self.provider_name,
            assets=[
                MetadataAsset(
                    id=str(payload.get("fullyQualifiedName", asset_name)),
                    display_name=str(payload.get("displayName", asset_name)),
                    physical_name=asset_name,
                    provider=self.provider_name,
                    description=payload.get("description"),
                    owner_ids=[str(owner.get("name"))] if owner.get("name") else [],
                    tags=[str(tag.get("tagFQN", tag)) if isinstance(tag, dict) else str(tag) for tag in payload.get("tags", [])],
                    certified=bool(payload.get("certification")),
                    columns=columns,
                )
            ],
        )


class GitSemanticModelProvider:
    def __init__(self, registry: SemanticRegistry):
        self.registry = registry

    def get_contract(self, contract_id: str, version: str) -> SemanticContract:
        return self.registry.get_certified(contract_id, version).contract


class ContractPolicyProvider:
    def get_policies(self, contract: SemanticContract) -> list[SemanticPolicy]:
        return list(contract.policies)
