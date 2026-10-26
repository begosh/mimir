"""Model-facing evidence views and identity hygiene (delegates to prompt_governance_gate)."""
from __future__ import annotations

from prompt_governance_gate import (
    INTERNAL,
    PromptGovernanceGate,
    compact_checker_context,
    model_view,
)

__all__ = [
    "INTERNAL",
    "compact_checker_context",
    "model_view",
    "PromptGovernanceGate",
]
