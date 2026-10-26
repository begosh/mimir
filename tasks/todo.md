# Mimir improvement backlog

Current priorities from the [2026-10-23 implementation assessment](../docs/SELF_HARDENING_ASSESSMENT_2026-10-23.md).
Earlier work and dated completion records remain in [history.md](history.md).

“Eliminating hallucinations through recursive decomposition & adversarial evolution”
is an ambition. Current checks demonstrate bounded execution and model consistency;
they do not establish independent factual correctness or hallucination elimination.

## Working baseline

| Status | Capability |
| --- | --- |
| Demonstrated | Dependency-ready scheduling, isolated requests, captured-source binding, shared material-finding admission, two result-repair cycles, checked single publication, review/swarm answer/appendix gates, identity-checked recovery and durable whole-run budgets |
| Insufficiently tested | Intent fidelity, clarification materiality, proportional decomposition, semantic source support, conflict handling and hybrid crash recovery |
| Missing | Complete mixed-worker retrieved-page binding and governed failure-to-prompt improvement |

DSPy Predict, interpreter-backed RLM and offline upstream GEPA execute. GEPA's
selected instructions remained unchanged in the recorded qualification. JEV is
optional heuristic pruning with no demonstrated net savings. Kahn-DAG supplies
ordering and integrity. None of these names establishes better answer quality.

Work in small increments using **gpt-6.1-sol / low**. Preserve agreed effort,
limits, user intent, provenance, conflicts and gaps. Prefer ordinary code and
the simplest checked baseline; require measured benefit before adding complexity.
Mark a task complete only after its acceptance criteria and meaningful test pass.

## Priority 1 — Bind material claims to evidence before release and publication

Expected benefit: reduce unsupported assertions and prevent a worker's claims
from becoming accepted facts merely through repetition or critique agreement.

Evidence: [source handoff](../docs/SOURCE_HANDOFF_2026-10-23.md),
[result gate](../docs/RESULT_GATE_2026-10-23.md),
[final gate](../docs/FINAL_ANSWER_GATE_2026-10-23.md), and the assessment's real-repository evaluation.
The assessment found ordinary single/review admission bypasses and a stale
appendix assertion. P1.1 now gates ordinary workers and reuses the accepted
single answer/gaps check for publication; review/swarm final checks include
appendix assertions. Retrieved pages are still not automatically frozen for dependents.

- [x] **P1.1** Define a small material-finding contract shared across policies;
  apply admission checking to ordinary workers and check the existing single
  answer without adding an unnecessary synthesis worker.
  Implemented with the existing structured findings schema, identity-bound
  admission, bounded repairs and single answer/gaps publication without duplicate
  synthesis/check calls. See [qualification](../docs/MATERIAL_FINDING_GATE_2026-10-23.md).
- [x] **P1.2** Generate source identity and capture metadata in the engine;
  freeze retrieve-worker evidence and bind exact needed spans to dependents.
  Implemented with engine reread across mixed research/tool workers, content SHA256
  and canonical capture_<sha256> IDs, UTC capture timestamps with SourceStore._RUN_CAPTURES
  run caching, frozen exact excerpts with line start/end derivations, claim link rebinding
  with alias tracking, and downstream span completeness gating (validate_downstream_span_completeness)
  verifying that all dependency claims have active frozen spans and all contract inputs are bound.
  See [qualification](../docs/DYNAMIC_SOURCE_CAPTURE_2026-10-26.md).
- [x] **P1.3** Validate source/version/span identity deterministically; add narrow
  semantic checks for associations, omissions and conditions against the source.
  Preserve conflicting assertions rather than resolving them by majority agreement.
  Bound citation ID/type/time/locator/quote checks run before semantic admission
  and during recovery. Narrow deterministic association and condition checks
  (check_association_integrity) detect inverted numbers and unconditional claims.
  Conflict integrity checks (check_conflict_preservation, detect_conflicts) reject
  resolving incompatible assertions by majority agreement. Smallest meaningful test
  verified on real task_graph word-limit spans across single and review modes,
  blocking dependent release upon corrupted association, enabling release upon checked repair,
  and preserving truthful appendix status.
  See [qualification](../docs/SEMANTIC_AND_CONFLICT_INTEGRITY_2026-10-26.md).
- [x] **P1.4** Publish accepted versions; quarantine rejected assertions or mark
  their correction status explicitly in appendices.
  Publication status view quarantines disputed task assertions with a checked
  reason while preserving original records, sources and gaps. Final checking
  covers answer/status view; released claim aggregates exclude quarantined claims.
  See [verification and scope](../docs/PUBLICATION_VIEW_2026-10-23.md).
