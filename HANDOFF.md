# Mimir development handoff — 2026-10-26

Start here on the home computer. The canonical backlog is [tasks/todo.md](tasks/todo.md);
completed historical work is in [tasks/history.md](tasks/history.md).
The code and durable qualification documents travel through Git. Local credentials,
virtual environments, installed skills, MCP launch configuration and raw `.mimir/`
run packets do not.

## Current implementation

This batch continues the direct-text API baseline with ordinary worker admission,
engine-owned retrieval capture, checked publication and durable run budgets. It
also includes the pending workspace cleanup: Mycroft, presentation code and the
old UX strategy were removed; curated project guidance remains in `LEARNINGS.md`.

Completed backlog items:

- **P1.1:** Common material-finding admission and bounded task repairs. Single
  uses one worker and one check, then publishes without another synthesis call.
- **P1.2:** Engine-owned source capture for mixed research workers and downstream span completeness (`scripts/retrieved_evidence.py`, `scripts/scheduler.py`).
  Engine rereads workspace files and approved HTTPS URLs cited by any worker (`operation in ("retrieve", "research", "extract")` or `required_evidence`),
  computes content SHA256 hashes, assigns canonical `capture_<sha256>` IDs, extracts exact character-offset spans, verifies non-ambiguity,
  rebinds claim links, and caches captures across concurrent workers via `SourceStore._RUN_CAPTURES` to prevent timestamp version conflicts.
  Enforces downstream span completeness (`validate_downstream_span_completeness`) verifying that all dependency claims have active frozen spans
  and all contract inputs are bound before dependent release.
  See [qualification](docs/DYNAMIC_SOURCE_CAPTURE_2026-10-26.md).
- **P1.3:** Bound semantic support, association integrity and conflict preservation (`scripts/source_support.py`, `scripts/scheduler.py`, `scripts/post_worker.py`).
  Deterministic separation: structural provenance checks (`check_bound_citations`) return REVIEW without claiming entailment.
  Narrow deterministic checks (`check_association_integrity`) detect inverted field-value pairings where both numbers exist in the source span,
  and reject unconditional claims contrary to stated scoping conditions.
  Conflict integrity checks (`check_conflict_preservation`, `detect_conflicts`) strictly reject resolving incompatible assertions through majority agreement.
  Smallest meaningful test verified on real task_graph word-limit spans across single and review modes, blocking dependent release upon corrupted association,
  enabling release upon checked repair, and preserving truthful appendix status in publication view.
  See [qualification](docs/SEMANTIC_AND_CONFLICT_INTEGRITY_2026-10-26.md).
- **P1.4:** Checked publication view, task-level quarantine and truthful diagnostic
  appendices. Original evidence remains immutable; quarantined claims are excluded
  from the released claim aggregate.
- **P1.5:** At most one assembly correction/recheck, with durable history and
  unchanged objective, evidence, model, effort and limits.
- **P1.6:** Provenance and presentation separation (`scripts/research_contract.py`, `scripts/extraction_checks.py`, `scripts/engine.py`).
  Structural provenance defects across citation checks, extraction checks, and reference audits consistently assign `check_type="structural_provenance"`.
  Exact source-ID abbreviations, unscoped IDs, and locator basenames resolve in `audit_final_references` without requiring literal full-path string equality.
  Invented or unbound citations in synthesis text are audited and collected under `unbound_references`, cleanly downgrading coverage to `partial`
  and reporting explicit issues in Markdown and JSON payload outputs.
  See [qualification](docs/PROVENANCE_AND_PRESENTATION_2026-10-26.md).
- **P2.1:** Distinction between genuine required-input blockers and unspecified preferences.
  Assumptions permitted in task brief schema, prompt hardening across planner and reviews,
  genuine blockers isolated to dependent decisions via TaskStatus.BLOCKED, upstream evidence
  gathering retained upon block, and contiguous procedures kept unsplit.
  See [qualification](docs/BLOCKER_QUALIFICATION_2026-10-25.md).
- **P2.2:** Proportional decomposition and bounded extraction baseline. Starts with one bounded
  retrieval/extraction leaf (<= 16k chars input, <= 150 words output); splits only for input/output
  bounds or distinct decisions (such as calculations, comparisons or independent multi-stage processes).
  Accepts short contiguous procedures (e.g. mixing/kneading). Simple supplied-source work auto-routes
  to mode="single" with 1 worker and 1 check without recursive planning calls.
  See [qualification](docs/BOUNDED_EXTRACTION_2026-10-25.md).
