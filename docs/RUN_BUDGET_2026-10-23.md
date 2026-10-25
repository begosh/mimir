# Durable whole-run budgets

All new native, DSPy and RLM runs use the same invocation broker budget. Defaults
are 64 model-call attempts and 1,800 elapsed seconds. `--research-budget` overrides
validated fields before the run starts; limits are fixed for resume. The recursive
planner's local limits remain additional caps inside this global allowance.

Planning, JEV checks, workers, admission checks, task repairs, nested research,
critique, synthesis, assembly correction and final checks share that allowance.
An attempt means a broker dispatch to the native adapter; provider-internal tool
turns are not separately counted as broker attempts. Adapter token reports can
include those turns. Missing token usage remains unknown.

Review/swarm reserve one initial synthesis call and one initial final-check call.
Each reserved role can consume only its own slot. Critique, additional research
and repairs cannot spend an outstanding publication slot. Single uses its worker
admission check for publication and reserves no extra synthesis calls. Optional
assembly correction/recheck still need remaining attempts; reservation does not
guarantee publication or authorize extra calls.

The sibling `.operations.jsonl` journal records the original budget, start time
and reservation policy. Each attempt is flushed and fsynced before dispatch;
success, failure and interruption are recorded afterward. Recovery merges the
journal with checkpoint calls, charges unfinished attempts as interrupted, and
derives remaining publication slots from already admitted calls. A torn final
record retains the valid prefix and its earlier admission record. Corrupt middle
records, missing original journals, changed limits and conflicting headers block
resume. Fresh planning cannot overwrite an existing budget journal: use the
checkpoint for resume or a new run path. Legacy budgetless checkpoints require
a new run.

The elapsed deadline includes time between phases and while the process is down.
Calls admitted before it receive only the remaining elapsed time; no later paid
call is admitted. Deterministic recovery of already checked publication artifacts
does not need another model call. This is an inference admission/deadline limit,
not a hard process-runtime limit on local file writes or cleanup.

`max_reported_tokens` is a threshold checked before dispatch against known reported
usage. One large turn or concurrent in-flight calls can overshoot it; unknown
usage cannot establish a hard token ceiling. Attempt and elapsed limits continue
to apply. Reports expose limits, deadline, attempts used, remaining publication
slots, known reported tokens and unknown-usage call count in `budget_status`.

Validation covers interrupted reserved calls, journal recovery, expired deadlines,
fixed limits, protected publication slots, reported-token overshoot, phased review
publication and an exhausted ordinary single run that cannot repeat paid work.

The final full suite passed in the research environment: 387 passed, 1 skipped
and 111 subtests passed (176.73 seconds). The focused budget, engine and checkpoint
regression set passed all 48 tests. Documentation links and scoped whitespace
checks passed. These tests use controlled adapters; no new paid-provider benchmark
is needed to establish the deterministic budget and recovery contract.
