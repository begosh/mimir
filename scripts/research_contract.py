"""Source-to-claim records and conservative, deterministic coverage accounting (delegates to evidence_provenance)."""
from __future__ import annotations

from evidence_provenance import (
    DISCOVERY_TYPES,
    EVIDENCE_INSTRUCTIONS,
    RETRIEVAL_TYPES,
    SUPPORT_STATUSES,
    aggregate_research_results,
    audit_final_references,
    normalize_worker_result,
    worker_result_schema,
)

__all__ = [
    "DISCOVERY_TYPES",
    "EVIDENCE_INSTRUCTIONS",
    "RETRIEVAL_TYPES",
    "SUPPORT_STATUSES",
    "aggregate_research_results",
    "audit_final_references",
    "normalize_worker_result",
    "worker_result_schema",
]
