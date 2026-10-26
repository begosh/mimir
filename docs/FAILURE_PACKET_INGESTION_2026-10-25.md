# Mímir Qualification: Failure Packet Capture, Deduplication & Defect Adjudication (P3.1)

**Date**: 2026-10-25  
**Component**: `scripts/failure_store.py`, `scripts/engine.py`, `tests/test_failure_store.py`  
**Execution Profile**: `codex` / `gpt-6.1-sol / low`  
**Related Requirements**: Priority 3.1 (`tasks/todo.md`)

---

## 1. Executive Summary

Backlog requirement **P3.1** mandates:
> *Capture and deduplicate failure packets with original intent, source snapshots/spans, attempts, feedback and independently adjudicated defects.*

To ensure that real-world reasoning errors, tool failures, missing input blocks, and quarantined assertions are systematically converted into actionable regression assets, Mímir now implements a persistent, process-safe, and content-addressable **Failure Store** (`scripts/failure_store.py`).

The Failure Store operates without external database dependencies, storing deduplicated packets in newline-delimited JSON (`.mimir/failure-packets.jsonl`) protected by file-level ownership locks (`run_locks.py`).

---

## 2. Architecture & Data Model

### 2.1 Content-Addressable Identity & Deduplication

A major failure mode in failure tracking is regression pollution: repeated retries, flaky executions, or identical runs across multiple test iterations flood the catalog with duplicate entries.

`FailurePacket` computes a deterministic SHA-256 identifier based on the normalized core semantics:

$$\text{hash} = \text{SHA256}(\text{original\_intent} \parallel \text{task\_objective} \parallel \text{failure\_kind} \parallel \text{defect\_fingerprint})$$

When an identical failure packet is ingested:
1. The store retrieves the existing record by `packet_id`.
2. It increments `occurrences` (tracking failure frequency).
3. It merges any new bound sources without duplicates.
4. It appends new attempts or checker feedback to the `history` log with ISO-8601 UTC timestamps.
5. It preserves any human or supervisor defect adjudications.

### 2.2 FailurePacket Schema

Each failure packet encapsulates the complete forensic context required to reproduce, analyze, and resolve the defect:

| Field | Type | Description |
|---|---|---|
| `packet_id` | `str` | 16-character deterministic hex hash of the semantic core. |
| `original_intent` | `str` | High-level goal or user prompt driving the run. |
| `task_id` | `str` | Unique node identifier in the execution DAG (e.g., `root.scale`). |
| `task_objective` | `str` | Specific atomic or sub-goal objective. |
| `failure_kind` | `str` | Enumerated taxonomy: `task_execution_failure`, `result_check_failure`, `missing_input_blocker`, `synthesis_quarantine`, `plan_error`. |
| `bound_sources` | `list[dict]` | Snapshots and citations of exact source texts bound to the task. |
| `attempts` | `list[dict]` | Complete execution attempts: prompts, outputs, raw responses, and checker feedback. |
| `adjudicated_defects` | `list[dict]` | Structured defects: `defect_type`, `severity`, `description`, `adjudicator`, `adjudicated_at`. |
| `occurrences` | `int` | Total count of observed occurrences. |
| `history` | `list[dict]` | Audit log of timestamped ingestion events and runs. |
| `resolution_status` | `str` | Lifecycle state: `open`, `triaged`, `resolved`, `wontfix`. |
| `metadata` | `dict` | Execution telemetry: `run_id`, backend, model, effort, tokens. |

### 2.3 Automated Defect Taxonomy & Classification

`classify_defect_from_feedback` parses worker and checker diagnostics into standardized defect classifications:

- `missing_required_input`: Missing operands or unresolved blockers required for computation.
- `arithmetic_contradiction`: Contradictions between calculated figures and verifiable facts.
- `hallucinated_entity`: Output references entities, sources, or claims absent from the bound source.
- `required_omission_violation`: Critical items or mandatory procedure steps omitted.
- `inverted_condition`: Logic inversions (e.g., swapping flour and water ratios).
- `wrong_association`: Attributes assigned to the wrong entity or step.
- `unsupported_claim`: Claims not directly entailed by cited source spans.
- `timeout`: Worker exceeded deadline.
- `execution_crash`: Process crash or malformed JSON envelope.

---

## 3. Engine Integration

Mímir integrates failure ingestion into three critical engine checkpoints:

1. **Worker Execution Failure / Block Halts** (`_run_execute_stage`):
   When any task node ends in `FAILED` or `BLOCKED` status, the engine extracts forensic packets via `capture_from_node` and commits them to `failure_store.ingest()` before terminating with `WorkerFailure` or `ConfigurationRequired`.
2. **Synthesis Quarantine** (`_run_synthesize_stage`):
   When claims or tasks are quarantined by the Result Gate or final synthesis verification, `_run_synthesize_stage` automatically ingests failure packets tagged with `synthesis_quarantine` and major severity.
3. **Report Sidecar Inspection** (`capture_from_report_file`):
   Provides offline ingestion from any published `report.json` sidecar.

---

## 4. Verification & Test Evidence

The failure packet implementation is validated by `tests/test_failure_store.py` (7 tests, 100% passing):

- `test_failure_packet_identity_and_deduplication`: Confirms deterministic IDs and occurrence incrementing without duplicate entries.
- `test_capture_from_failed_task_node`: Confirms capture of failed tasks, attempt histories, and checker issues.
- `test_capture_from_blocked_task_node`: Confirms capture of unresolved required inputs (`missing_input_blocker`).
- `test_engine_execution_halts_automatically_ingest_failure_packets`: Confirms end-to-end engine halts automatically ingest packets into `.mimir/failure-packets.jsonl`.
- `test_capture_from_report_file_with_quarantined_findings`: Confirms sidecar ingestion of quarantined assertions.
- `test_classify_defect_from_feedback`: Confirms heuristic defect standardization.
- `test_adjudicate_packet_defects`: Confirms supervisor defect triage, severity tagging, and lifecycle transitions.

---

## 5. Artifacts and Lineage

- **Implementation**: [`scripts/failure_store.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/failure_store.py)
- **Engine Ingestion**: [`scripts/engine.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/engine.py#L580-L597)
- **Test Suite**: [`tests/test_failure_store.py`](file:///C:/Users/jonas/code/skills.sh/mimir/tests/test_failure_store.py)
- **Workspace Report**: [`artifacts/failure_packet_ingestion_2026-10-25.md`](file:///C:/Users/jonas/code/skills.sh/mimir/artifacts/failure_packet_ingestion_2026-10-25.md)
