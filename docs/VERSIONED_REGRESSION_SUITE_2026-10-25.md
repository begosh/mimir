# Mímir Qualification: Versioned Regression Suite & Disjoint Split Isolation (P3.2)

**Date**: 2026-10-25  
**Component**: `scripts/regression_suite.py`, `tests/test_regression_suite.py`, `scripts/failure_store.py`  
**Execution Profile**: `codex` / `gpt-6.1-sol / low`  
**Related Requirements**: Priority 3.2 (`tasks/todo.md`)

---

## 1. Executive Summary

Backlog requirement **P3.2** mandates:
> *Convert confirmed failures into versioned regressions; separate train/dev and fresh held-out families by source/topic and failure lineage.*

To prevent overfitting, prompt degradation, and benchmark contamination during iterative reasoning refinement, Mímir implements a versioned **Regression Suite** (`scripts/regression_suite.py`). The suite converts independently confirmed failure packets from `FailureStore` into standardized, versioned `RegressionCase` specifications, enforcing strict family-disjoint separation across `train`, `dev`, and `held_out` partitions.

---

## 2. Architecture & Data Model

### 2.1 Versioned Regression Case Schema

Each `RegressionCase` captures the full deterministic lineage and verification constraints necessary to evaluate regression fixes:

| Field | Type | Description |
|---|---|---|
| `case_id` | `str` | Deterministic identifier: `reg-v{version}-{hash12}`. |
| `version` | `int` | Regression specification schema version (default: `1`). |
| `packet_id` | `str` | Provenance link to the originating `FailurePacket`. |
| `original_intent`| `str` | High-level user goal. |
| `goal` | `str` | Targeted evaluation objective. |
| `topic` | `str` | Semantic domain family (e.g., `baking_and_formulation`, `dependency_management`). |
| `source_family` | `str` | Primary document or source family identifier (e.g., `vincenzo`, `requirements_txt`). |
| `split_family` | `str` | Composite key (`{topic}::{source_family}`) used for disjoint partition allocation. |
| `split` | `str` | Partition assignment: `train`, `dev`, or `held_out`. |
| `failure_lineage`| `dict` | Forensic ancestry: `origin_run_id`, `failure_kind`, `defect_types`, `lineage_root`. |
| `bound_sources` | `list` | Frozen source snapshots, locators, and text excerpts. |
| `verification_spec` | `dict` | Test criteria: `required_locators`, `required_answer_markers`, `expected_blockers`, `expected_defect_types`. |
| `metadata` | `dict` | Creation timestamps, occurrences, and provenance tags. |

### 2.2 Failure-to-Regression Conversion

`convert_failure_to_regression()` validates and transforms confirmed failures:
1. **Adjudication Requirement**: Only failure packets with non-empty `adjudicated_defects` and status != `waived` are converted. Waived packets are strictly rejected to prevent noise pollution.
2. **Deterministic Family Derivation**: Heuristically extracts source family (`derive_source_family`) and topic family (`derive_topic_family`) from bound citations, goals, and defect descriptions.
3. **Verification Extraction**: Automatically populates `required_locators` from bound sources, `expected_blockers` from missing input blockers, and `expected_defect_types` from adjudicated defects.

---

## 3. Disjoint Partitioning & Leakage Prevention

### 3.1 Family-Disjoint Partitioning

To ensure that candidate prompt revisions or optimizer iterations do not memorize test questions or cheat by observing held-out sources, `partition_splits()` partitions entire `(topic, source_family)` groups:

$$\text{Family} = (\text{Topic}, \text{SourceFamily})$$

Allocation rules:
1. If a family is assigned to `held_out`, all cases belonging to that topic family or source family are exclusively held out.
2. No source document in `held_out` is ever exposed to `train` or `dev`.
3. No topic domain in `held_out` is ever exposed to `train` or `dev`.

### 3.2 Strict Split Isolation Validation

`validate_split_isolation()` verifies dataset integrity before any test or ingestion operation:

$$\text{sources}(\text{train} \cup \text{dev}) \cap \text{sources}(\text{held\_out}) = \emptyset$$
$$\text{topics}(\text{train} \cup \text{dev}) \cap \text{topics}(\text{held\_out}) = \emptyset$$
$$\text{lineages}(\text{train} \cup \text{dev}) \cap \text{lineages}(\text{held\_out}) = \emptyset$$

If any intersection is non-empty, execution fails closed with a `DataLeakageError`, reporting the exact overlapping identifiers.

---

## 4. Evaluator Integration

`RegressionStore.export_eval_dataset(split, out_file)` exports benchmark cases formatted for direct ingestion by `scripts/evaluate.py`:

```json
[
  {
    "id": "reg-v1-a1b2c3d4e5f6",
    "goal": "Scale Vincenzo's Neapolitan Pizza dough for 8 pizzas",
    "topic": "baking_and_formulation",
    "source_family": "vincenzo",
    "split": "held_out",
    "required_locators": ["fixtures/vincenzo_pizza_source.txt"],
    "required_answer_markers": ["60.0%"],
    "expected_blockers": [],
    "expected_defect_types": ["arithmetic_contradiction"],
    "lineage": {
      "packet_id": "8f3a129d4b0c7e21",
      "origin_run_id": "run-fail-pizza-01",
      "failure_kind": "result_check_failure"
    }
  }
]
```

---

## 5. Verification & Acceptance Evidence

Validated by `tests/test_regression_suite.py` (7 tests, 100% passing):

- `test_convert_confirmed_failure_to_regression_case`: Verifies accurate lineage mapping and spec compilation.
- `test_waived_packet_rejected_from_regression_conversion`: Confirms rejected conversion for waived records.
- `test_missing_input_blocker_conversion_extracts_expected_blockers`: Verifies automatic extraction of required inputs.
- `test_partition_splits_strictly_isolates_families`: Confirms family-level disjoint split allocation.
- `test_validate_split_isolation_blocks_source_topic_and_lineage_leakage`: Confirms detection of source, topic, and lineage leakage.
- `test_regression_store_ingest_from_failure_store_and_export_eval`: Confirms store persistence and evaluator dataset export.
- `test_smallest_meaningful_disjoint_split_and_leakage_rejection`: Implements the backlog acceptance criterion: verifies that one confirmed failure and one disjoint held-out case maintain independent family splits, and rejects candidate training cases attempting to consume held-out sources.

---

## 6. Artifacts & Code References

- **Implementation**: [`scripts/regression_suite.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/regression_suite.py)
- **Test Suite**: [`tests/test_regression_suite.py`](file:///C:/Users/jonas/code/skills.sh/mimir/tests/test_regression_suite.py)
- **Workspace Report**: [`artifacts/versioned_regression_suite_2026-10-25.md`](file:///C:/Users/jonas/code/skills.sh/mimir/artifacts/versioned_regression_suite_2026-10-25.md)
