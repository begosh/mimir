# Bounded extraction, proportional decomposition and minimal baseline — 2026-10-25

Durable qualification for backlog item **P2.2** from [tasks/todo.md](../tasks/todo.md).

## Problem and historical failure mode

In earlier evaluations ([execution conclusions](../docs/EXECUTION_CONCLUSIONS_2026-10-23.md)):
1. Fresh planning on straightforward extraction and recipe retrieval tasks over-split components into 4–6 micro-leaves, consuming 13,000–100,000+ tokens and stalling in recursive review/repair cycles.
2. Review guidelines historically mandated splitting any multi-stage procedure, forcing simple contiguous procedures (such as mixing and kneading described together in one section) or adjacent fields to be fractured into separate tasks with dependency overhead.
3. Invoking the engine with `max_tasks=1` without specifying `--mode` defaulted to review mode, raising a validation error (`Review mode needs at least three tasks; use single for a smaller budget`) instead of cleanly selecting the minimal single-worker baseline.

## Implemented contract

1. **Proportional Decomposition (`scripts/recursive_planner.py`, `scripts/task_graph.py`)**:
   - Decomposers are explicitly instructed to start with ONE bounded retrieval or extraction leaf (1–2 inputs, $\le 16{,}000$ characters input, $\le 150$ words output) or a short contiguous procedure.
   - Decompositions split into multiple children ONLY when:
     - Input bounds are exceeded ($> 16{,}000$ characters or separate documents/queries).
     - Output bounds are exceeded ($> 150$ words expected output).
     - Distinct operations or decisions are required (such as an extraction followed by a calculation formula, or comparison across distinct sources).
   - Short contiguous procedures (e.g. adjacent mixing and kneading steps) remain single operations without redundant splitting.

2. **Simplicity and Repair Review Guidelines (`prompts/TASK_SIMPLICITY_REVIEW.txt`, `prompts/TASK_REPAIR.txt`)**:
   - `TASK_SIMPLICITY_REVIEW.txt` accepts bounded extractions and short contiguous procedures as single leaves. It restricts `SPLIT` verdicts to genuine bounds violations ($>16\text{k}$ chars input, $>150$ words output), distinct operations (extraction vs calculation), or truly independent multi-stage processes across separate sections.
   - `TASK_REPAIR.txt` instructs the repairer to start with one bounded leaf and split only for bounds or distinct decisions.

3. **Minimal Single-Worker Auto-Routing (`scripts/engine.py`)**:
   - When `max_tasks == 1` and `mode` is omitted, the engine defaults cleanly to `mode="single"` (`max_tasks=1`).
   - Simple supplied-source work runs with exactly 1 worker and 1 check, making zero recursive planning calls.
   - The accepted single worker result and gaps are checked and published without an unnecessary synthesis worker or extra model transformations.

4. **Preservation Against Omissions and Unsupported Claims**:
   - Minimal single-worker extractions preserve all primary factual entities (yield, flour, water, salt, yeast) and declare unstated elements (mixing temperatures, proof durations) as gaps rather than fabricating claims.

## Verification

Qualified in `.venv-research` (Python 3.14.7 on Windows) via `tests/test_bounded_extraction.py` and `tests/test_blocker_qualification.py`:
- **Auto-route to single mode**: `run_mimir(max_tasks=1)` with `mode=None` routes to `single` mode, executes exactly `["Domain-Analyst", "Mimir-Result-Checker"]`, and succeeds with 0 planning calls.
- **Bounded single leaf**: Extraction of ingredients and yield over `pizza_extraction_source.txt` plans and accepts exactly 1 leaf (`root.extract`).
- **Distinct decisions**: Extraction followed by baker's hydration calculation splits into 2 sequential leaves (`extract` $\to$ `calc_hydration`) with explicit dependency.
- **Bounds enforcement & repair**: A proposed multi-stage task combining independent processes is flagged `SPLIT` by simplicity review and repaired into bounded leaves (`ingredients`, `method`).
- **Short contiguous procedure**: Mixing and kneading (L03–L04) is accepted as 1 bounded leaf without redundant splits.
- **Completeness without omission**: Single-worker extraction verified to contain all 4 ingredients and declared yield, with unstated parameters preserved in gaps and all claims supported by source locators.
- **Regression suites**:
  - `tests/test_bounded_extraction.py`: 5 passed.
  - `tests/test_blocker_qualification.py`: 6 passed.
  - Core planner/scheduler suites (`test_recursive_planner.py`, `test_planning_repairs.py`, `test_graph_hardening.py`, `test_scheduler.py`): 62 passed, 42 subtests.
  - `tests/test_engine_policy.py`: 13 passed.
  - `tests/test_publication_view.py`, `tests/test_run_manager.py`, `tests/test_assembly_repair.py`: 31 passed.

## Limitations and remaining gaps

- Explicit supported formula calculation (e.g. baker's percentage) currently uses model execution in `calculate` leaves; deterministic computation for supported formulas remains open under **P2.3**.
- Comparison of the minimal checked baseline with recursive plans across frozen real-source case sets remains open under **P2.5**.
