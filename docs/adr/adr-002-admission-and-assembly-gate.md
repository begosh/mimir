# ADR-002: Unify Task Admission, Coalesced Batching, Repair & Assembly into `AdmissionAndAssemblyGate`

- **Status**: Implemented
- **Date**: 2026-10-26
- **Module**: [`scripts/admission_and_assembly_gate.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/admission_and_assembly_gate.py)
- **Domain Glossary**: [`GLOSSARY.md`](file:///C:/Users/jonas/code/skills.sh/mimir/GLOSSARY.md)

---

## 1. Problem & Friction in the Previous Architecture

Previously, task result gating, coalesced batching, bounded repair, synthesis context preparation, 1-shot assembly repair, and `QuarantinedFinding` overlays were spread across five shallow modules plus inline state-machine loops in `scheduler.py` and `engine.py`:
1. [`scripts/post_worker.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/post_worker.py) — `check_task_result`, `repair_task_result`, `synthesis_context`, `synthesize`, `check_final_answer`, `repair_assembled_answer`, and policy hash definitions.
2. [`scripts/result_batcher.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/result_batcher.py) — `ResultBatcher` coalescing up to 4 completed task outputs over a 2.0-second window.
3. [`scripts/assembly_gate.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/assembly_gate.py) — `assemble_checked` persisting the `assembly_history` state machine (`new` $\to$ `synthesizing` $\to$ `assembled` $\to$ `checking` $\to$ `rejected` $\to$ `repairing` $\to$ `corrected` $\to$ `rechecking` $\to$ `passed` / `failed`).
4. [`scripts/publication_view.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/publication_view.py) — `build_publication_view` constructing `QuarantinedFinding` vs `"accepted"` overlays.
5. [`scripts/prompt_data.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/prompt_data.py) — `model_view` path redaction and `compact_checker_context` source deduplication.

### Key Sources of Friction
- [`scripts/scheduler.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/scheduler.py) had to instantiate and close `ResultBatcher`, sequence deterministic provenance + calculation checks ahead of model checks, append to `node.result_attempts`, reserve `node.retry_count += 1` before calling `repair_task_result`, and construct the repaired prompt (`atomic_prompt` vs `TARGETED REPAIR`).
- [`scripts/engine.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/engine.py) had over 100 lines in `_run_synthesize_stage` branching between `mode == "single"` and multi-worker `assemble_checked`, manually building `publication_view`, and projecting `QuarantinedFinding` stubs into `published_data`.

---

## 2. Design Decision

We created [`scripts/admission_and_assembly_gate.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/admission_and_assembly_gate.py) (`AdmissionAndAssemblyGate`) as a **deep module** that owns:
1. **Stage 1 — Pre-Execution Policy & Contract Binding**:
   - `AdmissionAndAssemblyGate.bind_node_policies(node, *, mode=None)`
   - `AdmissionAndAssemblyGate.bind_graph_policies(graph, *, mode=None)`
2. **Stage 2 — Coalesced Task Admission & Bounded 2-Retry Repair**:
   - `await gate.admit_or_repair_task(node, response, results, *, fingerprint, prompt, goal="", on_result_attempt=None) -> tuple[dict | None, str | None]`
   - Internally manages `ResultBatcher` when `backend.batch_result_checks` is enabled, runs `EvidenceProvenance.verify_task_result` and `check_calculation` before any paid model checker call, records `node.result_attempts`, reserves `node.retry_count += 1` before calling `RESULT_REPAIR`, and returns `(review, next_prompt)` when `REPHRASE` is proposed.
3. **Stage 3 — Checked Publication Assembly & Quarantine Projection**:
   - `await gate.assemble_publication(state, *, persist, emit, model=None) -> tuple[Any, str, dict[str, Any]]`
   - Unifies single-worker admission verification and multi-worker `assemble_checked` (including 1-shot assembly repair and `QuarantinedFinding` overlays) and projects `published_data` for report rendering.
4. **Prompt View & Checker Compaction**:
   - `AdmissionAndAssemblyGate.model_view(value, sources=())` and `AdmissionAndAssemblyGate.compact_checker_context(context)`.

---

## 3. Verification Summary

- Combined with Candidate 1 (`EvidenceProvenance`), [`scripts/scheduler.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/scheduler.py) shrank from **505 lines to 335 lines (-34%)**, and `_run_synthesize_stage` in [`scripts/engine.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/engine.py) shed ~85 lines of manual branching and quarantine projection.
- Added [`tests/test_admission_and_assembly_gate.py`](file:///C:/Users/jonas/code/skills.sh/mimir/tests/test_admission_and_assembly_gate.py) exercising `bind_graph_policies`, `admit_or_repair_task`, and `assemble_publication` with `QuarantinedFinding` projection.
