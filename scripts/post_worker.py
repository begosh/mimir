"""Result checking and answer assembly; distinct from reflective optimization (delegates to admission_and_assembly_gate)."""
from __future__ import annotations

from admission_and_assembly_gate import (
    PROMPTS,
    SOURCE_STATUSES,
    AdmissionAndAssemblyGate,
    assembly_repair_policy,
    check_final_answer,
    check_material_records,
    check_results,
    check_task_result,
    checker_schema,
    material_finding_contract,
    repair_assembled_answer,
    repair_task_result,
    result_gate_policy,
    result_repair_policy,
    synthesis_context,
    synthesize,
)

__all__ = [
    "PROMPTS",
    "SOURCE_STATUSES",
    "AdmissionAndAssemblyGate",
    "assembly_repair_policy",
    "check_final_answer",
    "check_material_records",
    "check_results",
    "check_task_result",
    "checker_schema",
    "material_finding_contract",
    "repair_assembled_answer",
    "repair_task_result",
    "result_gate_policy",
    "result_repair_policy",
    "synthesis_context",
    "synthesize",
]
