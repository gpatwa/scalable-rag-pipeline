"""Vendor-neutral metadata snapshots used by analytics context providers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class MetadataColumn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    data_type: str = Field(min_length=1, max_length=255)
    description: str | None = None
    nullable: bool = True
    classification: Literal["public", "internal", "confidential", "restricted"] = "internal"


class MetadataAsset(BaseModel):
    id: str = Field(min_length=1, max_length=512)
    display_name: str = Field(min_length=1, max_length=255)
    physical_name: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=100)
    description: str | None = None
    owner_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    certified: bool = False
    columns: list[MetadataColumn] = Field(default_factory=list)
    lineage_asset_ids: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MetadataSnapshot(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assets: list[MetadataAsset] = Field(default_factory=list)


class MetadataQualityReport(BaseModel):
    asset_id: str
    score: float = Field(ge=0, le=1)
    actionable: bool
    missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MetadataSearchResult(BaseModel):
    asset: MetadataAsset
    score: float = Field(ge=0)
