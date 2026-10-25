# Mimir workspace cleanup

Active priorities: [repository improvement backlog](todo.md). The dated entries
below retain historical progress; later sections can supersede earlier pending items.

- [x] Inventory tracked code, local setup, completed runs and generated leftovers.
- [x] Remove the discontinued Mycroft/presentation experiments and stale generated files.
- [x] Keep Mimir source, regression tests, design/setup docs, environments and local settings.
- [x] Update package documentation, ignore rules and legacy guidance to match the retained scope.
- [x] Verify the remaining package and check the final repository changes.

Scope: cleanup is local; retain .git, both virtual environments, MCP/Serena setup
and Mimir implementation/qualification documentation. No active saved runs found.
Review: 238 tests and 112 subtests passed; 9 explicit skips. Presentation-only
tests were removed with their utility. Cleanup did not recreate test caches.
Recursive deletion was blocked by automatic approval review; cleared files are
in the temporary recovery archive outside the repository. Local setup preserved.

Follow-up: two CLI backend tests wrote the default checkpoint into artifacts/.
Both now use their own temporary state paths. 37 affected tests passed; final
checks confirm no generated folders, unexpected source deletions or broken doc
links, and all local setup files remain present. Cleanup changes are uncommitted.

## Self-hardening design follow-up

Agreed direction and current gaps: [Self-hardening design](../docs/SELF_HARDENING_DESIGN.md).

- [x] Remove unconditional search before task interpretation.
- [x] Add compact host task briefs and interpretation output to swarm planning.
- [x] Diagnose search failures with native/curl probes and recommend an MCP.
- [ ] Make interpretation a reviewable input to decomposition, preserving intent and ambiguity.
- [ ] Enforce stupid-easy task contracts and recursively split difficult tasks within global limits.
  Initial opt-in recursive planner and contract admission implemented; semantic
  simplicity review now implemented; selective dependency inputs remain pending. See
  [pizza planning test](../docs/RECURSIVE_PIZZA_2026-10-22.md).
  Revised general prompt with separate domain context tested at low/medium/high:
  [effort comparison](../docs/PIZZA_PROMPT_EFFORT_COMPARISON_2026-10-22.md).
  Low produced five leaves in 26.6s; high six in 104.9s. Whole-method atomicity
  and source-page handoff remain unresolved; retain low as ordinary worker effort.
- [ ] Turn broad red-team review into narrow evidence-backed checks; use code for deterministic checks.
- [ ] Add bounded rephrasing/retries and rechecking; proposed two retries per task, fixed low effort.
  Standalone repair/review prompts tested on the pizza method task: a second
  repair covered a missed handling stage; reviewer accepted four children.
  [Repair experiment](../docs/PIZZA_TASK_REPAIR_2026-10-22.md). Planning integration
  now complete: batched review, two bounded repairs, scope re-review, inherited
  prerequisites and downstream rewiring under the existing global planning budget.
  [Integrated gate](../docs/PLANNING_REPAIR_INTEGRATION_2026-10-22.md).
  Execution-result correction/retries remain pending.
- [ ] Track failed/corrected result versions and invalidate affected dependents while retaining valid work.
- [ ] Check the assembled final answer against accepted results and the original request.
  Three accepted pizza extraction workers passed a fixed synthetic-source test;
  a batched result checker rejected an invented temperature and an omitted step.
  [Execution probe](../docs/PIZZA_EXECUTION_PROBE_2026-10-23.md). Enforcing this
  result gate before downstream admission and verifying retrieved-page handoff
  remain pending.
  Operation wrappers implemented and tested with blinded checker candidates:
  two actual extractions passed, shaping omitted required missing details and
  failed, and both injected errors failed. Worker prompts shrank about 46%; native
  context still dominates token usage. See
  [wrapper comparison](../docs/ATOMIC_WRAPPER_BLINDED_2026-10-23.md).
- [ ] Investigate stream disconnections in the earlier combined planning schema;
  separate interpretation/recursive planning passed live with a small JSON envelope.
- [ ] Integrate a verified search MCP where retrieval is needed; Firecrawl probe works, integration pending.

Potential experiments, not committed design: reusable worker sessions and selective
live blackboard tools. Measure their benefit before expanding runtime complexity.

## Post-worker prompt audit — 2026-10-23

