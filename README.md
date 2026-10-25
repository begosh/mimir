# Mímir — evidence-led research and review

[Measured performance investigation](docs/PERFORMANCE_2026-10-22.md) explains
the recent 24.6-minute high-effort run, cumulative token usage and synthesis fixes.

> **WORK IN PROGRESS — VERY BETA.** Mímir is experimental software under active
> development. Use it for supervised, bounded investigations and inspect the
> underlying evidence. APIs, checkpoints, instructions and dependencies may
> change. Production readiness, universal harness support, independent factual
> validation and general quality or performance improvements are not established.

Mímir helps your coding assistant investigate difficult questions, compare
designs and challenge consequential assumptions. A shared Python engine runs
bounded workers, retains source/claim/gap records and publishes recoverable
reports. Model findings remain evidence for review, not independently verified facts.

Text-only planning, extraction, checking and synthesis now use direct API calls
by default. Codex, AGY, Claude and OpenCode serve as tool runtimes, initialized
only when needed. Use `--backend responses` for direct-only work. Configure Azure
OpenAI or OpenAI API credentials and an explicit API model/deployment ID; CLI
login alone does not supply API access. The tested profile is gpt-6.1-sol at low
effort. [Measured comparison](docs/TEXT_TRANSPORT_COMPARISON_2026-10-23.md).
Read the [execution conclusions](docs/EXECUTION_CONCLUSIONS_2026-10-23.md) for
the measured gains, default routing, OpenCode results and remaining work.

Choose the smallest useful workflow:

| Mode | Model calls without retries/pruning | Use |
| --- | --- | --- |
| single | One research worker and one admission check | Focused questions and baseline comparisons |
| review (default) | Two specialists, a dependent critic, admission checks, one synthesis and final check | Architecture reviews and consequential proposals |
| swarm | One bounded planner, up to max-tasks workers, admission checks, one synthesis and final check | Broader objectives benefiting from custom decomposition |

Task count is independent of concurrency. Default task cap is four; JEV pruning
is optional and off. There is no executive worker before final synthesis.
Admission checks may batch up to four ready results. Single publishes its checked
answer and gaps without synthesis or a duplicate final model call. Review/swarm
final checks also cover the task-results appendix; corrected summary text cannot
excuse an unqualified conflicting appendix assertion. These are model checks,
not independent factual verification.
Explicit retrieve tasks now trigger an engine reread and frozen exact-span
handoff before admission. [Capture scope](docs/DYNAMIC_SOURCE_CAPTURE_2026-10-23.md)
describes domain/workspace limits and the remaining mixed-worker capture gap.
Bound citations now pass deterministic identity/excerpt checks before model support
checking. [Qualification](docs/BOUND_SOURCE_SUPPORT_2026-10-23.md) distinguishes
structural defects, supported locator forms and the remaining semantic gaps.
Review/swarm final FAIL permits [one targeted assembly correction](docs/ASSEMBLY_REPAIR_2026-10-23.md)
and recheck under unchanged evidence and limits. Rejected versions remain recorded.
The [publication view](docs/PUBLICATION_VIEW_2026-10-23.md) can quarantine a disputed
task with a checked reason while preserving original diagnostic records and gaps.
Every new run shares a durable budget across planning, workers, checks, retries
and publication: 64 model-call attempts and 1,800 elapsed seconds by default.
Review/swarm reserve one synthesis and one final-check call. Resume retains the
original deadline and consumed attempts; a reported-token threshold can overshoot
in-flight work. [Budget and recovery details](docs/RUN_BUDGET_2026-10-23.md).

Investigator implementation is a separate choice: `native`, typed DSPy, or
DSPy RLM with Deno/Pyodide evidence execution and bounded nested RLM calls.
Optional upstream GEPA training produces instruction candidates for explicit
review and activation. [DSPy/RLM setup and use](docs/DSPY_RLM.md) describes the
qualified Codex route, source manifests, budgets and current limits.

## What has changed

This development update replaces the older CLI-first swarm entrypoint with a
shared engine and phased MCP control, dependency-ready scheduling, recoverable
task/publication artifacts and explicit source/claim/gap records. Native worker
adapters preserve the selected provider and credentials; optional captured-corpus
DSPy/RLM investigators and separate upstream GEPA instruction training add bounded
research paths. Learning candidates require review rather than automatic promotion.

[Development notes](docs/DEVELOPMENT_STATUS.md) describe the implementation,
validation, compatibility changes and open limitations in detail.
The [improvement backlog](tasks/todo.md) tracks current priorities and acceptance criteria.
For another computer or coding session, start with the [development handoff](HANDOFF.md).

## Install and connect

