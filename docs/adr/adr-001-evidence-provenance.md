# ADR-001: Collapse the Evidence Provenance Pipeline into `EvidenceProvenance`

- **Status**: Implemented
- **Date**: 2026-10-26
- **Module**: [`scripts/evidence_provenance.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/evidence_provenance.py)
- **Domain Glossary**: [`GLOSSARY.md`](file:///C:/Users/jonas/code/skills.sh/mimir/GLOSSARY.md)

---

## 1. Problem & Friction in the Previous Architecture

Previously, Mímir's evidence provenance lifecycle was split across six shallow files with high co-change frequency and temporal coupling:
1. [`scripts/source_store.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/source_store.py) — Content-addressed snapshots (`SourceStore`), allowlisted HTTPS/workspace file capture, and bounded literal span queries (`read_span`, `search_sources`).
2. [`scripts/source_binding.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/source_binding.py) — Pre-task binding of named manifest sources (`bind_captured_sources`).
3. [`scripts/retrieved_evidence.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/retrieved_evidence.py) — Post-worker dynamic capture (`capture_result_evidence`, `capture_async`), packet verification (`validate_capture_packet`), span projection (`inline_spans`), upstream span completeness checks (`validate_downstream_span_completeness`), and downstream dependency binding (`bind_dependency_evidence`).
4. [`scripts/source_support.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/source_support.py) — Bound citation verification (`check_bound_citations`), entity-value association checks (`check_association_integrity`), and cross-finding conflict detection/preservation (`detect_conflicts`, `check_conflict_preservation`).
5. [`scripts/extraction_checks.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/extraction_checks.py) — Deterministic number and normalized unit checks (`check_extraction`).
6. [`scripts/research_contract.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/research_contract.py) — Structured output schema (`worker_result_schema`), result normalization (`normalize_worker_result`), task-scoped aggregation (`aggregate_research_results`), and synthesis reference auditing (`audit_final_references`).

### Key Sources of Friction
- **Temporal Coupling & Manual Dict Surgery**: Callers ([`scripts/engine.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/engine.py), [`scripts/scheduler.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/scheduler.py), and [`scripts/post_worker.py`](file:///C:/Users/jonas/code/skills.sh/mimir/scripts/post_worker.py)) had to invoke functions across all six modules in a strict sequence while manually mutating `node.input_artifacts["supplied_sources"]` and filtering `DeliveryMode` string literals (`"supplied_inline"`, `"retrieve_capture"`, `"frozen_dependency_span"`, `"frozen_publication_span"`).
- **Duplicated Locator Resolution**: Source ID and locator matching (`:L10-L20`, `#chars=start-end`, `capture_<sha256>`, basename matching) was implemented five separate times across the six files.
- **Process-Global Mutable State**: `SourceStore._RUN_CAPTURES` was a mutable class-level dictionary shared across the Python process, requiring tests to monkey-patch `urllib.request.build_opener` or `SourceStore.capture_reference`.

---

## 2. Design Decision ("Design It Twice" Synthesis)

We evaluated three radically different **interface** designs for `EvidenceProvenance`:
1. **Design 1 (Ultra-Minimalist — 3 Entry Points)**: Collapsed everything into `bind_task`, `verify_task_result`, and `audit_publication`, but overloaded `bind_task` and `audit_publication` with modal parameters (`retained_envelope`, `assembled=None`).
2. **Design 2 (Flexible — Pluggable Rules & Offline Scoring)**: Introduced a `ProvenanceRule` protocol, `dispatch_query` for DSPy/RLM child processes, and standalone candidate verification, at the cost of a wider 16-method **interface** that left capture eligibility branching in `scheduler.py`.
3. **Design 3 (Caller-Ergonomic — 1-Liner Lifecycle Calls)**: Provided 1-line lifecycle methods for every stage in `engine.py`, `scheduler.py`, and `post_worker.py`, eliminating ~180 lines of manual dictionary surgery.

### Chosen Hybrid Interface
We implemented **Design 3's caller-ergonomic lifecycle entry points** combined with **Design 2's standalone `verify_task_result` signature and `dispatch_query` broker helper**:

- **Construction & Rehydration**:
  - `EvidenceProvenance.from_manifest(manifest, *, workspace=None, https_fetcher=None)`
  - `EvidenceProvenance.from_state(state_or_config, *, workspace=None, https_fetcher=None)`
- **Stage 1 — Pre-Execution Binding**:
  - `provenance.bind_task_sources(node, *, mode=None)` / `provenance.bind_graph_sources(graph, *, mode=None)`
- **Stage 2 — Checkpoint Restore & Upstream Span Binding**:
  - `provenance.restore_task_evidence(node, envelope, retained_results)`
  - `provenance.verify_retained_citations(node, envelope)`
  - `provenance.bind_upstream_evidence(node, completed_results) -> bool`
- **Stage 3 — Post-Worker Capture, Deterministic Verification & Lineage Commit**:
  - `await provenance.capture_worker_evidence(node, worker_data, completed_results) -> tuple[Any, bool]`
  - `provenance.verify_task_result(result, *, node=None, bound_sources=None, operation=None, check_associations=None) -> ProvenanceVerdict`
  - `provenance.attach_envelope_lineage(node, envelope, completed_results)`
- **Stage 4 — Synthesis Registry, Conflict Preservation & Publication Audit**:
  - `provenance.build_synthesis_registry(state)`
  - `EvidenceProvenance.verify_conflict_preservation(assembled, context_or_conflicts)`
  - `EvidenceProvenance.audit_publication(final_answer, published_data, *, scout_gaps=())`
- **Bounded Queries & DSPy/RLM Dispatch**:
  - `provenance.dispatch_query(method, args) -> tuple[Any, str]`
  - `provenance.list_sources()`, `provenance.read_span(source_id, start, end)`, `provenance.search_sources(query, limit=20)`

---

## 3. Seam Placement & Dependency Strategy

- **Workspace Files (`local-substitutable`)**: Resolved strictly within `self.workspace` (`target.is_relative_to(root)` with a 20 MB cap) and tested against real temporary directories (`tmp_path`) without mock filesystem wrappers.
- **HTTPS Fetches (`HttpsFetcher` Adapter at Internal Seam)**: Scheme (`https`), port (`None` or `443`), credential rejection, and `allowed_domains` enforcement happen *inside* `EvidenceProvenance` before crossing the `https_fetcher: HttpsFetcher` **seam**. Production uses `default_https_fetcher` (`NoRedirect` opener); tests inject a deterministic in-memory callable.
- **Instance-Scoped Capture Cache**: `self._captures` on `EvidenceProvenance` deduplicates `(locator, sha256)` snapshots per instance when an `https_fetcher` **adapter** is used.

---

## 4. Verification Summary

- **Direct Interface Tests**: [`tests/test_evidence_provenance.py`](file:///C:/Users/jonas/code/skills.sh/mimir/tests/test_evidence_provenance.py) exercises `from_manifest`, `https_fetcher` **seam** injection, dynamic capture, upstream `FrozenSpan` binding, standalone `verify_task_result`, `build_synthesis_registry`, `verify_conflict_preservation`, `audit_publication`, and `dispatch_query`.
- **Full Provenance Suite**: All 79 tests across `test_evidence_provenance.py`, `test_real_source_post_p1_p2_evaluation.py`, `test_source_binding.py`, `test_retrieved_evidence.py`, `test_dynamic_source_capture.py`, `test_source_support.py`, `test_extraction_checks.py`, `test_research_policy.py`, `test_retrieval_publication.py`, `test_provenance_and_presentation_separation.py`, and `test_source_semantic_and_conflict_integrity.py` pass (`79 passed, 14 subtests passed`).