- [x] Audit byte identity across saved worker packets and correct verdict comparison.
- [x] Clarify checking answer plus gaps; retain blinded controls and shuffled five-run checks.
- [x] Replace routine GEPA reflection framing with dedicated synthesis prompt.
- [x] Pass scope, component coverage and merged qualified sources to synthesis.
- [x] Return direct structured objects from checker and recursive planner; live nested task schema passed.
- [ ] Enforce result gate and bounded execution repair before downstream admission.
- [ ] Final assembled-answer check; repeat synthesis evaluation before claiming reliability.

See [identity audit, repeated checks and exact prompts](../docs/POST_WORKER_REPEATED_2026-10-23.md).

## Execution gate — 2026-10-23

- [x] Check engine atomic results before blackboard/dependent admission.
- [x] Preserve rejected output; fail closed on checker errors; bind successful checks to recovery identity.
- [x] Pass accepted checks through to synthesis coverage.
- [x] Live correct/corrupted fixture gate test: only accepted parent and dependent committed.
- [ ] Bounded failed-result rephrasing/retries and final-answer check.

[Exact gate prompts and evidence](../docs/RESULT_GATE_2026-10-23.md).

## Bounded result repair — 2026-10-23

- [x] Valid failed checks trigger at most two objective rephrasing/rerun/check cycles.
- [x] Preserve original contract, model, effort, budget, prerequisites and rejected versions.
- [x] Persist retry reservations and attempt history; keep downstream blocked until PASS.
- [x] Test recovery, exhaustion and checker errors; live synthetic-fixture recovery used one retry.
- [ ] Final assembled-answer check; retrieved-source handoff and repeated repair reliability.

[Exact live repair prompts and history](../docs/RESULT_REPAIR_2026-10-23.md).

## Final assembly gate — 2026-10-23

- [x] Review/swarm assembled answer plus limitations must pass before report/sidecar/learning publication.
- [x] Preserve failed assembly/verdict diagnostics and successful check identity.
- [x] Live qualified fixture PASS; invented authenticity/temperature FAIL.
- [ ] Final-answer correction loop, full retrieved-page handoff and repeated end-to-end validation.

[Exact prompts and final gate limits](../docs/FINAL_ANSWER_GATE_2026-10-23.md).

## Full fixture pipeline — 2026-10-23

- [x] Live phased interpretation/recursive planning/repair/workers/checks/synthesis/final-check publication passed.
- [x] Correct native planning schema: required nullable planning_error; failures preserved.
- [ ] Automatic source binding and verified retrieved-page handoff; selective source excerpts.
- [ ] Reduce native context/call overhead with measured batching; repeated end-to-end evaluation.

[Full prompts, output and failed attempts](../docs/PIZZA_END_TO_END_2026-10-23.md).

## Captured-source handoff — 2026-10-23

- [x] Manifest capture supplies bounded evidence during recursive planning.
- [x] Engine binds exact named IDs to atomic workers without checkpoint edits.
- [x] Preserve explicit source qualification and frozen provenance; validate conflicts/limits/resume.
- [x] Live local fixture manifest pipeline final PASS: 20 calls, 309897 tokens, 103s.
- [ ] Dynamic retrieve-worker page handoff, selective excerpts and reduced runtime overhead.

[Handoff evidence and limitations](../docs/SOURCE_HANDOFF_2026-10-23.md).

## Batched result checks — 2026-10-23

- [x] Coalesce completed atomic results within concurrency/max-four and two-second flush limits.
- [x] Individual verdicts, fail-closed malformed batches, joined cancellation and existing repair.
- [x] Same six live fixture results: six to three checker calls; 89284 to 46970 tokens.
- [ ] Repeat checker comparison with blinded negatives and real worker timing; measure full pipeline.

[Exact batch prompts and usage](../docs/RESULT_BATCHING_2026-10-23.md).

## Fresh-worker batching measurement — 2026-10-23

- [x] Fixed six-task plan; six fresh workers and batch checks plus synthesis/final check passed.
- [x] Post-planning calls 14 to 11; tokens 215310 to 173504 (19.4% fewer).
- [ ] Reduce planning/context overhead; repeat randomized comparison before latency claims.

[Exact fresh prompts and fair stage comparison](../docs/LIVE_WORKER_BATCHING_2026-10-23.md).
