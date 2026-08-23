from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.search.models import SearchScope


_WHITESPACE = re.compile(r"\s+")


class ResolutionModel(BaseModel):
    """Immutable, provider-neutral resolution value object."""

    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="never")


class SupportIntentType(str, Enum):
    INCIDENT = "incident"
    HOW_TO = "how_to"
    CONFIGURATION = "configuration"
    ACCESS = "access"
    BILLING = "billing"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class QueryMode(str, Enum):
    EXACT = "exact"
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


def _normalize_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = _WHITESPACE.sub(" ", value).strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank")
    return normalized


class IntentEntity(ResolutionModel):
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=1000)

    _normalize_name = field_validator("name", mode="before")(
        lambda value: _normalize_text(value, "entity name")
    )
    _normalize_value = field_validator("value", mode="before")(
        lambda value: _normalize_text(value, "entity value")
    )


class IntentConstraint(ResolutionModel):
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=1000)

    _normalize_name = field_validator("name", mode="before")(
        lambda value: _normalize_text(value, "constraint name")
    )
    _normalize_value = field_validator("value", mode="before")(
        lambda value: _normalize_text(value, "constraint value")
    )


class SupportIntent(ResolutionModel):
    intent: SupportIntentType
    entities: tuple[IntentEntity, ...] = ()
    constraints: tuple[IntentConstraint, ...] = ()
    exact_terms: tuple[str, ...] = Field(default=(), max_length=16)
    reason: str = Field(min_length=1, max_length=2000)
    confidence: ConfidenceLevel

    @field_validator("exact_terms", mode="before")
    @classmethod
    def _normalize_exact_terms(cls, value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("exact_terms must be a sequence of strings")
        terms = tuple(_normalize_text(term, "exact term") for term in value)
        if len(set(terms)) != len(terms):
            raise ValueError("exact_terms must not contain duplicates")
        return terms

    _normalize_reason = field_validator("reason", mode="before")(
        lambda value: _normalize_text(value, "reason")
    )


class QueryVariant(ResolutionModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: QueryMode
    reason: str = Field(min_length=1, max_length=1000)
    confidence: ConfidenceLevel

    _normalize_query = field_validator("query", mode="before")(
        lambda value: _normalize_text(value, "query")
    )
    _normalize_reason = field_validator("reason", mode="before")(
        lambda value: _normalize_text(value, "reason")
    )


class SearchPlan(ResolutionModel):
    """A bounded query plan that carries, but cannot alter, authorization scope."""

    scope: SearchScope
    variants: tuple[QueryVariant, ...] = Field(min_length=1, max_length=4)
    reason: str = Field(min_length=1, max_length=2000)
    confidence: ConfidenceLevel

    @field_validator("scope", mode="before")
    @classmethod
    def _require_caller_scope(cls, value: Any) -> SearchScope:
        if not isinstance(value, SearchScope):
            raise ValueError("scope must be an existing SearchScope instance")
        return value

    _normalize_reason = field_validator("reason", mode="before")(
        lambda value: _normalize_text(value, "reason")
    )

    @model_validator(mode="after")
    def _reject_duplicate_variants(self) -> SearchPlan:
        normalized = tuple(variant.query.casefold() for variant in self.variants)
        if len(set(normalized)) != len(normalized):
            raise ValueError("variants must not contain duplicate queries")
        return self


__all__ = [
    "ConfidenceLevel",
    "IntentConstraint",
    "IntentEntity",
    "QueryMode",
    "QueryVariant",
    "SearchPlan",
    "SupportIntent",
    "SupportIntentType",
]
