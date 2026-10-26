# Bound Semantic and Conflict Integrity Qualification — 2026-10-26

## Overview

Backlog item **P1.3** enforces deterministic identity validation and narrow semantic checks for field/entity associations, stated conditions, and conflict preservation:
> "Validate source/version/span identity deterministically; add narrow semantic checks for associations, omissions and conditions against the source. Preserve conflicting assertions rather than resolving them by majority agreement."

This qualification documents the architectural implementation, the separation of deterministic assertions from fresh blinded model checks, and the verified smallest meaningful test across both `single` and `review` execution modes.

---

## Architectural Implementation

### 1. Separation of Structural Provenance and Semantic Association Checks
- **Structural Provenance (`check_bound_citations`)**:
  - Validates source identity, content SHA256 hashes, capture timestamps, delivery types, locator formats (full path, canonical ID, line range `:Lstart-Lend`, and char offsets `#chars=start-end`), and exact excerpt substring containment.
  - When passing, returns `{"verdict": "REVIEW", "check_type": "structural_provenance"}`. It **never claims factual truth or entailment** (`PASS`).
  - When failing, returns `{"verdict": "FAIL", "check_type": "structural_provenance"}` and blocks release of downstream tasks.

- **Deterministic Field/Entity Association & Condition Gate (`check_association_integrity`)**:
  - Extracts explicit entity-to-value bindings from bound source spans (including Python ternary expressions like `(180 if t["id"] == "critique" else 250)` and natural key-value pairings).
  - Normalizes canonical entities (e.g. `critique`/`critic`, `specialists`/`other`).
  - Detects **swapped or cross-associated numbers** where both numbers occur in the source text (which token bag-of-words or naive substring searching cannot catch).
  - Detects **unconditional assertions** (e.g. "in all modes" or "always") when the bound source text restricts the values (e.g. "Only in review mode").
  - When an association defect is detected, returns `{"verdict": "FAIL", "check_type": "deterministic_association"}` with specific defect details before expensive model calls.

### 2. Conflict Preservation Across Sources and Assembly
- **Conflict Integrity Gate (`check_conflict_preservation`)**:
  - When multiple sources or independent workers report incompatible assertions (e.g. conflicting ports, hydration percentages, or opposing specifications), the final gate strictly rejects resolving the conflict through majority agreement or suppressing one side.
  - Verifies that for every conflicting pair `(claim_a, claim_b)`, if one is asserted, the conflicting alternative is also explicitly retained in the answer, limitations, or gaps.
  - Failure returns `{"verdict": "FAIL", "check_type": "conflict_integrity", "issues": ["Conflicting assertion between sources suppressed..."]}`.
- **Conflict Detection (`detect_conflicts`)**:
  - Scans upstream findings for multi-task discrepancies, explicit `conflicts` lists, or disagreement expressions across parallel specialists.

### 3. Truthful Publication & Appendix Quarantine (`publication_view`)
- In `mode="single"`:
  - If a worker result fails association checking, publication is blocked.
  - Upon successful repair/rephrase, the accepted result publishes directly without an extra synthesis call, maintaining original evidence hashes and truthful status in `publication_view`.
- In `mode="review"`:
  - When a worker finding is disputed or rejected, assembly repair records a `quarantined_tasks` entry with a specific reason.
  - `build_publication_view` sets `status="quarantined"` for the task, preserving its original hash, reason, sources, and gaps, while excluding its unverified assertions from the released claim aggregate.

---

## Qualification Results

### 1. Smallest Meaningful Test
The specification requires:
> "one real source span, one factual claim, one dependent and one publication, parameterized for single/review. Corrupt the field association using numbers that both occur in the source. Verify rejection, blocked release, checked correction and truthful appendix status. Keep deterministic assertions separate from a fresh blinded low-effort model check."

- **Source**: Real span from `scripts/task_graph.py` defining review word limits:
  `(180 if t["id"] == "critique" else 250) if self.mode == "review" else None`
  (both `180` and `250` occur in the source).
- **Corrupted Assertion**: `Review limits: critique 250 words; specialists 180 words.`
- **Verification Outcomes**:
  - `check_bound_citations` returns `REVIEW` with `check_type="structural_provenance"`.
  - `check_association_integrity` returns `FAIL` with `check_type="deterministic_association"`, reporting that `critic` was associated with `250` and `specialists` with `180`.
  - Dependent child task is **not released** while parent is rejected.
  - Result repair applies checked correction: `critique 180 words; specialists 250 words.`
  - Recheck passes, dependent child task releases and executes.
  - Publication view records truthful appendix status:
    - In `single`: parent task accepted with verified original hash.
    - In `review`: quarantined entries reflect the exact rejection reason and retain archival evidence.

### 2. Multi-Source Conflict Preservation
- Tested conflicting deployment ports (`8100` vs `9999`) across independent sources:
  - Resolving by majority agreement ("Port is 8100 by majority agreement"): **FAIL** (`conflict_integrity`).
  - Preserving both conflicting assertions explicitly ("Source A states 8100, while Source B states 9999"): **PASS** (`conflict_integrity`).

### 3. Test Suites Executed
- [`tests/test_source_semantic_and_conflict_integrity.py`](../tests/test_source_semantic_and_conflict_integrity.py): **7/7 passed** (0.20s).
- Full Priority 1 Suite: **44/44 passed** (19.17s):
  - `tests/test_source_semantic_and_conflict_integrity.py` (7 tests)
  - `tests/test_source_support.py` (16 tests)
  - `tests/test_dynamic_source_capture.py` (6 tests)
  - `tests/test_retrieved_evidence.py` (8 tests)
  - `tests/test_material_finding_gate.py` (7 tests)
- Full Priority 2 & 3 Regression Suites: **71/71 passed** (34.76s).
- Total Suite Verification: **115 tests passed with 0 failures**.

---

## Status and Handoff

Item **P1.3** is complete `[x]`. The remaining open backlog items are:
- **P1.6**: Separate structural provenance defects from model support labels; unbound final-reference presentation.
- **E4, E5, E6**: Multi-source evaluation benchmarks and tool-runtime readiness.
