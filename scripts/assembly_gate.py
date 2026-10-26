"""Persisted one-correction final gate; interruptions never reset its allowance (delegates to admission_and_assembly_gate)."""
from __future__ import annotations

from admission_and_assembly_gate import (
    assemble_checked as _aag_assemble_checked,
    assembly_repair_policy,
    build_publication_view,
    check_final_answer,
    identity,
    repair_assembled_answer,
    synthesize,
)


async def assemble_checked(backend, context, state, persist, emit, *, model, max_answer_words=None):
    return await _aag_assemble_checked(
        backend,
        context,
        state,
        persist,
        emit,
        model=model,
        max_answer_words=max_answer_words,
        _policy_fn=assembly_repair_policy,
    )


__all__ = [
    "assemble_checked",
    "assembly_repair_policy",
    "build_publication_view",
    "check_final_answer",
    "identity",
    "repair_assembled_answer",
    "synthesize",
]
