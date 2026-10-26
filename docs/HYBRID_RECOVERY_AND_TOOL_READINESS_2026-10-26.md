# E6 Qualification: Hybrid Interruption/Recovery and Tool-Runtime Readiness — 2026-10-26

This document records the empirical and architectural qualification for backlog item **E6**:
qualifying hybrid interruption/recovery and target tool-runtime readiness separately
before making broader routing or recovery claims.

---

## 1. Tool-Runtime Readiness Qualification

Mimir decouples direct text API operations from deferred native tool runtimes:
- **Direct Text API Operations**: Atomic text tasks, extraction, deterministic calculation checks, review critiques, synthesis, and final answer checking use direct Responses API calls (`spawn_restricted`) under the fixed model profile (`gpt-6.1-sol / low`).
- **Deferred Native Tools**: Only operations requiring actual filesystem modification or connected MCP tools lazily instantiate and initialize native tool backends (`spawn`).
- **Preflight Diagnostics Separation**: In `scripts/diagnostics.py`, direct text API configuration readiness (`text_api["ready"] == True`, endpoint, model, provider) is reported separately from tool runtime preflight (`"tool_runtime_preflight": "Deferred until tools are needed"`).
- **Zero-Tool Initialization on Text Work**: In `test_hybrid_backend_defers_tool_runtime_initialization`, calling `spawn_restricted` completes with status `SUCCESS` while `tool_backend` remains `None` (0 tool initializations).
- **Model and Effort Invariance**: In `test_hybrid_backend_rejects_model_drift_on_tool_dispatch`, attempting to substitute a different model ID (e.g. `gpt-4o`) raises `ConfigurationRequired("Tool dispatch cannot change the selected model")`.
- **Fail-Closed Missing Credentials**: In `test_missing_direct_credentials_fails_closed`, missing `OPENAI_API_KEY` / `AZURE_OPENAI_API_KEY` fails closed immediately with `ConfigurationRequired`, preventing unconfigured silent native fallback.

---

## 2. Hybrid Interruption and Recovery Qualification

Mimir enforces strict persistence, crash recovery, and budget preservation invariants across lifecycle interruptions:

| Interruption / Recovery Concern | Guarded Invariant in Engine / Broker | Verified Behavior |
| :--- | :--- | :--- |
| **In-Flight Task Reset** | `_load_state` resets non-completed tasks (`status != COMPLETED`) to `PENDING` upon resume | In `test_interrupted_run_resumes_retaining_completed_results`, running task `t2` is reset to `PENDING` while completed task `t1` is retained |
| **Zero Partial Output Admission** | Interrupted or cancelled tasks never admit partial findings to `completed_data` | In `test_partial_worker_output_never_admitted_upon_interruption`, `asyncio.CancelledError` mid-execution leaves `completed_data` 100% empty |
| **Budget Journal Integrity** | Resuming a run requires `.operations.jsonl` with valid `budget_started` header | In `test_resume_without_budget_journal_fails_closed`, missing journal raises `ConfigurationRequired("Budget journal is missing; resume cannot reset the run deadline or attempts")` |
| **Deadline & Reservation Retention** | Resuming preserves original elapsed deadline and fixed publication reserves (2 calls for review/swarm) | Changing budget parameters upon resume raises `ConfigurationRequired("Budget limits and publication reserve are fixed by the journal")` |
| **Completed Task Result Reuse** | Tasks in `completed_data` with verified `result_hash`, `evidence_hash`, and `input_fingerprint` are safely reused | Completed upstream tasks do not re-execute, preventing token waste |
| **Idempotent Publication Recovery** | If synthesis completed and report/sidecar exist, recovery verifies SHA256 hashes and skips re-inference | In `test_idempotent_publication_recovery_skips_re_inference`, resuming `phase="synthesize"` performs 0 model calls (`len(backend.calls) == 0`) and validates report identity |

---

## 3. Test Suite Verification

All 8 qualification tests passed in `tests/test_hybrid_interruption_and_tool_runtime_qualification.py`:
```text
tests/test_hybrid_interruption_and_tool_runtime_qualification.py::ToolRuntimeReadinessQualificationTests::test_diagnostics_separates_direct_api_from_deferred_tool_runtime PASSED
tests/test_hybrid_interruption_and_tool_runtime_qualification.py::ToolRuntimeReadinessQualificationTests::test_hybrid_backend_defers_tool_runtime_initialization PASSED
tests/test_hybrid_interruption_and_tool_runtime_qualification.py::ToolRuntimeReadinessQualificationTests::test_hybrid_backend_rejects_model_drift_on_tool_dispatch PASSED
tests/test_hybrid_interruption_and_tool_runtime_qualification.py::ToolRuntimeReadinessQualificationTests::test_missing_direct_credentials_fails_closed PASSED
tests/test_hybrid_interruption_and_tool_runtime_qualification.py::HybridInterruptionAndRecoveryQualificationTests::test_idempotent_publication_recovery_skips_re_inference PASSED
tests/test_hybrid_interruption_and_tool_runtime_qualification.py::HybridInterruptionAndRecoveryQualificationTests::test_interrupted_run_resumes_retaining_completed_results PASSED
tests/test_hybrid_interruption_and_tool_runtime_qualification.py::HybridInterruptionAndRecoveryQualificationTests::test_partial_worker_output_never_admitted_upon_interruption PASSED
tests/test_hybrid_interruption_and_tool_runtime_qualification.py::HybridInterruptionAndRecoveryQualificationTests::test_resume_without_budget_journal_fails_closed PASSED

============================== 8 passed in 0.61s ==============================
```
