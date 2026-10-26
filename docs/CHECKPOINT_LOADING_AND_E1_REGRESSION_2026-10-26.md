# E4 Qualification: Checkpoint-Loading Completeness and E1 Repository Review Regression — 2026-10-26

This document records the qualification and verification of backlog item **E4**:
preserving the E1 repository review run (`7eacc84b92a44c51b92bffa8a4e71cdd`) as a durable regression,
establishing exact regression tests for the omitted checkpoint-loading guard in `_load_state` and `run_mimir(phase="synthesize")`,
and verifying publication quarantine and versioned regression suite registration.

---

## 1. Context and Findings from E1 Assessment

In the original E1 evaluation (run `7eacc84b92a44c51b92bffa8a4e71cdd`), the model was assigned a repository review:
*"Determine atomic admission, single/review publication and incomplete-graph behaviour"*.
During that run:
1. **Critic Softening**: The domain evidence specialist asserted an overreaching claim: that incomplete legacy state could publish. The critic softened this overreaching claim, but final model PASS could not independently discover whether evidence was missing from the narrow assignment.
2. **Omitted Checkpoint Guard**: The host independently inspected `scripts/engine.py:665-667` and confirmed that `_load_state` strictly requires results for every planned task before synthesis.
3. **Publication View**: In publication view, uncorrected or overreaching specialist assertions must be quarantined or marked corrected, ensuring they do not appear as accepted facts in released findings or published answers.
4. **Durable Regression Requirement**: While wrong-field association and corrected-summary/stale-appendix regressions covered release and publication (under P1.1, P1.3, P1.4), the exact checkpoint-loading completeness enforcement required its own dedicated durable test suite and formal regression registration.

---

## 2. Deterministic Completeness and Integrity Guards in `_load_state`

The regression suite in [`tests/test_checkpoint_loading_and_e1_regression.py`](../tests/test_checkpoint_loading_and_e1_regression.py) establishes exact, isolated test coverage across all `_load_state` completeness and integrity gates:

| Gate / Condition | Input State Defect | Expected Error / Halt | Verified Behavior |
| :--- | :--- | :--- | :--- |
| **Missing Completed Data** | `completed_data` is `None` or omitted | `ValueError("Synthesis requires results for every planned task.")` | Synthesis halts before runtime dispatch |
| **Partial Completed Data** | Planned nodes `{t1, t2}`, `completed_data` only contains `t1` | `ValueError("Synthesis requires results for every planned task.")` | Missing dependent or parallel task blocks synthesis |
| **Non-Dict Completed Data** | `completed_data = ["not", "a", "dict"]` | `ValueError("Synthesis requires results for every planned task.")` | Malformed container rejected |
| **Invalid Result Structure** | Task result is not a dict or lacks `"result"` key | `ValueError("Invalid persisted task results.")` | Unparseable task payload rejected |
| **Unusable Output** | Task result has empty output (`{}`) failing `has_worker_result` | `ValueError("Synthesis requires usable output for every planned task.")` | Blank/empty worker output fails closed |
| **Uncompleted Task Status** | Planned node status is `FAILED` or `PENDING` | `ConfigurationRequired("Synthesis requires every planned task to be completed.")` | Incomplete execution phase blocks synthesis |
| **Missing Identity Records** | Missing `result_hash`, `evidence_hash`, or `input_fingerprint` | `ConfigurationRequired("Retained task is missing its identity records; synthesis cannot consume it.")` | Unfingerprinted task cannot be consumed |
| **Tampered Result Hash** | Result answer modified without matching `result_hash` | `ConfigurationRequired("Retained result identity changed; synthesis cannot consume it.")` | Tampered content rejected before synthesis |
| **Tampered Evidence Hash** | Raw response modified without matching `evidence_hash` | `ConfigurationRequired("Retained raw evidence identity changed; synthesis cannot consume it.")` | Raw evidence tampering rejected |
| **Execute Missing Retained** | Node status `COMPLETED` but missing from `completed_data` | `ValueError("Completed task is missing its retained result.")` | Execute phase ensures state consistency |
| **Execute Unknown Retained** | `completed_data` contains tasks not in `graph.nodes` | `ValueError("Invalid retained task results.")` | Extraneous results rejected |
| **Illegal Phase Transition** | Attempting `phase="synthesize"` from `phase="planned"` | `ValueError("Cannot synthesize state in phase 'planned'.")` | Enforces plan -> execute -> synthesize order |

