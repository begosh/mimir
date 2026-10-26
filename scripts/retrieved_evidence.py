"""Engine freezes retrieve-worker references; excerpts never create captures (delegates to evidence_provenance)."""
from __future__ import annotations

from evidence_provenance import (
    SourceStore,
    bind_dependency_evidence,
    capture_async as _ep_capture_async,
    capture_result_evidence,
    identity,
    inline_spans,
    validate_capture_packet,
    validate_downstream_span_completeness,
)


async def capture_async(result, **options):
    """Join the owned reader on cancellation before releasing run resources."""
    return await _ep_capture_async(result, _reader=capture_result_evidence, **options)


__all__ = [
    "SourceStore",
    "bind_dependency_evidence",
    "capture_async",
    "capture_result_evidence",
    "identity",
    "inline_spans",
    "validate_capture_packet",
    "validate_downstream_span_completeness",
]
