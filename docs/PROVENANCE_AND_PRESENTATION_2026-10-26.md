# Provenance and Presentation Separation Qualification — 2026-10-26

## Overview

Backlog item **P1.6** addresses the clean separation between structural provenance defects and model semantic support labels, and improves final reference auditing:
> "Separate structural provenance defects from model support labels; avoid treating abbreviated-locator string mismatches as citation entailment failures. Bound structural defects have their own check type; exact source-ID abbreviations resolve without literal full-path comparison. Unbound final-reference audit and broader presentation cleanup remain pending."

This document records the architectural enhancements, test coverage, and qualification results.

---

## Architectural Implementation

### 1. Abbreviated Locator & Source ID Resolution (`audit_final_references`)
Previously, `audit_final_references` required exact string equality between the source's full locator (such as a full filesystem path or full HTTPS URL) and the synthesis text:
```python
missing = sorted(locator for locator in locators if locator not in answer)
```
This falsely downgraded coverage to `partial` whenever a worker cited a source using its canonical source ID (e.g. `[spec]`, `[task_1:spec]`), filename basename (e.g. `guide.md`, `solver.py`), or unscoped ID.

In [`scripts/research_contract.py`](../scripts/research_contract.py), `audit_final_references` now resolves sources across multiple valid representations:
- **Canonical Source ID**: `source["id"]` (e.g. `task_1:spec_doc`, `capture_<sha256>`).
- **Unscoped Source ID**: Suffix following task prefix (e.g. `spec_doc`).
- **Locator Basename**: `Path(source["locator"]).name` (e.g. `protocol_v1.html`, `task_graph.py`).
- **Cleaned URL**: URL path and trailing endpoint segment.
- **Exact Locator**: Full absolute path or URL.

A supported source is recognized as present if any of its valid representations appears in the answer, preventing false string-mismatch failures.

### 2. Unbound Final Reference Auditing
`audit_final_references` now inspects the synthesis text for bracketed citations (e.g. `[unknown_source]`, `[fake_file.py]`) or invented locators that do not resolve to any known bound source in `research["sources"]`.
- Detected unbound citations are collected under `unbound_references`.
- If any unbound citations are present, `reference_presence_passed` is set to `False`.
- In [`scripts/engine.py`](../scripts/engine.py), unbound citations downgrade `research["coverage"]` to `partial` and record explicit issues under `research["issues"]`.

### 3. Separation of Structural Provenance from Semantic Entailment
- **Dedicated Check Type**: Structural checks across all phases consistently set `check_type="structural_provenance"`:
  - Bound citation validation ([`scripts/source_support.py`](../scripts/source_support.py)): `check_bound_citations`
  - Extraction checks ([`scripts/extraction_checks.py`](../scripts/extraction_checks.py)): `check_extraction`
  - Final reference audit ([`scripts/research_contract.py`](../scripts/research_contract.py)): `audit_final_references`
- **Presentation Separation**:
  - The final Markdown report explicitly presents:
    ```markdown
    - Supporting source omitted from synthesis: <locator>
    - Unbound reference in synthesis text: <unbound_ref>
    - Final reference audit: **passed** / **partial** (String presence and ID resolution; not independent verification or citation entailment).
    ```
  - Reference presence confirms that expected sources were mentioned; it is explicitly decoupled from semantic citation entailment or factual truth.

---

## Qualification Results

A dedicated test suite [`tests/test_provenance_and_presentation_separation.py`](../tests/test_provenance_and_presentation_separation.py) was implemented and verified:

1. **Abbreviated Resolution (`test_abbreviated_locator_and_source_id_resolve_without_full_path`)**:
   - Verified that full locators, abbreviated IDs (`[spec_doc]`, `[solver.py]`), and scoped IDs (`[task_1:spec_doc]`) all pass reference presence without missing locator errors.
2. **Unbound Reference Detection (`test_unbound_final_references_are_detected_and_flagged`)**:
   - Verified that invented references (`[unknown_source_99]`, `[fake_file.py]`) are identified and populated in `unbound_references`, setting `reference_presence_passed=False`.
3. **Omitted Supported Sources (`test_omitted_supported_source_fails_reference_audit`)**:
   - Confirmed that completely omitting a worker-supported source fails the reference presence audit.
4. **Distinct Check Type (`test_structural_provenance_check_type_distinct_from_semantic_support`)**:
   - Verified that `check_bound_citations`, `check_extraction`, and `audit_final_references` return `check_type="structural_provenance"`.
5. **End-to-End Engine Presentation (`test_end_to_end_presentation_separates_resolution_and_flags_unbound`)**:
   - Executed full `run_mimir` runs parameterized across `single` and `review` modes.
   - Verified that abbreviated IDs resolve cleanly, unbound citations are detected and listed in the Markdown report, and JSON payload accurately records partial coverage.

### Test Execution Summary
- **P1.6 Suite**: 6 passed in 6.55s.
- **Combined Priority 1 Suite**: 66 passed in 25.51s.
- **Priority 2 & 3 Regression Suites**: 71 passed in 34.76s.
- **Total Combined Run**: **137 tests passed, 0 failures**.

---

## Status and Handoff

Item **P1.6** is complete `[x]`.
With this closure, **all core priorities (Priority 1, Priority 2, and Priority 3) are 100% complete**.

Remaining open backlog items are the evaluation benchmarks:
- **E4**: Create durable regression case for E1 repository review.
- **E5**: Multi-source real-world evaluation comparing support and omissions against the checked baseline.
- **E6**: Qualify hybrid interruption/recovery and target tool-runtime readiness.