---

## 3. End-to-End Engine Fail-Closed Execution

In `RunMimirIncompleteCheckpointRejectionTests.test_run_mimir_synthesize_fails_closed_without_worker_or_synthesis_dispatch`:
- An incomplete checkpoint with two planned tasks (`evidence` and `architecture`) where only `evidence` has completed is passed to `engine.run_mimir(phase="synthesize", ...)`.
- **Result**: The engine immediately raises `ValueError("Synthesis requires results for every planned task.")`.
- **Verification**: Exactly zero model calls (`len(backend.calls) == 0`), zero synthesizer spawns, zero checker calls, and zero report/sidecar writes occur.

---

## 4. End-to-End Repository Review Regression (E1 Run `7eacc84b92a44c51b92bffa8a4e71cdd`)

In `E1RepositoryReviewRegressionTests.test_e1_overreaching_claim_softened_by_critic_and_quarantined_in_publication`:
- Recreates the exact multi-agent review context from run `7eacc84b92a44c51b92bffa8a4e71cdd`:
  - `evidence` worker: overreaching assertion claiming incomplete legacy state could publish.
  - `architecture` worker: confirms node lifecycle completion requirement.
  - `critique` worker: refutes evidence worker, citing `_load_state` line 665 requiring results for every planned task.
- Evaluated with `build_publication_view`:
  1. The overreaching task `evidence` is marked `status="quarantined"`, preserving the explicit quarantine reason and original evidence hash while omitting the raw finding payload from the published view.
  2. The accepted tasks `architecture` and `critique` retain their verified payloads.
  3. Released tasks aggregate contains only verified tasks (`architecture`, `critique`).
  4. The uncorrected overreaching claim is completely excluded from released findings.

---

## 5. Versioned Regression Suite Registration

In `E1RegressionSuiteRegistrationTests.test_e1_failure_packet_conversion_and_split_isolation`:
- Converts confirmed E1 failure packet to versioned `RegressionCase` via `convert_failure_to_regression`:
  - **Case ID**: `reg-v1-7f876b3ae389`
  - **Split**: `dev`
  - **Topic Family**: `incomplete_graph_behavior`
  - **Source Family**: `engine_py`
  - **Lineage**: `{origin_run_id: "7eacc84b92a44c51b92bffa8a4e71cdd", failure_kind: "result_check_failure"}`
  - **Verification Spec**:
    - `required_locators`: `["scripts/engine.py"]`
    - `expected_defect_types`: `["unsupported_claim"]`
    - `required_answer_markers`: `["Synthesis requires results for every planned task."]`
    - `forbidden_answer_markers`: `["incomplete legacy state could publish"]`
- **Isolation Check**: Validated against disjoint held-out cases using `validate_split_isolation` with zero cross-split leakage.
- **Durable Store**: Saved in `.mimir/regressions.jsonl`.

---

## 6. Verification Summary

Executed using Python 3.14.7 in `.venv-research`:
```text
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_execute_phase_rejects_missing_retained_result_for_completed_task PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_execute_phase_rejects_retained_results_outside_graph PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_invalid_phase_transition_rejected PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_synthesize_rejects_invalid_result_structure PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_synthesize_rejects_missing_completed_data PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_synthesize_rejects_missing_identity_records PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_synthesize_rejects_non_dict_completed_data PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_synthesize_rejects_partial_completed_data PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_synthesize_rejects_tampered_evidence_hash PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_synthesize_rejects_tampered_result_hash PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_synthesize_rejects_uncompleted_task_status PASSED
tests/test_checkpoint_loading_and_e1_regression.py::CheckpointLoadingGuardsTests::test_synthesize_rejects_unusable_worker_output PASSED
tests/test_checkpoint_loading_and_e1_regression.py::RunMimirIncompleteCheckpointRejectionTests::test_run_mimir_synthesize_fails_closed_without_worker_or_synthesis_dispatch PASSED
tests/test_checkpoint_loading_and_e1_regression.py::E1RepositoryReviewRegressionTests::test_e1_overreaching_claim_softened_by_critic_and_quarantined_in_publication PASSED
tests/test_checkpoint_loading_and_e1_regression.py::E1RegressionSuiteRegistrationTests::test_e1_failure_packet_conversion_and_split_isolation PASSED

============================= 15 passed in 0.32s ==============================
```
