# Mimir development handoff — 2026-10-25

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
- **P1.4:** Checked publication view, task-level quarantine and truthful diagnostic
  appendices. Original evidence remains immutable; quarantined claims are excluded
  from the released claim aggregate.
- **P1.5:** At most one assembly correction/recheck, with durable history and
  unchanged objective, evidence, model, effort and limits.
- **P2.4:** All new runs share a journaled budget across planning, workers, checks,
  retries and publication. Defaults: 64 adapter attempts and 1,800 elapsed seconds.
  Review/swarm reserve one synthesis and one final-check call. Interrupted calls
  remain charged, and resume retains the original deadline and reservations.

P1.2/P1.3/P1.6 are partial: explicit retrieve tasks have engine-generated source
IDs/timestamps, frozen exact spans, dependent lineage and deterministic citation
checks. Mixed ordinary tool-worker capture, downstream span completeness, broader
conflict/omission evaluation and unbound final-reference presentation remain open.
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

## What to do next

There are **16 open backlog items**, including partially implemented ones.
Recommended next increment is **P2.1**, followed by P2.2; neither has been started
as part of this handoff. The most recent request was to commit, push and hand off,
not to implement another backlog item.

For P2.1, distinguish missing information that truly prevents a decision from an
unspecified preference that still permits evidence gathering and a qualified
answer. Preserve the original request and label assumptions. Start with two
requests over the same frozen source: an unspecified “best” preference should
proceed; a genuinely missing target should block only its dependent decision.
Inspect `task_brief.py`, `recursive_planner.py`, `task_graph.py` and engine blocker
handling before editing. Add meaningful deterministic regressions, then repeat
fresh low-effort planning without changing model, budget or checker rules.
If API access is unavailable, record the missing live qualification rather than
claiming semantic improvement from fixtures alone.

After P2.1, P2.2 should keep simple work to one bounded retrieval/extraction plus
its check, splitting only for bounds or distinct decisions. The other remaining
families are P1 evidence-completeness gaps, P2 computation/routing and baseline
comparison, P3 governed failure-to-regression/prompt evaluation, and E4–E6
repository-regression, live evaluation and hybrid recovery qualification.

Suggested instruction for the next coding session:

> Read HANDOFF.md and tasks/todo.md. Check the checkout and home environment,
> then implement P2.1 only, preserving gpt-6.1-sol/low and existing evidence,
> checker and budget rules. Test the qualified-preference and genuine-blocker
> cases; keep assumptions distinct from user constraints. Update the TODO and
> qualification notes with actual results and remaining gaps.

Relevant durable qualification:
[material admission](docs/MATERIAL_FINDING_GATE_2026-10-23.md),
[capture](docs/DYNAMIC_SOURCE_CAPTURE_2026-10-23.md),
[source support](docs/BOUND_SOURCE_SUPPORT_2026-10-23.md),
[publication](docs/PUBLICATION_VIEW_2026-10-23.md),
[assembly repair](docs/ASSEMBLY_REPAIR_2026-10-23.md),
[run budgets](docs/RUN_BUDGET_2026-10-23.md), and
[implementation assessment](docs/SELF_HARDENING_ASSESSMENT_2026-10-23.md).