- [x] **P1.5** Add at most one targeted assembly correction followed by recheck,
  preserving the original objective, sources, checker policy and run limits.
  Implemented with durable reservation/history, unchanged context and checker,
  and fail-closed exhaustion/interruption. See [verification](../docs/ASSEMBLY_REPAIR_2026-10-23.md).
- [x] **P1.6** Separate structural provenance defects from model support labels;
  avoid treating abbreviated-locator string mismatches as citation entailment failures.
  Bound structural defects across citation checking, extraction checking and final reference
  auditing consistently assign check_type="structural_provenance". Exact source-ID abbreviations,
  unscoped IDs and locator basenames resolve in audit_final_references without literal full-path
  comparison. Unbound citations in synthesis text are audited and flagged in unbound_references,
  cleanly updating coverage to partial and recording explicit issues in Markdown and JSON reports.
  See [qualification](../docs/PROVENANCE_AND_PRESENTATION_2026-10-26.md).

Acceptance criteria: required rejected findings never release dependents or become
unqualified published claims. Unknown/changed source versions and unsupported
additions fail the relevant gate. Conflicts and material omissions survive
assembly. Model PASS never becomes a claim of independent verification.

Smallest meaningful test: one real source span, one factual claim, one dependent
and one publication, parameterized for single/review. Corrupt the field association
using numbers that both occur in the source. Verify rejection, blocked release,
checked correction and truthful appendix status. Keep deterministic assertions
separate from a fresh blinded low-effort model check.

## Priority 2 — Start with the cheapest sufficient task; split only when needed

Expected benefit: improve ordinary-request completion while removing unnecessary
clarifications, decomposition and model calls.

Evidence: [execution conclusions](../docs/EXECUTION_CONCLUSIONS_2026-10-23.md).
Fresh recipe planning blocked retrieval on an unanswered “best” criterion or
exhausted limits. A minimal direct fixture pipeline used 72.5% fewer reported
tokens than the direct six-task pipeline, with fewer acceptance boundaries.
The real-repository review routed a supplied-input critic through native tools.

- [x] **P2.1** Distinguish genuine required-input blockers from ambiguity that
  permits evidence gathering and a qualified answer; retain the original request
  and label assumptions without inventing user constraints.
  Implemented with schema assumptions, uncertainty classification, prompt hardening,
  graph TaskStatus.BLOCKED isolation, and retained upstream evidence.
  See [qualification](../docs/BLOCKER_QUALIFICATION_2026-10-25.md).
- [x] **P2.2** Start with one bounded retrieval/extraction; split for input/output
  bounds or distinct decisions, permitting short contiguous procedures.
  Implemented with proportional decomposition, bounds triggers, simplicity review
  acceptance of bounded leaves and contiguous steps, and single-mode auto-routing.
  See [qualification](../docs/BOUNDED_EXTRACTION_2026-10-25.md).
- [x] **P2.3** Use deterministic computation for explicit supported formulas;
  route text/tool work using an explicit tool need rather than a broad role name.
  Implemented with formula_engine (baker's percentage, hydration, scaling, total weight,
  safe AST evaluation), 0-token deterministic calculation interception, missing operand
  gap reporting, Result Gate contradiction checking, and explicit tool need routing
  (needs_tools=False routing to spawn_restricted for review critiques and atomic text tasks).
  See [qualification](../docs/FORMULA_AND_TOOL_ROUTING_2026-10-25.md).
- [x] **P2.4** Enforce one persisted attempt/deadline budget across planning,
  execution, checks, repairs and assembly, with reserved publication calls and
  durable attempt journaling for ordinary runs. Count interruptions and retries.
  [Budget/recovery contract and validation](../docs/RUN_BUDGET_2026-10-23.md).
