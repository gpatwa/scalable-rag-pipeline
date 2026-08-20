"""Certified semantic-contract compilation service."""
from __future__ import annotations

from pathlib import Path

from app.compiler.adapter import CompilerAdapter, PostgreSQLCompilerAdapter
from app.semantic_registry import SemanticRegistry
from packages.platform_contracts.analytics_intent import AnalyticalIntent


class CertifiedIntentCompiler:
    """Compile only intents bound to an exact certified Git-backed contract."""

    def __init__(self, registry_root: Path | str, adapter: CompilerAdapter | None = None):
        self.registry = SemanticRegistry(registry_root)
        self.adapter = adapter or PostgreSQLCompilerAdapter()

    def compile(self, intent: AnalyticalIntent):
        document = self.registry.get_certified(
            intent.semantic_contract.contract_id,
            intent.semantic_contract.contract_version,
        )
        return self.adapter.compile(intent, document.contract)
