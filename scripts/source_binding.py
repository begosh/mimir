"""Bind explicitly named frozen evidence before atomic execution (delegates to evidence_provenance)."""
from __future__ import annotations

from evidence_provenance import bind_captured_sources

__all__ = ["bind_captured_sources"]