- [x] **P2.5** Compare the minimal checked baseline with recursive plans on a
  frozen real-source case set; retain failures, omissions and known/unknown usage.
  Implemented with frozen real sources (Vincenzo's Plate and King Arthur), quantitative
  comparison (~70% token and call reduction with single worker + check), verification of zero
  increase in critical omissions, qualification of unspecified 'best' preferences, isolated
  blocking of missing inputs with retained upstream evidence, contiguous procedure unsplit
  preservation, and budget reservation/overshoot accounting.
  See [qualification](../docs/BASELINE_COMPARISON_2026-10-25.md).

Acceptance criteria: unspecified recommendation preferences do not unnecessarily
block retrieval, while genuine missing inputs block only the dependent decision.
Simple supplied-source work uses one worker and its check without recursive
planning calls. Fewer calls/tokens do not increase critical omissions or unsupported
claims. Resume retains reservations; exhaustion cannot silently widen limits.
A reported-token threshold must be described as able to overshoot in-flight work.

Smallest meaningful test: two requests over the same real source, one with an
unspecified “best” preference and one genuinely requiring a missing target.
The first proceeds with qualification; the second blocks the dependent decision.
Add one contiguous-procedure case with no redundant split. Repeat fresh planning
at unchanged settings; scripted wiring alone cannot prove semantic improvement.

## Priority 3 — Build an offline failure-to-regression loop before more evolution

Expected benefit: improve across runs without overfitting, weakening checks or
turning failed assumptions into standing guidance.

Evidence: [DSPy/RLM qualification](../docs/DSPY_RLM_IMPLEMENTATION_2026-10-22.md)
and [evaluation policy](../docs/EVALUATION.md). Failure records and unvalidated
learning candidates exist, but ordinary failed-run ingestion is missing.
Recorded GEPA proposals did not yield an accepted changed instruction set.
Exact-answer and locator-presence metrics do not establish source entailment.

- [x] **P3.1** Capture and deduplicate failure packets with original intent,
  source snapshots/spans, attempts, feedback and independently adjudicated defects.
  Implemented with failure_store (process-safe .mimir/failure-packets.jsonl),
  deterministic content-addressable SHA256 deduplication hashing (original intent, task objective,
  failure kind, defect fingerprint) with occurrence incrementing and history tracking, automated
  defect taxonomy classification (classify_defect_from_feedback), independent supervisor defect
  adjudication, and automatic failure ingestion on engine execution halts and synthesis quarantine.
  See [qualification](../docs/FAILURE_PACKET_INGESTION_2026-10-25.md).
- [x] **P3.2** Convert confirmed failures into versioned regressions; separate
  train/dev and fresh held-out families by source/topic and failure lineage.
  Implemented with regression_suite (RegressionCase, RegressionStore),
  deterministic case IDs, failure-to-regression conversion with lineage preservation,
  family-disjoint partitioning (partition_splits by topic and source family),
  strict split isolation validation (validate_split_isolation raising DataLeakageError
  on source, topic, or lineage leakage), and evaluator benchmark exporting for evaluate.py.
  See [qualification](../docs/VERSIONED_REGRESSION_SUITE_2026-10-25.md).
- [x] **P3.3** Compare baseline with one manually edited prompt first, fixing
  model, effort, tools, budgets, checker rules and intent contracts.
  Implemented with prompt_comparison (PromptCandidate, run_prompt_comparison),
  locking model (gpt-6.1-sol), effort (low), tools, budgets, and checker immutability.
  Detects and rejects checker tampering, disk checksum alterations, held-out answer/locator
  leakage (DataLeakageError), and invented user constraints (REJECTED_INVENTED_CONSTRAINT).
  Side-by-side evaluation against versioned train and held-out regression splits.
  See [qualification](../docs/MANUAL_PROMPT_COMPARISON_2026-10-25.md).
- [x] **P3.4** Score unsupported material claims, omissions, unnecessary blockers,
  conflict retention and usage; predeclare adoption thresholds and independently
  review source support before explicit manifest selection.
  Implemented with candidate_scoring (CandidateScoreVector, IndependentSourceReviewer,
  AdoptionThresholds, SelectionRecord, evaluate_candidate_adoption).
  Audits material claims against bound source texts, flags hallucinations and omissions,
  enforces 100% conflict retention, caps usage inflation at 1.15x, requires >=1 training
  defect repair, and generates cryptographic selection records prior to manifest activation.
  See [qualification](../docs/MULTI_DIMENSIONAL_SCORING_2026-10-25.md).
- [x] **P3.5** Test rejected/unchanged candidates, activation history and rollback;
  prevent held-out-answer leakage or promotion of unvalidated notes into guidance.
  Implemented with manifest_activation (ManifestActivationManager, ActivationRecord,
  guard_guidance_promotion, check_held_out_leakage).
  Guarantees rejected/unchanged candidates leave runtime prompts 100% bit-for-bit unchanged,
  records durable cryptographic lineage (prior_hash parent pointers and snapshots in
  .mimir/manifest-activations.jsonl), provides atomic verified rollback, halts on held-out
  answer/locator leakage (DataLeakageError), and strictly guards LEARNINGS.md against
  unvalidated candidate notes (PromotionGateError).
  See [qualification](../docs/MANIFEST_ACTIVATION_2026-10-26.md).
- [x] **P3.6** Use GEPA only after it demonstrates benefit over manual edits;
  keep RLM and JEV optional until their target workloads show a useful gain.
  Implemented with gepa_evaluation (CandidateProfile, GepaComparisonReport,
  evaluate_gepa_vs_manual, audit_workload_optionality). Rejects GEPA when no measured
  benefit over manual edit (gepa_train_fixed <= manual_train_fixed or token bloat > 1.25x),
  rejects GEPA on any held-out regression or new hallucination/omission, disqualifies
  candidates on held-out leakage (DISQUALIFIED_DATA_LEAKAGE), and adopts GEPA only
  upon strictly superior defect reduction without regressions. Audits CLI and research program
  defaults to guarantee JEV and RLM swarms remain strictly optional and default-disabled.
  See [qualification](../docs/GEPA_EVALUATION_2026-10-26.md).

Acceptance criteria: candidates cannot consume held-out answers or modify checker
and intent policy. Activation requires a useful measured benefit with no critical
source-support regression and explicit review. Losing/unchanged candidates do not
change runtime behaviour. Split identities, selection history and rollback are reproducible.

Smallest meaningful test: one independently confirmed repository failure and one
disjoint held-out question, baseline versus edited prompt. Reject a candidate
that fixes training by inventing a constraint or weakening a check. This validates
governance; a larger representative set is needed before claiming general improvement.

## Evaluation baseline and follow-up

- [x] **E1** Run a real current-repository review beyond synthetic fixtures:
  atomic admission, single/review publication and incomplete-graph behaviour.
  Completed at gpt-6.1-sol/low: 94.116 seconds, five adapter invocations,
  240,752 reported tokens including 155,317 cached input tokens; final PASS,
  evidence coverage partial. Usage is not verified billing.
- [x] **E2** Independently resolve the omitted checkpoint-loading guard:
  incomplete synthesis checkpoints reject with “Synthesis requires results for
  every planned task.” Completed graphs still need semantic completeness checks.
- [x] **E3** Run focused verification: 96 tests and 21 subtests passed. These
  engineering tests do not establish general live-model accuracy.
- [x] **E4** Preserve E1 as a regression: the critic softened an overreaching
  claim, but final PASS missed evidence excluded from the narrow assignment;
  the original assertion remained in the task-results appendix.
  Implemented with 12 isolated unit tests in tests/test_checkpoint_loading_and_e1_regression.py
  covering all _load_state completeness and integrity guards (missing/partial completed_data,
  unusable results, uncompleted status, missing identity records, tampered hashes, invalid phase transitions).
  Engine-level run_mimir(phase="synthesize") fail-closed verification ensures 0 model calls are made
  on incomplete checkpoints. End-to-end repository review regression verifies overreaching claim softening
  and publication quarantine. Registered E1 failure packet as versioned regression case reg-v1-7f876b3ae389
  in .mimir/regressions.jsonl with family-disjoint split isolation.
  See [qualification](../docs/CHECKPOINT_LOADING_AND_E1_REGRESSION_2026-10-26.md).
- [x] **E5** Repeat the real-source evaluation after P1/P2, comparing support,
  omissions, clarification, calls and usage against the minimal checked baseline.
  Implemented with 7 targeted evaluation tests in tests/test_real_source_post_p1_p2_evaluation.py
  across Vincenzo's Plate and King Arthur real-source fixtures. Demonstrates 0.0% critical omission rate
  in the minimal baseline while reducing model calls by 75% and tokens by 72.5% (2 calls / 5,154 tokens
  vs 8 calls / 18,728 tokens). Validates deterministic association gate (P1.3), non-blocking assumption
  qualification (P2.1), isolated required-input blockers (P2.1), multi-source conflict preservation (P1.3),
  abbreviated locator audits (P1.6), and 0-token AST formula computation (P2.3).
  See [qualification](../docs/REAL_SOURCE_EVALUATION_POST_P1_P2_2026-10-26.md).
- [x] **E6** Qualify hybrid interruption/recovery and target tool-runtime readiness
  separately before making broader routing/recovery claims.
  Implemented with 8 targeted qualification tests in tests/test_hybrid_interruption_and_tool_runtime_qualification.py.
  Validates diagnostics decoupling direct text API readiness from deferred tool runtime preflight. Confirms
  HybridSwarmBackend routes direct text tasks with 0 tool initializations while lazily initializing native tools
  only on explicit tool-using calls. Rejects model drift fail-closed (ConfigurationRequired) and ensures missing
  credentials do not silently fall back to native tools. Qualifies interruption recovery: in-flight tasks reset to PENDING
  while retaining verified completed findings; partial outputs never admit; budget journals (.operations.jsonl) prevent
  deadline/attempt resets; and idempotent publication recovery verifies hashes and skips re-inference.
  See [qualification](../docs/HYBRID_RECOVERY_AND_TOOL_READINESS_2026-10-26.md).
Historical measurements are documentary evidence; some raw packets were removed.
The full assessment records limitations. Local original artifacts:
[report](../.mimir/runs/7eacc84b92a44c51b92bffa8a4e71cdd/report.md) and
[sidecar](../.mimir/runs/7eacc84b92a44c51b92bffa8a4e71cdd/report.json).
These local artifacts are not required to read this backlog or its durable assessment.
