# Mímir — evidence-led research and review

> **WORK IN PROGRESS — VERY BETA.** Mímir is experimental software under active
> development. Use it for supervised, bounded investigations and inspect the
> underlying evidence. APIs, checkpoints, instructions and dependencies may
> change. Production readiness, universal harness support, independent factual
> validation and general quality or performance improvements are not established.

Mímir helps your coding assistant investigate difficult questions, compare
designs and challenge consequential assumptions. A shared Python engine runs
bounded workers, retains source/claim/gap records and publishes recoverable
reports. Model findings remain evidence for review, not independently verified facts.

Choose the smallest useful workflow:

| Mode | Model calls without retries/pruning | Use |
| --- | --- | --- |
| single | One research worker | Focused questions and baseline comparisons |
| review (default) | Two specialists, a dependent critic, one synthesis | Architecture reviews and consequential proposals |
| swarm | One bounded planner, up to max-tasks workers, one synthesis | Broader objectives benefiting from custom decomposition |

Task count is independent of concurrency. Default task cap is four; JEV pruning
is optional and off. There is no executive worker before final synthesis.

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

The repository also contains [Mycroft](mycroft/README.md), a **very BETA** experiment
that transfers the research method to native harness subagents and skills without
a Python orchestrator. It approximates DSPy/RLM/GEPA procedures; it does not execute
those libraries. An independent Mímir review found admission, publication, recovery
and isolation gaps. Use it for supervised experiments, with no claim of equivalent
reliability. Its source, installer and acceptance fixtures are included; generate
its transfer ZIP locally with `mycroft/Build-Package.ps1`.

## Install and connect

Use Python 3.10+ and one explicit interpreter:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-workers.txt
.\.venv\Scripts\python.exe scripts/install.py --skip-pip
.\.venv\Scripts\python.exe scripts/mimir.py --diagnostics --backend codex --model gpt-6.1-sol --effort low
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