Use Python 3.10+ and one explicit interpreter:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-workers.txt
.\.venv\Scripts\python.exe scripts/install.py --skip-pip
.\.venv\Scripts\python.exe scripts/mimir.py --diagnostics --backend codex --model gpt-6.1-sol --effort low
.\.venv\Scripts\python.exe scripts/mimir.py --doctor
```

The installer preserves existing notes and backups and links harness skill
discovery to one package. Installing the skill does not register MCP or copy its
virtual environment. Configure the interpreter, workspace and durable run root
using [integration instructions](docs/INTEGRATION.md). Existing project configs
are local machine files. Reconnect the host after changing server code/tools.

The installer installs native worker dependencies by default; --base-only is for
explicit legacy/HTTP use. npx skills add begosh/mimir --skill mimir installs skill
resources; the same Python dependencies and host MCP registration remain necessary.

## Use

Ask your assistant to use Mímir. Reuse an agreed backend/model/effort; otherwise
consult once. The connected MCP exposes start_run, get_status, cancel_run,
get_result and get_diagnostics. Plan, execute and synthesize share the same run
ID. Final success follows cleanup; ready events describe saved checkpoints.
Status supplies Mímir's concise narration and waits for meaningful changes by
default. The assistant relays source gathering, specialist returns, critique and
synthesis in chat; raw events are available as opt-in diagnostics.

[SKILL.md](SKILL.md) contains concise host instructions.
[Terminal execution](docs/TERMINAL_EXECUTION.md) covers hosts without MCP.
[Runtime research](docs/IMPLEMENTATION_RESEARCH_2026-10-22.md) records primary-source contracts.

Native worker defaults use Codex/Claude SDKs, an owned OpenCode HTTP server, or
authenticated AGY CLI. Native configuration selects credentials and provider;
host tools are not automatically available to workers. An explicit
--worker-transport cli selects legacy adapters, with no automatic fallback.
Old checkpoints retain their transport unless explicitly overridden.

## Evidence, recovery and learning

Worker results retain readable answers, source locators, retrieval times/types,
supporting excerpts, linked claims and gaps. Reports distinguish record coverage
from factual validation; search snippets and abstracts are discovery material.
Hashes and citation-string presence establish neither truth nor entailment.

Successful task artifacts are checkpointed before dependent admission.
Dependency-ready scheduling avoids tier barriers. Retries validate prompts,
profiles, dependencies and raw/parsed output identities before reusing completed
work. Changed inputs require a new plan. Publication recovery validates existing
artifacts and avoids repeated model/learning calls; it does not certify historical
descendant cleanup from an earlier failed process.

Memory defaults to read. Curated guidance lives at project .mimir/LEARNINGS.md;
legacy project notes are read without modification. Explicit write mode appends
unvalidated candidates to .mimir/learning-candidates.jsonl. Candidates are not
automatically promoted or consumed. off omits memory context.

Diagnostics expose runtime/installed identity, interpreter, native credential
presence, workspace and storage paths without inference or secrets. On Windows,
a required Codex provider key absent from the process can be supplied from User
then Machine scope to the owned child only; explicitly empty process values
suppress that inheritance.

Context admission rejects oversized worker input without silently truncating
evidence. Per-call input characters, durations and available tokens are retained.
Unknown usage and billed cost remain explicit. [Evaluation workflow](docs/EVALUATION.md)
provides a matched single/review comparison; no universal quality or speed gain
is claimed.

## Dated support

| Worker | Current implementation | Qualification |
| --- | --- | --- |
| Codex | Python SDK 0.163.0, fresh ephemeral read-only threads | Direct Azure full MCP single/review runs verified; focused research qualification, not universal quality proof |
| Claude | Agent SDK 0.2.172, fresh nonpersistent query | Last live provider probe HTTP 401; authenticated research unverified |
| OpenCode | Owned localhost HTTP runtime, 1.19.3 routes | Health/session/cleanup passed without inference; native configuration discovery timed out |
| AGY | Cached-login CLI with disposable storage | Historical one-call probe passed; full managed research unqualified |
| Direct HTTP | Explicit selected endpoint adapters | No worker MCP tools; legacy cancellation limits remain |

Native Claude/OpenCode restrict research tools to approved read/query catalogs.
Codex filesystem read-only policy does not restrict remote MCP writes.
Provider/tool permissions must match the objective. Legacy dated CLI observations
are in [HARNESS_EXECUTION.md](prompts/HARNESS_EXECUTION.md); they do not qualify
native transports.

Run .venv/Scripts/python.exe -m pytest -q for regression coverage. Mechanical
tests and live source retrieval do not establish research completeness.
