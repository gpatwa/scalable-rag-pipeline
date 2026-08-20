"""Compiler adapter boundary for future SQL dialect implementations."""
from __future__ import annotations

from typing import Any, Protocol

from app.compiler.postgres import CompiledQuery, PostgreSQLCompiler
from packages.platform_contracts.analytics_intent import AnalyticalIntent
from packages.platform_contracts.semantic import SemanticContract


class CompilerAdapter(Protocol):
    dialect: str

    def compile(
        self,
        intent: AnalyticalIntent,
        contract: SemanticContract,
        policy_values: dict[str, Any] | None = None,
    ) -> CompiledQuery:
        ...


class PostgreSQLCompilerAdapter(PostgreSQLCompiler):
    """Named adapter used by the production selection point."""

    dialect = "postgres"


class CompilerRegistry:
    """Register dialect adapters without coupling the planner to SQL details."""

    def __init__(self, adapters: list[CompilerAdapter] | None = None):
        self._adapters: dict[str, CompilerAdapter] = {}
        for adapter in adapters or []:
            self.register(adapter)

    def register(self, adapter: CompilerAdapter) -> None:
        if adapter.dialect in self._adapters:
            raise ValueError(f"compiler dialect already registered: {adapter.dialect}")
        self._adapters[adapter.dialect] = adapter

    def get(self, dialect: str) -> CompilerAdapter:
        try:
            return self._adapters[dialect]
        except KeyError as exc:
            raise LookupError(f"compiler dialect is not registered: {dialect}") from exc
