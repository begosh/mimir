"""Deterministic bound-citation identity checks, separate from semantic support (delegates to evidence_provenance)."""
from __future__ import annotations

from evidence_provenance import (
    ENGINE_DELIVERIES,
    _locator_matches,
    check_association_integrity,
    check_bound_citations,
    check_conflict_preservation,
    detect_conflicts,
    extract_associations,
    normalize_entity,
)

__all__ = [
    "ENGINE_DELIVERIES",
    "_locator_matches",
    "check_association_integrity",
    "check_bound_citations",
    "check_conflict_preservation",
    "detect_conflicts",
    "extract_associations",
    "normalize_entity",
]