- **P2.3:** Deterministic computation for explicit supported formulas (hydration, baker's
  percentage, batch scaling, total dough weight, safe AST math) with 0 tokens and model calls;
  missing operands reported in gaps; result gate contradiction checks rejecting math errors.
  Tool need routing (`needs_tools=False`) directs review critique and atomic text tasks to
  `spawn_restricted` (direct text API Responses) rather than native tools.
  See [qualification](docs/FORMULA_AND_TOOL_ROUTING_2026-10-25.md).
- **P2.4:** All new runs share a journaled budget across planning, workers, checks,
  retries and publication. Defaults: 64 adapter attempts and 1,800 elapsed seconds.
  Review/swarm reserve one synthesis and one final-check call. Interrupted calls
  remain charged, and resume retains the original deadline and reservations.
- **P2.5:** Minimal checked baseline vs. recursive plan comparison on frozen real sources
  (Vincenzo's Plate and King Arthur). Single worker + check uses ~70% fewer tokens and calls,
  0 planning calls, and produces 0 critical omissions. Unspecified 'best' preference proceeds
  with qualification; missing inputs isolate blocking to dependent decisions while retaining
  upstream evidence; contiguous procedures remain unsplit; budgets fail closed on exhaustion.
  See [qualification](docs/BASELINE_COMPARISON_2026-10-25.md).
- **P3.1:** Content-addressable, process-safe failure packet capture and deduplication
  in `.mimir/failure-packets.jsonl`. SHA256 semantic core deduplication increments occurrences
  and tracks run history. Standardizes defect taxonomy via `classify_defect_from_feedback`,
  supports independent supervisor defect adjudication, and automatically ingests failures
  upon engine execution halts (failed and blocked nodes) and synthesis quarantine.
  See [qualification](docs/FAILURE_PACKET_INGESTION_2026-10-25.md).
- **P3.2:** Versioned regression suite and failure-to-regression loop (`scripts/regression_suite.py`).
  Converts confirmed/triaged failures into versioned `RegressionCase` records with preserved lineage.
  Enforces family-disjoint partitioning (`partition_splits`) across `train`, `dev`, and `held_out`
  by topic and source family. Strict isolation validator (`validate_split_isolation`) detects and
  blocks any cross-split data leakage. Exports benchmark datasets directly compatible with `evaluate.py`.
  See [qualification](docs/VERSIONED_REGRESSION_SUITE_2026-10-25.md).
- **P3.3:** Controlled manual prompt comparison against baseline (`scripts/prompt_comparison.py`).
  Locks model (`gpt-6.1-sol`), effort (`low`), tools, budgets, and checker immutability.
  Detects and rejects checker tampering, disk checksum alterations, held-out answer/locator
  leakage (`DataLeakageError`), and invented user constraints (`REJECTED_INVENTED_CONSTRAINT`).
  Executes side-by-side evaluations across versioned train and held-out regression splits.
  See [qualification](docs/MANUAL_PROMPT_COMPARISON_2026-10-25.md).
- **P3.4:** Multi-dimensional scoring, independent source review, and adoption thresholds (`scripts/candidate_scoring.py`).
  Scores unsupported material claims, omissions, unnecessary blockers, conflict retention, and usage.
  Autonomous `IndependentSourceReviewer` checks numbers, percentages, and pinned versions against bound source texts
  (never trusting model self-reported PASS). Enforces predeclared adoption thresholds (zero tolerance for held-out
  hallucinations or omissions, 100% conflict retention, >=1 train defect repair, <=1.15x usage ratio) and creates
  cryptographic `SelectionRecord` artifacts prior to manifest selection.
  See [qualification](docs/MULTI_DIMENSIONAL_SCORING_2026-10-25.md).
- **P3.5:** Manifest activation history, rollback governance, leakage prevention, and guidance guards (`scripts/manifest_activation.py`).
  Guarantees rejected and unchanged candidates leave runtime files 100% bit-for-bit unchanged.
  Records cryptographic lineage pointers (`prior_hash`, `candidate_hash`, pre/post snapshots) in `.mimir/manifest-activations.jsonl`.
  Supplies atomic, verified rollback restoring exact parent baseline state.
  Strictly audits candidate text and metadata against held-out regression splits (`DataLeakageError`).
  Prevents unvalidated candidate notes (`requires_independent_validation`) from polluting standing guidance (`LEARNINGS.md`).
  See [qualification](docs/MANIFEST_ACTIVATION_2026-10-26.md).
- **P3.6:** GEPA evaluation against manual edits, leakage gating, and subsystem optionality (`scripts/gepa_evaluation.py`).
  Requires GEPA to demonstrate strictly superior defect reduction over manual prompt edits without held-out regressions or token bloat.
  Disqualifies any candidate containing held-out answers or locators (`DISQUALIFIED_DATA_LEAKAGE`).
  Enforces workload optionality: CLI defaults to `--jev None` and research program defaults to `'native'` engine mode,
  keeping RLM and JEV swarms strictly optional until workloads prove benefit.
  See [qualification](docs/GEPA_EVALUATION_2026-10-26.md).

All Priority 1, 2, and 3 backlog items are 100% complete. Remaining backlog items are the evaluation benchmarks (E4, E5, E6).
Model PASS is not independent factual verification.

Useful implementation entry points:

| Concern | Files |
| --- | --- |
| Run lifecycle and reporting | `scripts/engine.py`, `scripts/cli.py` |
| Admission, batching and task repair | `scripts/scheduler.py`, `scripts/post_worker.py`, `scripts/result_batcher.py` |
| Source capture and support | `scripts/retrieved_evidence.py`, `scripts/source_store.py`, `scripts/source_support.py` |
| Publication and assembly repair | `scripts/publication_view.py`, `scripts/assembly_gate.py` |
| Budget and recovery | `scripts/invocation_broker.py`, `scripts/research_program.py` |
| Interpretation and planning | `scripts/task_brief.py`, `scripts/task_graph.py`, `scripts/recursive_planner.py` |

## Get the checkout and Python environment

For a new Windows checkout, use the normal GitHub URL rather than the work
computer's machine-specific SSH alias. GitHub authentication is configured locally.
Python 3.14.2 on Windows was the qualified environment; install Python 3.14 first
if `py -3.14` is unavailable.

```powershell
git clone https://github.com/begosh/mimir.git
Set-Location mimir
git switch main
py -3.14 -m venv .venv-research
.\.venv-research\Scripts\python.exe -m pip install -r requirements-research.txt pytest pytest-subtests
.\.venv-research\Scripts\python.exe -m pytest -q
```

For an existing checkout, inspect `git status` and preserve any home changes,
then use `git switch main` and `git pull --ff-only`. Recreate the environment
locally; virtual environments should not be copied between computers.
The research requirements include the ordinary worker/MCP dependencies as well
as pinned DSPy, GEPA and Deno dependencies. Plain system Python previously failed
test collection because it lacked `mcp`; use the environment's explicit interpreter.

To install project skill discovery for Codex after the dependencies are installed:

```powershell
.\.venv-research\Scripts\python.exe scripts/install.py --skip-pip --project . --target codex
.\.venv-research\Scripts\python.exe scripts/mimir.py --diagnostics --backend codex --model gpt-6.1-sol --effort low
```

Configure API access and tool-runtime authentication separately on the home
computer. The hybrid default uses direct Responses calls for text work and a
native runtime when tools are required. Codex login alone does not supply API
access. Configure the appropriate `OPENAI_API_KEY` or `AZURE_OPENAI_API_KEY` and
endpoint locally; use the configured API model/deployment ID. Keep the agreed
**gpt-6.1-sol / low** profile; do not silently substitute a model or effort.
Full local MCP registration and transport details are in
[docs/INTEGRATION.md](docs/INTEGRATION.md). Use the home interpreter/workspace
absolute paths and reconnect the host after registration; the installer does not
register MCP automatically. Diagnostics are not a fresh live-provider qualification.

## Validation and recovery limits

Last full code verification, **2026-10-23**, in `.venv-research`:
**387 passed, 1 skipped, 111 subtests passed**, in 176.73 seconds.
The focused budget/engine/checkpoint set passed all 48 tests.
These are historical results; run the suite locally to establish the home baseline.
Provider access, tool-runtime readiness and hybrid crash recovery need separate
qualification. No new live benchmark was run for this handoff.

Use a new run/checkpoint path for new work. Legacy budgetless checkpoints cannot
resume, and an existing budget journal cannot be overwritten by fresh planning.
Missing journals or changed runtime/source/budget policy fail closed. The elapsed
deadline includes downtime between phases. Work-machine packets also contain
absolute source paths, so starting a new home run is the reliable approach.
Raw historical packets are not shipped; durable documents record the evidence
and its limits. A reported-token threshold can overshoot in-flight work and cannot
establish a hard ceiling when usage is unknown.

## Current status

All backlog priorities from the 2026-10-23 self-hardening assessment are **100% complete and qualified**:
- **Priority 1 (P1.1–P1.6)**: Evidence capture, material-finding admission, deterministic association/conflict checks, checked publication view, assembly repairs, and presentation separation.
- **Priority 2 (P2.1–P2.5)**: Blocker qualification, proportional decomposition, 0-token deterministic formula computation, tool need routing, journaled budgets, and minimal checked baseline comparison.
- **Priority 3 (P3.1–P3.6)**: Content-addressable failure packet ingestion, versioned regression suite, controlled manual prompt comparisons, multi-dimensional scoring, manifest activation history/rollback, and leakage-governed GEPA evaluation.
- **Evaluations & Regressions (E1–E6)**: Real-repository review (E1), checkpoint-loading guard resolution (E2), focused verification (E3), durable E1 repository review regression (E4), post-P1/P2 real-source evaluation (E5), and hybrid interruption/recovery with decoupled tool-runtime readiness (E6).

Relevant durable qualification documents:
- [Material Admission Gate (P1.1)](docs/MATERIAL_FINDING_GATE_2026-10-23.md)
- [Dynamic Source Capture (P1.2)](docs/DYNAMIC_SOURCE_CAPTURE_2026-10-26.md)
- [Semantic & Conflict Integrity (P1.3)](docs/SEMANTIC_AND_CONFLICT_INTEGRITY_2026-10-26.md)
- [Publication View & Quarantine (P1.4)](docs/PUBLICATION_VIEW_2026-10-23.md)
- [Targeted Assembly Repair (P1.5)](docs/ASSEMBLY_REPAIR_2026-10-23.md)
- [Provenance & Presentation Separation (P1.6)](docs/PROVENANCE_AND_PRESENTATION_2026-10-26.md)
- [Blocker Qualification (P2.1)](docs/BLOCKER_QUALIFICATION_2026-10-25.md)
- [Bounded Extraction (P2.2)](docs/BOUNDED_EXTRACTION_2026-10-25.md)
- [Formula Engine & Tool Routing (P2.3)](docs/FORMULA_AND_TOOL_ROUTING_2026-10-25.md)
- [Run Budget & Journaling (P2.4)](docs/RUN_BUDGET_2026-10-23.md)
- [Baseline Comparison on Real Sources (P2.5)](docs/BASELINE_COMPARISON_2026-10-25.md)
- [Failure Packet Ingestion (P3.1)](docs/FAILURE_PACKET_INGESTION_2026-10-25.md)
- [Versioned Regression Suite (P3.2)](docs/VERSIONED_REGRESSION_SUITE_2026-10-25.md)
- [Manual Prompt Comparison (P3.3)](docs/MANUAL_PROMPT_COMPARISON_2026-10-25.md)
- [Multi-Dimensional Scoring (P3.4)](docs/MULTI_DIMENSIONAL_SCORING_2026-10-25.md)
- [Manifest Activation & Rollback (P3.5)](docs/MANIFEST_ACTIVATION_2026-10-26.md)
- [GEPA Evaluation & Optionality (P3.6)](docs/GEPA_EVALUATION_2026-10-26.md)
- [Checkpoint Loading & E1 Regression (E4)](docs/CHECKPOINT_LOADING_AND_E1_REGRESSION_2026-10-26.md)
- [Post-P1/P2 Real-Source Evaluation (E5)](docs/REAL_SOURCE_EVALUATION_POST_P1_P2_2026-10-26.md)
- [Hybrid Recovery & Tool Readiness (E6)](docs/HYBRID_RECOVERY_AND_TOOL_READINESS_2026-10-26.md)
- [Original Assessment](docs/SELF_HARDENING_ASSESSMENT_2026-10-23.md)
