# Mímir Domain Glossary

Canonical domain terms used across Mímir's architecture and module interfaces.

## Evidence & Provenance Domain

- **EvidenceProvenance** (module): The single deep module owning source capture, span binding, structural citation verification, numeric/unit association checks, conflict detection, and final publication reference auditing.
- **CapturedSource**: An immutable snapshot of a workspace file or allowlisted HTTPS URL, identified by a content-addressed `capture_<sha256>` ID, locator, UTC retrieval timestamp, and retrieval type.
- **FrozenSpan**: A bounded character-offset (`span_start`, `span_end`) and line-range (`line_start`, `line_end`) excerpt sliced from a `CapturedSource` and bound to a task or publication record.
- **DeliveryMode**: The provenance lifecycle tag of a bound source or span (`supplied_inline`, `retrieve_capture`, `frozen_dependency_span`, `frozen_publication_span`).
- **ProvenanceVerdict**: The deterministic check result (`REVIEW` or `FAIL`, never `PASS`—since structural presence and numeric membership do not establish semantic entailment) produced before any model result-gate evaluation.
- **SourceConflict**: Incompatible material assertions across two or more `CapturedSource` records or worker findings that must be preserved in synthesis rather than resolved by majority vote.

## Orchestration, Gating & Governance Domain

- **RunCheckpoint**: The durable, versioned state of a phased run (`plan` → `execute` → `synthesize`), owning task output identities, attempt history, budget reservations, and publication hashes.
- **AdmissionAndAssemblyGate**: The module governing task-level result checking, coalesced batch evaluation, bounded 2-step execution repair, 1-step final assembly repair, and task quarantine projection.
- **QuarantinedFinding**: A disputed or unsupported worker result excluded from the released claim aggregate while preserved in diagnostic appendices with an explicit checked reason.
- **WorkerBroker**: The module sitting at the seam between orchestration and transport adapters, owning run budgets, context-size admission, tool-policy routing (`text_only` vs `read_only_tools`), prompt framing, and schema validation.
- **FailureRegressionCorpus**: The deduplicated store of confirmed run/quarantine failure packets and their family-disjoint regression splits (`train`, `dev`, `held_out`).
- **PromptGovernanceGate**: The offline evaluation module that scores manual and GEPA prompt candidates against a `FailureRegressionCorpus`, enforces held-out leakage invariants, and manages atomic manifest activation and rollback.
