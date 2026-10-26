"""Immutable, task-scoped evidence snapshots and bounded literal queries (delegates to evidence_provenance)."""
from __future__ import annotations

from evidence_provenance import EvidenceProvenance, SourceStore, identity

__all__ = ["EvidenceProvenance", "SourceStore", "identity"]
