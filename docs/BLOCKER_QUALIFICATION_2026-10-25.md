# Blocker qualification and preference assumptions — 2026-10-25

Durable qualification for backlog item **P2.1** from [tasks/todo.md](../tasks/todo.md).

## Problem and historical failure mode

Previously, fresh planning on subjective or recommendation requests (such as "give me the best Neapolitan pizza dough recipe") stalled in recursive planning loops or halted execution prematurely:
1. The interpreter treated subjective preferences ("best") as missing required information rather than an unspecified preference permitting evidence gathering.
2. The decomposer emitted `clarify` leaves marked with `blocked_by`, or attached `blocked_by` to the retrieval/extraction tasks themselves.
3. The engine previously halted execution of the entire graph upon encountering any `blocked_by` attribute, preventing upstream or parallel evidence-gathering tasks from running or retaining findings.
4. Planning reviews did not distinguish short contiguous extraction steps from complex multi-stage procedures, creating unnecessary task splits.

## Implemented contract

1. **Uncertainty Classification (`scripts/task_brief.py`)**:
   - `TASK_BRIEF_SCHEMA` now accepts bounded `assumptions` alongside `missing_information`.
   - `classify_uncertainty` and `is_genuine_blocker` deterministically distinguish unspecified recommendation preferences (e.g., "best", "optimal", "recommended") from genuine required-input blockers (e.g., missing target batch quantity or target oven model).
   - `BEARINGS_INSTRUCTIONS` instruct workers that an unspecified preference permits evidence gathering and a qualified answer; it must not become an invented constraint or block retrieval.

2. **Recursive Planner and Review Prompts (`scripts/recursive_planner.py`, `prompts/`)**:
   - Interpretation prompts explicitly instruct the model to distinguish genuine blockers from ambiguity or unspecified preferences, labeling assumptions without inventing user constraints.
   - Decomposition instructions state that unspecified recommendation preferences must not create clarification leaves or block retrieval. Bounded contiguous procedures (e.g., adjacent mixing and kneading steps) remain single operations unless independent decisions or token limits require splitting.
   - `TASK_SIMPLICITY_REVIEW.txt`, `TASK_REPAIR.txt`, and `TASK_PLAN_COVERAGE.txt` enforce that `BLOCKED` requires genuine missing inputs, not subjective preferences.

3. **Graph and Scheduler Isolation (`scripts/task_graph.py`, `scripts/scheduler.py`, `scripts/engine.py`)**:
   - `TaskStatus.BLOCKED` represents a task whose execution cannot proceed due to unresolved required inputs.
   - When a task has `blocked_by` in its contract, the scheduler marks only that task `BLOCKED` and cascades cancellations to its dependent tasks.
   - Upstream and independent tasks proceed: evidence is gathered, checked, committed to the blackboard, and persisted in `completed_data`.
   - If blocked tasks remain upon graph completion, `engine.py` raises `ConfigurationRequired` identifying the unresolved required inputs, while preserving all completed task results and artifacts.
   - `usage["token_scope"]` explicitly documents that reported-token thresholds can overshoot in-flight concurrent calls.

## Verification

Qualified in `.venv-research` (Python 3.14.7 on Windows) via `tests/test_blocker_qualification.py`:
- **Unspecified "best" preference**: Ran end-to-end swarm planning and execution over `tests/fixtures/pizza_extraction_source.txt`. Extraction proceeded without blocker leaves, qualified "best" as unestablished in findings and limitations, and published report and sidecar.
- **Genuine missing target**: Ran two-task DAG (unblocked extraction + dependent scaling requiring missing target quantity). Extraction executed, passed result check, and committed to `completed_data`; scaling was marked `BLOCKED`, halting execution with `ConfigurationRequired` while retaining completed evidence.
- **Contiguous procedure**: Verified that mixing and kneading (L03-L04) is admitted and accepted as a single contiguous extraction leaf without redundant splitting.
- **Single-worker baseline**: Verified that `mode="single"` over supplied source uses exactly one worker and one check, with zero planning calls.
- **Core regressions**: 68 tests and 42 subtests passed across `test_blocker_qualification.py`, `test_recursive_planner.py`, `test_planning_repairs.py`, `test_graph_hardening.py`, and `test_scheduler.py`.

## Limitations and remaining gaps

- These tests qualify deterministic execution, graph isolation, prompt contracts, and mock-adapter pipelines. Live model qualification using `gpt-6.1-sol / low` against fresh unstructured web targets remains open under E5.
- P2.2 (proportional decomposition for bounded extraction) will build upon these contiguous procedure rules.
