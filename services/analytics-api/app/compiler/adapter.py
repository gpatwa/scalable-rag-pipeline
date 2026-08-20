"""Compiler adapter boundary for future SQL dialect implementations."""
from __future__ import annotations

from typing import Protocol

from app.compiler.postgres import CompiledQuery, PostgreSQLCompiler
from packages.platform_contracts.analytics_intent import AnalyticalIntent
from packages.platform_contracts.semantic import SemanticContract


class CompilerAdapter(Protocol):
    dialect: str

    def compile(self, intent: AnalyticalIntent, contract: SemanticContract) -> CompiledQuery:
        ...


class PostgreSQLCompilerAdapter(PostgreSQLCompiler):
    """Named adapter used by the production selection point."""

    dialect = "postgres"
