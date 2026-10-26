# Mímir Qualification: Controlled Manual Prompt Comparison & Invariant Enforcement (P3.3)

**Date**: 2026-10-25  
**Component**: `scripts/prompt_comparison.py`, `tests/test_prompt_comparison.py`, `scripts/regression_suite.py`  
**Execution Profile**: `codex` / `gpt-6.1-sol / low`  
**Related Requirements**: Priority 3.3 (`tasks/todo.md`)

---

## 1. Executive Summary

Backlog requirement **P3.3** mandates:
> *Compare baseline with one manually edited prompt first, fixing model, effort, tools, budgets, checker rules and intent contracts.*

Before employing automated prompt optimizers (such as GEPA or DSPy instruction synthesizers), Mímir establishes a rigorous, controlled evaluation protocol (`scripts/prompt_comparison.py`). This protocol tests a manually edited prompt candidate against the established baseline on versioned regression suites (P3.2) while locking all critical control invariants.

Any prompt revision that passes training by weakening checks, inventing constraints, or leaking held-out data is caught and rejected.

---

## 2. Invariant Enforcement & Anti-Gaming Controls

Prompt candidates are subject to strict invariance verification (`check_invariants()`) before execution:

| Invariant | Control Mechanism | Violation Consequence |
|---|---|---|
| **Model & Effort** | Locked to `gpt-6.1-sol` at `low` effort. | Disallowed configuration change. |
| **Tool Profile** | Equal tool definitions; no shell or backdoor escalation. | Rejection of unapproved capabilities. |
| **Run Budgets** | Identical attempt and wall-clock ceilings via `InvocationBroker`. | Identical operational allowances. |
| **Checker Immutability** | Result Gate templates (`RESULT_CHECKER.txt`, `FINAL_ANSWER_CHECK.txt`) are bitwise immutable and verified via SHA-256 checksums. | `InvariantViolationError`: "Checker rules are immutable; candidates cannot weaken verification." |
| **Intent Contracts** | User goals, constraints, and task briefs cannot be rewritten or diluted. | `REJECTED_INVENTED_CONSTRAINT`: Rejection of artificial limits (e.g. "assuming you only want 1"). |
| **Held-Out Isolation** | Candidate prompt text is scanned for held-out answer markers, locators, and verbatim text. | `DataLeakageError`: Immediate rejection on data contamination. |

---

## 3. Comparative Evaluation Protocol

The evaluation engine (`run_prompt_comparison`) executes baseline and candidate prompts side-by-side across disjoint `train` and `held_out` splits:

1. **Split Isolation Verification**: Confirms that training and held-out cases have zero source, topic, or failure lineage overlap.
2. **Baseline Benchmark**: Runs baseline prompt on both splits, recording pass rates, locator citations, answer markers, and defect occurrences.
3. **Candidate Evaluation**: Runs the candidate prompt under identical execution conditions.
4. **Adjudication Hierarchy**:
   - If any invented constraints or unrequested assumptions are detected $\rightarrow$ `REJECTED_INVENTED_CONSTRAINT`.
   - If held-out pass rate decreases $\rightarrow$ `REJECTED_HELD_OUT_REGRESSION`.
   - If training pass rate does not improve $\rightarrow$ `REJECTED_NO_MEASURED_BENEFIT`.
   - If training defects are resolved with zero held-out regressions and all invariants hold $\rightarrow$ `ACCEPTED_CANDIDATE`.

---

## 4. Verification Evidence & Test Results

The protocol is validated by `tests/test_prompt_comparison.py` (7 tests, 100% passing in 0.12s):

- `test_checker_tampering_rejected`: Confirms that candidate prompts targeting checker files are rejected.
- `test_modified_checker_on_disk_detected`: Confirms that alterations to disk checker files trigger checksum invariant errors.
- `test_held_out_leakage_detected`: Confirms that prompts referencing held-out answer tokens or locators raise `DataLeakageError`.
- `test_accepted_candidate_resolves_training_defect_without_held_out_regression`: Confirms acceptance of a candidate prompt that clarifies hydration formula precedence (fixing a 166.7% vs 60.0% contradiction) while preserving 100% held-out passes.
- `test_rejected_candidate_when_held_out_regresses`: Confirms rejection when an overfitted training edit degrades held-out performance.
- `test_rejected_candidate_that_invents_user_constraints`: Confirms rejection when a candidate attempts to pass by injecting unrequested assumptions.
- `test_rejected_candidate_when_no_measured_benefit`: Confirms rejection when a trivial edit yields zero net improvement.

---

## 5. Artifacts & Code References

- **Implementation**: [`scripts/prompt_comparison.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/prompt_comparison.py)
- **Test Suite**: [`tests/test_prompt_comparison.py`](file:///C:/Users/jonas/code/skills.sh/mimir/tests/test_prompt_comparison.py)
- **Workspace Report**: [`artifacts/manual_prompt_comparison_2026-10-25.md`](file:///C:/Users/jonas/code/skills.sh/mimir/artifacts/manual_prompt_comparison_2026-10-25.md)
