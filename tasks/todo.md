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
- [ ] **P1.2** Generate source identity and capture metadata in the engine;
  freeze retrieve-worker evidence and bind exact needed spans to dependents.
  Explicit retrieve-task capture implemented: engine reread, generated ID/time,
  frozen exact excerpts, durable dependent lineage and publication/recovery checks.
  Ordinary mixed research/tool-output capture and downstream span completeness
  remain pending. See [scope and verification](../docs/DYNAMIC_SOURCE_CAPTURE_2026-10-23.md).
- [ ] **P1.3** Validate source/version/span identity deterministically; add narrow
  semantic checks for associations, omissions and conditions against the source.
  Preserve conflicting assertions rather than resolving them by majority agreement.
  Bound citation ID/type/time/locator/quote checks now run before semantic admission
  and during recovery. Real-code blinded checks caught wrong associations, conditions
  and required omissions. Broader conflict/omission evaluation remains pending.
  See [qualification](../docs/BOUND_SOURCE_SUPPORT_2026-10-23.md).
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
- [ ] **P1.6** Separate structural provenance defects from model support labels;
  avoid treating abbreviated-locator string mismatches as citation entailment failures.
  Bound structural defects have their own check type; exact source-ID abbreviations
  resolve without literal full-path comparison. Unbound final-reference audit and
  broader presentation cleanup remain pending.

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

- [ ] **P2.1** Distinguish genuine required-input blockers from ambiguity that
  permits evidence gathering and a qualified answer; retain the original request
  and label assumptions without inventing user constraints.
- [ ] **P2.2** Start with one bounded retrieval/extraction; split for input/output
  bounds or distinct decisions, permitting short contiguous procedures.
- [ ] **P2.3** Use deterministic computation for explicit supported formulas;
  route text/tool work using an explicit tool need rather than a broad role name.
- [x] **P2.4** Enforce one persisted attempt/deadline budget across planning,
  execution, checks, repairs and assembly, with reserved publication calls and
  durable attempt journaling for ordinary runs. Count interruptions and retries.
  [Budget/recovery contract and validation](../docs/RUN_BUDGET_2026-10-23.md).
- [ ] **P2.5** Compare the minimal checked baseline with recursive plans on a
  frozen real-source case set; retain failures, omissions and known/unknown usage.

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

- [ ] **P3.1** Capture and deduplicate failure packets with original intent,
  source snapshots/spans, attempts, feedback and independently adjudicated defects.
- [ ] **P3.2** Convert confirmed failures into versioned regressions; separate
  train/dev and fresh held-out families by source/topic and failure lineage.
- [ ] **P3.3** Compare baseline with one manually edited prompt first, fixing
  model, effort, tools, budgets, checker rules and intent contracts.
- [ ] **P3.4** Score unsupported material claims, omissions, unnecessary blockers,
  conflict retention and usage; predeclare adoption thresholds and independently
  review source support before explicit manifest selection.
- [ ] **P3.5** Test rejected/unchanged candidates, activation history and rollback;
  prevent held-out-answer leakage or promotion of unvalidated notes into guidance.
- [ ] **P3.6** Use GEPA only after it demonstrates benefit over manual edits;
  keep RLM and JEV optional until their target workloads show a useful gain.

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
- [ ] **E4** Preserve E1 as a regression: the critic softened an overreaching
  claim, but final PASS missed evidence excluded from the narrow assignment;
  the original assertion remained in the task-results appendix.
  Wrong-field association and corrected-summary/stale-appendix regressions now
  cover release and publication. E1's omitted checkpoint guard still needs its
  exact durable regression; this item remains open.
- [ ] **E5** Repeat the real-source evaluation after P1/P2, comparing support,
  omissions, clarification, calls and usage against the minimal checked baseline.
- [ ] **E6** Qualify hybrid interruption/recovery and target tool-runtime readiness
  separately before making broader routing/recovery claims.

Historical measurements are documentary evidence; some raw packets were removed.
The full assessment records limitations. Local original artifacts:
[report](../.mimir/runs/7eacc84b92a44c51b92bffa8a4e71cdd/report.md) and
[sidecar](../.mimir/runs/7eacc84b92a44c51b92bffa8a4e71cdd/report.json).
These local artifacts are not required to read this backlog or its durable assessment.
