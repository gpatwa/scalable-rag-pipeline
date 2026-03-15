# services/api/app/context/assembler.py
"""
Context Layer Assembler.

Orchestrates all four context layers in parallel, merges results
with token budget management, and returns a formatted context block
for injection into the LLM prompt.
"""
import asyncio
import logging
from typing import List, Tuple, Union

from app.config import settings
from app.context.layer1_metadata import MetadataLayer
from app.context.layer2_annotations import AnnotationLayer
from app.context.layer3_code import CodeContextLayer
from app.context.layer4_business import BusinessContextLayer

logger = logging.getLogger(__name__)

# Approximate tokens-per-character ratio (conservative estimate)
_CHARS_PER_TOKEN = 4


class ContextAssembler:
    """Orchestrates all context layers and merges results."""

    def __init__(self):
        self.layer1 = MetadataLayer()
        self.layer2 = AnnotationLayer()
        self.layer3 = CodeContextLayer()
        self.layer4 = BusinessContextLayer()

    async def assemble(
        self,
        query: str,
        documents: List[Union[str, dict]],
        tenant_id: str,
        user_role: str = "all",
    ) -> str:
        """
        Fetch context from all enabled layers in parallel and merge.

        Args:
            query: User's query text.
            documents: Retrieved documents (from retriever node).
            tenant_id: Tenant scope.
            user_role: User's role for Layer 4 filtering.

        Returns:
            Formatted context string within token budget.
        """
        filenames = self._extract_filenames(documents)

        # Build task list for enabled layers
        tasks: List[Tuple[str, asyncio.Task]] = []

        if settings.CONTEXT_LAYER1_ENABLED:
            tasks.append(("Document Metadata", self.layer1.fetch(query, tenant_id, filenames, user_role)))
        if settings.CONTEXT_LAYER2_ENABLED:
            tasks.append(("Glossary & Annotations", self.layer2.fetch(query, tenant_id, filenames, user_role)))
        if settings.CONTEXT_LAYER3_ENABLED:
            tasks.append(("Code & Pipeline Context", self.layer3.fetch(query, tenant_id, filenames, user_role)))
        if settings.CONTEXT_LAYER4_ENABLED:
            tasks.append(("Business Context", self.layer4.fetch(query, tenant_id, filenames, user_role)))

        if not tasks:
            return ""

        # Run all layers in parallel
        results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)

        # Pair layer names with results, filter out empties and errors
        layer_results: List[Tuple[str, str]] = []
        for (name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error(f"Context layer '{name}' failed: {result}")
                continue
            if result and result.strip():
                layer_results.append((name, result))

        if not layer_results:
            return ""

        # Merge with token budget — priority: Business > Annotations > Metadata > Code
        return self._format_with_budget(layer_results)

    def _extract_filenames(self, documents: List[Union[str, dict]]) -> List[str]:
        """Extract filenames from retrieved documents."""
        filenames = set()
        for doc in documents:
            if isinstance(doc, str):
                # Format: "text content [Source: filename.pdf]"
                if "[Source: " in doc:
                    fn = doc.split("[Source: ")[-1].rstrip("]")
                    filenames.add(fn)
            elif isinstance(doc, dict):
                fn = doc.get("filename", "")
                if fn:
                    filenames.add(fn)
        return list(filenames)

    def _format_with_budget(self, layer_results: List[Tuple[str, str]]) -> str:
        """
        Format context layers within token budget.

        Priority order (highest first):
        1. Business Context (Layer 4) — most critical for correct interpretation
        2. Glossary & Annotations (Layer 2) — definitions matter
        3. Document Metadata (Layer 1) — helpful but less critical
        4. Code & Pipeline Context (Layer 3) — supplementary

        Truncates lower-priority layers if budget exceeded.
        """
        max_chars = settings.CONTEXT_LAYERS_MAX_TOKENS * _CHARS_PER_TOKEN
        priority_order = [
            "Business Context",
            "Glossary & Annotations",
            "Document Metadata",
            "Code & Pipeline Context",
        ]

        # Sort by priority
        sorted_results = sorted(
            layer_results,
            key=lambda x: priority_order.index(x[0]) if x[0] in priority_order else 99,
        )

        sections = []
        total_chars = 0

        for name, content in sorted_results:
            section = f"[{name}]\n{content}"
            section_len = len(section) + 1  # +1 for newline separator

            if total_chars + section_len > max_chars:
                # Truncate this section to fit remaining budget
                remaining = max_chars - total_chars
                if remaining > 50:  # Only include if meaningful space left
                    sections.append(section[:remaining] + "...")
                break

            sections.append(section)
            total_chars += section_len

        return "\n\n".join(sections)
