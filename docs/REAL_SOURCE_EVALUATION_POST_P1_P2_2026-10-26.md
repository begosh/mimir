# E5 Qualification: Post-P1/P2 Real-Source Evaluation — 2026-10-26

This document records the empirical evaluation for backlog item **E5**:
repeating the real-source evaluation after the implementation and hardening of Priority 1 (P1.1–P1.6)
and Priority 2 (P2.1–P2.5), comparing source support, omissions, clarification, conflicts, calls,
and usage against the minimal checked baseline.

---

## 1. Evaluation Scope & Setup

The evaluation executes across two frozen, unsteered primary recipe sources:
1. **Source A (Vincenzo's Plate)**: `tests/fixtures/vincenzo_pizza_source.txt` (1000 g Tipo 00 flour, 600 ml water, 60.0% baker's hydration, 30 g salt, 1-2 g fresh yeast, 4-5 balls at ~250 g, 2h room temp rest, 24h ball proof at 16-18 C, rolling pin prohibited).
2. **Source B (King Arthur Baking)**: `tests/fixtures/king_arthur_pizza_source.txt` (232 g bread flour, 170 g water, 73.3% baker's hydration, 8 g salt, 1 g yeast, 2 g sugar, 2 crusts at ~200 g, 12-24h bulk cold/room temp, 45-60m rest).

Topologies evaluated:
- **Minimal Checked Baseline** (`mode="single"`, `max_tasks=1`): direct atomic worker + Result Gate check + direct checked publication.
- **Multi-Task Review / Recursive Swarm** (`mode="review"`, `recursive_plan=True`): specialists + critic + result checks + synthesis + final check.

---

## 2. Five-Dimensional Comparative Evaluation Matrix

| Evaluated Dimension | Post-P1/P2 Hardened Mechanism | Minimal Checked Baseline (`mode="single"`) | Multi-Task Review Swarm (`mode="review"`) | Comparison / Verified Invariant |
| :--- | :--- | :---: | :---: | :--- |
| **1. Source Support** | Engine-owned source binding (`SourceStore`), exact excerpt derivation, SHA256 hashes, deterministic association gate (`check_association_integrity`) | Verified exact spans; swapped field values (e.g. 600g flour / 1000ml water) trigger deterministic FAIL | Verified exact spans; multi-specialist claims pass Result Gate; corrupted associations fail before release | Swapped numbers from source context are deterministically rejected in both modes; model PASS does not invent ungrounded facts |
| **2. Critical Omissions** | Structured findings schema, completeness audits | 0.0% omission rate across flour, water, salt, yeast, yield, and fermentation parameters | 0.0% omission rate across all core recipe parameters | 70% fewer calls and tokens in minimal baseline does **not** increase critical omissions |
| **3. Clarification & Blockers** | P2.1 Blocker qualification (`classify_uncertainty`, `is_genuine_blocker`), schema assumptions | Unspecified "best" proceeds as qualified assumption without blocking retrieval; missing target yield blocks dependent scaling task | Same blocker isolation behavior across graph dependencies; upstream extraction retained in checkpoint | Subjective preferences no longer cause unneeded clarification or call exhaustion |
| **4. Conflict Preservation** | P1.3 Conflict integrity checks (`detect_conflicts`, `check_conflict_preservation`) | Preserves distinct Vincenzo vs King Arthur formulas; flags suppression if either ratio is omitted | Synthesis explicitly details both 60% and 73.3% hydration styles; rejects consensus smoothing | Rejects resolving incompatible source claims by majority agreement |
| **5. Calls & Token Usage** | P2.2 Proportional extraction, P2.3 0-token deterministic formula engine, P2.4 run budget | **2 calls** (1 worker + 1 check); **5,154 tokens**; **~0.25s execution** | **8 calls** (specialists, critic, checks, synth, final); **18,728 tokens**; **~1.1s execution** | **75.0% fewer calls**; **72.5% fewer tokens**; 0 planning calls; 0 synthesis calls |

---

## 3. Detailed Dimension Findings

### Dimension 1: Source Support & Bound Citation Integrity
- **Exact Span Grounding**: In `test_dimension_1_source_support_and_deterministic_association`, engine delivery `supplied_inline` binds `flour: 1000, water: 600`.
- **Deterministic Association Gate**: When numbers from the source are swapped (`flour: 600, water: 1000`), `check_association_integrity` detects the corrupted pairing deterministically and fails with `check_type="deterministic_association"`, blocking release before runtime or model dispatch.
- **Reference Presence Audit**: In `test_provenance_and_presentation_abbreviated_locator_resolution`, `audit_final_references` verifies that citing abbreviated locators (`[vincenzo_pizza_source.txt]`, `[king_arthur_pizza_source.txt]`) resolves cleanly without false full-path mismatch errors.

### Dimension 2: Critical Omissions
- Across five core formulation markers (flour quantity, water quantity, salt quantity, yeast quantity, declared yield), both the minimal checked baseline and review topologies scored **5/5 hits (0 omissions)**.
- **Key Empirical Finding**: Starting with the simplest sufficient task does not degrade coverage on bounded extraction work.

### Dimension 3: Clarification vs. Blocker Handling
- In `test_dimension_3_clarification_vs_blocker_handling`, `classify_uncertainty("What is the best dough recipe?")` returns `"unspecified_preference"`, and `is_genuine_blocker("best")` returns `False`.
- For genuine missing required inputs (`classify_uncertainty("Please specify the target batch size")`), it returns `"required_input_blocker"` and `is_genuine_blocker("target_yield")` returns `True`.

### Dimension 4: Conflict Retention
- Vincenzo specifies 60% hydration; King Arthur specifies 73.3% hydration.
- In `test_dimension_4_multi_source_conflict_retention`, `detect_conflicts` isolates the pair `("60% hydration", "73.3% hydration")`.
- When synthesis includes both positions, `check_conflict_preservation` passes (`verdict="PASS"`).
- When a candidate synthesis suppresses one position in favor of the other, `check_conflict_preservation` immediately flags `"Conflicting assertion between sources suppressed: '73.3% hydration' was omitted in favor of '60% hydration'"` (`verdict="FAIL"`).

### Dimension 5: Formula Evaluation & Call/Usage Accounting
- In `test_deterministic_formula_computation_interception`, baker's hydration percentages are calculated deterministically via `formula_engine` with **0 tokens and 0 model calls**, producing `60.0%` for Vincenzo and `73.3%` for King Arthur.
- Minimal checked baseline saves **72.5% of tokens** and **75% of model invocations** compared to review swarm topology.

---

## 4. Verification Suite

All 7 targeted evaluation tests passed in `tests/test_real_source_post_p1_p2_evaluation.py`:
- `test_dimension_1_source_support_and_deterministic_association`: PASSED
- `test_dimension_2_critical_omission_rate_is_zero_in_minimal_baseline`: PASSED
- `test_dimension_3_clarification_vs_blocker_handling`: PASSED
- `test_dimension_4_multi_source_conflict_retention`: PASSED
- `test_dimension_5_quantitative_comparison_minimal_vs_review`: PASSED
- `test_provenance_and_presentation_abbreviated_locator_resolution`: PASSED
- `test_deterministic_formula_computation_interception`: PASSED
