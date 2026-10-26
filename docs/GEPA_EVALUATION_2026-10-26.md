# GEPA Evaluation and Workload Optionality Qualification — 2026-10-26

## 1. Executive Summary

This qualification document closes **P3.6** from the Mímir backlog:
> *"Use GEPA only after it demonstrates benefit over manual edits; keep RLM and JEV optional until their target workloads show a useful gain."*

Automated reflective optimizers (like GEPA) frequently churn prompt syntax, overfit to training failure packets, inflate prompt token budgets, or cause regressions on held-out tasks. Under Mímir's governed prompt evolution architecture, GEPA is not treated as an unconstrained autonomous autorun. Instead, any GEPA-generated candidate prompt must pass through a strict comparative evaluation harness against a controlled manual prompt edit before it can even be considered for manifest activation. Furthermore, heavy recursive mechanisms (RLM and JEV) remain strictly optional and default-disabled until empirical workload evidence justifies their cost.

The implementation is encapsulated in [`scripts/gepa_evaluation.py`](../scripts/gepa_evaluation.py) and thoroughly tested in [`tests/test_gepa_evaluation.py`](../tests/test_gepa_evaluation.py) (7/7 tests passing).

---

## 2. Architecture & Decision Policy

### 2.1 Comparative Benefit Gate (`evaluate_gepa_vs_manual`)

The comparative evaluation function accepts three candidate profiles (Baseline, Manual, and GEPA) alongside the held-out regression suite:

```
[Baseline Candidate]  ──────┐
[Manual Candidate]    ──────┼──> [evaluate_gepa_vs_manual] ──> [GepaComparisonReport]
[GEPA Candidate]      ──────┤                                  ├── ADOPT_GEPA
[Held-Out Splits]     ──────┘                                  ├── REJECT_GEPA_NO_BENEFIT
                                                               ├── REJECT_GEPA_HELD_OUT_REGRESSION
                                                               └── DISQUALIFIED_DATA_LEAKAGE
```

The gate applies the following decision rules in strict order:

1. **Held-Out Leakage Audit**:
   - The GEPA candidate prompt and its rationale/metadata are audited against all held-out regression cases via `check_held_out_leakage`.
   - If any verbatim target answer or ground-truth locator from held-out splits appears in the candidate, it is immediately disqualified (`DISQUALIFIED_DATA_LEAKAGE`) and blocked from activation.

2. **Held-Out Regression Check**:
   - The candidate must not increase held-out regressions over the manual candidate (`gepa_held_out_regressions <= manual_held_out_regressions`).
   - The candidate must not introduce any new hallucinations or omissions on held-out cases (`held_out_hallucinations == 0`, `held_out_omissions == 0`).
   - The candidate must maintain 100% conflict retention (`conflict_retention == 1.0`).
   - If any regression occurs, the candidate is rejected (`REJECT_GEPA_HELD_OUT_REGRESSION`).

3. **Demonstrated Benefit Over Manual Edits**:
   - GEPA must fix strictly *more* confirmed training defects than the manual candidate (`gepa_train_fixed > manual_train_fixed`). If GEPA achieves only equivalent or fewer fixes, it is rejected (`REJECT_GEPA_NO_BENEFIT`) to avoid unneeded prompt churn and complexity.
   - GEPA prompt token length must not inflate beyond 1.25x of the manual candidate's length. Unbounded prompt bloat triggers `REJECT_GEPA_NO_BENEFIT`.

4. **Adoption**:
   - If and only if GEPA demonstrates strictly superior verified defect reduction, passes the token threshold, and induces zero held-out regressions or leakage, the evaluation recommends `ADOPT_GEPA`.

---

### 2.2 Workload Optionality Audit (`audit_workload_optionality`)

To guarantee that complex subsystems do not silently become mandatory overhead:
- **JEV (Joint Expected Value) Pruning**:
  - The CLI argument parser in [`scripts/cli.py`](../scripts/cli.py) enforces `--jev` defaults to `None` (disabled).
  - JEV is executed only when explicitly requested by flag, preserving the zero-overhead baseline for standard workloads.
- **RLM (Recursive Language Model) Swarms**:
  - The research program in [`scripts/research_program.py`](../scripts/research_program.py) defaults to `native` tool execution.
  - RLM and interpreter-backed sub-agents are strictly opt-in and engaged only when `--mode swarm` or explicit RLM configurations are passed.

---

## 3. Test Coverage & Empirical Verification

The evaluation module is tested in [`tests/test_gepa_evaluation.py`](../tests/test_gepa_evaluation.py), verifying all governance invariants:

| Test Case | Scenario Evaluated | Expected Outcome | Verified |
| :--- | :--- | :--- | :--- |
| `test_gepa_rejected_when_no_benefit_over_manual` | GEPA matches manual fixes (1 fix each) with equal held-out performance. | `REJECT_GEPA_NO_BENEFIT` | PASS |
| `test_gepa_rejected_on_held_out_regression` | GEPA fixes 2 training defects but causes 1 regression on held-out. | `REJECT_GEPA_HELD_OUT_REGRESSION` | PASS |
| `test_gepa_disqualified_on_data_leakage` | GEPA candidate contains exact held-out ground truth answer text. | `DISQUALIFIED_DATA_LEAKAGE` | PASS |
| `test_gepa_rejected_on_excessive_token_bloat` | GEPA fixes 2 training defects vs manual 1, but prompt length is 1.4x manual. | `REJECT_GEPA_NO_BENEFIT` | PASS |
| `test_gepa_adopted_when_strictly_superior_and_safe` | GEPA fixes 2 training defects vs manual 1, zero regressions, safe tokens. | `ADOPT_GEPA` | PASS |
| `test_workload_optionality_cli_defaults` | CLI argument parser inspection of `--jev` parameter defaults. | `default=None` (disabled) | PASS |
| `test_workload_optionality_program_defaults` | Research program configuration inspection for default engine mode. | `mode='native'` | PASS |

---

## 4. Acceptance Criteria Verification

- [x] **Candidates cannot consume held-out answers or modify checker and intent policy**:
  Verified by `check_held_out_leakage` check in Step 1 of `evaluate_gepa_vs_manual` and prompt comparison policy immutability.
- [x] **Activation requires a useful measured benefit with no critical source-support regression**:
  Enforced by `gepa_train_fixed > manual_train_fixed` and strict rejection on any held-out hallucination or regression.
- [x] **Losing/unchanged candidates do not change runtime behaviour**:
  Governed by `ManifestActivationManager`, which guarantees bit-for-bit file invariance on unaccepted candidates.
- [x] **RLM and JEV remain optional**:
  Verified by `audit_workload_optionality` confirming `--jev` default is `None` and research program defaults to `native`.
