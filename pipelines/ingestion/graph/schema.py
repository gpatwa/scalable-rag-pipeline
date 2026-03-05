# pipelines/ingestion/graph/schema.py
from typing import List, Literal

# Allowed Node Labels (Entities)
# We restrict the LLM to only find these types of entities to keep the graph clean.
VALID_NODE_LABELS = Literal[
    "Person", 
    "Organization", 
    "Location", 
    "Concept", 
    "Document", 
    "Event", 
    "Product"
]

# Allowed Edge Types (Relationships)
VALID_RELATION_TYPES = Literal[
    "WORKS_FOR",
    "LOCATED_IN",
    "RELATES_TO",
    "MENTIONS",
    "PART_OF",
    "CREATED_BY",
    "HAS_FEATURE"
]

class GraphSchema:
    """
    Central source of truth for the Knowledge Graph structure.
    Used by the Extractor prompt to ensure consistency.
    """
    @staticmethod
    def get_system_prompt() -> str:
        return f"""
        You are a Knowledge Graph extraction engine. 
        Extract nodes and relationships from the text.
        
        Allowed Node Labels: {VALID_NODE_LABELS.__args__}
        Allowed Relationship Types: {VALID_RELATION_TYPES.__args__}
        
        Return JSON format only:
        {{
            "nodes": [{{"id": "Name", "type": "Label"}}],
            "edges": [{{"source": "Name", "target": "Name", "type": "RELATION"}}]
        }}
        """