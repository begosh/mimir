# Manifest Activation, Rollback Governance & Guidance Promotion (P3.5)

**Date:** 2026-10-26  
**Status:** Qualified and Verified  
**Backlog Task:** P3.5 — *"Test rejected/unchanged candidates, activation history and rollback; prevent held-out-answer leakage or promotion of unvalidated notes into guidance."*  
**Implementation Modules:** [`scripts/manifest_activation.py`](../scripts/manifest_activation.py), [`tests/test_manifest_activation.py`](../tests/test_manifest_activation.py)  
**Execution Profile:** `codex` / `gpt-6.1-sol / low`

---

## 1. Objectives & Governance Contract

To close the loop from candidate scoring (P3.4) to live system configuration without data leakage or silent regressions:

1. **Rejected/Unchanged Candidates Invariance**: Losing or unchanged candidates must never alter runtime prompts, manifests, or configuration. If a candidate is rejected (e.g. weakens a check, invents a constraint, regresses on held-out data, or has zero net gain), the active files must remain 100% bit-for-bit unchanged.
2. **Cryptographic Lineage Tracking**: Every activation records a durable entry in `.mimir/manifest-activations.jsonl` under cross-process file locks, documenting:
   - Target prompt/manifest path
   - Candidate hash & parent `prior_hash`
   - Selection record ID & decision rationale
   - Full pre-state and post-state content snapshots
3. **Reproducible Atomic Rollback**: A clean rollback mechanism restores the exact pre-activation content, verifies that the restored SHA-256 matches the parent baseline, and refuses rollback if the target file was tampered with out-of-band.
4. **Held-Out Answer Leakage Prevention**: Candidates and metadata are scanned against held-out regression splits (`expected_output`, specific numbers, locators, and case IDs). Any leakage immediately halts the pipeline with `DataLeakageError`.
5. **Guidance Promotion Guard (`guard_guidance_promotion`)**: Candidate memory notes (`learning-candidates.jsonl`) marked `requires_independent_validation` cannot be promoted into standing project guidance (`LEARNINGS.md`) without explicit supervisor review (`adjudicator_status="validated"`), grounded source citations, and zero held-out leakage.

---

## 2. Architecture & Components

```
                ┌───────────────────────────────────────┐
                │   Candidate Selection Record (P3.4)   │
                └───────────────────┬───────────────────┘
                                    │
                                    ▼
         ┌─────────────────────────────────────────────────────┐
         │ check_held_out_leakage(candidate, held_out_cases)   │
         │ (Raises DataLeakageError on held-out contamination) │
         └──────────────────────────┬──────────────────────────┘
                                    │
                 ┌──────────────────┴──────────────────┐
                 │ Decision == "ADOPT"                 │ Decision in {"REJECT", "UNCHANGED"}
                 ▼                                     ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│ ManifestActivationManager       │   │ ManifestActivationManager       │
│ - Reads current SHA-256 hash    │   │ - Target file UNTOUCHED         │
│ - Stores pre_state_content      │   │ - Verified bit-for-bit identical│
│ - Atomically writes candidate   │   │ - Ledger records REJECT event   │
│ - Ledger records ACTIVATE event │   └─────────────────────────────────┘
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│ Rollback Mechanism              │
│ - Verifies active candidate SHA │
│ - Restores exact pre_state text │
│ - Confirms prior_hash match     │
│ - Ledger records ROLLBACK event │
└─────────────────────────────────┘
```

---

## 3. Verification & Test Results

The test suite in [`tests/test_manifest_activation.py`](../tests/test_manifest_activation.py) exercises all governance invariants:

1. `test_rejected_candidate_leaves_target_untouched`: Target prompt remains 100% bit-for-bit unchanged when candidate is rejected.
2. `test_unchanged_candidate_records_event_without_modification`: Identical candidate records `UNCHANGED` event without disk churn.
3. `test_adopted_candidate_activation_and_lineage`: Successfully updates target atomically, records `ACTIVATE` with parent `prior_hash` and snapshots.
4. `test_reproducible_rollback_restores_exact_prior_state`: Cleanly restores original baseline; SHA-256 matches parent.
5. `test_rollback_refuses_out_of_band_tampered_file`: Fails closed with `RollbackError` if the active file was altered out-of-band.
6. `test_held_out_answer_leakage_rejected`: Catches held-out expected outputs and locators in candidate text, raising `DataLeakageError`.
7. `test_guidance_promotion_guard_blocks_unvalidated_candidates`: Rejects unvalidated candidate notes (`requires_independent_validation`) or unreviewed status with `PromotionGateError`; permits verified heuristics.
8. `test_end_to_end_governance_rejection_adoption_and_rollback`: Full end-to-end simulation with 1 confirmed failure and 1 disjoint held-out case:
   - Candidate A (weakens check / regresses held-out) is rejected, target untouched.
   - Candidate B (verified source support + defect reduction) is adopted with lineage.
   - Rollback restores original baseline cleanly.

**Test Execution:** 8/8 tests passed in 0.17s. Full combined priority suite: 62/62 tests passed in 9.38s.
